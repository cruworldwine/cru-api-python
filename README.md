<p align="center">
  <a href="https://developers.cruworldwine.com">
    <img src="https://uk.cruworldwine.com/skin/frontend/cru/default/images/cru-world-wine-logo.svg" alt="Cru World Wine" width="200">
  </a>
</p>

# Cru Trading API for Python

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

cru = Cru(client_key="cru_live_...", client_secret="...", market="uk")
```

### As a connected app (OAuth 2.0)

An app that acts for a Cru customer gets their tokens with the OAuth 2.0 authorization code flow
with PKCE (S256), at `/api/oauth/authorize` and `/api/oauth/token` on the market's host. The SDK
uses the access token and, given the refresh token and your app's client id, refreshes it once when
it expires. A refresh token works once, so store the new tokens `on_token_refresh` hands you. A
connected app's writes are staged: nothing happens until the customer confirms them.

```python
cru = Cru(
    access_token=tokens["access_token"],
    refresh_token=tokens["refresh_token"],
    oauth_client_id="your-client-id",
    on_token_refresh=save_tokens,
)
```

### From the environment

Anything not given is read from `CRU_CLIENT_KEY`, `CRU_CLIENT_SECRET`, `CRU_ACCESS_TOKEN`,
`CRU_MARKET` and `CRU_BASE_URL`, so `Cru()` alone works when they are set. Other options:
`base_url`, `timeout` (seconds, default 30), `max_retries` (default 2) and `http_client`.

### Check the connection

```python
client = cru.ping().client
print(client.organisation, client.market, client.currency, client.scopes, client.expires_at)
```

## Typed models

Every endpoint is a typed method, and every answer is a typed model: a class per API object, with
an attribute per API field and the API's descriptions as its docstring, so an editor completes
and checks them. Attributes that can be null are `Optional`.

```python
for wine in cru.portfolio.list(is_listed=True).auto_paging_iter():  # PortfolioWine
    for line in wine.portfolio:                                    # PortfolioLine
        print(wine.wine_name, line.quantity, line.stock_type,
              line.pricing.listing_price, line.pricing.net_proceeds, wine.currency)
```

Each resource has a module of methods in `cruworldwine/resources/` and a module of the models it
returns in `cruworldwine/models/`. For example, `models/portfolio.py` has `PortfolioWine`,
`PortfolioLine`, `LinePricing` and `LineWarehouse`, and `resources/portfolio.py` the
`cru.portfolio` methods that return them. Import any model from `cruworldwine.models`.

[`examples/`](examples) has scripts to run: `portfolio.py` prints your portfolio, `market.py` the
bids and offers on a wine, and `place_bid.py` places a bid and, as a connected app, confirms it.

## Reading

```python
for wine in cru.market.list_bids(lwin=["101174520151200750"]).auto_paging_iter():
    for bid in wine.bids:
        print(wine.wine_name, bid.price, bid.quantity)

page = cru.portfolio.list(stock_type=["cru"], is_listed=False, limit=50)
print(page.total, page.has_more)
```

Every endpoint is a method on a resource of the client: `cru.market`, `cru.wines`, `cru.bids`,
`cru.offers`, `cru.portfolio`, `cru.trades`, `cru.warehouses`, `cru.inbond_warehouses`,
`cru.inbond_addresses`, `cru.photos` and `cru.confirmations`; `cru.ping()` is on the client.
[Every method](#every-method) lists them all. Lists return a `Page`: iterate it for its items, call `next_page()`, or `auto_paging_iter()` for
every item of every page.

## Writing

```python
write = cru.bids.place(lwin18="101174520151200750", quantity=6, price=1450)
if write.staged:                       # a connected app: nothing has happened yet
    print(write.confirmation.preview.summary)
    write = cru.confirmations.confirm(write.confirmation.code)
print(write.result.bid.status)
```

A partner write needs a `reference`, its idempotency key. The SDK makes one when you do not pass
it and keeps it across its own retries, so a retry can never act twice. Pass your own to retry
safely across restarts.

## Errors

Every error is a `CruError`. The API's are `APIStatusError` subclasses by status
(`NotFoundError`, `UnprocessableEntityError`, `PriceChangedError`, ...), with `code`, `message`,
`field`, `details`, `errors` and `request_id`.

```python
from cruworldwine import PriceChangedError, UnprocessableEntityError

try:
    cru.market.buy_offer("CS-12345", quantity=1, max_price=1500)
except PriceChangedError:
    ...  # preview again
except UnprocessableEntityError as e:
    print(e.code, e.field, e.message)
```

Reads and partner writes are retried on connection errors, 429 and 5xx (`max_retries=2`), honouring
`Retry-After`. Redirects are never followed, so your credentials never reach another host.

## Built for an API that changes

The API grows. Fields this version does not know are kept: every model has `.raw`, and
`model["new_field"]` reads one. Values listed as "more may be added" are plain strings. Every
method takes `extra_query` (and writes `extra_body`) for a parameter this version does not know,
and for an endpoint it does not have, `cru.request("GET", "/new/path", query={...})` returns the
envelope.

## Every method

Generated from the spec; each method's docstring has the full description.

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
| `cru.warehouses.list()` | `GET /warehouses` | `List[Warehouse]` |
| `cru.warehouses.get(code)` | `GET /warehouses/{code}` | `Warehouse` |
| `cru.inbond_warehouses.list()` | `GET /warehouses/inbond` | `List[InbondWarehouse]` |
| `cru.inbond_warehouses.suggest(...)` | `POST /warehouses/inbond` | `Write[InbondWarehouseResult]` |
| `cru.inbond_warehouses.get(id)` | `GET /warehouses/inbond/{id}` | `InbondWarehouse` |
| `cru.inbond_addresses.list()` | `GET /addresses/inbond` | `List[InbondAddress]` |
| `cru.inbond_addresses.add(...)` | `POST /addresses/inbond` | `Write[InbondAddressResult]` |
| `cru.inbond_addresses.remove(id, ...)` | `DELETE /addresses/inbond/{id}` | `Write[InbondAddressResult]` |
| `cru.confirmations.get(code)` | `GET /confirmations/{code}` | `Confirmation` |
| `cru.confirmations.confirm(code)` | `POST /confirmations/{code}` | `Write[Any]` |
| `cru.confirmations.cancel(code)` | `DELETE /confirmations/{code}` | `None` |
| `cru.photos.get(id)` | `GET /photos/{id}` | `bytes` |
<!-- /sdkgen:methods -->

## Running the tests

The tests need no credentials and make no network calls: every call goes through a mocked
transport.

```sh
uv run --with httpx --with pytest --with-editable . pytest
```

- `tests/test_client.py`: authentication, the environment, query and path encoding, references
  kept across retries, retries and back-off, the OAuth refresh, every error class, staged writes
  and confirmations, paging, and fields and values this version does not know.
- `tests/test_replay.py`: replays real API answers through the method that asks for each one and
  checks every typed field against what the API sent. It runs when `CRU_CAPTURES` names a capture
  run, and is skipped otherwise. Captures hold customer data, so keep them out of the repository.

## Development

`cruworldwine/models/`, `cruworldwine/resources/` and the method table above are generated from
the OpenAPI spec (`spec/openapi.yaml` is the copy they were generated from); each generated file
starts with `DO NOT EDIT`. The rest is written by hand. Cru regenerates them from the API's own
repository after each API change:

```sh
uv run --quiet --with pyyaml==6.0.3 python docs/api/tools/sdkgen/generate.py --python <this checkout>
```

## License

Apache License 2.0. See [LICENSE](LICENSE).
