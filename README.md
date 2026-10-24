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
Lists return a `Page`: iterate it for its items, call `next_page()`, or `auto_paging_iter()` for
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

`models.py` and `_resources.py` are generated from the OpenAPI spec (`spec/openapi.yaml` is the
copy they were generated from); do not edit them. Cru regenerates them from the API's own
repository after each API change:

```sh
uv run --quiet --with pyyaml==6.0.3 python docs/api/tools/sdkgen/generate.py --python <this checkout>
```

## License

Apache License 2.0. See [LICENSE](LICENSE).
