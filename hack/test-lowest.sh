#!/usr/bin/env bash
# Runs the unit tests on Python 3.9 with httpx and the test tools at the lowest versions pyproject.toml
# allows, so a lower bound that no longer works is caught. It resolves in a scratch copy of the
# project: resolving for the lowest versions would otherwise rewrite uv.lock.
#
#   hack/test-lowest.sh [pytest arguments]
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT

cp -R "$root/pyproject.toml" "$root/README.md" "$root/LICENSE" "$root/src" "$root/tests" "$scratch/"
cd "$scratch"
uv run --python 3.9 --resolution lowest-direct --no-dev --group test pytest tests/unit "$@"
