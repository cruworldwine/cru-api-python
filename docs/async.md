# Async

`AsyncCru` is the asyncio client. It takes the same arguments as `Cru` and has the same resources
and methods, each a coroutine to await. It runs on `httpx.AsyncClient`.

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

## Lifecycle

Use the client as an async context manager, or call `await cru.aclose()` when you are done, to
close its connection pool. Make one client and share it: it is safe to use from many tasks at once,
and they share its connections.

## Pages

Lists return an `AsyncPage`:

- `async for item in page` walks every item of every page, fetching pages as it goes;
- `await page.next_page()` fetches the next page, or returns `None` after the last one;
- `page.auto_paging_iter()` is the same async iterator as `async for`;
- a plain `for item in page` iterates only the page in hand.

See [Pagination](pagination.md).

## Concurrency and token refresh

Run calls concurrently with `asyncio.gather()` or task groups. When the OAuth access token expires
while several tasks are using it, one task refreshes it under an `asyncio.Lock`, and the others
wait and then retry with the new token: the single-use refresh token is never spent twice.
`on_token_refresh` may be a plain function or a coroutine function; a coroutine is awaited.

## Everything else is the same

Retries and their waits (with `asyncio.sleep`), idempotency references, staged writes, errors,
request ids, typed models, per-call options and `with_options()` behave exactly as they do with
`Cru`, because both clients share one core; see [Architecture](architecture.md).

`AsyncCru` uses asyncio. It does not run under trio.
