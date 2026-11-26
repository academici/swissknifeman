#!/usr/bin/env bash
# One-time run: sync MCP/hooks + skiller hub + health for new/lagging projects.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MAIN="$ROOT/packages/maind/bin/maind"
SK="$ROOT/packages/skiller/bin/skiller"

repair_project() {
  local id="$1" path="$2"
  echo "== $id =="
  "$MAIN" sync --project "$id" --repair --yes
  "$SK" connect "$path" --hub --yes
  "$SK" update "$path" --hub 2>/dev/null || true
  "$MAIN" health --cwd "$path" --fix
}

repair_project agentools "$ROOT/../agentools"
repair_project themeon "$ROOT/../themeon"

echo "Done. Restart MCP/daemon on the hub if themeon did not appear in maind_projects_status."
