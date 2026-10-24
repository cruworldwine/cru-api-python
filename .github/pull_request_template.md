## What and why

<!-- What this changes, and why. Link the issue it fixes: "Fixes #123". -->

## How it was tested

<!-- The tests you added or ran. CI runs `make ci`'s checks, with the unit tests on Python 3.9 to 3.15. -->

## Checklist

- [ ] It changes no generated file by hand (`models/`, `resources/`, the README method table,
      `api/`): API changes come from the OpenAPI spec in Cru's API repository.
- [ ] `make ci` passes (lint, format, mypy --strict, unit tests with coverage, build).
- [ ] New behaviour has tests, for `Cru` and `AsyncCru` alike.
- [ ] `CHANGELOG.md` has a line under `## [Unreleased]`; a public API change says what users must do.
- [ ] Nothing here holds a credential, a token or customer data.
