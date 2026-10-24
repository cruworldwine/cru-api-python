# Writes and confirmations

Every write (placing, changing or cancelling a bid, listing or removing an offer, buying an offer,
selling into a bid, adding an inbond address) returns a `Write`. What it holds depends on how you
connected.

```python
write = cru.bids.place(lwin18='101174520151200750', quantity=6, price=1450)
if write.staged:  # a connected app: nothing has happened yet
    print(write.confirmation.preview.summary)
    write = cru.confirmations.confirm(write.confirmation.code)
print(write.result.bid.status)
```

## A Write

| Attribute | Meaning |
|---|---|
| `staged` | `True` for a connected app's write, which has not happened yet. |
| `result` | What the write did, as a typed model (`BidResult`, `OfferResult`, ...), once it ran. |
| `confirmation` | For a staged write: the code to confirm and a `preview` of what would happen. |
| `replayed` | `True` when this is the stored answer to an earlier request with the same `reference`. |
| `request_id` | The id of the request that answered. |

## Partner credentials: writes run at once

A partner credential's write is carried out straight away, and `result` holds what it did.

Each partner write carries a `reference`, its idempotency key. The SDK makes one when you do not
pass it (`sdk_` and a random id) and keeps it across its own retries, so a retry after a timeout
can never place a bid twice. Pass your own to retry safely across restarts of your program:

```python
write = cru.bids.place(lwin18='101174520151200750', quantity=6, price=1450, reference='order-8812')
if write.replayed:
    print('Already placed by an earlier attempt')
```

## Connected apps: writes are staged

A connected app acts for a customer, so its writes are staged: the API answers 202 with a
confirmation, and nothing happens until the customer agrees. Show them `preview.summary`, a sentence
they can say yes to, and confirm only on their explicit yes:

```python
write = cru.market.buy_offer('CS-12345', quantity=1, max_price=1500)
if write.staged and ask(write.confirmation.preview.summary):
    write = cru.confirmations.confirm(write.confirmation.code)
```

- `cru.confirmations.confirm(code)` carries the instruction out and returns a `Write` whose
  `result` is typed by the action confirmed (a bid placement gives a `BidResult`, a purchase a
  `BuyResult`, and an action this version does not know an `InstructionResult`).
- `cru.confirmations.get(code)` shows how far it has got: pending, executing, completed, failed,
  expired or cancelled.
- `cru.confirmations.cancel(code)` discards it; the code cannot be used again.

A confirmation code expires; confirming one too late raises `GoneError`. A staged write has no
reference and is never retried by the SDK.

## When the price moves

Buying an offer takes `max_price`, the most you will pay per unit, and selling into a bid takes
`min_price`, the least you will take. A partner credential should always send them: its trade has
no preview, so they are what hold the price you read from the book. If the price is past them,
nothing is traded.

When the price has moved since a staged instruction's preview, the API answers 409
`PRICE_CHANGED`, raised as `PriceChangedError`: preview it again and ask the customer again.

```python
from cruworldwine import PriceChangedError

try:
    write = cru.confirmations.confirm(code)
except PriceChangedError:
    ...  # stage the purchase again and show the new preview
```
