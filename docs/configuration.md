# Configuration

Everything a client can be told, which host it calls, how long it waits, when it retries, and how
to see what it does. `Cru` and `AsyncCru` take the same options.

## Constructor options

| Option | Default | What it does |
|---|---|---|
| `client_key`, `client_secret` | `CRU_CLIENT_KEY`, `CRU_CLIENT_SECRET` | A partner credential. See [Authentication](authentication.md). |
| `access_token` | `CRU_ACCESS_TOKEN` | A connected app's OAuth access token. |
| `refresh_token`, `oauth_client_id`, `oauth_client_secret` | none | What the SDK needs to refresh an expired access token. |
| `on_token_refresh` | none | Called with the new tokens after each refresh; store them. |
| `market` | `CRU_MARKET`, else `uk` | The market whose host to call: `uk`, `us`, `hk`, `sg`, `eu`, `ae` or `cn`. |
| `environment` | `CRU_ENVIRONMENT`, else `live` | `live` or `sandbox`, in any case. See [The sandbox](#the-sandbox). |
| `base_url` | `CRU_BASE_URL`, else the market's in the environment | The API's base URL, in place of the market's and the environment's, for a server of your own. |
| `timeout` | 30 seconds | Seconds, or an `httpx.Timeout`. See [Timeouts](#timeouts). |
| `max_retries` | 2 | Retries after the first attempt. See [Retries](#retries). |
| `http_client` | a new one | Your own `httpx.Client` (`httpx.AsyncClient` for `AsyncCru`). |
| `app_info` | none | `(name, version, url)` of your application, for the User-Agent. |

## The sandbox

Cru's sandbox has the same API and the same markets as live, at
`https://{market}.crusandbox.com/api/v1`, with credentials issued for the sandbox, and no real
money or wine changes hands there. Pass `environment='sandbox'`, or set `CRU_ENVIRONMENT=sandbox`:

```python
cru = Cru(client_key='...', client_secret='...', environment='sandbox', market='hk')
cru.base_url  # 'https://hk.crusandbox.com/api/v1'
```

There, `cru.ping().client.environment` is `test`, and a connected app's tokens are refreshed on the
sandbox's host. Any other value of `environment` raises `CruError` when the client is made, and a
`base_url` wins over both `market` and `environment`.

## Markets

`MARKETS` is every market this version of the SDK knows, in the API's order, by code; each is a
`MarketInfo` with its `code`, `name`, the `currency` every amount on its host is in, the `symbol`
Cru's website shows for it, and its `live_url` and `sandbox_url`. `lookup_market()` finds one by
code, in any case, and returns `None` for a code it does not know. A market code the SDK does not
know still makes a host, so a new market needs no new release.

```python
from cruworldwine import MARKETS, lookup_market

[m.code for m in MARKETS.values()]  # ['uk', 'us', 'hk', 'sg', 'eu', 'ae', 'cn']
lookup_market('HK').currency  # 'HKD'
MARKETS['sg'].url('sandbox')  # 'https://sg.crusandbox.com/api/v1'
```

`cru.market_info` is the client's own market, or `None`:

- with no `base_url`, the market the client was made for: `market`, else `CRU_MARKET`, else `uk`;
- with a `base_url` on a Cru host, such as `https://hk.crusandbox.com/api/v1`, that host's market;
- with any other `base_url`, the `market` (or `CRU_MARKET`) given, else `None`;
- `None` too when that market is not in `MARKETS`.

(`cru.market` is the market data resource: the bid and offer books.)

## Per-call options

Every method also takes these, for that call only:

| Option | What it does |
|---|---|
| `extra_headers` | Headers to add to, or replace, the SDK's own. |
| `extra_query` | Query parameters this version of the SDK does not know yet, sent as given. |
| `extra_body` | Body fields this version does not know yet (writes only), sent as given, `None` as JSON null. |
| `timeout` | Seconds, or an `httpx.Timeout`. `None` keeps the client's. |
| `max_retries` | Retries after the first attempt. `None` keeps the client's. |

```python
bids = cru.bids.list(timeout=5, max_retries=0, extra_headers={'X-Trace-Id': trace_id})
```

When a list is paged, the next pages are asked for with the same options.

## with_options()

`with_options()` returns a copy of the client with another `timeout` or `max_retries`. The copy
shares the original's connection pool and credentials, OAuth tokens included, so it is cheap to
make one where a part of your code needs different limits:

```python
patient = cru.with_options(timeout=120, max_retries=5)
patient.trades.list_sales(limit=500)
```

Closing either the copy or the original closes the shared pool, so close the original once, when
your application is done with it.

## Timeouts

The default is 30 seconds for each phase of a request (connecting, writing, reading, waiting for a
connection from the pool). Set it for a client, for a copy with `with_options()`, or for one call.
A number is seconds; an `httpx.Timeout` sets each phase on its own:

```python
import httpx

cru = Cru(timeout=httpx.Timeout(60.0, connect=5.0))
```

`None` always means "keep the default" (the client's, or for a client 30 seconds). To wait
forever, which is rarely wise, pass `httpx.Timeout(None)`. When you give your own `http_client`
and no `timeout`, the SDK uses the timeout you gave that client, or 30 seconds if you gave it none.

A request that times out raises `APITimeoutError`, after the retries below.

## Retries

The SDK retries a request when the connection fails or times out, on 429 and on 500, 502, 503 and
504, and on 409 `REQUEST_IN_PROGRESS` (an earlier request with the same reference is still running).
It retries `max_retries` times, 2 unless you say otherwise.

- **What is retried:** every read, and a partner credential's writes, which carry a `reference`
  the SDK keeps across its retries so a retry can never act twice. A connected app's write is only
  staged and has no reference, so it is never retried.
- **How long it waits:** what the API asks for first (its `details.retry_after`, then the
  `Retry-After` header, in seconds or as an HTTP date), otherwise exponential back-off from half a
  second with jitter. It never waits more than 30 seconds.
- **What is not retried:** any other 4xx, and redirects, which are never followed.

`max_retries=0` turns retries off, for a client or for one call.

## Your own httpx client

Pass `http_client` to configure what httpx does: proxies, certificates, connection limits or
transports.

```python
import httpx

cru = Cru(http_client=httpx.Client(proxy='http://proxy.internal:3128', verify='/etc/ssl/corp.pem'))
```

Whatever the client is set to do, the SDK never follows redirects. Closing the Cru client closes
the httpx client too.

## Logging

The SDK logs to the `cruworldwine` logger:

- every attempt at DEBUG: method, path, status, attempt, time taken and request id;
- every retry and every token refresh at INFO.

Configure it as you would any logger, or set `CRU_LOG=debug` (or `info`) to print it to stderr:

```sh
CRU_LOG=debug python examples/portfolio.py
```

```text
[2026-10-24 12:00:00,000 DEBUG cruworldwine] GET /portfolio -> 503 in 0.120s (attempt 1, request_id req_...)
[2026-10-24 12:00:00,001 INFO cruworldwine] Retrying GET /portfolio in 0.52s (retry 1 of 2) after HTTP 503
[2026-10-24 12:00:00,700 DEBUG cruworldwine] GET /portfolio -> 200 in 0.180s (attempt 2, request_id req_...)
```

Logs never hold your client key or secret, access or refresh tokens, or request and response
bodies. httpx logs its own lines through the `httpx` logger.

## app_info and the User-Agent

Every request carries a User-Agent such as
`cruworldwine-python/0.2.0 Python/3.13.2 (Linux; x86_64)`. If you build an integration others use,
name it with `app_info`; it is added at the end, so Cru can tell integrations apart when helping
you:

```python
cru = Cru(app_info=('cellar-sync', '2.3.0', 'https://cellar-sync.example'))
# cruworldwine-python/0.2.0 Python/3.13.2 (Linux; x86_64) cellar-sync/2.3.0 (https://cellar-sync.example)
```

The version and the URL may be `None`.
