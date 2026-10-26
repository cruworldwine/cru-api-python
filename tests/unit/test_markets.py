"""Environments and markets: the sandbox, MARKETS, lookup_market() and market_info, on Cru and AsyncCru."""

import dataclasses
import inspect

import pytest

import cruworldwine
from cruworldwine import MARKETS, MarketInfo, lookup_market
from tests.helpers import envelope, partner

PONG = {'pong': True, 'client': {}}
LOCAL = 'http://localhost:8080/api/v1'


def ping_url(mock, kind, run, **kwargs):
    mock.add(200, envelope(PONG))
    run(partner(mock, kind, **kwargs).ping())
    return str(mock.requests[-1].url)


def test_live_and_uk_are_the_defaults(mock, kind, run):
    assert ping_url(mock, kind, run) == 'https://uk.cruworldwine.com/api/v1/ping'


@pytest.mark.parametrize(
    ('kwargs', 'url'),
    [
        ({'environment': 'sandbox'}, 'https://uk.crusandbox.com/api/v1/ping'),
        ({'environment': 'sandbox', 'market': 'hk'}, 'https://hk.crusandbox.com/api/v1/ping'),
        ({'environment': ' SandBox ', 'market': 'HK'}, 'https://hk.crusandbox.com/api/v1/ping'),
        ({'environment': 'LIVE', 'market': 'sg'}, 'https://sg.cruworldwine.com/api/v1/ping'),
        ({'environment': 'sandbox', 'market': 'fr'}, 'https://fr.crusandbox.com/api/v1/ping'),
    ],
)
def test_environment_and_market_make_the_host(mock, kind, run, kwargs, url):
    assert ping_url(mock, kind, run, **kwargs) == url


def test_environment_from_env(mock, kind, run, monkeypatch):
    monkeypatch.setenv('CRU_ENVIRONMENT', 'Sandbox')
    monkeypatch.setenv('CRU_MARKET', 'eu')
    assert ping_url(mock, kind, run) == 'https://eu.crusandbox.com/api/v1/ping'


def test_environment_option_wins_over_env(mock, kind, run, monkeypatch):
    monkeypatch.setenv('CRU_ENVIRONMENT', 'sandbox')
    assert ping_url(mock, kind, run, environment='live') == 'https://uk.cruworldwine.com/api/v1/ping'


@pytest.mark.parametrize(
    'kwargs',
    [
        {'base_url': LOCAL},
        {'base_url': LOCAL, 'environment': 'sandbox', 'market': 'hk'},
        {'base_url': LOCAL + '/', 'environment': 'live'},
    ],
)
def test_base_url_wins_over_environment(mock, kind, run, monkeypatch, kwargs):
    monkeypatch.setenv('CRU_ENVIRONMENT', 'sandbox')
    assert ping_url(mock, kind, run, **kwargs) == LOCAL + '/ping'


def test_env_base_url_wins_over_environment(mock, kind, run, monkeypatch):
    monkeypatch.setenv('CRU_BASE_URL', LOCAL)
    assert ping_url(mock, kind, run, environment='sandbox') == LOCAL + '/ping'


@pytest.mark.parametrize('cls', [cruworldwine.Cru, cruworldwine.AsyncCru])
@pytest.mark.parametrize('environment', ['production', 'test', 'staging', 'live-ish', 1])
def test_other_environments_are_refused(cls, environment):
    with pytest.raises(cruworldwine.CruError, match='environment must be live or sandbox, not '):
        cls(client_key='k', client_secret='s', environment=environment)


@pytest.mark.parametrize('cls', [cruworldwine.Cru, cruworldwine.AsyncCru])
def test_other_environments_from_env_are_refused_even_with_a_base_url(cls, monkeypatch):
    monkeypatch.setenv('CRU_ENVIRONMENT', 'prod')
    with pytest.raises(cruworldwine.CruError, match='environment must be live or sandbox'):
        cls(client_key='k', client_secret='s', base_url=LOCAL)


@pytest.mark.parametrize('cls', [cruworldwine.Cru, cruworldwine.AsyncCru])
def test_environment_is_a_keyword_option(cls):
    parameter = inspect.signature(cls).parameters['environment']
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is None


def test_markets_in_the_api_order():
    assert list(MARKETS) == ['uk', 'us', 'hk', 'sg', 'eu', 'ae', 'cn']
    assert MARKETS['uk'] == MarketInfo(
        'uk', 'United Kingdom', 'GBP', '£', 'https://uk.cruworldwine.com/api/v1', 'https://uk.crusandbox.com/api/v1'
    )
    assert (MARKETS['us'].currency, MARKETS['hk'].currency, MARKETS['eu'].symbol) == ('USD', 'HKD', '€')
    for code, info in MARKETS.items():
        assert info.code == code
        assert info.live_url == f'https://{code}.cruworldwine.com/api/v1'
        assert info.sandbox_url == f'https://{code}.crusandbox.com/api/v1'


def test_markets_are_read_only():
    with pytest.raises(TypeError):
        MARKETS['fr'] = MARKETS['uk']
    with pytest.raises(TypeError):
        del MARKETS['uk']
    with pytest.raises(dataclasses.FrozenInstanceError):
        MARKETS['uk'].currency = 'EUR'
    assert 'fr' not in MARKETS


@pytest.mark.parametrize(
    ('code', 'expected'),
    [('hk', 'hk'), ('HK', 'hk'), (' Ae ', 'ae'), ('CN', 'cn'), ('fr', None), ('', None), ('u k', None)],
)
def test_lookup_market(code, expected):
    assert lookup_market(code) is (MARKETS[expected] if expected else None)


def test_lookup_market_takes_only_a_string():
    assert lookup_market(None) is None


def test_market_url_by_environment():
    hk = MARKETS['hk']
    assert hk.url('live') == 'https://hk.cruworldwine.com/api/v1'
    assert hk.url('SANDBOX') == 'https://hk.crusandbox.com/api/v1'
    with pytest.raises(cruworldwine.CruError, match="environment must be live or sandbox, not 'staging'"):
        hk.url('staging')


@pytest.mark.parametrize(
    ('kwargs', 'env', 'code'),
    [
        # No base URL: the market the client was made for.
        ({}, {}, 'uk'),
        ({'market': ' HK '}, {}, 'hk'),
        ({}, {'CRU_MARKET': 'sg'}, 'sg'),
        ({'environment': 'sandbox', 'market': 'ae'}, {}, 'ae'),
        ({'market': 'fr'}, {}, None),
        # A Cru host: its first label, whatever market was given.
        ({'base_url': 'https://hk.crusandbox.com/api/v1'}, {}, 'hk'),
        ({'base_url': 'https://EU.CruWorldWine.com:443/api/v1', 'market': 'uk'}, {}, 'eu'),
        ({}, {'CRU_BASE_URL': 'https://us.cruworldwine.com/api/v1', 'CRU_MARKET': 'uk'}, 'us'),
        ({'base_url': 'https://fr.crusandbox.com/api/v1', 'market': 'uk'}, {}, None),
        # Any other host: the market given, else none.
        ({'base_url': LOCAL, 'market': 'US'}, {}, 'us'),
        ({'base_url': LOCAL}, {'CRU_MARKET': 'cn'}, 'cn'),
        ({'base_url': 'https://uk.example.test/api/v1'}, {}, None),
        ({'base_url': 'https://a.uk.cruworldwine.com/api/v1', 'market': 'sg'}, {}, 'sg'),
        ({'base_url': LOCAL, 'market': 'fr'}, {}, None),
        ({'base_url': LOCAL}, {}, None),
    ],
)
def test_market_info(mock, kind, monkeypatch, kwargs, env, code):
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    cru = partner(mock, kind, **kwargs)
    assert cru.market_info is (MARKETS[code] if code else None)
    assert cru.with_options(timeout=1).market_info is cru.market_info
    assert mock.requests == []
