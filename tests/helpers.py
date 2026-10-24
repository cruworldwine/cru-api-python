"""Helpers the unit and integration tests share: envelopes, a recording mock transport, and clients."""

from __future__ import annotations

import json
from typing import Any, Callable, Optional

import httpx

import cruworldwine


def envelope(
    data: Any,
    status: str = 'OK',
    pagination: Optional[dict[str, Any]] = None,
    errors: Optional[list[dict[str, Any]]] = None,
    request_id: str = 'req_test_0001',
) -> dict[str, Any]:
    meta: dict[str, Any] = {'version': '1.0', 'timestamp': '2026-01-01T00:00:00Z', 'request_id': request_id}
    if pagination is not None:
        meta['pagination'] = pagination
    body: dict[str, Any] = {'status': status, 'message': 'x', 'meta': meta, 'data': data}
    if errors is not None:
        body['errors'] = errors
    return body


def error(code: str, field: Optional[str] = None, details: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    entry: dict[str, Any] = {'code': code, 'message': code.lower()}
    if field:
        entry['field'] = field
    if details:
        entry['details'] = details
    return envelope(None, 'ERROR', errors=[entry])


class Recorder:
    """A mock transport: answers queued responses in order and keeps every request."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.responses: list[Callable[[httpx.Request], httpx.Response]] = []

    def add(
        self,
        status: int,
        body: Any = None,
        headers: Optional[dict[str, str]] = None,
        content: Optional[bytes] = None,
    ) -> Recorder:
        def respond(request: httpx.Request) -> httpx.Response:
            if content is not None:
                return httpx.Response(status, content=content, headers=headers)
            if body is None:
                return httpx.Response(status, headers=headers)
            return httpx.Response(status, json=body, headers=headers)

        self.responses.append(respond)
        return self

    def fail(self, exc: Exception) -> Recorder:
        def respond(request: httpx.Request) -> httpx.Response:
            raise exc

        self.responses.append(respond)
        return self

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.responses.pop(0)(request)

    def body(self, i: int = -1) -> Any:
        content = self.requests[i].content
        return json.loads(content) if content else None


sleeps: list[float] = []
"""The waits between retries the unit tests' mock fixture recorded instead of sleeping."""


def make(kind: str, handler: Callable[[httpx.Request], Any], **kwargs: Any) -> Any:
    """A Cru (kind 'sync') or an AsyncCru (kind 'async') whose requests all go to handler."""
    transport = httpx.MockTransport(handler)
    if kind == 'async':
        return cruworldwine.AsyncCru(http_client=httpx.AsyncClient(transport=transport), **kwargs)
    return cruworldwine.Cru(http_client=httpx.Client(transport=transport), **kwargs)


def partner(mock: Callable[[httpx.Request], Any], kind: str = 'sync', **kwargs: Any) -> Any:
    return make(kind, mock, client_key='cru_test_key', client_secret='secret', **kwargs)


def app(mock: Callable[[httpx.Request], Any], kind: str = 'sync', **kwargs: Any) -> Any:
    return make(kind, mock, access_token='cru_at_one', **kwargs)


def collect(run: Callable[[Any], Any], page: Any) -> list[Any]:
    """Every item of every page, from a Page or an AsyncPage."""
    if isinstance(page, cruworldwine.AsyncPage):

        async def every() -> list[Any]:
            return [item async for item in page]

        return list(run(every()))
    return list(page.auto_paging_iter())
