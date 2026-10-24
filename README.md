<p align="center">
  <a href="https://developers.cruworldwine.com">
    <img src="https://uk.cruworldwine.com/skin/frontend/cru/default/images/cru-world-wine-logo.svg" alt="Cru World Wine" width="200">
  </a>
</p>

# Cru Trading API for Python

[![CI](https://github.com/cruworldwine/cru-api-python/actions/workflows/ci.yml/badge.svg)](https://github.com/cruworldwine/cru-api-python/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/cruworldwine.svg)](https://pypi.org/project/cruworldwine/)
[![Python versions](https://img.shields.io/pypi/pyversions/cruworldwine.svg)](https://pypi.org/project/cruworldwine/)
[![License](https://img.shields.io/github/license/cruworldwine/cru-api-python.svg)](https://github.com/cruworldwine/cru-api-python/blob/main/LICENSE)

The Python SDK for the [Cru Trading API](https://developers.cruworldwine.com), Cru World Wine's
partner REST API. Read Cru's live bid and offer books for every wine, manage your own bids and
offers, see your portfolio, purchases and sales, and trade: buy an offer or sell into a bid. It has
a synchronous client, `Cru`, and an asyncio one, `AsyncCru`, with typed models for every answer,
automatic retries and OAuth token refresh, and nothing to install beyond
[httpx](https://www.python-httpx.org).

## Installation

```sh
pip install cruworldwine
```

Python 3.9 or later.

## Connecting

With a partner credential, whose writes run at once:

```python
from cruworldwine import Cru

with Cru(client_key='cru_live_...', client_secret='...', market='uk') as cru:
    client = cru.ping().client
    print(client.organisation, client.market, client.currency, client.scopes)
```

Or with asyncio, here as a connected app acting for a customer, whose writes wait for the
customer to confirm them:

```python
import asyncio

from cruworldwine import AsyncCru


async def main() -> None:
    async with AsyncCru(access_token='...', refresh_token='...', oauth_client_id='...') as cru:
        page = await cru.bids.list(status=['live'])
        async for bid in page:
            print(bid.code, bid.price, bid.quantity)


asyncio.run(main())
```

`Cru()` alone reads `CRU_CLIENT_KEY` and `CRU_CLIENT_SECRET` (or `CRU_ACCESS_TOKEN`) and
`CRU_MARKET` from the environment. [Authentication](docs/authentication.md) covers both ways in.

## Typed models

Every endpoint is a typed method, and every answer a typed model with an attribute per API field
and the API's descriptions as docstrings, so an editor completes and checks them. Fields this
version does not know are kept in `.raw`.

```python
for wine in cru.portfolio.list(is_listed=True).auto_paging_iter():  # PortfolioWine
    for line in wine.portfolio:  # PortfolioLine
        print(wine.wine_name, line.quantity, line.pricing.listing_price, line.pricing.net_proceeds)
```

Import any model from `cruworldwine.models`.

## Documentation

- [Authentication](docs/authentication.md): partner credentials, connected apps and OAuth refresh,
  the environment.
- [Configuration](docs/configuration.md): constructor and per-call options, `with_options()`,
  timeouts, retries, logging, `app_info`.
- [Async](docs/async.md): `AsyncCru`, async paging and concurrency.
- [Pagination](docs/pagination.md): pages, and walking every item.
- [Writes and confirmations](docs/writes-and-confirmations.md): idempotency references, staged
  writes and confirming them.
- [Errors](docs/errors.md): the error classes, what they hold, and request ids.
- [Compatibility](docs/compatibility.md): tolerant models, values that may grow, and the versioning
  policy.
- [Architecture](docs/architecture.md): how the SDK is built, the life of a request, and the code
  generation.
- The API itself: [developers.cruworldwine.com](https://developers.cruworldwine.com).

## Examples

[`examples/`](examples) has scripts to run with credentials in the environment: `portfolio.py`
prints your portfolio, `market.py` the bids and offers on a wine, `place_bid.py` places a bid and,
as a connected app, confirms it, and `async_market.py` asks for several wines at once with
`AsyncCru`.

## Versioning and support

The SDK follows [semantic versioning](https://semver.org). While it is 0.x, a minor release may
change the public API, and every such change is in the [changelog](CHANGELOG.md); patch releases
never do. It supports Python 3.9 to 3.15 on Linux, macOS and Windows, and only the latest minor
release gets fixes. [Compatibility](docs/compatibility.md) has the whole policy.

## Every method

Generated from the spec; each method's docstring has the full description. `AsyncCru` has the
same methods: await them, and a `Page` is an `AsyncPage`.

<!-- sdkgen:methods -->
| Method | Endpoint | Returns |
|---|---|---|
| `cru.ping()` | `GET /ping` | `Ping` |
| `cru.portfolio.list(...)` | `GET /portfolio` | `Page[PortfolioWine]` |
| `cru.offers.list(...)` | `GET /offers` | `Page[PortfolioWine]` |
| `cru.offers.create(...)` | `POST /offers` | `Write[OfferResult]` |
| `cru.offers.get(code)` | `GET /offers/{code}` | `PortfolioWine` |
| `cru.offers.update(code, ...)` | `PATCH /offers/{code}` | `Write[OfferResult]` |
| `cru.offers.remove(code, ...)` | `DELETE /offers/{code}` | `Write[OfferRemoveResult]` |
| `cru.bids.list(...)` | `GET /bids` | `Page[OwnBid]` |
| `cru.bids.place(...)` | `POST /bids` | `Write[BidResult]` |
| `cru.bids.get(code)` | `GET /bids/{code}` | `OwnBid` |
| `cru.bids.update(code, ...)` | `PATCH /bids/{code}` | `Write[BidResult]` |
| `cru.bids.cancel(code, ...)` | `DELETE /bids/{code}` | `Write[BidResult]` |
| `cru.bids.renew(code, ...)` | `POST /bids/{code}/renew` | `Write[BidResult]` |
| `cru.market.list(...)` | `GET /market` | `Page[MarketWine]` |
| `cru.market.get_wine(lwin18, ...)` | `GET /market/wines/{lwin18}` | `MarketWine` |
| `cru.market.list_bids(...)` | `GET /market/bids` | `Page[MarketWine]` |
| `cru.market.get_bid(code)` | `GET /market/bids/{code}` | `MarketBidDetail` |
| `cru.market.get_wine_bids(lwin18, ...)` | `GET /market/wines/{lwin18}/bids` | `MarketWine` |
| `cru.market.list_offers(...)` | `GET /market/offers` | `Page[MarketWine]` |
| `cru.market.get_offer(code)` | `GET /market/offers/{code}` | `MarketOfferDetail` |
| `cru.market.get_wine_offers(lwin18, ...)` | `GET /market/wines/{lwin18}/offers` | `MarketWine` |
| `cru.market.buy_offer(code, ...)` | `POST /market/offers/{code}/buy` | `Write[BuyResult]` |
| `cru.market.sell_to_bid(code, ...)` | `POST /market/bids/{code}/sell` | `Write[SellResult]` |
| `cru.wines.search(...)` | `GET /wines` | `Page[Wine]` |
| `cru.wines.get(lwin18)` | `GET /wines/{lwin18}` | `WineDetail` |
| `cru.trades.list_purchases(...)` | `GET /trades/purchases` | `Page[Purchase]` |
| `cru.trades.list_sales(...)` | `GET /trades/sales` | `Page[Sale]` |
| `cru.warehouses.list()` | `GET /warehouses` | `list[Warehouse]` |
| `cru.warehouses.get(code)` | `GET /warehouses/{code}` | `Warehouse` |
| `cru.inbond_warehouses.list()` | `GET /warehouses/inbond` | `list[InbondWarehouse]` |
| `cru.inbond_warehouses.suggest(...)` | `POST /warehouses/inbond` | `Write[InbondWarehouseResult]` |
| `cru.inbond_warehouses.get(id)` | `GET /warehouses/inbond/{id}` | `InbondWarehouse` |
| `cru.inbond_addresses.list()` | `GET /addresses/inbond` | `list[InbondAddress]` |
| `cru.inbond_addresses.add(...)` | `POST /addresses/inbond` | `Write[InbondAddressResult]` |
| `cru.inbond_addresses.remove(id, ...)` | `DELETE /addresses/inbond/{id}` | `Write[InbondAddressResult]` |
| `cru.confirmations.get(code)` | `GET /confirmations/{code}` | `Confirmation` |
| `cru.confirmations.confirm(code)` | `POST /confirmations/{code}` | `Write[Any]` |
| `cru.confirmations.cancel(code)` | `DELETE /confirmations/{code}` | `None` |
| `cru.photos.get(id)` | `GET /photos/{id}` | `bytes` |
<!-- /sdkgen:methods -->

## Contributing, security and licence

[CONTRIBUTING.md](CONTRIBUTING.md) explains the layout, the Makefile and how releases are cut.
Report a vulnerability privately, as [SECURITY.md](SECURITY.md) explains, never in a public issue.
Apache License 2.0; see [LICENSE](LICENSE).
