#!/usr/bin/env bash
# Fails if regenerating would change any generated file, which means one was edited by hand or the
# spec moved on without a regeneration. It regenerates into a scratch copy, so the checkout is never
# touched and local changes elsewhere do not matter.
#
#   CRU_API_REPO=/path/to/the/api/web-root hack/verify-generated.sh
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT

generated=(api src/cruworldwine/models src/cruworldwine/resources src/cruworldwine/_market_table.py README.md)
mkdir -p "$scratch/src"
cp -R "$root/api" "$root/README.md" "$scratch/"
cp -R "$root/src/cruworldwine" "$scratch/src/"

"$root/hack/generate.sh" "$scratch" >/dev/null

status=0
for path in "${generated[@]}"; do
  if ! diff -r -u -x __pycache__ "$root/$path" "$scratch/$path"; then
    status=1
  fi
done
if [ "$status" -ne 0 ]; then
  echo "error: regenerating changes the files above; run 'make generate' and commit, never edit them by hand" >&2
  exit 1
fi
echo "Generated files are up to date."
