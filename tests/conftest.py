"""Shared helpers: envelopes, a recording mock transport, and clients of both kinds on it."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
from typing import Any, Callable, Optional

import httpx
import pytest
from hypothesis import settings

import cruworldwine

# Hypothesis: a quick run by default, a thorough one in CI (HYPOTHESIS_PROFILE=ci).
settings.register_profile('dev', max_examples=25, deadline=None)
settings.register_profile('ci', max_examples=150, deadline=None, print_blob=True)
settings.load_profile(os.environ.get('HYPOTHESIS_PROFILE', 'dev'))

ENV = ('CRU_CLIENT_KEY', 'CRU_CLIENT_SECRET', 'CRU_ACCESS_TOKEN', 'CRU_MARKET', 'CRU_BASE_URL', 'CRU_LOG')


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


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def mock(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    """A Recorder, with both clients' waits between retries recorded instead of slept."""

    def sync_sleep(self: object, seconds: float) -> None:
        sleeps.append(seconds)

    async def async_sleep(self: object, seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(cruworldwine.Cru, '_sleep', sync_sleep)
    monkeypatch.setattr(cruworldwine.AsyncCru, '_sleep', async_sleep)
    sleeps.clear()
    return Recorder()


@pytest.fixture(params=['sync', 'async'])
def kind(request: pytest.FixtureRequest) -> str:
    """Run the test with Cru and again with AsyncCru."""
    return str(request.param)


@pytest.fixture
def run() -> Any:
    """Resolve what a client method returned: a coroutine runs on this test's event loop."""
    loop = asyncio.new_event_loop()

    def resolve(value: Any) -> Any:
        return loop.run_until_complete(value) if inspect.isawaitable(value) else value

    yield resolve
    loop.close()


def make(kind: str, handler: Callable[[httpx.Request], Any], **kwargs: Any) -> Any:
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
