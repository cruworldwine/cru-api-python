# Compatibility

The Cru Trading API grows: new fields, new values, new parameters and new endpoints. The SDK is
built so that code written against this version keeps working when the API moves on, and so that
you can use what is new before the SDK knows about it.

## Typed models that tolerate what they do not know

Every answer is a typed model: a class per API object, with an attribute per API field and the
API's descriptions as its docstring, so an editor completes and checks them.

```python
for wine in cru.portfolio.list(is_listed=True).auto_paging_iter():  # PortfolioWine
    for line in wine.portfolio:  # PortfolioLine
        print(wine.wine_name, line.quantity, line.pricing.listing_price, line.pricing.net_proceeds)
```

- **Unknown fields are kept.** Every model has `.raw`, the object exactly as the API sent it, new
  fields included; `model['new_field']` and `model.get('new_field')` read one, and
  `model.to_dict()` returns a copy of it all.
- **Nothing raises on an unexpected shape.** A field that is missing is `None`; one of a type the
  SDK did not expect is kept as sent. This is checked with property-based tests that feed every
  model arbitrary JSON.
- **Types follow the spec.** A field the spec says is always present and never null is typed as
  such (`code: str`), so typed code needs no `None` checks for it; one that can be null is
  `Optional`. At run time a missing field is still `None`, never an error.

Models compare equal when they are of the same class and hold the same data.

## Values that may grow

Many fields hold one of a set of values that "may grow", such as a bid's `status` (`live`,
`matched`, `complete`, ...) or a market code. The SDK keeps them as plain strings, not enums, so a
value added later never breaks parsing. Each field's docstring lists the values known today.
Compare with strings, and have a default branch:

```python
if bid.status == 'live':
    ...
elif bid.status in ('matched', 'complete'):
    ...
else:
    ...  # a status added after this version
```

## Parameters and endpoints the SDK does not know yet

Every method takes `extra_query` and, for writes, `extra_body`, sent as given, for a parameter
this version does not have. For an endpoint it does not have at all, `cru.request()` sends any
request with the SDK's authentication, retries and errors, and returns the envelope:

```python
response = cru.request('GET', '/new/path', query={'limit': 10})
print(response.status_code, response.data, response.request_id)
```

## Versioning policy

The SDK follows [semantic versioning](https://semver.org).

- While it is 0.x, a minor release (0.1 to 0.2) may change the public API, and every such change
  is listed in the [changelog](../CHANGELOG.md) with what to do; patch releases never do.
- From 1.0, only a major release changes the public API.
- Names that start with an underscore are internal and may change in any release. The one
  exception is `_request_id`, which is public.
- A deprecated name keeps working, with a `DeprecationWarning`, for at least one minor release
  before it is removed.

## Supported Python versions

The SDK supports every Python version its CI tests, currently 3.9 to 3.15, on Linux, macOS and
Windows, and it is checked with mypy in strict mode. Support for a Python version that has reached
its end of life may be dropped in a minor release, with a changelog entry. Only the latest minor
release gets fixes, security fixes included.
