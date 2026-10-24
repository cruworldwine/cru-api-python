import json
from typing import Any, Callable, Dict, List, Optional

import httpx
import pytest

import cruworldwine
from cruworldwine import _client


def envelope(data: Any, status: str = 'OK', pagination: Optional[Dict[str, Any]] = None, errors: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    meta: Dict[str, Any] = {'version': '1.0', 'timestamp': '2026-01-01T00:00:00Z', 'request_id': 'req_test_0001'}
    if pagination is not None:
        meta['pagination'] = pagination
    body: Dict[str, Any] = {'status': status, 'message': 'x', 'meta': meta, 'data': data}
    if errors is not None:
        body['errors'] = errors
    return body


def error(code: str, field: Optional[str] = None, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    entry: Dict[str, Any] = {'code': code, 'message': code.lower()}
    if field:
        entry['field'] = field
    if details:
        entry['details'] = details
    return envelope(None, 'ERROR', errors=[entry])


class Recorder:
    """A mock transport: answers queued responses in order and keeps every request."""

    def __init__(self) -> None:
        self.requests: List[httpx.Request] = []
        self.responses: List[Callable[[httpx.Request], httpx.Response]] = []

    def add(self, status: int, body: Any = None, headers: Optional[Dict[str, str]] = None, content: Optional[bytes] = None) -> 'Recorder':
        def respond(request: httpx.Request) -> httpx.Response:
            if content is not None:
                return httpx.Response(status, content=content, headers=headers)
            if body is None:
                return httpx.Response(status, headers=headers)
            return httpx.Response(status, json=body, headers=headers)
        self.responses.append(respond)
        return self

    def fail(self, exc: Exception) -> 'Recorder':
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


@pytest.fixture
def mock(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    monkeypatch.setattr(_client.time, 'sleep', lambda s: sleeps.append(s))
    sleeps.clear()
    return Recorder()


sleeps: List[float] = []


def partner(mock: Recorder, **kwargs: Any) -> cruworldwine.Cru:
    return cruworldwine.Cru(client_key='cru_test_key', client_secret='secret', http_client=httpx.Client(transport=httpx.MockTransport(mock)), **kwargs)


def app(mock: Recorder, **kwargs: Any) -> cruworldwine.Cru:
    return cruworldwine.Cru(access_token='cru_at_one', http_client=httpx.Client(transport=httpx.MockTransport(mock)), **kwargs)
