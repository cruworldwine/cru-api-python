## What and why

<!-- What this changes, and why. Link the issue it fixes: "Fixes #123". -->

## How it was tested

<!-- The tests you added or ran. CI runs ruff, mypy --strict and pytest on Python 3.9 to 3.15. -->

## Checklist

- [ ] It changes no generated file by hand (`models/`, `resources/`, the README method table,
      `spec/`): API changes come from the OpenAPI spec in Cru's API repository.
- [ ] `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` and `uv run pytest` pass.
- [ ] New behaviour has tests, for `Cru` and `AsyncCru` alike.
- [ ] `CHANGELOG.md` has a line under `## [Unreleased]`; a public API change says what users must do.
- [ ] Nothing here holds a credential, a token or customer data.
