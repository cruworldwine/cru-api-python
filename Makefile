# The project's tasks. CI calls these same targets, so a green `make ci` here means green checks there.
# `make` alone lists them.

UV ?= uv
PYTEST_ARGS ?=

.DEFAULT_GOAL := help
.PHONY: help install generate verify-generated fmt lint typecheck test test-lowest integration live build clean ci

help: ## List the targets
	@awk 'BEGIN { FS = ":.*## " } /^[a-z][a-z-]*:.*## / { printf "  %-17s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

install: ## Install the package and every development tool, as uv.lock pins them
	$(UV) sync --locked

generate: ## Regenerate models/, resources/, the README table and api/ (needs CRU_API_REPO)
	hack/generate.sh

verify-generated: ## Fail if regenerating would change a generated file (needs CRU_API_REPO)
	hack/verify-generated.sh

fmt: ## Format the code and apply ruff's safe fixes
	$(UV) run --locked --only-group lint ruff format .
	$(UV) run --locked --only-group lint ruff check --fix .

lint: ## ruff check, and ruff format --check
	$(UV) run --locked --only-group lint ruff check .
	$(UV) run --locked --only-group lint ruff format --check .

typecheck: ## mypy --strict on src/ and examples/
	$(UV) run --locked --no-dev --group typecheck mypy

test: ## Unit tests, with branch coverage of at least 90%
	$(UV) run --locked --no-dev --group test pytest tests/unit --cov --cov-report=term-missing $(PYTEST_ARGS)

test-lowest: ## Unit tests on Python 3.9, with httpx and the test tools at their lowest allowed versions
	hack/test-lowest.sh $(PYTEST_ARGS)

integration: ## Replay captured API answers through Cru and AsyncCru (needs CRU_CAPTURES)
	@if [ -z "$$CRU_CAPTURES" ]; then echo "error: set CRU_CAPTURES to a spec_capture.php run" >&2; exit 2; fi
	$(UV) run --locked --no-dev --group test pytest tests/integration/test_replay.py $(PYTEST_ARGS)

live: ## Read-only smoke test against the live API (needs credentials in the environment)
	CRU_LIVE=1 $(UV) run --locked --no-dev --group test pytest tests/integration/test_live.py -v $(PYTEST_ARGS)

build: ## Build the sdist and wheel, check them with twine, and check the wheel is typed and imports
	rm -rf dist
	$(UV) build
	$(UV) run --locked --only-group release twine check --strict dist/*
	$(UV) run --no-project python -c "import glob, sys, zipfile; names = zipfile.ZipFile(glob.glob('dist/*.whl')[0]).namelist(); sys.exit(0 if 'cruworldwine/py.typed' in names else 'py.typed is missing from the wheel')"
	$(UV) run --isolated --no-project --with "$$(ls dist/*.whl)" python -c "import cruworldwine; print('cruworldwine', cruworldwine.__version__, 'imports')"

clean: ## Remove build outputs and caches
	rm -rf dist build htmlcov .coverage .coverage.* coverage.xml .pytest_cache .mypy_cache .ruff_cache .hypothesis
	find . -name __pycache__ -type d -not -path './.venv/*' -prune -exec rm -rf {} +

ci: lint typecheck test test-lowest build ## Every check CI runs, with this machine's Python for the unit tests
