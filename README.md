<p align="center">
  <a href="https://developers.cruworldwine.com">
    <img src="https://uk.cruworldwine.com/skin/frontend/cru/default/images/cru-world-wine-logo.svg" alt="Cru World Wine" width="200">
  </a>
</p>

# Cru Trading API for Python

[![CI](https://github.com/cruworldwine/cru-api-python/actions/workflows/ci.yml/badge.svg)](https://github.com/cruworldwine/cru-api-python/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/cruworldwine.svg)](https://pypi.org/project/cruworldwine/)
[![Python versions](https://img.shields.io/pypi/pyversions/cruworldwine.svg)](https://pypi.org/project/cruworldwine/)

The Python SDK for the [Cru Trading API](https://developers.cruworldwine.com), Cru World Wine's
partner REST API. Read Cru's live bid and offer books for every wine, manage your own bids and
offers, see your portfolio, purchases and sales, and trade: buy an offer or sell into a bid.

## Installation

```sh
pip install cruworldwine
```

Python 3.9 or later. The only dependency is [httpx](https://www.python-httpx.org).

## Connecting

There are two ways to connect. Each answers on one market's host,
`https://{market}.cruworldwine.com/api/v1`, where market is `uk` (the default), `us`, `hk`, `sg`,
`eu`, `ae` or `cn`. A credential works on its own market only.

### With a partner credential

Cru issues a partner credential: a key (`cru_live_...`) and a secret, which is shown once. Keep
both out of source control. A partner credential's writes run at once.

```python
from cruworldwine import Cru

cru = Cru(client_key='cru_live_...', client_secret='...', market='uk')
```

### As a connected app (OAuth 2.0)

An app that acts for a Cru customer gets their tokens with the OAuth 2.0 authorization code flow
with PKCE (S256), at `/api/oauth/authorize` and `/api/oauth/token` on the market's host. The SDK
uses the access token and, given the refresh token and your app's client id, refreshes it once when
it expires. A refresh token works once, so store the new tokens `on_token_refresh` hands you. A
connected app's writes are staged: nothing happens until the customer confirms them.

```python
cru = Cru(
    access_token=tokens['access_token'],
    refresh_token=tokens['refresh_token'],
    oauth_client_id='your-client-id',
    on_token_refresh=save_tokens,
)
```

Refreshes are serialised: when many threads or tasks share a client and its token expires, one of
them refreshes it and the others carry on with the new token.

### From the environment

Anything not given is read from `CRU_CLIENT_KEY`, `CRU_CLIENT_SECRET`, `CRU_ACCESS_TOKEN`,
`CRU_MARKET` and `CRU_BASE_URL`, so `Cru()` alone works when they are set. Other options:
`base_url`, `timeout` (seconds or an `httpx.Timeout`, default 30), `max_retries` (default 2),
`http_client` (your own `httpx.Client`, for proxies, certificates or connection limits) and
`app_info`.

If you build an integration others use, name it with `app_info`. It is added to the User-Agent
header, after the SDK's own `cruworldwine-python/<version> Python/<version> (<os>; <machine>)`, so
Cru can tell integrations apart when helping you:

```python
cru = Cru(app_info=('cellar-sync', '2.3.0', 'https://cellar-sync.example'))
```

### Check the connection

```python
client = cru.ping().client
print(client.organisation, client.market, client.currency, client.scopes, client.expires_at)
```

## Typed models

Every endpoint is a typed method, and every answer is a typed model: a class per API object, with
an attribute per API field and the API's descriptions as its docstring, so an editor completes
and checks them. Attributes that can be null are `Optional`. The package ships `py.typed` and is
checked with mypy in strict mode.

```python
for wine in cru.portfolio.list(is_listed=True).auto_paging_iter():  # PortfolioWine
    for line in wine.portfolio:  # PortfolioLine
        print(wine.wine_name, line.quantity, line.pricing.listing_price, line.pricing.net_proceeds)
```

Each resource has a module of methods in `cruworldwine/resources/` and a module of the models it
returns in `cruworldwine/models/`. For example, `models/portfolio.py` has `PortfolioWine`,
`PortfolioLine`, `LinePricing` and `LineWarehouse`, and `resources/portfolio.py` the
`cru.portfolio` methods that return them. Import any model from `cruworldwine.models`.

[`examples/`](examples) has scripts to run: `portfolio.py` prints your portfolio, `market.py` the
bids and offers on a wine, `place_bid.py` places a bid and, as a connected app, confirms it, and
`async_market.py` asks for several wines at once with `AsyncCru`.

## Reading

```python
for wine in cru.market.list_bids(lwin=['101174520151200750']).auto_paging_iter():
    for bid in wine.bids:
        print(wine.wine_name, bid.price, bid.quantity)

page = cru.portfolio.list(stock_type=['cru'], is_listed=False, limit=50)
print(page.total, page.has_more)
```

Every endpoint is a method on a resource of the client: `cru.market`, `cru.wines`, `cru.bids`,
`cru.offers`, `cru.portfolio`, `cru.trades`, `cru.warehouses`, `cru.inbond_warehouses`,
`cru.inbond_addresses`, `cru.photos` and `cru.confirmations`; `cru.ping()` is on the client.
[Every method](#every-method) lists them all. Lists return a `Page`: iterate it for its items,
call `next_page()`, or `auto_paging_iter()` for every item of every page.

## Writing

```python
write = cru.bids.place(lwin18='101174520151200750', quantity=6, price=1450)
if write.staged:  # a connected app: nothing has happened yet
    print(write.confirmation.preview.summary)
    write = cru.confirmations.confirm(write.confirmation.code)
print(write.result.bid.status)
```

A partner write needs a `reference`, its idempotency key. The SDK makes one when you do not pass
it and keeps it across its own retries, so a retry can never act twice. Pass your own to retry
safely across restarts.

## Async usage

`AsyncCru` takes the same arguments as `Cru` and has the same resources and methods, each a
coroutine. It runs on `httpx.AsyncClient` with asyncio. Lists return an `AsyncPage`: `async for`
walks every item of every page, `await page.next_page()` fetches the next one, and a plain `for`
iterates the page in hand.

```python
import asyncio

from cruworldwine import AsyncCru


async def main(lwins: list[str]) -> None:
    async with AsyncCru() as cru:
        page = await cru.bids.list(status=['live'])
        async for bid in page:
            print(bid.code, bid.price)
        wines = await asyncio.gather(*(cru.market.get_wine(lwin18) for lwin18 in lwins))
        print([wine.wine_name for wine in wines])


asyncio.run(main(['101174520151200750']))
```

Use it as an async context manager, or call `await cru.aclose()` when done. `on_token_refresh`
may be a coroutine function. Retries, errors, models, references and refreshes behave exactly as
they do with `Cru`.

## Errors

Every error is a `CruError`. The API's are `APIStatusError` subclasses by status
(`NotFoundError`, `UnprocessableEntityError`, `PriceChangedError`, ...), with `status_code`,
`code`, `message`, `field`, `details`, `errors`, `headers` and `request_id`. A connection failure is
an `APIConnectionError`, and a timeout an `APITimeoutError`.

```python
from cruworldwine import PriceChangedError, UnprocessableEntityError

try:
    cru.market.buy_offer('CS-12345', quantity=1, max_price=1500)
except PriceChangedError:
    ...  # preview again
except UnprocessableEntityError as e:
    print(e.code, e.field, e.message, e.request_id)
```

Reads and partner writes are retried on connection errors, timeouts, 429 and 5xx (`max_retries=2`),
with exponential back-off and jitter, honouring `Retry-After` in seconds or as an HTTP date, never
waiting more than 30 seconds. A connected app's write is staged, not carried out, and is never
retried. Redirects are never followed, so your credentials never reach another host.

## Per-call options

Every method also takes `extra_headers`, `extra_query`, `extra_body` (writes), `timeout` and
`max_retries`, for that call only:

```python
bids = cru.bids.list(timeout=5, max_retries=0, extra_headers={'X-Trace-Id': trace_id})
```

`with_options()` returns a copy of the client with another `timeout` or `max_retries`. The copy
shares the original's connection pool and credentials, OAuth tokens included, so it is cheap:

```python
patient = cru.with_options(timeout=120, max_retries=5)
patient.trades.list_sales(limit=500)
```

## Request ids

Cru support finds a request by its id. Every error has `request_id`, and so does every answer:

```python
page = cru.bids.list()
print(page.request_id)  # a Page, and a Write, have request_id
bid = cru.bids.get('CB-1001')
print(bid._request_id)  # a model has _request_id
```

A model's attributes are the API's fields, and the API has fields named `request_id` (the response
envelope's `meta` has one), so on a model it is `_request_id`, a name no API field can take. It is
set on the model a method returns, and on each item of a list or page. `Page` and `Write` are the
SDK's own, so they have `request_id`, and `_request_id` as well, so every answer reads the same way.

## Logging and debugging

The SDK logs to the `cruworldwine` logger: every attempt at DEBUG (method, path, status, attempt,
time taken and request id) and every retry and token refresh at INFO. Configure it as you would any
logger, or set `CRU_LOG=debug` (or `info`) to print it to stderr:

```sh
CRU_LOG=debug python examples/portfolio.py
```

Logs never hold your client key or secret, access or refresh tokens, or request and response
bodies. Neither do `repr(client)` or any error's message.

## Built for an API that changes

The API grows. Fields this version does not know are kept: every model has `.raw`, and
`model['new_field']` reads one. Values listed as "more may be added" are plain strings. Every
method takes `extra_query` (and writes `extra_body`) for a parameter this version does not know,
and for an endpoint it does not have, `cru.request('GET', '/new/path', query={...})` returns the
envelope.

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

## Versioning and support

The SDK follows [semantic versioning](https://semver.org). While it is 0.x, a minor release
(0.1 to 0.2) may change the public API, and every such change is listed in the
[changelog](CHANGELOG.md); patch releases never do. Names that start with an underscore, other than
`_request_id`, are internal and may change in any release.

It supports every Python version its CI tests, currently 3.9 to 3.15, on Linux, macOS and Windows.
Support for a Python version that has reached its end of life may be dropped in a minor release,
with a changelog entry. Only the latest minor release gets fixes, security fixes included.

## Development

`cruworldwine/models/`, `cruworldwine/resources/` and the method table above are generated from
the OpenAPI spec (`spec/openapi.yaml` is the copy they were generated from); each generated file
starts with `DO NOT EDIT`. The rest is written by hand. [CONTRIBUTING.md](CONTRIBUTING.md) explains
how to set up, test, lint, type-check, build and release.

The tests need no credentials and make no network calls: every call goes through a mocked
transport.

```sh
uv run pytest
```

## Security

Report a vulnerability privately, as [SECURITY.md](SECURITY.md) explains, never in a public issue.

## License

Apache License 2.0. See [LICENSE](LICENSE).
