#!/usr/bin/env bash
# Read-only smoke of the browser-mode backend against the real hub: a throwaway SKM_HOME and HOME, the units of
# `swissknifeman units list`, `gui serve --port 0`; checks /v1/bootstrap, the catalog (gui-hub accepted) and the
# query gui-hub.units, then stops the backend. No command is run.
set -euo pipefail
MODULE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GUI="$MODULE_ROOT/bin/gui"
command -v swissknifeman >/dev/null 2>&1 || { echo "SMOKE: swissknifeman is not on PATH (the real hub is needed)" >&2; exit 2; }

PYDEPS="$("$GUI" deps path)"
"$GUI" deps ensure >/dev/null
UMBRELLA="$(command -v swissknifeman)"
BASE="$(mktemp -d)"
PID=""
cleanup() {
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    kill -TERM "$PID" 2>/dev/null || true
    for _ in $(seq 1 50); do kill -0 "$PID" 2>/dev/null || break; sleep 0.1; done
    kill -KILL "$PID" 2>/dev/null || true
  fi
  rm -rf "$BASE"
}
trap cleanup EXIT
mkdir -p "$BASE/home"

# The hub registry is read once with the real environment; the backend itself sees only the throwaway home.
UNITS="$(swissknifeman units list --json 2>/dev/null | python3 -c '
import json, os, sys
doc = json.load(sys.stdin)
print(os.pathsep.join(os.path.join(doc["hub_root"], unit["root"]) for unit in doc["units"]))')"

env -i PATH="$PATH" HOME="$BASE/home" SKM_HOME="$BASE/skm" LANG=C.UTF-8 GUI_PYDEPS_DIR="$PYDEPS" \
  SKM_UNITS_PATH="$UNITS" SKM_UMBRELLA="$UMBRELLA" \
  "$GUI" serve --port 0 --no-browser > "$BASE/serve.out" 2> "$BASE/serve.err" &
PID=$!
RUNTIME="$BASE/skm/state/gui/backend.json"
for _ in $(seq 1 300); do
  if [ -s "$RUNTIME" ] && grep -q '^GUI_URL ' "$BASE/serve.out" 2>/dev/null; then break; fi
  kill -0 "$PID" 2>/dev/null || { echo "SMOKE: gui serve exited" >&2; cat "$BASE/serve.err" >&2; exit 1; }
  sleep 0.1
done
[ -s "$RUNTIME" ] || { echo "SMOKE: no backend.json after 30 s" >&2; cat "$BASE/serve.err" >&2; exit 1; }

python3 - "$RUNTIME" <<'PY'
import json
import sys
import urllib.request

info = json.load(open(sys.argv[1], encoding="utf-8"))
base = f"http://127.0.0.1:{info['port']}"
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def call(method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(base + path, data=data, method=method, headers={
        "Authorization": f"Bearer {info['session_secret']}", "Content-Type": "application/json"})
    with opener.open(request, timeout=120) as response:
        return response.status, json.loads(response.read())


status, bootstrap = call("GET", "/v1/bootstrap")
assert status == 200 and bootstrap["epoch"] == info["epoch"], bootstrap
status, catalog = call("GET", "/v1/ui/contributions")
owners = [entry["owner"] for entry in catalog["contributions"]]
assert status == 200 and "gui-hub" in owners, catalog["rejected"]
status, units = call("POST", "/v1/queries/gui-hub.units", {"context": {}, "params": {}})
assert status == 200 and units["view"] == "resource-list" and units["rows"], units
print(f"smoke: OK (backend {bootstrap['backend']['version']}, owners {', '.join(owners)}, {len(units['rows'])} units)")
PY
