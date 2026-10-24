# Pagination

Endpoints that list many things (your portfolio, bids, offers, purchases and sales, the market,
the wine search) answer one page at a time. Their methods return a `Page`, or with `AsyncCru` an
`AsyncPage`. The short lists (warehouses, inbond warehouses and addresses) return a plain `list`.

```python
for wine in cru.market.list_bids(lwin=['101174520151200750']).auto_paging_iter():
    for bid in wine.bids:
        print(wine.wine_name, bid.price, bid.quantity)

page = cru.portfolio.list(stock_type=['cru'], is_listed=False, limit=50)
print(page.total, page.has_more)
```

## Walking every page

| | `Page` (Cru) | `AsyncPage` (AsyncCru) |
|---|---|---|
| This page's items | `for item in page`, `page.items` | `for item in page`, `page.items` |
| Every item of every page | `page.auto_paging_iter()` | `async for item in page`, or `page.auto_paging_iter()` |
| The next page | `page.next_page()` | `await page.next_page()` |

`next_page()` returns `None` after the last page. Pages are fetched only as they are needed, and
each with the same parameters and per-call options as the first, at the next offset.

## What a page tells you

| Attribute | Meaning |
|---|---|
| `items` | This page's typed models. `len(page)` is their number. |
| `total` | How many there are in all, or `None` where the API does not count them (`GET /wines`). |
| `has_more` | Whether another page follows. |
| `limit`, `offset` | The limit and offset the API applied. |
| `data`, `meta` | The response's `data` and `meta`, as sent, for anything else they hold. |
| `request_id` | The id of the request that answered this page. |

## Page size

Pass `limit` to choose how many items a page holds, and `offset` to start further in. A `limit`
above an endpoint's maximum is refused with `VALIDATION_INVALID_VALUE` rather than reduced; each
method's docstring gives the endpoint's range.
