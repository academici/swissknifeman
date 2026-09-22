#!/usr/bin/env bash
# Local post-tag release delivery. This command never creates/moves/pushes tags or publishes releases.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILLER="$ROOT/packages/skiller/bin/skiller"
MAIND="$ROOT/packages/maind/bin/maind"
RELEASE="${1:-}"
MODE="${2:-}"

if [[ ! "$RELEASE" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || [[ -n "$MODE" && "$MODE" != "--dry-run" ]]; then
  echo "usage: ./bin/swissknifeman release-fleet vX.Y.Z [--dry-run]" >&2
  exit 2
fi

tag_commit="$(git -C "$ROOT" rev-parse "$RELEASE^{commit}")"
head_commit="$(git -C "$ROOT" rev-parse HEAD)"
if [[ "$tag_commit" != "$head_commit" ]]; then
  echo "RELEASE_FLEET_HEAD_MISMATCH: $RELEASE=$tag_commit HEAD=$head_commit" >&2
  exit 1
fi

python3 "$ROOT/scripts/verify-tag.py" "$RELEASE"
"$SKILLER" attest --release "$RELEASE" --check

if [[ "$MODE" == "--dry-run" ]]; then
  "$SKILLER" deliver --release "$RELEASE" --all --dry-run
  "$MAIND" sync --all --dry-run
  exit 0
fi

"$SKILLER" deliver --release "$RELEASE" --all
"$MAIND" sync --all

# Idempotence and fleet gates run after mutation. A failure keeps the workflow non-green.
"$SKILLER" deliver --release "$RELEASE" --all --dry-run
sync_readback="$(mktemp)"
trap 'rm -f "$sync_readback"' EXIT
"$MAIND" sync --all --dry-run --json >"$sync_readback"
python3 - "$sync_readback" <<'PY'
import json
import pathlib
import sys

rows = json.loads(pathlib.Path(sys.argv[1]).read_text())
changed = [f"{row['id']}:{row['provisioner']}" for row in rows if row.get("changed")]
non_green = [f"{row['id']}:{row['provisioner']}" for row in rows
             if row.get("provider_aggregate") == "non-green"]
if changed or non_green:
    raise SystemExit("MAIND_SYNC_NOT_IDEMPOTENT: changed=" + ",".join(changed)
                     + "; non_green=" + ",".join(non_green))
PY
"$SKILLER" doctor --vendor-drift
"$SKILLER" doctor --provider-distribution
"$MAIND" projects status --all
"$MAIND" verify
"$MAIND" doctor --audit mcp

echo "release fleet delivery GREEN: $RELEASE (local only; no push/tag/publication performed)"
