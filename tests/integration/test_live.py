"""A read-only smoke test against the live API, with Cru and with AsyncCru.

Skipped unless CRU_LIVE=1. Credentials come from the environment, as for Cru(): CRU_CLIENT_KEY and
CRU_CLIENT_SECRET, or CRU_ACCESS_TOKEN, with CRU_MARKET or CRU_BASE_URL to choose the host. It only
reads: ping, the warehouses and one small page of the market. It never writes.
"""

import asyncio
import os

import pytest

import cruworldwine
from cruworldwine import AsyncCru, Cru, PermissionDeniedError

pytestmark = pytest.mark.skipif(
    os.environ.get('CRU_LIVE') != '1',
    reason='set CRU_LIVE=1 and credentials in the environment to call the live API',
)

APP = ('cruworldwine-live-test', cruworldwine.__version__, None)


def check_ping(ping):
    assert ping.pong is True
    assert ping._request_id
    assert ping.client.market
    assert ping.client.currency


def check_warehouses(warehouses):
    assert isinstance(warehouses, list)
    assert all(w.code for w in warehouses)


def check_market(page):
    assert page.request_id
    assert len(page.items) <= 2
    for wine in page.items:
        assert wine.lwin18
        assert isinstance(wine.bids or [], list)
        assert isinstance(wine.offers or [], list)


def test_live_read_only_sync():
    with Cru(app_info=APP) as cru:
        check_ping(cru.ping())
        try:
            check_warehouses(cru.warehouses.list())
            check_market(cru.market.list(limit=2, depth=1))
        except PermissionDeniedError as e:
            pytest.skip(f'the credential lacks a scope this test reads with: {e.code} {e.details}')


def test_live_read_only_async():
    async def main():
        async with AsyncCru(app_info=APP) as cru:
            ping, warehouses, market = await asyncio.gather(
                cru.ping(), cru.warehouses.list(), cru.market.list(limit=2, depth=1)
            )
        check_ping(ping)
        check_warehouses(warehouses)
        check_market(market)

    try:
        asyncio.run(main())
    except PermissionDeniedError as e:
        pytest.skip(f'the credential lacks a scope this test reads with: {e.code} {e.details}')
