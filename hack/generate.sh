#!/usr/bin/env bash
# Regenerates the generated code (src/cruworldwine/models/, src/cruworldwine/resources/,
# src/cruworldwine/_market_table.py, the README method table and api/openapi.yaml) with the generator
# in Cru's API repository.
#
#   CRU_API_REPO=/path/to/the/api/web-root hack/generate.sh [sdk-dir]
#
# sdk-dir defaults to this checkout; hack/verify-generated.sh passes a scratch copy instead.
set -euo pipefail

if [ -z "${CRU_API_REPO:-}" ]; then
  echo "error: set CRU_API_REPO to the web-root of Cru's API repository, the folder that holds docs/api/tools/sdkgen" >&2
  exit 2
fi
generator="docs/api/tools/sdkgen/generate.py"
if [ ! -f "$CRU_API_REPO/$generator" ]; then
  echo "error: $CRU_API_REPO/$generator not found; is CRU_API_REPO the API repository's web-root?" >&2
  exit 2
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target="$(cd "${1:-$root}" && pwd)"

# -B: no __pycache__ is written into the API repository.
cd "$CRU_API_REPO"
uv run --quiet --no-project --with pyyaml==6.0.3 python -B "$generator" --python "$target"
