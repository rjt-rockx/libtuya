#!/usr/bin/env bash
# Refresh the vendored snapshot of Home Assistant's Tuya integration and the
# data generated from it.
#
#   scripts/sync-upstream.sh <ref>     # a release tag such as 2026.11.2
#
# The snapshot under third_party/home-assistant-core/ is never edited by hand;
# third_party/home-assistant-core/UPSTREAM records the commit it came from.
set -euo pipefail

URL=https://github.com/home-assistant/core.git
DEST=third_party/home-assistant-core
PATHS=(
    LICENSE.md
    homeassistant/components/tuya
    tests/components/tuya/fixtures
    tests/components/tuya/snapshots
)

ref=${1:?usage: scripts/sync-upstream.sh <ref>}
cd "$(git rev-parse --show-toplevel)"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
git init --quiet "$work"
git -C "$work" sparse-checkout set --no-cone "${PATHS[@]/#//}"
git -C "$work" fetch --quiet --depth 1 --filter=blob:none "$URL" "$ref"
git -C "$work" checkout --quiet FETCH_HEAD

rm -rf "$DEST"
for path in "${PATHS[@]}"; do
    mkdir -p "$DEST/$(dirname "$path")"
    cp -R "$work/$path" "$DEST/$path"
done
cat >"$DEST/UPSTREAM" <<EOF
repository: $URL
ref: $ref
commit: $(git -C "$work" rev-parse HEAD)
date: $(git -C "$work" log -1 --format=%cs)
license: Apache-2.0 (LICENSE.md)
paths: ${PATHS[*]}
EOF

python3 scripts/gen_ha_tables.py
echo "Vendored home-assistant/core@$ref. Update the pins in pyproject.toml if" \
    "manifest.json changed, then run the tests."
