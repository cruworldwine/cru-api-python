"""What Cru and AsyncCru share: building requests, deciding retries, refreshing and parsing.

Only the transport differs between them. Each has a short send loop that does the I/O (send, sleep,
refresh) and asks the shared BaseClient._decide() what to do after every attempt, so a retry, a
refresh or an error is decided the same way for both.
"""

from __future__ import annotations

import asyncio
import copy
import email.utils
import inspect
import math
import os
import platform
import random
import re
import threading
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable, Generic, NamedTuple, Optional, TypeVar, Union, overload
from urllib.parse import quote, urlsplit

import httpx

from . import _errors, _markets, models
from ._constants import DEFAULT_TIMEOUT, INITIAL_RETRY_DELAY, MAX_BACKOFF, MAX_RETRY_DELAY, RETRY_STATUSES
from ._logs import logger
from ._market_table import ENVIRONMENTS
from ._markets import MarketInfo
from ._models import _registry, with_request_id
from ._operations import M, Op, Operation, PageOp, R
from ._types import AsyncPage, Page, Response, Write
from ._version import VERSION

_HttpT = TypeVar('_HttpT', httpx.Client, httpx.AsyncClient)
_ClientT = TypeVar('_ClientT', bound='BaseClient[Any]')

AppInfo = tuple[str, Optional[str], Optional[str]]
"""(name, version, url) of the application using the SDK; version and url may be None."""

Timeout = Union[float, httpx.Timeout]
"""Seconds, or an httpx.Timeout for each phase of a request."""

_MakePage = Callable[[list[Any], dict[str, Any], dict[str, Any], Optional[str]], Any]
_HTTPX_DEFAULT_TIMEOUT = httpx.Timeout(5.0)  # what an httpx client has when nobody set one
_MARKET = re.compile(r'[a-z0-9][a-z0-9-]{0,30}')


class _Auth:
    """The OAuth tokens a client and its with_options() copies share, and the lock that guards them.

    A refresh token works once, so a copy that refreshes must hand the new tokens to the others.
    """

    def __init__(self, access_token: Optional[str], refresh_token: Optional[str]) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.thread_lock = threading.Lock()
        self.async_lock: Optional[asyncio.Lock] = None

    def __repr__(self) -> str:
        return '_Auth(<redacted>)'


@dataclass(frozen=True)
class _Call:
    """A generated method's call, as given, so the next page can be asked for the same way."""

    op: Operation
    path: Optional[Mapping[str, Any]] = None
    query: Optional[Mapping[str, Any]] = None
    body: Optional[Mapping[str, Any]] = None
    extra_headers: Optional[Mapping[str, str]] = None
    extra_query: Optional[Mapping[str, Any]] = None
    extra_body: Optional[Mapping[str, Any]] = None
    timeout: Optional[Timeout] = None
    max_retries: Optional[int] = None


@dataclass(frozen=True)
class _RequestOptions:
    """One request, ready to send, and how to send it. It is the same for every attempt."""

    method: str
    path: str
    query: Mapping[str, str]
    body: Optional[Mapping[str, Any]]
    accept: str
    retryable: bool
    headers: Mapping[str, str]
    timeout: httpx.Timeout
    max_retries: int


class _Step(NamedTuple):
    """What the send loop does after an attempt: return the response, refresh, or retry."""

    action: str
    delay: float = 0.0
    response: Optional[httpx.Response] = None


class BaseClient(Generic[_HttpT]):
    """The configuration and logic Cru and AsyncCru share. Not used directly."""

    _http: _HttpT

    def __init__(
        self,
        *,
        client_key: Optional[str],
        client_secret: Optional[str],
        access_token: Optional[str],
        refresh_token: Optional[str],
        oauth_client_id: Optional[str],
        oauth_client_secret: Optional[str],
        on_token_refresh: Optional[Callable[[dict[str, Any]], Any]],
        market: Optional[str],
        environment: Optional[str],
        base_url: Optional[str],
        timeout: Optional[Timeout],
        max_retries: int,
        http_client: Optional[_HttpT],
        app_info: Optional[AppInfo],
    ) -> None:
        # The environment fills in only when neither kind of credential is given.
        if not (client_key or client_secret or access_token):
            client_key = os.environ.get('CRU_CLIENT_KEY')
            client_secret = os.environ.get('CRU_CLIENT_SECRET')
            access_token = os.environ.get('CRU_ACCESS_TOKEN')
        if not (client_key and client_secret) and not access_token:
            raise _errors.CruError('Give client_key and client_secret, or access_token')
        self.client_key = client_key
        self.client_secret = client_secret
        self._auth = _Auth(access_token, refresh_token)
        self.oauth_client_id = oauth_client_id
        self.oauth_client_secret = oauth_client_secret
        self.on_token_refresh = on_token_refresh
        market = market or os.environ.get('CRU_MARKET')
        environment = _markets.environment_name(environment or os.environ.get('CRU_ENVIRONMENT') or 'live')
        self.base_url = _base_url(base_url or os.environ.get('CRU_BASE_URL'), market, environment)
        # Without a base_url, self.base_url is the Cru host built from the market, so its host says it.
        self._market_info = _markets.market_of(self.base_url, market)
        self.max_retries = _max_retries(max_retries)
        if timeout is not None:
            self.timeout = _timeout(timeout)
        elif http_client is not None and http_client.timeout != _HTTPX_DEFAULT_TIMEOUT:
            self.timeout = http_client.timeout
        else:
            self.timeout = httpx.Timeout(DEFAULT_TIMEOUT)
        self._http = http_client if http_client is not None else self._default_http_client()
        self.user_agent = _user_agent(app_info)

    def _default_http_client(self) -> _HttpT:
        raise NotImplementedError

    def _attach(self) -> None:
        """Bind the resources to this client; the generated Resources classes override it."""

    @property
    def access_token(self) -> Optional[str]:
        """The OAuth access token in use; it changes when the SDK refreshes it."""
        return self._auth.access_token

    @access_token.setter
    def access_token(self, value: Optional[str]) -> None:
        self._auth.access_token = value

    @property
    def refresh_token(self) -> Optional[str]:
        """The OAuth refresh token the next refresh will use; it changes with every refresh."""
        return self._auth.refresh_token

    @refresh_token.setter
    def refresh_token(self, value: Optional[str]) -> None:
        self._auth.refresh_token = value

    @property
    def market_info(self) -> Optional[MarketInfo]:
        """The market this client calls, from MARKETS: its code, name, currency and URLs.

        With no base_url, the market the client was made for. With one, the market of a Cru host
        such as hk.crusandbox.com, else the market given, if any. None when there is none, or it is
        not in MARKETS.
        """
        return self._market_info

    @property
    def is_partner(self) -> bool:
        """True for a partner credential, whose writes run at once; False for a connected app."""
        return bool(self.client_key and self.client_secret)

    def with_options(
        self: _ClientT,
        *,
        timeout: Optional[Timeout] = None,
        max_retries: Optional[int] = None,
    ) -> _ClientT:
        """A copy of this client with another timeout or max_retries.

        The copy shares this client's connection pool and credentials, including OAuth tokens it
        refreshes, so it is cheap to make one per call site. Closing either closes the pool.

        Args:
            timeout: Seconds, or an httpx.Timeout. None keeps this client's.
            max_retries: Retries after the first attempt. None keeps this client's.
        """
        clone = copy.copy(self)
        if timeout is not None:
            clone.timeout = _timeout(timeout)
        if max_retries is not None:
            clone.max_retries = _max_retries(max_retries)
        clone._attach()
        return clone

    def __repr__(self) -> str:
        auth = 'partner credential' if self.is_partner else 'connected app'
        return (
            f'{type(self).__name__}(base_url={self.base_url!r}, auth={auth!r}, '
            f'timeout={self.timeout!r}, max_retries={self.max_retries})'
        )

    # Building requests.

    def _prepare(self, call: _Call) -> _RequestOptions:
        op = call.op
        url = op.path
        for name, value in (call.path or {}).items():
            if value is None or value == '':
                raise _errors.CruError(f'{name} is required')
            url = url.replace('{' + name + '}', quote(str(value), safe=''))
        body: Optional[dict[str, Any]] = None
        if op.method != 'GET':
            body = {k: v for k, v in (call.body or {}).items() if v is not None}
            body.update(call.extra_body or {})
        return self._options(
            op.method,
            url,
            {**(call.query or {}), **(call.extra_query or {})},
            body,
            '*/*' if op.kind == 'binary' else 'application/json',
            call.extra_headers,
            call.timeout,
            call.max_retries,
        )

    def _options(
        self,
        method: str,
        path: str,
        query: Mapping[str, Any],
        body: Optional[Mapping[str, Any]],
        accept: str,
        headers: Optional[Mapping[str, str]],
        timeout: Optional[Timeout],
        max_retries: Optional[int],
    ) -> _RequestOptions:
        write = method != 'GET'
        # A partner's write needs a reference, and keeping one across retries is what makes them
        # safe. A connected app's staged write has none, so it is never retried.
        if write and self.is_partner:
            body = dict(body or {})
            if not body.get('reference'):
                body['reference'] = 'sdk_' + uuid.uuid4().hex
        return _RequestOptions(
            method=method,
            path=path,
            query=_query(query),
            body=body,
            accept=accept,
            retryable=not write or self.is_partner,
            headers=dict(headers or {}),
            timeout=self.timeout if timeout is None else _timeout(timeout),
            max_retries=self.max_retries if max_retries is None else _max_retries(max_retries),
        )

    def _headers(self, opts: _RequestOptions) -> dict[str, str]:
        headers = {'Accept': opts.accept, 'User-Agent': self.user_agent}
        key, secret = self.client_key, self.client_secret
        if key and secret:
            headers['CLIENT-KEY'] = key
            headers['CLIENT-SECRET'] = secret
        else:
            headers['Authorization'] = f'Bearer {self._auth.access_token}'
        headers.update(opts.headers)
        return headers

    def _build_request(self, opts: _RequestOptions) -> httpx.Request:
        return self._http.build_request(
            opts.method,
            self.base_url + opts.path,
            params=opts.query,
            json=opts.body,
            headers=self._headers(opts),
            timeout=opts.timeout,
        )

    # Deciding what to do after each attempt.

    def _decide(
        self,
        opts: _RequestOptions,
        response: httpx.Response,
        attempt: int,
        retries: int,
        refreshed: bool,
        started: float,
    ) -> _Step:
        """Return, refresh or retry after an answer; raise the API's error when none of them applies.

        attempt counts every send of this request, retries only those spent from max_retries: the
        send after a token refresh is not a retry. Redirects are never followed, so the credentials
        never reach another host: a 3xx raises.
        """
        status = response.status_code
        logger.debug(
            '%s %s -> %d in %.3fs (attempt %d, request_id %s)',
            opts.method,
            opts.path,
            status,
            time.monotonic() - started,
            attempt,
            response.headers.get('x-request-id'),
        )
        if 200 <= status < 300:
            return _Step('return', response=response)
        envelope = _envelope(response)
        if status == 401 and not refreshed and self._can_refresh():
            return _Step('refresh')
        in_progress = status == 409 and _errors.error_code(envelope) == 'REQUEST_IN_PROGRESS'
        if opts.retryable and retries < opts.max_retries and (status in RETRY_STATUSES or in_progress):
            return self._retry(opts, retries, _retry_delay(retries + 1, response, envelope), f'HTTP {status}')
        raise _errors.error_for(status, envelope, response.headers)

    def _decide_failure(
        self,
        opts: _RequestOptions,
        error: httpx.RequestError,
        attempt: int,
        retries: int,
        started: float,
    ) -> _Step:
        """Retry after a connection failure or a timeout, or raise it as an APIConnectionError."""
        logger.debug(
            '%s %s failed in %.3fs (attempt %d): %s',
            opts.method,
            opts.path,
            time.monotonic() - started,
            attempt,
            type(error).__name__,
        )
        if opts.retryable and retries < opts.max_retries and isinstance(error, httpx.TransportError):
            return self._retry(opts, retries, _retry_delay(retries + 1), type(error).__name__)
        raise _connection_error(error) from error

    def _retry(self, opts: _RequestOptions, retries: int, delay: float, reason: str) -> _Step:
        logger.info(
            'Retrying %s %s in %.2fs (retry %d of %d) after %s',
            opts.method,
            opts.path,
            delay,
            retries + 1,
            opts.max_retries,
            reason,
        )
        return _Step('retry', delay=delay)

    # Refreshing an OAuth access token.

    def _can_refresh(self) -> bool:
        return not self.is_partner and bool(self._auth.refresh_token and self.oauth_client_id)

    def _still_stale(self, failed: httpx.Request) -> bool:
        """Whether the token the failed request used is still the current one.

        Another request may have refreshed it while this one waited for the lock; then this one
        only has to retry.
        """
        used: Optional[str] = failed.headers.get('authorization')
        return used == f'Bearer {self._auth.access_token}'

    def _refresh_request(self) -> httpx.Request:
        logger.info('Refreshing the OAuth access token')
        parts = urlsplit(self.base_url)
        form = {
            'grant_type': 'refresh_token',
            'refresh_token': self._auth.refresh_token or '',
            'client_id': self.oauth_client_id or '',
        }
        if self.oauth_client_secret:
            form['client_secret'] = self.oauth_client_secret
        return self._http.build_request(
            'POST',
            f'{parts.scheme}://{parts.netloc}/api/oauth/token',
            data=form,
            headers={'Accept': 'application/json', 'User-Agent': self.user_agent},
            timeout=self.timeout,
        )

    def _accept_tokens(self, response: httpx.Response, started: float) -> dict[str, Any]:
        logger.debug('POST /api/oauth/token -> %d in %.3fs', response.status_code, time.monotonic() - started)
        tokens = _envelope(response)
        access_token = tokens.get('access_token')
        if response.status_code != 200 or not isinstance(access_token, str) or not access_token:
            description = tokens.get('error_description')
            message = description if isinstance(description, str) else 'The token could not be refreshed'
            raise _errors.AuthenticationError(response.status_code, {'message': message}, response.headers)
        self._auth.access_token = access_token
        refresh_token = tokens.get('refresh_token')
        if isinstance(refresh_token, str) and refresh_token:
            self._auth.refresh_token = refresh_token
        logger.info('Refreshed the OAuth access token')
        return tokens

    # Parsing answers.

    def _process(self, op: Operation, response: httpx.Response, make_page: _MakePage) -> Any:
        if op.kind == 'empty':
            return None
        if op.kind == 'binary':
            return response.content
        envelope = _envelope(response)
        data = _dict(envelope.get('data'))
        meta = _dict(envelope.get('meta'))
        request_id = _request_id(meta, response)
        if op.kind in ('write', 'confirm'):
            return _write(op, response, data, request_id)
        model = _registry[op.model or '']
        if op.kind == 'get':
            if op.items_key and op.items_key not in data:
                raise _errors.CruError(f'The response has no data.{op.items_key}')
            return with_request_id(model.parse(data[op.items_key] if op.items_key else data), request_id)
        raw_items = data.get(op.items_key or '')
        items = [with_request_id(model.parse(i), request_id) for i in raw_items] if isinstance(raw_items, list) else []
        if op.kind == 'list':
            return items
        return make_page(items, data, meta, request_id)

    def _raw_response(self, response: httpx.Response) -> Response:
        return Response(response.status_code, response.headers, _json(response))


class SyncAPIClient(BaseClient[httpx.Client]):
    """The synchronous transport: Cru."""

    def _default_http_client(self) -> httpx.Client:
        return httpx.Client(timeout=self.timeout, follow_redirects=False)

    def close(self) -> None:
        """Close the connection pool. A client used in a with block closes on leaving it."""
        self._http.close()

    @property
    def is_closed(self) -> bool:
        """Whether close() has been called."""
        return self._http.is_closed

    def __enter__(self: _ClientT) -> _ClientT:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        query: Optional[Mapping[str, Any]] = None,
        body: Optional[Mapping[str, Any]] = None,
        headers: Optional[Mapping[str, str]] = None,
        timeout: Optional[Timeout] = None,
        max_retries: Optional[int] = None,
    ) -> Response:
        """Call any endpoint, even one this SDK does not know yet, and get the envelope back.

        Errors raise as they do everywhere else; a partner write gets a reference if it has none.

        Args:
            method: The HTTP method, such as GET or POST.
            path: The path after the base URL, such as /bids, already URL-encoded.
            query: Query parameters; lists are sent comma-separated and None is left out.
            body: The JSON body of a write.
            headers: Headers to add to, or replace, the SDK's own.
            timeout: Seconds, or an httpx.Timeout, for this call only.
            max_retries: Retries after the first attempt, for this call only.
        """
        method = method.upper()
        accept = 'application/json'
        opts = self._options(method, path, query or {}, body, accept, headers, timeout, max_retries)
        return self._raw_response(self._send(opts))

    @overload
    def _call(
        self,
        op: PageOp[M],
        path: Optional[Mapping[str, Any]] = None,
        *,
        query: Optional[Mapping[str, Any]] = None,
        body: Optional[Mapping[str, Any]] = None,
        extra_headers: Optional[Mapping[str, str]] = None,
        extra_query: Optional[Mapping[str, Any]] = None,
        extra_body: Optional[Mapping[str, Any]] = None,
        timeout: Optional[Timeout] = None,
        max_retries: Optional[int] = None,
    ) -> Page[M]: ...

    @overload
    def _call(
        self,
        op: Op[R],
        path: Optional[Mapping[str, Any]] = None,
        *,
        query: Optional[Mapping[str, Any]] = None,
        body: Optional[Mapping[str, Any]] = None,
        extra_headers: Optional[Mapping[str, str]] = None,
        extra_query: Optional[Mapping[str, Any]] = None,
        extra_body: Optional[Mapping[str, Any]] = None,
        timeout: Optional[Timeout] = None,
        max_retries: Optional[int] = None,
    ) -> R: ...

    def _call(
        self,
        op: Operation,
        path: Optional[Mapping[str, Any]] = None,
        *,
        query: Optional[Mapping[str, Any]] = None,
        body: Optional[Mapping[str, Any]] = None,
        extra_headers: Optional[Mapping[str, str]] = None,
        extra_query: Optional[Mapping[str, Any]] = None,
        extra_body: Optional[Mapping[str, Any]] = None,
        timeout: Optional[Timeout] = None,
        max_retries: Optional[int] = None,
    ) -> Any:
        return self._execute(_Call(op, path, query, body, extra_headers, extra_query, extra_body, timeout, max_retries))

    def _execute(self, call: _Call) -> Any:
        response = self._send(self._prepare(call))

        def fetch(offset: int) -> Page[Any]:
            page: Page[Any] = self._execute(replace(call, extra_query={**(call.extra_query or {}), 'offset': offset}))
            return page

        return self._process(
            call.op, response, lambda items, data, meta, request_id: Page(items, data, meta, fetch, request_id)
        )

    def _send(self, opts: _RequestOptions) -> httpx.Response:
        attempt = retries = 0
        refreshed = False
        while True:
            attempt += 1
            request = self._build_request(opts)
            started = time.monotonic()
            try:
                response = self._http.send(request, follow_redirects=False)
            except httpx.RequestError as exc:
                step = self._decide_failure(opts, exc, attempt, retries, started)
            else:
                step = self._decide(opts, response, attempt, retries, refreshed, started)
            if step.response is not None:
                return step.response
            if step.action == 'refresh':
                self._refresh(request)
                refreshed = True
                continue
            retries += 1
            self._sleep(step.delay)

    def _refresh(self, failed: httpx.Request) -> None:
        # One refresh at a time: a refresh token works once.
        with self._auth.thread_lock:
            if not self._still_stale(failed):
                return
            request = self._refresh_request()
            started = time.monotonic()
            try:
                response = self._http.send(request, follow_redirects=False)
            except httpx.RequestError as exc:
                raise _connection_error(exc) from exc
            tokens = self._accept_tokens(response, started)
            if self.on_token_refresh is not None:
                self.on_token_refresh(tokens)

    def _sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class AsyncAPIClient(BaseClient[httpx.AsyncClient]):
    """The asynchronous transport: AsyncCru."""

    def _default_http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.timeout, follow_redirects=False)

    async def aclose(self) -> None:
        """Close the connection pool. A client used in an async with block closes on leaving it."""
        await self._http.aclose()

    @property
    def is_closed(self) -> bool:
        """Whether aclose() has been called."""
        return self._http.is_closed

    async def __aenter__(self: _ClientT) -> _ClientT:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        query: Optional[Mapping[str, Any]] = None,
        body: Optional[Mapping[str, Any]] = None,
        headers: Optional[Mapping[str, str]] = None,
        timeout: Optional[Timeout] = None,
        max_retries: Optional[int] = None,
    ) -> Response:
        """Call any endpoint, even one this SDK does not know yet, and get the envelope back.

        Errors raise as they do everywhere else; a partner write gets a reference if it has none.

        Args:
            method: The HTTP method, such as GET or POST.
            path: The path after the base URL, such as /bids, already URL-encoded.
            query: Query parameters; lists are sent comma-separated and None is left out.
            body: The JSON body of a write.
            headers: Headers to add to, or replace, the SDK's own.
            timeout: Seconds, or an httpx.Timeout, for this call only.
            max_retries: Retries after the first attempt, for this call only.
        """
        method = method.upper()
        accept = 'application/json'
        opts = self._options(method, path, query or {}, body, accept, headers, timeout, max_retries)
        return self._raw_response(await self._send(opts))

    @overload
    async def _call(
        self,
        op: PageOp[M],
        path: Optional[Mapping[str, Any]] = None,
        *,
        query: Optional[Mapping[str, Any]] = None,
        body: Optional[Mapping[str, Any]] = None,
        extra_headers: Optional[Mapping[str, str]] = None,
        extra_query: Optional[Mapping[str, Any]] = None,
        extra_body: Optional[Mapping[str, Any]] = None,
        timeout: Optional[Timeout] = None,
        max_retries: Optional[int] = None,
    ) -> AsyncPage[M]: ...

    @overload
    async def _call(
        self,
        op: Op[R],
        path: Optional[Mapping[str, Any]] = None,
        *,
        query: Optional[Mapping[str, Any]] = None,
        body: Optional[Mapping[str, Any]] = None,
        extra_headers: Optional[Mapping[str, str]] = None,
        extra_query: Optional[Mapping[str, Any]] = None,
        extra_body: Optional[Mapping[str, Any]] = None,
        timeout: Optional[Timeout] = None,
        max_retries: Optional[int] = None,
    ) -> R: ...

    async def _call(
        self,
        op: Operation,
        path: Optional[Mapping[str, Any]] = None,
        *,
        query: Optional[Mapping[str, Any]] = None,
        body: Optional[Mapping[str, Any]] = None,
        extra_headers: Optional[Mapping[str, str]] = None,
        extra_query: Optional[Mapping[str, Any]] = None,
        extra_body: Optional[Mapping[str, Any]] = None,
        timeout: Optional[Timeout] = None,
        max_retries: Optional[int] = None,
    ) -> Any:
        return await self._execute(
            _Call(op, path, query, body, extra_headers, extra_query, extra_body, timeout, max_retries)
        )

    async def _execute(self, call: _Call) -> Any:
        response = await self._send(self._prepare(call))

        async def fetch(offset: int) -> AsyncPage[Any]:
            page: AsyncPage[Any] = await self._execute(
                replace(call, extra_query={**(call.extra_query or {}), 'offset': offset})
            )
            return page

        return self._process(
            call.op, response, lambda items, data, meta, request_id: AsyncPage(items, data, meta, fetch, request_id)
        )

    async def _send(self, opts: _RequestOptions) -> httpx.Response:
        attempt = retries = 0
        refreshed = False
        while True:
            attempt += 1
            request = self._build_request(opts)
            started = time.monotonic()
            try:
                response = await self._http.send(request, follow_redirects=False)
            except httpx.RequestError as exc:
                step = self._decide_failure(opts, exc, attempt, retries, started)
            else:
                step = self._decide(opts, response, attempt, retries, refreshed, started)
            if step.response is not None:
                return step.response
            if step.action == 'refresh':
                await self._refresh(request)
                refreshed = True
                continue
            retries += 1
            await self._sleep(step.delay)

    async def _refresh(self, failed: httpx.Request) -> None:
        # One refresh at a time: a refresh token works once. The lock is made on first use, inside
        # the running event loop.
        if self._auth.async_lock is None:
            self._auth.async_lock = asyncio.Lock()
        async with self._auth.async_lock:
            if not self._still_stale(failed):
                return
            request = self._refresh_request()
            started = time.monotonic()
            try:
                response = await self._http.send(request, follow_redirects=False)
            except httpx.RequestError as exc:
                raise _connection_error(exc) from exc
            tokens = self._accept_tokens(response, started)
            if self.on_token_refresh is not None:
                result = self.on_token_refresh(tokens)
                if inspect.isawaitable(result):
                    await result

    async def _sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


def _write(op: Operation, response: httpx.Response, data: dict[str, Any], request_id: Optional[str]) -> Write[Any]:
    if response.status_code == 202:
        confirmation = with_request_id(models.StagedConfirmation.parse(_dict(data.get('confirmation'))), request_id)
        return Write(None, confirmation, False, request_id)
    name = op.model or ''
    action = data.get('action')
    if op.kind == 'confirm' and isinstance(action, str):
        name = op.results.get(action, name)
    result = with_request_id(_registry[name].parse(data), request_id)
    return Write(result, None, response.headers.get('idempotent-replayed') == 'true', request_id)


def _base_url(base_url: Optional[str], market: Optional[str], environment: str) -> str:
    if not base_url:
        market = (market or 'uk').strip().lower()
        if not _MARKET.fullmatch(market):
            raise _errors.CruError(f'market must be a market code such as uk, us or hk, not {market!r}')
        # A code the table does not know still makes a host, so a new market needs no release.
        base_url = ENVIRONMENTS[environment].replace('{market}', market)
    if urlsplit(base_url).scheme not in ('http', 'https'):
        raise _errors.CruError('base_url must be an http or https URL')
    return base_url.rstrip('/')


# The validators take object: callers without a type checker can pass anything.


def _timeout(value: object) -> httpx.Timeout:
    if isinstance(value, httpx.Timeout):
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise _errors.CruError(f'timeout must be a number of seconds or an httpx.Timeout, not {value!r}')
    return httpx.Timeout(value)


def _max_retries(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _errors.CruError(f'max_retries must be a whole number of 0 or more, not {value!r}')
    return value


def _user_agent(app_info: object) -> str:
    system = platform.system() or 'unknown'
    machine = platform.machine() or 'unknown'
    agent = f'cruworldwine-python/{VERSION} Python/{platform.python_version()} ({system}; {machine})'
    if not app_info:
        return agent
    parts = list(app_info) if isinstance(app_info, (tuple, list)) else []
    name, version, url = (*parts, None, None, None)[:3]
    if not isinstance(name, str) or not name.strip():
        raise _errors.CruError('app_info must be (name, version, url), with a name')
    product = _token(name) + (f'/{_token(version)}' if version else '')
    return f'{agent} {product}' + (f' ({_clean(url)})' if url else '')


def _token(value: object) -> str:
    return re.sub(r'\s+', '-', _clean(value))


def _clean(value: object) -> str:
    text = str(value)
    if any(ord(c) < 32 or ord(c) == 127 for c in text):
        raise _errors.CruError('app_info must not hold control characters')
    return text.strip()


def _query(query: Mapping[str, Any]) -> dict[str, str]:
    out = {}
    for key, value in query.items():
        if value is None:
            continue
        if isinstance(value, bool):
            value = 'true' if value else 'false'
        elif isinstance(value, (list, tuple, set, frozenset)):
            if not value:
                continue
            value = ','.join(str(v) for v in value)
        out[key] = str(value)
    return out


def _json(response: httpx.Response) -> Any:
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {}


def _envelope(response: httpx.Response) -> dict[str, Any]:
    return _dict(_json(response))


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _request_id(meta: Mapping[str, Any], response: httpx.Response) -> Optional[str]:
    request_id = meta.get('request_id')
    return request_id if isinstance(request_id, str) and request_id else response.headers.get('x-request-id')


def _connection_error(error: httpx.RequestError) -> _errors.APIConnectionError:
    message = str(error) or type(error).__name__
    if isinstance(error, httpx.TimeoutException):
        return _errors.APITimeoutError(message)
    return _errors.APIConnectionError(message)


def _retry_delay(attempt: int, response: Optional[httpx.Response] = None, envelope: Any = None) -> float:
    """Seconds to wait before the next attempt, at most MAX_RETRY_DELAY.

    The API's details.retry_after wins, then a Retry-After header (seconds or an HTTP date), then
    exponential back-off with jitter.
    """
    wait = _retry_after_detail(envelope)
    if wait is None and response is not None:
        wait = _retry_after_header(response.headers.get('retry-after'))
    if wait is None:
        wait = min(MAX_BACKOFF, INITIAL_RETRY_DELAY * 2 ** (attempt - 1)) * (0.75 + random.random() / 2)  # noqa: S311
    return min(max(wait, 0.0), MAX_RETRY_DELAY)


def _retry_after_detail(envelope: Any) -> Optional[float]:
    entries = envelope.get('errors') if isinstance(envelope, dict) else None
    first = entries[0] if isinstance(entries, list) and entries else None
    details = first.get('details') if isinstance(first, dict) else None
    value = details.get('retry_after') if isinstance(details, dict) else None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _retry_after_header(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    value = value.strip()
    try:
        seconds = float(value)
    except ValueError:
        pass
    else:
        return seconds if math.isfinite(seconds) else None
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (when - datetime.now(timezone.utc)).total_seconds()
