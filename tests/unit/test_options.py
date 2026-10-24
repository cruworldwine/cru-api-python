"""Per-call options, with_options(), timeouts, back-off, the User-Agent, request ids and closing."""

import email.utils
import platform
import re
from datetime import datetime, timedelta, timezone

import httpx
import pytest

import cruworldwine
from cruworldwine import _base_client
from tests.helpers import app, envelope, error, make, partner, sleeps

PONG = {'pong': True, 'client': {}}


def timeout_of(request):
    return request.extensions['timeout']


def test_per_call_headers_timeout_and_max_retries(mock, kind, run):
    mock.add(503, error('SERVICE_UNAVAILABLE'))
    cru = partner(mock, kind)
    with pytest.raises(cruworldwine.InternalServerError):
        run(cru.bids.get('CB-1', extra_headers={'X-Trace': 't1'}, timeout=3.5, max_retries=0))
    assert len(mock.requests) == 1
    assert mock.requests[0].headers['x-trace'] == 't1'
    assert timeout_of(mock.requests[0]) == httpx.Timeout(3.5).as_dict()


def test_per_call_max_retries_can_raise_the_count(mock, kind, run):
    for _ in range(4):
        mock.add(500, error('INTERNAL_ERROR'))
    mock.add(200, envelope(PONG))
    run(partner(mock, kind).ping(max_retries=4))
    assert len(mock.requests) == 5
    assert len(sleeps) == 4


def test_extra_headers_can_replace_the_sdks(mock, kind, run):
    mock.add(200, envelope(PONG))
    run(partner(mock, kind).ping(extra_headers={'User-Agent': 'mine/1', 'Accept': 'application/vnd.cru+json'}))
    assert mock.requests[0].headers['user-agent'] == 'mine/1'
    assert mock.requests[0].headers['accept'] == 'application/vnd.cru+json'


def test_default_timeout_is_thirty_seconds(mock, kind, run):
    mock.add(200, envelope(PONG))
    cru = partner(mock, kind)
    run(cru.ping())
    assert timeout_of(mock.requests[0]) == httpx.Timeout(30.0).as_dict()
    assert cru.timeout == httpx.Timeout(30.0)


def test_http_clients_own_timeout_is_kept(mock, kind, run):
    mock.add(200, envelope(PONG)).add(200, envelope(PONG))
    transport = httpx.MockTransport(mock)
    if kind == 'sync':
        cru = cruworldwine.Cru(access_token='t', http_client=httpx.Client(transport=transport, timeout=7))
    else:
        cru = cruworldwine.AsyncCru(access_token='t', http_client=httpx.AsyncClient(transport=transport, timeout=7))
    run(cru.ping())
    run(cru.ping(timeout=httpx.Timeout(1.0, connect=2.0)))
    assert timeout_of(mock.requests[0]) == httpx.Timeout(7).as_dict()
    assert timeout_of(mock.requests[1]) == httpx.Timeout(1.0, connect=2.0).as_dict()


def test_constructor_timeout_wins(mock, kind, run):
    mock.add(200, envelope(PONG))
    run(partner(mock, kind, timeout=12).ping())
    assert timeout_of(mock.requests[0]) == httpx.Timeout(12).as_dict()


@pytest.mark.parametrize('cls', [cruworldwine.Cru, cruworldwine.AsyncCru])
def test_default_http_client(cls, run):
    cru = cls(client_key='k', client_secret='s')
    assert cru._http.timeout == httpx.Timeout(30.0)
    assert cru._http.follow_redirects is False
    assert not cru.is_closed
    run(cru.close() if cls is cruworldwine.Cru else cru.aclose())
    assert cru.is_closed


def test_with_options_copies_and_shares_the_pool(mock, kind, run):
    mock.add(503, error('SERVICE_UNAVAILABLE'))
    cru = partner(mock, kind)
    fast = cru.with_options(timeout=2, max_retries=0)
    assert fast is not cru
    assert fast._http is cru._http
    assert fast.bids._client is fast
    assert cru.bids._client is cru
    assert (fast.max_retries, cru.max_retries) == (0, 2)
    assert (fast.timeout, cru.timeout) == (httpx.Timeout(2), httpx.Timeout(30.0))
    with pytest.raises(cruworldwine.InternalServerError):
        run(fast.bids.get('CB-1'))
    assert len(mock.requests) == 1
    assert timeout_of(mock.requests[0]) == httpx.Timeout(2).as_dict()
    assert cru.with_options().max_retries == 2


def test_with_options_shares_refreshed_tokens(mock, kind, run):
    mock.add(401, error('AUTH_INVALID_CREDENTIALS'))
    mock.add(200, {'access_token': 'cru_at_two', 'refresh_token': 'cru_rt_two'})
    mock.add(200, envelope(PONG)).add(200, envelope(PONG))
    cru = app(mock, kind, refresh_token='cru_rt_one', oauth_client_id='client-1')
    run(cru.with_options(max_retries=0).ping())
    assert (cru.access_token, cru.refresh_token) == ('cru_at_two', 'cru_rt_two')
    run(cru.ping())
    assert mock.requests[-1].headers['authorization'] == 'Bearer cru_at_two'
    cru.access_token = 'cru_at_three'
    assert cru.with_options(timeout=1).access_token == 'cru_at_three'


@pytest.mark.parametrize(
    'options',
    [{'timeout': -1}, {'timeout': 'soon'}, {'timeout': True}, {'max_retries': -1}, {'max_retries': 1.5}],
)
def test_bad_options_are_refused(mock, kind, run, options):
    cru = partner(mock, kind)
    with pytest.raises(cruworldwine.CruError):
        cru.with_options(**options)
    with pytest.raises(cruworldwine.CruError):
        run(cru.ping(**options))
    with pytest.raises(cruworldwine.CruError):
        partner(mock, kind, **options)
    assert mock.requests == []


@pytest.mark.parametrize(
    ('kwargs', 'match'),
    [
        ({'market': 'evil.example/x#'}, 'market'),
        ({'base_url': 'ftp://example.test/api/v1'}, 'base_url'),
    ],
)
def test_bad_endpoints_are_refused(kwargs, match):
    with pytest.raises(cruworldwine.CruError, match=match):
        cruworldwine.Cru(client_key='k', client_secret='s', **kwargs)


def test_market_is_lower_cased(mock, kind, run):
    mock.add(200, envelope(PONG))
    run(partner(mock, kind, market=' US ').ping())
    assert mock.requests[0].url.host == 'us.cruworldwine.com'


def test_user_agent(mock, kind, run):
    mock.add(200, envelope(PONG))
    run(partner(mock, kind).ping())
    agent = mock.requests[0].headers['user-agent']
    assert re.fullmatch(r'cruworldwine-python/\S+ Python/\S+ \([^;()]+; [^;()]+\)', agent)
    assert agent.startswith(f'cruworldwine-python/{cruworldwine.__version__} Python/{platform.python_version()} (')


@pytest.mark.parametrize(
    ('app_info', 'suffix'),
    [
        (('cellar-sync', '2.3.0', 'https://cellar.example'), ' cellar-sync/2.3.0 (https://cellar.example)'),
        (('My App', None, None), ' My-App'),
        (('tool', '1.0', None), ' tool/1.0'),
        (['listy', '9'], ' listy/9'),
    ],
)
def test_app_info_is_appended(mock, kind, run, app_info, suffix):
    mock.add(200, envelope(PONG))
    run(partner(mock, kind, app_info=app_info).ping())
    assert mock.requests[0].headers['user-agent'].endswith(f') {suffix.lstrip()}')


@pytest.mark.parametrize('app_info', [('', None, None), ('bad\r\nname', None, None), ('ok', '1\n', None), 'name'])
def test_bad_app_info_is_refused(app_info):
    with pytest.raises(cruworldwine.CruError, match='app_info'):
        cruworldwine.Cru(client_key='k', client_secret='s', app_info=app_info)


def http_date(seconds_from_now):
    return email.utils.format_datetime(datetime.now(timezone.utc) + timedelta(seconds=seconds_from_now), usegmt=True)


@pytest.mark.parametrize(
    ('header', 'low', 'high'),
    [
        (lambda: http_date(12), 9.0, 12.0),
        (lambda: http_date(-60), 0.0, 0.0),
        (lambda: http_date(3600), 30.0, 30.0),
        (lambda: '1.5', 1.5, 1.5),
        (lambda: '120', 30.0, 30.0),
        (lambda: 'inf', 0.375, 0.625),
        (lambda: 'not a date', 0.375, 0.625),
        (lambda: 'Tue, 32 Foo 2026 99:00:00 GMT', 0.375, 0.625),
    ],
)
def test_retry_after(mock, kind, run, header, low, high):
    mock.add(503, error('SERVICE_UNAVAILABLE'), headers={'Retry-After': header()})
    mock.add(200, envelope(PONG))
    run(partner(mock, kind).ping())
    assert len(sleeps) == 1
    assert low <= sleeps[0] <= high


def test_retry_after_detail_beats_the_header(mock, kind, run):
    mock.add(429, error('RATE_LIMIT_EXCEEDED', details={'retry_after': 4}), headers={'Retry-After': '9'})
    mock.add(200, envelope(PONG))
    run(partner(mock, kind).ping())
    assert sleeps == [4.0]


def test_exponential_back_off_with_jitter(mock, kind, run):
    for _ in range(4):
        mock.add(502, error('INTERNAL_ERROR'))
    mock.add(200, envelope(PONG))
    run(partner(mock, kind, max_retries=4).ping())
    bounds = [(0.375, 0.625), (0.75, 1.25), (1.5, 2.5), (3.0, 5.0)]
    assert all(low <= s <= high for s, (low, high) in zip(sleeps, bounds))
    assert len(sleeps) == 4


def test_back_off_is_capped():
    assert _base_client._retry_delay(30) <= 8.0 * 1.25
    assert _base_client._retry_delay(1, envelope=error('X', details={'retry_after': 999})) == 30.0
    assert _base_client._retry_delay(1, envelope=error('X', details={'retry_after': float('nan')})) < 1


def test_request_ids_on_every_answer(mock, kind, run):
    cru = partner(mock, kind)
    mock.add(200, envelope({'bid': {'code': 'CB-1', 'requirements': {}}}, request_id='req_get'))
    bid = run(cru.market.get_bid('CB-1'))
    assert bid._request_id == 'req_get'
    assert bid.requirements._request_id is None

    pagination = {'limit': 1, 'offset': 0, 'total': 1, 'has_more': False}
    mock.add(200, envelope({'bids': [{'code': 'CB-1'}]}, pagination=pagination, request_id='req_page'))
    page = run(cru.bids.list())
    assert page.request_id == page._request_id == page.items[0]._request_id == 'req_page'
    assert 'req_page' in repr(page)

    mock.add(200, envelope({'warehouses': [{'code': 'W1'}, {'code': 'W2'}]}, request_id='req_list'))
    assert [w._request_id for w in run(cru.warehouses.list())] == ['req_list', 'req_list']

    mock.add(201, envelope({'action': 'bid.place', 'status': 'completed', 'bid': {}}, request_id='req_write'))
    write = run(cru.bids.place(lwin18='1', quantity=1, price=1))
    assert write.request_id == write._request_id == write.result._request_id == 'req_write'
    assert 'req_write' in repr(write)


def test_request_id_falls_back_to_the_header(mock, kind, run):
    mock.add(200, {'data': PONG}, headers={'X-Request-Id': 'req_header'})
    assert run(partner(mock, kind).ping())._request_id == 'req_header'


def test_sync_context_manager_closes(mock):
    with partner(mock) as cru:
        assert not cru.is_closed
    assert cru.is_closed


def test_async_context_manager_closes(mock, run):
    async def use():
        async with partner(mock, 'async') as cru:
            assert not cru.is_closed
        return cru

    assert run(use()).is_closed


def test_page_and_write_reprs():
    page = cruworldwine.Page([1, 2], {}, {'pagination': {'limit': 2, 'offset': 4}}, lambda offset: None)
    assert repr(page) == 'Page(items=2, offset=4, total=None, has_more=True, request_id=None)'
    write = cruworldwine.Write(None, {'code': 'cnf_1'}, False, 'r1')
    assert repr(write) == "Write(staged=True, confirmation={'code': 'cnf_1'}, request_id='r1')"


def test_odd_pagination_is_tolerated(mock, kind, run):
    mock.add(200, envelope({'bids': 'nope'}, pagination={'limit': 'x', 'offset': None, 'has_more': 'yes'}))
    page = run(partner(mock, kind).bids.list())
    assert (page.items, page.limit, page.offset, page.total, page.has_more) == ([], None, 0, None, False)


def test_handler_can_inspect_the_client(kind, run):
    seen = []

    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200, json=envelope(PONG))

    cru = make(kind, handler, client_key='k', client_secret='s', base_url='http://localhost:8080/api/v1')
    run(cru.ping())
    assert seen == ['/api/v1/ping']
    assert 'localhost:8080' in repr(cru)
