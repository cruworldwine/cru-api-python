import httpx
import pytest
from conftest import app, envelope, error, partner, sleeps

import cruworldwine
from cruworldwine import models

BID = {
    'code': 'CB-1001', 'client_ref': None, 'lwin18': '100000000000000001', 'wine_name': 'Example Estate 2016 (6x75cl)',
    'vintage': 2016, 'pack_size': '6x75cl', 'product_url': None, 'price': 1200.0, 'currency': 'GBP', 'bid_currency': 'GBP',
    'quantity': 2, 'quantity_matched': 0, 'quantity_open': 2, 'order_numbers': [], 'order_urls': [], 'status': 'live',
    'renewable': False, 'market': 'uk', 'local_only': False, 'auto_transfer': False, 'expires_on': '2027-01-01',
    'created_at': '2026-01-01T00:00:00Z', 'updated_at': None,
}


def test_partner_headers_and_base_url(mock):
    mock.add(200, envelope({'pong': True, 'client': {'market': 'hk', 'scopes': ['meta:read']}}))
    ping = partner(mock, market='hk').ping()
    req = mock.requests[0]
    assert str(req.url) == 'https://hk.cruworldwine.com/api/v1/ping'
    assert req.headers['CLIENT-KEY'] == 'cru_test_key' and req.headers['CLIENT-SECRET'] == 'secret'
    assert 'authorization' not in req.headers
    assert req.headers['user-agent'].startswith('cruworldwine-python/')
    assert ping.pong is True and ping.client.scopes == ['meta:read']


def test_bearer_and_env(mock, monkeypatch):
    monkeypatch.setenv('CRU_BASE_URL', 'https://example.test/api/v1/')
    mock.add(200, envelope({'pong': True, 'client': {}}))
    app(mock).ping()
    assert str(mock.requests[0].url) == 'https://example.test/api/v1/ping'
    assert mock.requests[0].headers['authorization'] == 'Bearer cru_at_one'


def test_needs_credentials(monkeypatch):
    for name in ('CRU_CLIENT_KEY', 'CRU_CLIENT_SECRET', 'CRU_ACCESS_TOKEN'):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(cruworldwine.CruError):
        cruworldwine.Cru()


def test_query_encoding_and_page(mock):
    mock.add(200, envelope({'bids': [BID]}, pagination={'limit': 1, 'offset': 0, 'total': 3, 'has_more': True}))
    page = partner(mock).bids.list(status=['live', 'expired'], lwin='100000000000000001', limit=1)
    assert dict(mock.requests[0].url.params) == {'status': 'live,expired', 'lwin': '100000000000000001', 'limit': '1'}
    assert isinstance(page.items[0], models.OwnBid) and page.items[0].price == 1200.0
    assert (page.total, page.has_more, len(page)) == (3, True, 1)


def test_auto_paging(mock):
    for offset, more in ((0, True), (1, True), (2, False)):
        mock.add(200, envelope({'bids': [dict(BID, code=f'CB-{offset}')]}, pagination={'limit': 1, 'offset': offset, 'total': 3, 'has_more': more}))
    codes = [b.code for b in partner(mock).bids.list(limit=1).auto_paging_iter()]
    assert codes == ['CB-0', 'CB-1', 'CB-2']
    assert [r.url.params.get('offset') for r in mock.requests] == [None, '1', '2']


def test_booleans_and_path_escaping(mock):
    mock.add(200, envelope({'market': {'lwin18': 'x', 'bids': []}}))
    partner(mock).market.get_wine_bids('ARM/RB 1', landed_stock_only=True)
    assert mock.requests[0].url.raw_path == b'/api/v1/market/wines/ARM%2FRB%201/bids?landed_stock_only=true'


def test_empty_path_param_refused(mock):
    with pytest.raises(cruworldwine.CruError):
        partner(mock).bids.get('')


def test_partner_write_gets_one_reference_across_retries(mock):
    mock.add(503, error('SERVICE_UNAVAILABLE')).fail(httpx.ConnectError('reset')).add(201, envelope({'action': 'bid.place', 'status': 'completed', 'bid': BID}))
    write = partner(mock).bids.place(lwin18='100000000000000001', quantity=2, price=1200)
    refs = {mock.body(i)['reference'] for i in range(3)}
    assert len(refs) == 1 and next(iter(refs)).startswith('sdk_')
    assert mock.body(0) == {'lwin18': '100000000000000001', 'quantity': 2, 'price': 1200, 'reference': next(iter(refs))}
    assert not write.staged and write.result.bid.code == 'CB-1001' and write.result.action == 'bid.place'
    assert len(sleeps) == 2


def test_given_reference_kept_and_empty_body_is_object(mock):
    mock.add(200, envelope({'action': 'bid.cancel', 'status': 'completed', 'bid': BID}), headers={'Idempotent-Replayed': 'true'})
    write = partner(mock).bids.cancel('CB-1001', reference='my-ref-1')
    assert mock.body() == {'reference': 'my-ref-1'}
    assert write.replayed is True


def test_app_write_is_staged_and_never_retried(mock):
    mock.add(503, error('SERVICE_UNAVAILABLE'))
    with pytest.raises(cruworldwine.InternalServerError):
        app(mock).bids.place(lwin18='100000000000000001', quantity=1, price=10)
    assert len(mock.requests) == 1 and 'reference' not in mock.body()

    confirmation = {'code': 'cnf_' + 'a' * 43, 'action': 'bid.place', 'status': 'pending', 'expires_at': '2026-01-01T00:15:00Z',
                    'preview': {'summary': 'Bid 1200 for 2.', 'quantity': 2}}
    mock.add(202, envelope({'confirmation': confirmation}))
    write = app(mock).bids.place(lwin18='100000000000000001', quantity=2, price=1200)
    assert write.staged and write.result is None
    assert write.confirmation.code.startswith('cnf_') and write.confirmation.preview.summary == 'Bid 1200 for 2.'
    assert write.confirmation.preview['quantity'] == 2


def test_confirm_is_typed_by_action(mock):
    mock.add(200, envelope({'action': 'offer.remove', 'status': 'completed', 'offer': None, 'removed': 3, 'deleted': True}))
    write = app(mock).confirmations.confirm('cnf_x')
    assert isinstance(write.result, models.OfferRemoveResult) and write.result.removed == 3
    mock.add(201, envelope({'action': 'something.new', 'status': 'completed', 'thing': 1}))
    write = app(mock).confirmations.confirm('cnf_y')
    assert isinstance(write.result, models.InstructionResult) and write.result['thing'] == 1
    assert mock.requests[-1].method == 'POST' and mock.body() == {}


def test_no_content_and_binary(mock):
    mock.add(204)
    assert app(mock).confirmations.cancel('cnf_x') is None
    mock.add(200, content=b'\x89PNG', headers={'Content-Type': 'image/png'})
    assert partner(mock).photos.get('abc') == b'\x89PNG'


@pytest.mark.parametrize('status,code,cls', [
    (400, 'VALIDATION_UNKNOWN_PARAMETER', cruworldwine.BadRequestError),
    (401, 'AUTH_INVALID_CREDENTIALS', cruworldwine.AuthenticationError),
    (403, 'AUTH_INSUFFICIENT_SCOPE', cruworldwine.PermissionDeniedError),
    (404, 'BID_NOT_FOUND', cruworldwine.NotFoundError),
    (405, 'METHOD_NOT_ALLOWED', cruworldwine.MethodNotAllowedError),
    (409, 'PRICE_CHANGED', cruworldwine.PriceChangedError),
    (409, 'CONFIRMATION_LIMIT_REACHED', cruworldwine.ConflictError),
    (410, 'CONFIRMATION_EXPIRED', cruworldwine.GoneError),
    (422, 'TRADE_REFUSED', cruworldwine.UnprocessableEntityError),
])
def test_errors(mock, status, code, cls):
    mock.add(status, error(code, field='price', details={'allowed_methods': ['GET']}))
    with pytest.raises(cls) as caught:
        partner(mock).bids.get('CB-1')
    e = caught.value
    assert (e.status_code, e.code, e.field, e.request_id) == (status, code, 'price', 'req_test_0001')
    assert e.details == {'allowed_methods': ['GET']} and len(e.errors) == 1


def test_rate_limit_retries_then_raises(mock):
    for _ in range(3):
        mock.add(429, error('RATE_LIMIT_EXCEEDED'), headers={'Retry-After': '3'})
    with pytest.raises(cruworldwine.RateLimitError):
        partner(mock).bids.get('CB-1')
    assert len(mock.requests) == 3 and sleeps == [3.0, 3.0]


def test_request_in_progress_waits_retry_after(mock):
    mock.add(409, error('REQUEST_IN_PROGRESS', field='reference', details={'retry_after': 2}))
    mock.add(200, envelope({'action': 'bid.renew', 'status': 'completed', 'bid': BID}))
    partner(mock).bids.renew('CB-1')
    assert sleeps == [2.0] and mock.body(0)['reference'] == mock.body(1)['reference']


def test_refresh_once_rotates_and_calls_back(mock):
    seen = []
    mock.add(401, error('AUTH_INVALID_CREDENTIALS'))
    mock.add(200, {'access_token': 'cru_at_two', 'refresh_token': 'cru_rt_two', 'token_type': 'Bearer', 'expires_in': 3600})
    mock.add(200, envelope({'pong': True, 'client': {}}))
    cru = app(mock, refresh_token='cru_rt_one', oauth_client_id='client-1', oauth_client_secret='s3', on_token_refresh=seen.append, base_url='https://uk.cruworldwine.com/api/v1')
    cru.ping()
    token_req = mock.requests[1]
    assert str(token_req.url) == 'https://uk.cruworldwine.com/api/oauth/token'
    assert dict(httpx.QueryParams(token_req.content.decode())) == {'grant_type': 'refresh_token', 'refresh_token': 'cru_rt_one', 'client_id': 'client-1', 'client_secret': 's3'}
    assert mock.requests[2].headers['authorization'] == 'Bearer cru_at_two'
    assert (cru.access_token, cru.refresh_token, seen[0]['access_token']) == ('cru_at_two', 'cru_rt_two', 'cru_at_two')


def test_failed_refresh_raises(mock):
    mock.add(401, error('AUTH_INVALID_CREDENTIALS'))
    mock.add(400, {'error': 'invalid_grant', 'error_description': 'The refresh token was used already.'})
    with pytest.raises(cruworldwine.AuthenticationError):
        app(mock, refresh_token='cru_rt_one', oauth_client_id='client-1').ping()


def test_no_refresh_without_refresh_token(mock):
    mock.add(401, error('AUTH_INVALID_CREDENTIALS'))
    with pytest.raises(cruworldwine.AuthenticationError):
        app(mock).ping()
    assert len(mock.requests) == 1


def test_unknown_fields_and_values_tolerated(mock):
    line = {'portfolio_id': 'PORTFOLIO-1', 'stock_type': 'warehouse_x', 'brand_new': {'a': 1},
            'pricing': {'cost': 10, 'listing_price': None, 'surprise': True}, 'warehouse': None}
    mock.add(200, envelope({'wines': [{'lwin18': '1', 'portfolio': [line], 'added_later': [1, 2]}]}, pagination={'limit': 100, 'offset': 0}))
    wine = partner(mock).portfolio.list().items[0]
    assert wine['added_later'] == [1, 2] and wine.total_quantity is None
    got = wine.portfolio[0]
    assert got.stock_type == 'warehouse_x' and got['brand_new'] == {'a': 1}
    assert got.pricing.cost == 10 and got.pricing['surprise'] is True and got.warehouse is None
    assert got.to_dict() == line


def test_explicit_token_ignores_env_key_pair(mock, monkeypatch):
    monkeypatch.setenv('CRU_CLIENT_KEY', 'env_key')
    monkeypatch.setenv('CRU_CLIENT_SECRET', 'env_secret')
    mock.add(200, envelope({'pong': True, 'client': {}}))
    cru = app(mock)
    cru.ping()
    assert not cru.is_partner and 'client-key' not in mock.requests[0].headers


def test_empty_list_not_sent(mock):
    mock.add(200, envelope({'bids': []}, pagination={'limit': 100, 'offset': 0, 'total': 0, 'has_more': False}))
    partner(mock).bids.list(status=[])
    assert 'status' not in mock.requests[0].url.params


def test_redirect_is_an_error_not_followed(mock):
    mock.add(302, headers={'Location': 'https://elsewhere.test/api/v1/ping'})
    with pytest.raises(cruworldwine.APIStatusError) as caught:
        partner(mock).ping()
    assert caught.value.status_code == 302 and len(mock.requests) == 1


def test_price_changed_only_on_409(mock):
    mock.add(422, error('PRICE_CHANGED'))
    with pytest.raises(cruworldwine.UnprocessableEntityError) as caught:
        partner(mock).bids.get('CB-1')
    assert not isinstance(caught.value, cruworldwine.PriceChangedError)


def test_refresh_connection_failure_is_a_connection_error(mock):
    mock.add(401, error('AUTH_INVALID_CREDENTIALS')).fail(httpx.ConnectError('down'))
    with pytest.raises(cruworldwine.APIConnectionError):
        app(mock, refresh_token='cru_rt_one', oauth_client_id='client-1').ping()


def test_missing_data_key_is_an_error(mock):
    mock.add(200, envelope({}))
    with pytest.raises(cruworldwine.CruError):
        partner(mock).bids.get('CB-1')


def test_photo_accepts_any_type(mock):
    mock.add(200, content=b'img', headers={'Content-Type': 'image/jpeg'})
    partner(mock).photos.get('PHOTO-1')
    assert mock.requests[0].headers['accept'] == '*/*'


def test_extra_query_and_body(mock):
    mock.add(200, envelope({'action': 'offer.update', 'status': 'completed', 'offer': None}))
    partner(mock).offers.update('PORTFOLIO-1', price=10, extra_query={'dry': True}, extra_body={'new_field': 'x'})
    assert mock.requests[0].url.params['dry'] == 'true'
    assert mock.body()['new_field'] == 'x' and mock.body()['price'] == 10


def test_raw_request_escape_hatch(mock):
    mock.add(200, envelope({'anything': 1}))
    resp = partner(mock).request('POST', '/new/thing', body={'x': 1})
    assert resp.status_code == 200 and resp.data == {'anything': 1}
    assert mock.body()['x'] == 1 and mock.body()['reference'].startswith('sdk_')
