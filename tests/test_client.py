"""The client's behaviour, checked on Cru and again on AsyncCru."""

import httpx
import pytest

import cruworldwine
from conftest import app, collect, envelope, error, partner, sleeps
from cruworldwine import models

BID = {
    'code': 'CB-1001',
    'client_ref': None,
    'lwin18': '100000000000000001',
    'wine_name': 'Example Estate 2016 (6x75cl)',
    'vintage': 2016,
    'pack_size': '6x75cl',
    'product_url': None,
    'price': 1200.0,
    'currency': 'GBP',
    'bid_currency': 'GBP',
    'quantity': 2,
    'quantity_matched': 0,
    'quantity_open': 2,
    'order_numbers': [],
    'order_urls': [],
    'status': 'live',
    'renewable': False,
    'market': 'uk',
    'local_only': False,
    'auto_transfer': False,
    'expires_on': '2027-01-01',
    'created_at': '2026-01-01T00:00:00Z',
    'updated_at': None,
}


def test_partner_headers_and_base_url(mock, kind, run):
    mock.add(200, envelope({'pong': True, 'client': {'market': 'hk', 'scopes': ['meta:read']}}))
    ping = run(partner(mock, kind, market='hk').ping())
    req = mock.requests[0]
    assert str(req.url) == 'https://hk.cruworldwine.com/api/v1/ping'
    assert req.headers['CLIENT-KEY'] == 'cru_test_key'
    assert req.headers['CLIENT-SECRET'] == 'secret'
    assert 'authorization' not in req.headers
    assert req.headers['user-agent'].startswith('cruworldwine-python/')
    assert ping.pong is True
    assert ping.client.scopes == ['meta:read']


def test_bearer_and_env(mock, kind, run, monkeypatch):
    monkeypatch.setenv('CRU_BASE_URL', 'https://example.test/api/v1/')
    mock.add(200, envelope({'pong': True, 'client': {}}))
    run(app(mock, kind).ping())
    assert str(mock.requests[0].url) == 'https://example.test/api/v1/ping'
    assert mock.requests[0].headers['authorization'] == 'Bearer cru_at_one'


def test_credentials_from_env(mock, kind, run, monkeypatch):
    monkeypatch.setenv('CRU_CLIENT_KEY', 'env_key')
    monkeypatch.setenv('CRU_CLIENT_SECRET', 'env_secret')
    monkeypatch.setenv('CRU_MARKET', 'sg')
    mock.add(200, envelope({'pong': True, 'client': {}}))
    client = cruworldwine.Cru if kind == 'sync' else cruworldwine.AsyncCru
    transport = httpx.MockTransport(mock)
    http = httpx.Client(transport=transport) if kind == 'sync' else httpx.AsyncClient(transport=transport)
    run(client(http_client=http).ping())
    assert mock.requests[0].headers['client-key'] == 'env_key'
    assert mock.requests[0].url.host == 'sg.cruworldwine.com'


@pytest.mark.parametrize('cls', [cruworldwine.Cru, cruworldwine.AsyncCru])
def test_needs_credentials(cls):
    with pytest.raises(cruworldwine.CruError, match='client_key and client_secret, or access_token'):
        cls()


def test_query_encoding_and_page(mock, kind, run):
    mock.add(200, envelope({'bids': [BID]}, pagination={'limit': 1, 'offset': 0, 'total': 3, 'has_more': True}))
    page = run(partner(mock, kind).bids.list(status=['live', 'expired'], lwin='100000000000000001', limit=1))
    assert dict(mock.requests[0].url.params) == {'status': 'live,expired', 'lwin': '100000000000000001', 'limit': '1'}
    assert isinstance(page.items[0], models.OwnBid)
    assert page.items[0].price == 1200.0
    assert (page.total, page.has_more, len(page)) == (3, True, 1)
    assert [b.code for b in page] == ['CB-1001']


def test_auto_paging(mock, kind, run):
    for offset, more in ((0, True), (1, True), (2, False)):
        pagination = {'limit': 1, 'offset': offset, 'total': 3, 'has_more': more}
        mock.add(200, envelope({'bids': [dict(BID, code=f'CB-{offset}')]}, pagination=pagination))
    page = run(partner(mock, kind).bids.list(limit=1))
    assert [b.code for b in collect(run, page)] == ['CB-0', 'CB-1', 'CB-2']
    assert [r.url.params.get('offset') for r in mock.requests] == [None, '1', '2']


def test_next_page_keeps_the_call(mock, kind, run):
    mock.add(200, envelope({'bids': [BID]}, pagination={'limit': 1, 'offset': 0, 'total': 2, 'has_more': True}))
    mock.add(200, envelope({'bids': [BID]}, pagination={'limit': 1, 'offset': 1, 'total': 2, 'has_more': False}))
    page = run(partner(mock, kind).bids.list(limit=1, extra_query={'offset': 0, 'x': 1}, extra_headers={'X-A': 'b'}))
    second = run(page.next_page())
    assert second.offset == 1
    assert run(second.next_page()) is None
    assert dict(mock.requests[1].url.params) == {'limit': '1', 'offset': '1', 'x': '1'}
    assert mock.requests[1].headers['x-a'] == 'b'


def test_booleans_and_path_escaping(mock, kind, run):
    mock.add(200, envelope({'market': {'lwin18': 'x', 'bids': []}}))
    run(partner(mock, kind).market.get_wine_bids('ARM/RB 1', landed_stock_only=True))
    assert mock.requests[0].url.raw_path == b'/api/v1/market/wines/ARM%2FRB%201/bids?landed_stock_only=true'


def test_empty_path_param_refused(mock, kind, run):
    with pytest.raises(cruworldwine.CruError, match='code is required'):
        run(partner(mock, kind).bids.get(''))
    assert mock.requests == []


def test_partner_write_gets_one_reference_across_retries(mock, kind, run):
    mock.add(503, error('SERVICE_UNAVAILABLE')).fail(httpx.ConnectError('reset'))
    mock.add(201, envelope({'action': 'bid.place', 'status': 'completed', 'bid': BID}))
    write = run(partner(mock, kind).bids.place(lwin18='100000000000000001', quantity=2, price=1200))
    refs = {mock.body(i)['reference'] for i in range(3)}
    assert len(refs) == 1
    ref = next(iter(refs))
    assert ref.startswith('sdk_')
    assert mock.body(0) == {'lwin18': '100000000000000001', 'quantity': 2, 'price': 1200, 'reference': ref}
    assert not write.staged
    assert write.result.bid.code == 'CB-1001'
    assert write.result.action == 'bid.place'
    assert len(sleeps) == 2


def test_given_reference_kept_and_empty_body_is_object(mock, kind, run):
    mock.add(
        200,
        envelope({'action': 'bid.cancel', 'status': 'completed', 'bid': BID}),
        headers={'Idempotent-Replayed': 'true'},
    )
    write = run(partner(mock, kind).bids.cancel('CB-1001', reference='my-ref-1'))
    assert mock.body() == {'reference': 'my-ref-1'}
    assert write.replayed is True


def test_app_write_is_staged_and_never_retried(mock, kind, run):
    mock.add(503, error('SERVICE_UNAVAILABLE'))
    with pytest.raises(cruworldwine.InternalServerError):
        run(app(mock, kind).bids.place(lwin18='100000000000000001', quantity=1, price=10))
    assert len(mock.requests) == 1
    assert 'reference' not in mock.body()

    confirmation = {
        'code': 'cnf_' + 'a' * 43,
        'action': 'bid.place',
        'status': 'pending',
        'expires_at': '2026-01-01T00:15:00Z',
        'preview': {'summary': 'Bid 1200 for 2.', 'quantity': 2},
    }
    mock.add(202, envelope({'confirmation': confirmation}, request_id='req_staged'))
    write = run(app(mock, kind).bids.place(lwin18='100000000000000001', quantity=2, price=1200))
    assert write.staged
    assert write.result is None
    assert write.confirmation.code.startswith('cnf_')
    assert write.confirmation.preview.summary == 'Bid 1200 for 2.'
    assert write.confirmation.preview['quantity'] == 2
    assert write.request_id == write._request_id == write.confirmation._request_id == 'req_staged'


def test_confirm_is_typed_by_action(mock, kind, run):
    mock.add(200, envelope({'action': 'offer.remove', 'status': 'completed', 'offer': None, 'removed': 3}))
    write = run(app(mock, kind).confirmations.confirm('cnf_x'))
    assert isinstance(write.result, models.OfferRemoveResult)
    assert write.result.removed == 3
    mock.add(201, envelope({'action': 'something.new', 'status': 'completed', 'thing': 1}))
    write = run(app(mock, kind).confirmations.confirm('cnf_y'))
    assert isinstance(write.result, models.InstructionResult)
    assert write.result['thing'] == 1
    assert mock.requests[-1].method == 'POST'
    assert mock.body() == {}


def test_no_content_and_binary(mock, kind, run):
    mock.add(204)
    assert run(app(mock, kind).confirmations.cancel('cnf_x')) is None
    mock.add(200, content=b'\x89PNG', headers={'Content-Type': 'image/png'})
    assert run(partner(mock, kind).photos.get('abc')) == b'\x89PNG'


@pytest.mark.parametrize(
    ('status', 'code', 'cls'),
    [
        (400, 'VALIDATION_UNKNOWN_PARAMETER', cruworldwine.BadRequestError),
        (401, 'AUTH_INVALID_CREDENTIALS', cruworldwine.AuthenticationError),
        (403, 'AUTH_INSUFFICIENT_SCOPE', cruworldwine.PermissionDeniedError),
        (404, 'BID_NOT_FOUND', cruworldwine.NotFoundError),
        (405, 'METHOD_NOT_ALLOWED', cruworldwine.MethodNotAllowedError),
        (409, 'PRICE_CHANGED', cruworldwine.PriceChangedError),
        (409, 'CONFIRMATION_LIMIT_REACHED', cruworldwine.ConflictError),
        (410, 'CONFIRMATION_EXPIRED', cruworldwine.GoneError),
        (422, 'TRADE_REFUSED', cruworldwine.UnprocessableEntityError),
        (418, 'SOMETHING_NEW', cruworldwine.APIStatusError),
    ],
)
def test_errors(mock, kind, run, status, code, cls):
    mock.add(status, error(code, field='price', details={'allowed_methods': ['GET']}))
    with pytest.raises(cls) as caught:
        run(partner(mock, kind).bids.get('CB-1'))
    e = caught.value
    assert type(e) is cls
    assert (e.status_code, e.code, e.field, e.request_id) == (status, code, 'price', 'req_test_0001')
    assert e.details == {'allowed_methods': ['GET']}
    assert len(e.errors) == 1
    assert str(e) == f'{status} {code}: {code.lower()}'
    assert repr(e).startswith(f'{cls.__name__}(status_code={status}, code={code!r}')


def test_error_without_envelope(mock, kind, run):
    mock.add(502, content=b'<html>Bad gateway</html>', headers={'X-Request-Id': 'req_edge'})
    with pytest.raises(cruworldwine.InternalServerError) as caught:
        run(partner(mock, kind, max_retries=0).bids.get('CB-1'))
    e = caught.value
    assert (e.code, e.message, e.request_id, str(e)) == (None, 'HTTP 502', 'req_edge', '502: HTTP 502')
    assert e.headers['x-request-id'] == 'req_edge'


def test_odd_error_shapes_are_tolerated():
    e = cruworldwine.APIStatusError(400, {'errors': 'oops', 'meta': [], 'message': 'plain'}, None)
    assert (e.errors, e.code, e.message, e.request_id) == ([], None, 'plain', None)
    e = cruworldwine.APIStatusError(400, {'errors': [1, {'code': 'X', 'details': 'no'}]}, {'X-Request-Id': 'r'})
    assert (e.code, e.details, e.request_id, len(e.errors)) == ('X', {}, 'r', 1)


def test_rate_limit_retries_then_raises(mock, kind, run):
    for _ in range(3):
        mock.add(429, error('RATE_LIMIT_EXCEEDED'), headers={'Retry-After': '3'})
    with pytest.raises(cruworldwine.RateLimitError):
        run(partner(mock, kind).bids.get('CB-1'))
    assert len(mock.requests) == 3
    assert sleeps == [3.0, 3.0]


def test_request_in_progress_waits_retry_after(mock, kind, run):
    mock.add(409, error('REQUEST_IN_PROGRESS', field='reference', details={'retry_after': 2}))
    mock.add(200, envelope({'action': 'bid.renew', 'status': 'completed', 'bid': BID}))
    run(partner(mock, kind).bids.renew('CB-1'))
    assert sleeps == [2.0]
    assert mock.body(0)['reference'] == mock.body(1)['reference']


def test_refresh_once_rotates_and_calls_back(mock, kind, run):
    seen = []
    mock.add(401, error('AUTH_INVALID_CREDENTIALS'))
    mock.add(200, {'access_token': 'cru_at_two', 'refresh_token': 'cru_rt_two', 'token_type': 'Bearer'})
    mock.add(200, envelope({'pong': True, 'client': {}}))
    cru = app(
        mock,
        kind,
        refresh_token='cru_rt_one',
        oauth_client_id='client-1',
        oauth_client_secret='s3',
        on_token_refresh=seen.append,
        base_url='https://uk.cruworldwine.com/api/v1',
    )
    run(cru.ping())
    token_req = mock.requests[1]
    assert str(token_req.url) == 'https://uk.cruworldwine.com/api/oauth/token'
    assert dict(httpx.QueryParams(token_req.content.decode())) == {
        'grant_type': 'refresh_token',
        'refresh_token': 'cru_rt_one',
        'client_id': 'client-1',
        'client_secret': 's3',
    }
    assert mock.requests[2].headers['authorization'] == 'Bearer cru_at_two'
    assert (cru.access_token, cru.refresh_token, seen[0]['access_token']) == ('cru_at_two', 'cru_rt_two', 'cru_at_two')


def test_refresh_keeps_refresh_token_when_none_is_returned(mock, kind, run):
    mock.add(401, error('AUTH_INVALID_CREDENTIALS'))
    mock.add(200, {'access_token': 'cru_at_two'})
    mock.add(200, envelope({'pong': True, 'client': {}}))
    cru = app(mock, kind, refresh_token='cru_rt_one', oauth_client_id='client-1')
    run(cru.ping())
    assert (cru.access_token, cru.refresh_token) == ('cru_at_two', 'cru_rt_one')
    assert 'client_secret' not in httpx.QueryParams(mock.requests[1].content.decode())


def test_failed_refresh_raises(mock, kind, run):
    mock.add(401, error('AUTH_INVALID_CREDENTIALS'))
    mock.add(400, {'error': 'invalid_grant', 'error_description': 'The refresh token was used already.'})
    with pytest.raises(cruworldwine.AuthenticationError, match='used already'):
        run(app(mock, kind, refresh_token='cru_rt_one', oauth_client_id='client-1').ping())


def test_second_401_after_refresh_raises(mock, kind, run):
    mock.add(401, error('AUTH_INVALID_CREDENTIALS'))
    mock.add(200, {'access_token': 'cru_at_two'})
    mock.add(401, error('AUTH_INVALID_CREDENTIALS'))
    with pytest.raises(cruworldwine.AuthenticationError):
        run(app(mock, kind, refresh_token='cru_rt_one', oauth_client_id='client-1').ping())
    assert len(mock.requests) == 3


def test_no_refresh_without_refresh_token(mock, kind, run):
    mock.add(401, error('AUTH_INVALID_CREDENTIALS'))
    with pytest.raises(cruworldwine.AuthenticationError):
        run(app(mock, kind).ping())
    assert len(mock.requests) == 1


def test_unknown_fields_and_values_tolerated(mock, kind, run):
    line = {
        'portfolio_id': 'PORTFOLIO-1',
        'stock_type': 'warehouse_x',
        'brand_new': {'a': 1},
        'pricing': {'cost': 10, 'listing_price': None, 'surprise': True},
        'warehouse': None,
    }
    wines = [{'lwin18': '1', 'portfolio': [line], 'added_later': [1, 2]}]
    mock.add(200, envelope({'wines': wines}, pagination={'limit': 100, 'offset': 0}))
    wine = run(partner(mock, kind).portfolio.list()).items[0]
    assert wine['added_later'] == [1, 2]
    assert wine.total_quantity is None
    got = wine.portfolio[0]
    assert got.stock_type == 'warehouse_x'
    assert got['brand_new'] == {'a': 1}
    assert got.pricing.cost == 10
    assert got.pricing['surprise'] is True
    assert got.warehouse is None
    assert got.to_dict() == line


def test_explicit_token_ignores_env_key_pair(mock, kind, run, monkeypatch):
    monkeypatch.setenv('CRU_CLIENT_KEY', 'env_key')
    monkeypatch.setenv('CRU_CLIENT_SECRET', 'env_secret')
    mock.add(200, envelope({'pong': True, 'client': {}}))
    cru = app(mock, kind)
    run(cru.ping())
    assert not cru.is_partner
    assert 'client-key' not in mock.requests[0].headers


def test_empty_list_not_sent(mock, kind, run):
    mock.add(200, envelope({'bids': []}, pagination={'limit': 100, 'offset': 0, 'total': 0, 'has_more': False}))
    page = run(partner(mock, kind).bids.list(status=[]))
    assert 'status' not in mock.requests[0].url.params
    assert run(page.next_page()) is None


def test_redirect_is_an_error_not_followed(mock, kind, run):
    mock.add(302, headers={'Location': 'https://elsewhere.test/api/v1/ping'})
    with pytest.raises(cruworldwine.APIStatusError) as caught:
        run(partner(mock, kind).ping())
    assert caught.value.status_code == 302
    assert len(mock.requests) == 1


def test_price_changed_only_on_409(mock, kind, run):
    mock.add(422, error('PRICE_CHANGED'))
    with pytest.raises(cruworldwine.UnprocessableEntityError) as caught:
        run(partner(mock, kind).bids.get('CB-1'))
    assert not isinstance(caught.value, cruworldwine.PriceChangedError)


def test_refresh_connection_failure_is_a_connection_error(mock, kind, run):
    mock.add(401, error('AUTH_INVALID_CREDENTIALS')).fail(httpx.ConnectError('down'))
    with pytest.raises(cruworldwine.APIConnectionError):
        run(app(mock, kind, refresh_token='cru_rt_one', oauth_client_id='client-1').ping())


def test_timeouts_retry_then_raise(mock, kind, run):
    for _ in range(3):
        mock.fail(httpx.ReadTimeout('slow'))
    with pytest.raises(cruworldwine.APITimeoutError, match='slow'):
        run(partner(mock, kind).bids.get('CB-1'))
    assert len(mock.requests) == 3
    assert len(sleeps) == 2


def test_connection_errors_retry_then_raise(mock, kind, run):
    mock.fail(httpx.ConnectError('refused')).fail(httpx.ConnectError('refused'))
    with pytest.raises(cruworldwine.APIConnectionError) as caught:
        run(partner(mock, kind, max_retries=1).bids.get('CB-1'))
    assert not isinstance(caught.value, cruworldwine.APITimeoutError)
    assert len(mock.requests) == 2


def test_request_errors_that_are_not_transport_errors_are_not_retried(mock, kind, run):
    mock.fail(httpx.DecodingError('bad gzip'))
    with pytest.raises(cruworldwine.APIConnectionError, match='bad gzip'):
        run(partner(mock, kind).bids.get('CB-1'))
    assert len(mock.requests) == 1


def test_missing_data_key_is_an_error(mock, kind, run):
    mock.add(200, envelope({}))
    with pytest.raises(cruworldwine.CruError, match=r'data\.bid'):
        run(partner(mock, kind).bids.get('CB-1'))


def test_photo_accepts_any_type(mock, kind, run):
    mock.add(200, content=b'img', headers={'Content-Type': 'image/jpeg'})
    run(partner(mock, kind).photos.get('PHOTO-1'))
    assert mock.requests[0].headers['accept'] == '*/*'


def test_extra_query_and_body(mock, kind, run):
    mock.add(200, envelope({'action': 'offer.update', 'status': 'completed', 'offer': None}))
    run(
        partner(mock, kind).offers.update(
            'PORTFOLIO-1', price=10, extra_query={'dry': True}, extra_body={'new_field': 'x', 'cleared': None}
        )
    )
    assert mock.requests[0].url.params['dry'] == 'true'
    assert mock.body()['new_field'] == 'x'
    assert mock.body()['price'] == 10
    assert mock.body()['cleared'] is None


def test_raw_request_escape_hatch(mock, kind, run):
    mock.add(200, envelope({'anything': 1}, request_id='req_raw'))
    resp = run(partner(mock, kind).request('post', '/new/thing', query={'a': [1, 2]}, body={'x': 1}))
    assert resp.status_code == 200
    assert resp.data == {'anything': 1}
    assert resp.request_id == 'req_raw'
    assert repr(resp) == "Response(status_code=200, request_id='req_raw')"
    assert mock.requests[0].method == 'POST'
    assert mock.requests[0].url.params['a'] == '1,2'
    assert mock.body()['x'] == 1
    assert mock.body()['reference'].startswith('sdk_')


def test_raw_request_without_a_body(mock, kind, run):
    mock.add(200, content=b'not json', headers={'X-Request-Id': 'req_h'})
    resp = run(app(mock, kind).request('DELETE', '/thing'))
    assert mock.requests[0].content == b''
    assert (resp.body, resp.data, resp.meta, resp.request_id) == ({}, None, {}, 'req_h')
