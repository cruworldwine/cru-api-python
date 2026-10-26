# Architecture

How the SDK is put together, what happens on every request, how the generated code is made, and
where to change what. For setting up and running the checks, see [CONTRIBUTING.md](../CONTRIBUTING.md).

## Package layout

```text
src/cruworldwine/
├── __init__.py         the public names: Cru, AsyncCru, the errors, Page, AsyncPage, Write, Model, MARKETS, models
├── _client.py          Cru and AsyncCru: their constructors and documentation
├── _base_client.py     the shared core: BaseClient, and the sync and async transports
├── _markets.py         MarketInfo, MARKETS and lookup_market(), and which market a client calls
├── _market_table.py    generated: each environment's URL template and every market
├── _operations.py      Operation, Op and PageOp: typed descriptions of the endpoints
├── _types.py           Page, AsyncPage, Write and Response
├── _models.py          Model, the base of every API object, and the registry of model classes
├── _errors.py          CruError and the error classes, chosen by status and code
├── _logs.py            the cruworldwine logger and CRU_LOG
├── _constants.py       default timeout, retries and back-off
├── _version.py         VERSION
├── py.typed
├── models/             generated: one module of models per resource
└── resources/          generated: one module per resource, a class for Cru and one for AsyncCru
```

Modules whose names start with an underscore are internal: their contents may change in any
release. What users import is re-exported from `cruworldwine` and `cruworldwine.models`.

## One core, two transports

`Cru` and `AsyncCru` differ only in how they do I/O. Everything else lives once, in
`BaseClient`, so the two cannot drift apart:

```text
BaseClient            building requests, deciding after each attempt, refreshing, parsing
├── SyncAPIClient     httpx.Client, time.sleep, a threading.Lock around refreshes
│   └── Resources     generated: cru.bids, cru.market, ..., and cru.ping()
│       └── Cru
└── AsyncAPIClient    httpx.AsyncClient, asyncio.sleep, an asyncio.Lock around refreshes
    └── AsyncResources   generated: the same resources, every method a coroutine
        └── AsyncCru
```

## The life of a request

Take `cru.bids.place(lwin18=..., quantity=6, price=1450, timeout=10)`.

1. **The generated method** passes its operation descriptor (`_PLACE_BID: Op[Write[BidResult]]`),
   the path, query and body parameters and the per-call options to `client._call()`. The
   descriptor's type parameter is what lets mypy check every method's return type without a cast.
2. **Preparing** (`BaseClient._prepare`, shared): path parameters are URL-encoded into the path,
   unset parameters are dropped, `extra_query` and `extra_body` are merged in, and a partner
   write gets its idempotency `reference` (`sdk_` and a random id) unless you gave one. The result,
   `_RequestOptions`, is fixed for every attempt, so a retry resends the same reference.
3. **Sending** (the transport's `_send` loop): each attempt builds the request with fresh
   authentication headers and sends it, never following redirects.
4. **Deciding** (`BaseClient._decide` and `_decide_failure`, shared): after each attempt the core
   logs it and returns one of three steps, or raises:
   - *return* a 2xx response;
   - *refresh* after a 401, once, when there is a refresh token; the transport refreshes under its
     lock, unless another request already did, and sends again;
   - *retry* after a connection failure, a timeout, 429, 5xx or `REQUEST_IN_PROGRESS`, if the request
     may be retried and retries remain, after the wait the core works out (`Retry-After`, or
     back-off with jitter, at most 30 seconds); the transport sleeps and sends again;
   - otherwise *raise* the `APIStatusError` subclass for the status and code, or an
     `APIConnectionError`.
5. **Parsing** (`BaseClient._process`, shared): the envelope's `data` becomes the typed model, a
   list of them, a `Page` or `AsyncPage` (whose `next_page()` repeats the call at the next offset),
   or a `Write`, typed by the action for a confirmation. Each answer is marked with its request id.

## How the generated code is made

`src/cruworldwine/models/`, `src/cruworldwine/resources/`, `src/cruworldwine/_market_table.py`,
the method table in `README.md` and `api/openapi.yaml` are generated from the Cru Trading API's
OpenAPI spec, which lives in Cru's API repository with the generator:

```text
openapi-v1-implemented.yaml      the spec, in the API repository
  → sdkgen/ir.py                 reads it into models, operations, environments and markets, shared by every SDK's generator
  → sdkgen/gen_python.py         writes this SDK's models/, resources/, _market_table.py and README table
  → generate.py                  runs the generators, and copies the spec to api/openapi.yaml
```

The generator writes code that is already formatted as `ruff format` would, passes `ruff check`
and `mypy --strict`, and is byte-identical from one run to the next. Every generated file starts
with `# Code generated by sdkgen ... DO NOT EDIT.`, and files it no longer writes are removed by
that header. `make generate` runs it, with `CRU_API_REPO` pointing at the API repository's
web-root; `make verify-generated` fails if regenerating would change anything.

## Where to change what

| To change | Edit |
|---|---|
| An endpoint, parameter, field, description or method name | The spec in Cru's API repository (`x-cru-sdk` names the resource and method), then `make generate` |
| A market, or an environment's URL | The spec's `x-cru-markets` and `servers`, then `make generate` |
| How a client picks its host and its `market_info` | `_base_client.py` and `_markets.py` |
| How generated code looks | `gen_python.py` in Cru's API repository, then `make generate` |
| Retries, back-off, timeouts, refreshing, logging, request building | `_base_client.py` and `_constants.py` |
| The constructors and their documentation | `_client.py` |
| Pages, writes, raw responses | `_types.py` |
| How a model parses | `_models.py` |
| An error class or how one is chosen | `_errors.py` |
| What `import cruworldwine` exports | `__init__.py` |
| Tests | `tests/unit/` for mocked behaviour, `tests/integration/` for replays and the live test |
| Guides | `docs/` |
