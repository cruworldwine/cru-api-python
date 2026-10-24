# Errors

Every error the SDK raises is a `CruError`, so `except CruError` catches them all.

```python
from cruworldwine import PriceChangedError, UnprocessableEntityError

try:
    cru.market.buy_offer('CS-12345', quantity=1, max_price=1500)
except PriceChangedError:
    ...  # preview again
except UnprocessableEntityError as e:
    print(e.code, e.field, e.message, e.request_id)
```

## The hierarchy

```text
CruError
├── APIConnectionError           the API could not be reached, or the connection broke
│   └── APITimeoutError          it did not answer in time
└── APIStatusError               the API answered with an error
    ├── BadRequestError          400  VALIDATION_UNKNOWN_PARAMETER, VALIDATION_MALFORMED_BODY
    ├── AuthenticationError      401  wrong credentials, or an expired token that could not be refreshed
    ├── PermissionDeniedError    403  a scope, store, address or account check refused the call
    ├── NotFoundError            404
    ├── MethodNotAllowedError    405
    ├── ConflictError            409
    │   ├── PriceChangedError        PRICE_CHANGED: the price moved since the preview
    │   └── RequestInProgressError   REQUEST_IN_PROGRESS: the same reference is still running
    ├── GoneError                410  the confirmation code expired or was cancelled
    ├── UnprocessableEntityError 422  a value was refused (VALIDATION_*), or the trade was (TRADE_REFUSED)
    ├── RateLimitError           429
    └── InternalServerError      5xx
```

A status the SDK has no class for raises `APIStatusError` itself. Invalid arguments to the SDK
(an empty path parameter, a negative timeout, an unknown market) raise `CruError`.

## What an APIStatusError holds

| Attribute | Meaning |
|---|---|
| `status_code` | The HTTP status. |
| `code` | The API's stable, symbolic code, such as `TRADE_REFUSED`. Branch on this. |
| `message` | What went wrong, for people. It may change; never branch on it. |
| `field` | The parameter or body field the error is about, if any. |
| `details` | Structured context, such as `required_scope` or `retry_after`. |
| `errors` | Every error entry the API sent; the attributes above come from the first. |
| `headers` | The response's headers. |
| `request_id` | The id Cru support needs to find the request. |
| `body` | The whole error response, as sent. |

`str(e)` reads like `422 TRADE_REFUSED: The bid is above your allowance.`, and `repr(e)` adds the
request id. Neither ever shows a credential or a token.

## Retried errors

Before an error reaches you, the SDK has already retried what is safe to retry: connection errors,
timeouts, 429, 5xx and `REQUEST_IN_PROGRESS`, for reads and partner writes. See
[Retries](configuration.md#retries).

## Request ids

Cru support finds a request by its id. Every error has `request_id`, and so does every answer:

```python
page = cru.bids.list()
print(page.request_id)  # a Page, an AsyncPage and a Write have request_id
bid = cru.bids.get('CB-1001')
print(bid._request_id)  # a model has _request_id
```

A model's attributes are the API's fields, and the API has fields named `request_id` (the response
envelope's `meta` has one), so on a model it is `_request_id`, a name no API field can take. It is
set on the model a method returns, and on each item of a list or page. `Page`, `AsyncPage` and
`Write` are the SDK's own, so they have `request_id`, and `_request_id` as well, so every answer
reads the same way. The id comes from the envelope's `meta.request_id`, or else the
`X-Request-Id` header.
