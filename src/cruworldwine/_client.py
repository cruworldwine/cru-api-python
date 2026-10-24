from __future__ import annotations

import os
import random
import time
import uuid
from typing import Any, Callable, Dict, Mapping, Optional
from urllib.parse import quote, urlsplit

import httpx

from . import _errors, models
from ._models import Model, _registry
from .resources import Resources
from ._types import Page, Response, Write
from ._version import VERSION

RETRY_STATUSES = {429, 500, 502, 503, 504}


class Cru(Resources):
    """A client for the Cru Trading API.

    Authenticate with a partner credential (client_key and client_secret), whose writes run at once,
    or as a connected app with an OAuth access token, whose writes are staged for the customer to
    confirm. Give refresh_token and oauth_client_id as well and an expired access token is
    refreshed once, automatically; on_token_refresh is then called with the new tokens, which must
    be stored, since a refresh token works once.

    The environment supplies what is not given: CRU_CLIENT_KEY, CRU_CLIENT_SECRET, CRU_ACCESS_TOKEN,
    CRU_MARKET and CRU_BASE_URL.
    """

    def __init__(
        self,
        *,
        client_key: Optional[str] = None,
        client_secret: Optional[str] = None,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        oauth_client_id: Optional[str] = None,
        oauth_client_secret: Optional[str] = None,
        on_token_refresh: Optional[Callable[[Dict[str, Any]], None]] = None,
        market: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        # The environment fills in only when neither kind of credential is given.
        if not (client_key or client_secret or access_token):
            client_key = os.environ.get('CRU_CLIENT_KEY')
            client_secret = os.environ.get('CRU_CLIENT_SECRET')
            access_token = os.environ.get('CRU_ACCESS_TOKEN')
        self.client_key = client_key
        self.client_secret = client_secret
        self.access_token = access_token
        if not (self.client_key and self.client_secret) and not self.access_token:
            raise _errors.CruError('Give client_key and client_secret, or access_token')
        self.refresh_token = refresh_token
        self.oauth_client_id = oauth_client_id
        self.oauth_client_secret = oauth_client_secret
        self.on_token_refresh = on_token_refresh
        market = market or os.environ.get('CRU_MARKET') or 'uk'
        self.base_url = (base_url or os.environ.get('CRU_BASE_URL') or f'https://{market}.cruworldwine.com/api/v1').rstrip('/')
        self.max_retries = max_retries
        self._http = http_client or httpx.Client(timeout=timeout)
        self._attach()

    @property
    def is_partner(self) -> bool:
        """True for a partner credential, whose writes run at once; False for a connected app."""
        return bool(self.client_key and self.client_secret)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> 'Cru':
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def request(self, method: str, path: str, *, query: Optional[Mapping[str, Any]] = None, body: Optional[Mapping[str, Any]] = None) -> Response:
        """Call any endpoint, even one this SDK does not know yet, and get the envelope back.

        Errors raise as they do everywhere else; a partner write gets a reference if it has none.
        """
        write = method.upper() != 'GET'
        resp = self._send(method.upper(), path, _query(query or {}), self._body(dict(body) if body is not None else None, write), write, 'application/json')
        return Response(resp.status_code, dict(resp.headers), _json(resp))

    # The generated resources call this with the operation's descriptor.
    def _call(self, op: Dict[str, Any], path: Dict[str, Any], query: Dict[str, Any], body: Optional[Dict[str, Any]]) -> Any:
        url = op['path']
        for name, value in path.items():
            if value is None or value == '':
                raise _errors.CruError(f'{name} is required')
            url = url.replace('{' + name + '}', quote(str(value), safe=''))
        write = op['method'] != 'GET'
        clean = None if body is None else {k: v for k, v in body.items() if v is not None}
        kind = op['kind']
        accept = '*/*' if kind == 'binary' else 'application/json'
        resp = self._send(op['method'], url, _query(query), self._body(clean, write), write, accept)
        if kind == 'empty':
            return None
        if kind == 'binary':
            return resp.content
        envelope = _json(resp)
        data = envelope.get('data') or {}
        if kind in ('write', 'confirm'):
            return self._write(op, resp, data)
        model = _registry[op['model']]
        if kind == 'get':
            if op['items_key'] and op['items_key'] not in data:
                raise _errors.CruError(f'The response has no data.{op["items_key"]}')
            return model.parse(data[op['items_key']] if op['items_key'] else data)
        items = [model.parse(item) for item in data.get(op['items_key']) or []]
        if kind == 'list':
            return items

        def fetch(offset: int) -> Page:
            return self._call(op, path, {**query, 'offset': offset}, body)

        return Page(items, data, envelope.get('meta') or {}, fetch)

    def _write(self, op: Dict[str, Any], resp: httpx.Response, data: Dict[str, Any]) -> Write:
        request_id = resp.headers.get('x-request-id')
        if resp.status_code == 202:
            return Write(None, models.StagedConfirmation.parse(data.get('confirmation') or {}), False, request_id)
        model = op['model']
        if op['kind'] == 'confirm':
            model = op['results'].get(data.get('action'), model)
        replayed = resp.headers.get('idempotent-replayed') == 'true'
        return Write(_registry[model].parse(data), None, replayed, request_id)

    def _body(self, body: Optional[Dict[str, Any]], write: bool) -> Optional[Dict[str, Any]]:
        # A partner's write needs a reference, and keeping one across retries is what makes them safe.
        if write and self.is_partner:
            body = dict(body or {})
            body.setdefault('reference', 'sdk_' + uuid.uuid4().hex)
        return body

    def _headers(self, accept: str) -> Dict[str, str]:
        headers = {'Accept': accept, 'User-Agent': f'cruworldwine-python/{VERSION}'}
        if self.is_partner:
            headers['CLIENT-KEY'] = self.client_key  # type: ignore[assignment]
            headers['CLIENT-SECRET'] = self.client_secret  # type: ignore[assignment]
        else:
            headers['Authorization'] = f'Bearer {self.access_token}'
        return headers

    def _send(self, method: str, path: str, query: Dict[str, str], body: Optional[Dict[str, Any]], write: bool, accept: str) -> httpx.Response:
        # Reads retry freely. A partner's write retries with the same reference, which cannot act
        # twice; a connected app's staged write has none, so it is never retried.
        retryable = not write or self.is_partner
        refreshed = False
        attempt = 0
        while True:
            try:
                resp = self._http.request(method, self.base_url + path, params=query, json=body, headers=self._headers(accept), follow_redirects=False)
            except httpx.TimeoutException as e:
                if retryable and attempt < self.max_retries:
                    attempt += 1
                    time.sleep(_backoff(attempt, None))
                    continue
                raise _errors.APITimeoutError(str(e)) from e
            except httpx.TransportError as e:
                if retryable and attempt < self.max_retries:
                    attempt += 1
                    time.sleep(_backoff(attempt, None))
                    continue
                raise _errors.APIConnectionError(str(e)) from e
            # Redirects are never followed, so the credentials never reach another host.
            if 200 <= resp.status_code < 300:
                return resp
            envelope = _json(resp)
            code = ((envelope.get('errors') or [{}])[0]).get('code') if isinstance(envelope, dict) else None
            if resp.status_code == 401 and not refreshed and self._can_refresh():
                self._refresh()
                refreshed = True
                continue
            in_progress = resp.status_code == 409 and code == 'REQUEST_IN_PROGRESS'
            if retryable and attempt < self.max_retries and (resp.status_code in RETRY_STATUSES or in_progress):
                attempt += 1
                time.sleep(_backoff(attempt, resp, envelope))
                continue
            raise _errors.error_for(resp.status_code, envelope if isinstance(envelope, dict) else None, dict(resp.headers))

    def _can_refresh(self) -> bool:
        return not self.is_partner and bool(self.refresh_token and self.oauth_client_id)

    def _refresh(self) -> None:
        parts = urlsplit(self.base_url)
        form = {'grant_type': 'refresh_token', 'refresh_token': self.refresh_token, 'client_id': self.oauth_client_id}
        if self.oauth_client_secret:
            form['client_secret'] = self.oauth_client_secret
        try:
            resp = self._http.post(f'{parts.scheme}://{parts.netloc}/api/oauth/token', data=form, headers={'Accept': 'application/json'}, follow_redirects=False)
        except httpx.TimeoutException as e:
            raise _errors.APITimeoutError(str(e)) from e
        except httpx.TransportError as e:
            raise _errors.APIConnectionError(str(e)) from e
        tokens = _json(resp)
        if resp.status_code != 200 or not isinstance(tokens, dict) or 'access_token' not in tokens:
            raise _errors.AuthenticationError(resp.status_code, {'message': (tokens or {}).get('error_description', 'The token could not be refreshed')}, dict(resp.headers))
        self.access_token = tokens['access_token']
        self.refresh_token = tokens.get('refresh_token', self.refresh_token)
        if self.on_token_refresh:
            self.on_token_refresh(tokens)


def _query(query: Mapping[str, Any]) -> Dict[str, str]:
    out = {}
    for key, value in query.items():
        if value is None:
            continue
        if isinstance(value, bool):
            value = 'true' if value else 'false'
        elif isinstance(value, (list, tuple, set)):
            if not value:
                continue
            value = ','.join(str(v) for v in value)
        out[key] = str(value)
    return out


def _json(resp: httpx.Response) -> Any:
    if not resp.content:
        return {}
    try:
        return resp.json()
    except ValueError:
        return {}


def _backoff(attempt: int, resp: Optional[httpx.Response], envelope: Any = None) -> float:
    wait = None
    if resp is not None:
        header = resp.headers.get('retry-after')
        if header and header.isdigit():
            wait = float(header)
        details = ((envelope or {}).get('errors') or [{}])[0].get('details') if isinstance(envelope, dict) else None
        if details and isinstance(details.get('retry_after'), (int, float)):
            wait = float(details['retry_after'])
    if wait is None:
        wait = min(8.0, 0.5 * 2 ** (attempt - 1)) * (0.75 + random.random() / 2)
    return min(wait, 30.0)
