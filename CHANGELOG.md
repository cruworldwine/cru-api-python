# Changelog

Every notable change to the `cruworldwine` package is listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html): while it is 0.x, a minor release may
change the public API, and each such change is listed under **Changed** or **Removed**.

## [Unreleased]

The next release is **0.1.1**: everything below, including the per-resource layout already on
`main`. When it is cut, this heading becomes `## [0.1.1] - <date>`.

### Added

- `AsyncCru`, an asyncio client on `httpx.AsyncClient`, with the same constructor, resources and
  methods as `Cru`, each a coroutine. It retries, refreshes OAuth tokens, raises and parses exactly
  as `Cru` does; the two share that logic rather than duplicating it. Use it as an async context
  manager or call `aclose()`. `on_token_refresh` may be a coroutine function.
- `AsyncPage`: `async for` walks every item of every page, `await page.next_page()` fetches the
  next page, and `auto_paging_iter()` is an async iterator.
- Per-call options on every method: `extra_headers`, `timeout` and `max_retries`, next to
  `extra_query` and `extra_body`.
- `client.with_options(timeout=..., max_retries=...)`: a copy that shares the connection pool and
  the credentials, OAuth tokens included.
- Request ids on successful answers: `_request_id` on the model a method returns and on each item of
  a list or page; `request_id` (and `_request_id`) on `Page`, `AsyncPage` and `Write`;
  `request_id` on `Response`. Taken from `meta.request_id`, or the `X-Request-Id` header.
- Logging through `logging.getLogger('cruworldwine')`: each attempt at DEBUG (method, path, status,
  attempt, time taken, request id), each retry and token refresh at INFO. `CRU_LOG=debug` or
  `CRU_LOG=info` prints it to stderr. Credentials, tokens and bodies are never logged.
- `app_info=(name, version, url)` on the clients, appended to a User-Agent that now reads
  `cruworldwine-python/<version> Python/<version> (<os>; <machine>)`.
- `Retry-After` given as an HTTP date is honoured, as well as seconds; waits stay capped at 30
  seconds.
- `APIStatusError.headers`, the response's headers; a `repr()` for errors, clients, pages, writes
  and raw responses, none of which ever shows a secret or a token.
- `is_closed` on both clients; `DEFAULT_TIMEOUT`, `DEFAULT_MAX_RETRIES` and `__version__` exported.
- One module per resource, for methods (`cruworldwine/resources/`) and for the models they return
  (`cruworldwine/models/`); `from cruworldwine.models import X` works as before.
- A field the spec says is always there and never null is typed as such (`code: str`, not
  `Optional[str]`); at run time a missing one is still `None`.
- `examples/`: `portfolio.py`, `market.py`, `place_bid.py` and `async_market.py`, all type-checked.
- A method table in the README, generated from the spec with the code.
- Project: CI on Python 3.9 to 3.15 (Linux, macOS, Windows) with ruff, strict mypy, coverage of
  at least 90% and a Hypothesis property test of the models; a release workflow that publishes to
  PyPI by Trusted Publishing with build provenance attestations; Dependabot; issue and pull request
  templates; `CONTRIBUTING.md` and `SECURITY.md`; `uv.lock` for reproducible development and CI.
- Guides in `docs/`: authentication, configuration, async, pagination, writes and confirmations,
  errors, compatibility and architecture. The README is shorter and links to them.
- Repository layout, with no change to the package or its API: the spec copy is in
  `api/openapi.yaml` (it was `spec/`); tests are split into `tests/unit/` and `tests/integration/`,
  where a new live smoke test runs read-only calls when `CRU_LIVE=1`; `hack/` holds the scripts that
  regenerate the code and verify it is up to date; a `Makefile` has a target for every task, and
  CI runs those same targets.

### Changed

- `timeout=None` now means "the default" everywhere (constructor, call, `with_options()`): 30
  seconds, or the timeout your own `http_client` was given. Pass `httpx.Timeout(None)` for no
  timeout at all. Before, `None` given to the constructor meant no timeout.
- With your own `http_client`, the `timeout` argument now applies (it was ignored), and a client
  that was given no timeout of its own waits the SDK's 30 seconds rather than httpx's 5.
- `extra_query`, `extra_body` and `extra_headers` take any mapping. `extra_body` is sent as given:
  a `None` in it is sent as JSON `null` (it was dropped), so a field can be cleared.
- `Write.request_id` also comes from `meta.request_id`, not only from the `X-Request-Id` header.
- The text of an error without an API code reads `502: HTTP 502` (it was `502 : HTTP 502`).
- An invalid `market`, a `base_url` that is not http or https, a negative `timeout` or
  `max_retries`, or an invalid `app_info` raise `CruError` when the client is made.
- Annotations use built-in generics (`dict`, `list`); the README's table shows `list[Warehouse]`.
- Internal: the generated resources describe each endpoint with a typed operation descriptor, so
  every method's return type is checked by mypy; `Cru` and `AsyncCru` build on a shared
  `BaseClient`. Names starting with an underscore are internal and may change in any release.

### Fixed

- Concurrent requests that find the OAuth access token expired now refresh it once: one refresh at
  a time, under a lock, and the others retry with the new token. Before, two threads could both
  spend the single-use refresh token, and the second failed.
- A model no longer raises when a list field holds something else (a number, a string or an
  object); the value is kept as the API sent it. An error response whose `errors` is not a list of
  objects no longer raises while the error is being built.

## [0.1.0] - 2026-10-24

### Added

- First release, for the Cru Trading API v1: `Cru`, a client for partner credentials and OAuth
  connected apps, with every endpoint as a typed method and every answer as a typed model generated
  from the OpenAPI spec.
- Lists return a `Page` with `next_page()` and `auto_paging_iter()`; writes return a `Write` that
  is either carried out (`result`) or staged for the customer to confirm (`confirmation`).
- Partner writes carry an idempotency `reference`, made by the SDK when not given and kept across
  its retries. Reads and partner writes are retried on connection errors, 429 and 5xx, honouring
  `Retry-After`. Redirects are never followed.
- An expired OAuth access token is refreshed once, and `on_token_refresh` receives the new tokens.
- Errors by status and code (`NotFoundError`, `PriceChangedError`, ...), with `code`, `message`,
  `field`, `details`, `errors` and `request_id`.
- Fields and values this version does not know are kept in `.raw`; `extra_query`, `extra_body` and
  `client.request()` reach parameters and endpoints it does not know.

[Unreleased]: https://github.com/cruworldwine/cru-api-python/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/cruworldwine/cru-api-python/releases/tag/v0.1.0
