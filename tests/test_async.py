"""What only AsyncCru does: async paging, and refreshing once for many concurrent requests.

Concurrent refreshes are checked for Cru too, with threads.
"""

import asyncio
import inspect
import threading

import httpx
import pytest

import cruworldwine
from conftest import envelope, error, partner

BIDS = ('CB-0', 'CB-1', 'CB-2')


def paged(mock):
    for offset, code in enumerate(BIDS):
        pagination = {'limit': 1, 'offset': offset, 'total': 3, 'has_more': offset < 2}
        mock.add(200, envelope({'bids': [{'code': code}]}, pagination=pagination, request_id=f'req_{offset}'))


def test_async_for_walks_every_page(mock, run):
    paged(mock)

    async def walk():
        page = await partner(mock, 'async').bids.list(limit=1)
        return page, [bid.code async for bid in page]

    page, codes = run(walk())
    assert isinstance(page, cruworldwine.AsyncPage)
    assert codes == list(BIDS)
    assert [bid.code for bid in page] == ['CB-0']
    assert len(page) == 1


def test_next_page_and_auto_paging_iter(mock, run):
    paged(mock)

    async def walk():
        first = await partner(mock, 'async').bids.list(limit=1)
        second = await first.next_page()
        rest = [bid.code async for bid in second.auto_paging_iter()]
        return first, second, rest

    first, second, rest = run(walk())
    assert (first.request_id, second.request_id, second.offset) == ('req_0', 'req_1', 1)
    assert rest == ['CB-1', 'CB-2']
    assert [r.url.params.get('offset') for r in mock.requests] == [None, '1', '2']


def oauth_server(old, new):
    """Answers 401 to the old token, rotates it once at /api/oauth/token, and 200 to the new one."""
    state = {'token_requests': 0, 'unauthorised': 0}

    def answer(request):
        if request.url.path == '/api/oauth/token':
            state['token_requests'] += 1
            return httpx.Response(200, json={'access_token': new, 'refresh_token': 'cru_rt_' + new})
        if request.headers['authorization'] == f'Bearer {old}':
            state['unauthorised'] += 1
            return httpx.Response(401, json=error('AUTH_INVALID_CREDENTIALS'))
        return httpx.Response(200, json=envelope({'pong': True, 'client': {}}))

    return state, answer


def test_concurrent_tasks_refresh_once(run):
    state, answer = oauth_server('cru_at_one', 'cru_at_two')
    stored = []

    async def on_token_refresh(tokens):
        await asyncio.sleep(0)
        stored.append(tokens['refresh_token'])

    async def main():
        arrived = []
        all_arrived = asyncio.Event()  # made in the running loop, as Python 3.9 needs

        async def handler(request):
            if request.headers.get('authorization') == 'Bearer cru_at_one':
                arrived.append(request)
                if len(arrived) == 5:
                    all_arrived.set()
                await all_arrived.wait()  # every task holds the stale token before any is refused
            elif request.url.path == '/api/oauth/token':
                await asyncio.sleep(0)  # let the others reach the lock while this refresh runs
            return answer(request)

        cru = cruworldwine.AsyncCru(
            access_token='cru_at_one',
            refresh_token='cru_rt_one',
            oauth_client_id='client-1',
            on_token_refresh=on_token_refresh,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        async with cru:
            pings = await asyncio.gather(*(cru.ping() for _ in range(5)))
        return cru, pings

    cru, pings = run(main())
    assert all(p.pong for p in pings)
    assert state == {'token_requests': 1, 'unauthorised': 5}
    assert stored == ['cru_rt_cru_at_two']
    assert cru.access_token == 'cru_at_two'


def test_concurrent_threads_refresh_once():
    state, answer = oauth_server('cru_at_one', 'cru_at_two')
    barrier = threading.Barrier(4, timeout=10)
    stored = []

    def handler(request):
        if request.headers.get('authorization') == 'Bearer cru_at_one':
            barrier.wait()  # every thread holds the stale token before any is refused
        return answer(request)

    cru = cruworldwine.Cru(
        access_token='cru_at_one',
        refresh_token='cru_rt_one',
        oauth_client_id='client-1',
        on_token_refresh=lambda tokens: stored.append(tokens['access_token']),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    results, failures = [], []

    def ping():
        try:
            results.append(cru.ping().pong)
        except Exception as e:
            failures.append(e)

    threads = [threading.Thread(target=ping) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert failures == []
    assert results == [True] * 4
    assert state == {'token_requests': 1, 'unauthorised': 4}
    assert stored == ['cru_at_two']


def test_async_client_accepts_a_sync_callback(mock, run):
    seen = []
    mock.add(401, error('AUTH_INVALID_CREDENTIALS'))
    mock.add(200, {'access_token': 'cru_at_two'})
    mock.add(200, envelope({'pong': True, 'client': {}}))
    cru = cruworldwine.AsyncCru(
        access_token='cru_at_one',
        refresh_token='cru_rt_one',
        oauth_client_id='client-1',
        on_token_refresh=seen.append,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(mock)),
    )
    run(cru.ping())
    assert seen[0]['access_token'] == 'cru_at_two'


def test_async_sleeps_between_retries(monkeypatch, run):
    waits = []

    async def fake_sleep(seconds):
        waits.append(seconds)

    monkeypatch.setattr(asyncio, 'sleep', fake_sleep)
    responses = [httpx.Response(503, json=error('SERVICE_UNAVAILABLE'), headers={'Retry-After': '2'})]
    responses.append(httpx.Response(200, json=envelope({'pong': True, 'client': {}})))
    cru = cruworldwine.AsyncCru(
        client_key='k',
        client_secret='s',
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: responses.pop(0))),
    )
    run(cru.ping())
    assert waits == [2.0]


def test_sync_sleeps_between_retries(monkeypatch):
    waits = []
    monkeypatch.setattr(cruworldwine._base_client.time, 'sleep', waits.append)
    responses = [httpx.Response(503, json=error('SERVICE_UNAVAILABLE'), headers={'Retry-After': '2'})]
    responses.append(httpx.Response(200, json=envelope({'pong': True, 'client': {}})))
    cru = cruworldwine.Cru(
        client_key='k',
        client_secret='s',
        http_client=httpx.Client(transport=httpx.MockTransport(lambda request: responses.pop(0))),
    )
    cru.ping()
    assert waits == [2.0]


@pytest.mark.parametrize('name', ['ping', 'request'])
def test_async_methods_are_coroutines(name):
    assert inspect.iscoroutinefunction(getattr(cruworldwine.AsyncCru, name))
    assert not inspect.iscoroutinefunction(getattr(cruworldwine.Cru, name))
