#!/usr/bin/env bash
# e2e-module-skills.sh [--toml] — end-to-end check that the skills of the host modules reach projects through both
# channels of the host-provided bucket `system` (plugins of the modules, and vendored copies).
#
# Plugin channel: `skiller connect` in a project of type node-package enables the plugins of the modules that stand
# behind the bucket and no longer enables `system@swissknifeman`; a repeated connect with a stale `system@...` key
# replaces it and prints `Replaced:`.
# Vendor channel: `skiller sync` in a second project with the vendor set {buckets: [system]} copies the module skills
# as managed copies (recorded as such in skills-lock.json), honours the CORE `default_exclude`, writes the lock and the
# copy manifest, and `skiller status` reads the copies as one vendor channel. The vendor set is written to
# .swissknifeman/config.json; with --toml it is written to the [skiller.sync] section of .swissknifeman/config.toml
# instead, and the plugin-channel project declares its type in [skiller] there rather than in .swissknife.json.
# Exit 0: everything held. Any other exit: a check failed (a line "e2e-module-skills: FAIL ..." names it) or the call
# is wrong.
#
# It must run in a throwaway HOME (the projects are created under it and the machine configuration is read from it),
# for example inside scripts/dev-sandbox.sh of the development clone, and it writes only inside $HOME.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"

# --- aicore locator ---
# Finds the aicore foundation: $AICORE_ROOT, then <module>/_vendor/aicore, then the sibling <module>/../aicore.
# Canonical copy: packages/aicore/scripts/aicore-locator.sh; copies must stay identical.
_aicore_ok() { [ -f "$1/unit.json" ] && grep -q '"id": *"aicore"' "$1/unit.json"; }
if [ -n "${AICORE_ROOT:-}" ]; then
  _aicore_ok "$AICORE_ROOT" || { echo "AICORE_NOT_FOUND: AICORE_ROOT=$AICORE_ROOT is not an aicore checkout" >&2; exit 2; }
elif _aicore_ok "$REPO_ROOT/_vendor/aicore"; then
  AICORE_ROOT="$REPO_ROOT/_vendor/aicore"
elif _aicore_ok "$REPO_ROOT/../aicore"; then
  AICORE_ROOT="$(cd "$REPO_ROOT/../aicore" && pwd)"
elif _aicore_ok "$REPO_ROOT/packages/aicore"; then
  AICORE_ROOT="$REPO_ROOT/packages/aicore"
else
  echo "AICORE_NOT_FOUND: no aicore in \$AICORE_ROOT, $REPO_ROOT/_vendor/aicore or $REPO_ROOT/../aicore; set AICORE_ROOT" >&2
  exit 2
fi
export AICORE_ROOT
AICORE_LIB="$AICORE_ROOT/lib"
unset -f _aicore_ok
# --- end aicore locator ---

say() { echo "e2e-module-skills: $*" >&2; }
fail() { say "FAIL $*"; exit 1; }

USE_TOML=0
case "${1:-}" in
  "") ;;
  --toml) USE_TOML=1 ;;
  *) echo "usage: e2e-module-skills.sh [--toml]" >&2; exit 2 ;;
esac
[ $# -le 1 ] || { echo "usage: e2e-module-skills.sh [--toml]" >&2; exit 2; }

# Refuse the real home directory (the same test as the development-clone guard).
real_home="$(python3 -c 'import os, pwd; print(pwd.getpwuid(os.getuid()).pw_dir)' 2>/dev/null || true)"
if [ -z "$real_home" ] || [ "$(readlink -f "${HOME:-/}")" = "$(readlink -f "$real_home")" ]; then
  echo "SKM_DEV_GUARD: e2e-module-skills.sh changes the machine configuration; run it with a throwaway HOME (scripts/dev-sandbox.sh)" >&2
  exit 3
fi

SKILLER="$REPO_ROOT/packages/skiller/bin/skiller"
[ -x "$SKILLER" ] || fail "skiller not found: $SKILLER"
export PYTHONPATH="$AICORE_LIB${PYTHONPATH:+:$PYTHONPATH}"

WORK="$(mktemp -d "$HOME/e2e-module-skills.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
LOG="$WORK/out.log"

# --- plugin channel ---
P="$WORK/plugins-project"
mkdir -p "$P"
git -C "$P" init -q
if [ "$USE_TOML" -eq 1 ]; then
  mkdir -p "$P/.swissknifeman"
  printf 'schema_version = 1\n\n[skiller]\nproject_type = "node-package"\n' > "$P/.swissknifeman/config.toml"
else
  printf '{"project_type": "node-package"}\n' > "$P/.swissknife.json"
fi

(cd "$P" && "$SKILLER" connect --no-permissions) > "$LOG" 2>&1 || { cat "$LOG" >&2; fail "connect exited non-zero"; }

check_enabled() {  # check_enabled FILE — the module plugins are on, the bucket plugin is absent
  python3 - "$1" <<'PY' || return 1
import json, sys
enabled = json.load(open(sys.argv[1], encoding="utf-8")).get("enabledPlugins", {})
missing = [n for n in ("maind", "harness", "analyst", "brain") if enabled.get(n + "@swissknifeman") is not True]
if missing:
    sys.exit("module plugins not enabled: " + ", ".join(missing))
if "system@swissknifeman" in enabled:
    sys.exit("system@swissknifeman is still enabled")
PY
}
check_enabled "$P/.claude/settings.local.json" || fail "connect: enabledPlugins"
say "ok connect enables maind, harness, analyst, brain and not system"

# A stale bucket key from an earlier connect is replaced by the module plugins.
python3 - "$P/.claude/settings.local.json" <<'PY'
import json, sys
path = sys.argv[1]
data = json.load(open(path, encoding="utf-8"))
data["enabledPlugins"]["system@swissknifeman"] = True
json.dump(data, open(path, "w", encoding="utf-8"), indent=2)
PY
(cd "$P" && "$SKILLER" connect --no-permissions) > "$LOG" 2>&1 || { cat "$LOG" >&2; fail "second connect exited non-zero"; }
grep -q '^Replaced:' "$LOG" || { cat "$LOG" >&2; fail "second connect did not print Replaced:"; }
check_enabled "$P/.claude/settings.local.json" || fail "second connect: enabledPlugins"
say "ok a stale system@swissknifeman key is replaced"

# --- vendor channel ---
V="$WORK/vendor-project"
mkdir -p "$V/.swissknifeman"
git -C "$V" init -q
if [ "$USE_TOML" -eq 1 ]; then
  printf 'schema_version = 1\n\n[skiller.sync]\nbuckets = ["system"]\n' > "$V/.swissknifeman/config.toml"
else
  printf '{"version": 1, "mode": "vendor", "buckets": ["system"]}\n' > "$V/.swissknifeman/config.json"
fi

(cd "$V" && "$SKILLER" sync) > "$LOG" 2>&1 || { cat "$LOG" >&2; fail "sync exited non-zero"; }

python3 - "$V" <<'PY' || fail "vendor channel"
import json, sys
from pathlib import Path

from aicore.delivery.materialize import MANIFEST, LOCK_FILE

project = Path(sys.argv[1])
skills = project / ".claude" / "skills"
problems = []

delivered = ["local-topology", "swissknifeman-locator", "agent-packs", "session-observer", "brain-locator"]
for name in delivered:
    md = skills / name / "SKILL.md"
    if not md.is_file():
        problems.append(f"{name}: SKILL.md missing")
for name in ("shared-memory", "cross-project-coordinator"):
    if (skills / name).exists():
        problems.append(f"{name}: delivered although CORE default_exclude drops it")
for name in ("context-economy", "anti-drift", "session-handoff", "verify-claims"):
    if not (skills / name / "SKILL.md").is_file():
        problems.append(f"{name}: CORE skill missing")

lock = json.loads((project / LOCK_FILE).read_text(encoding="utf-8")).get("skills", {})
manifest = json.loads((skills / MANIFEST).read_text(encoding="utf-8"))
listed = {s.get("flat_name") for s in manifest.get("skills", [])}
for name in delivered:
    if name not in lock:
        problems.append(f"{name}: not in {LOCK_FILE}")
    elif lock[name].get("managed") is not True:
        problems.append(f"{name}: not recorded as a managed copy in {LOCK_FILE}")
    if name not in listed:
        problems.append(f"{name}: not in {MANIFEST}")

if problems:
    sys.exit("; ".join(problems))
PY
say "ok sync delivers the module skills, honours default_exclude, writes the lock and the manifest"

(cd "$V" && "$SKILLER" status) > "$LOG" 2>&1 || { cat "$LOG" >&2; fail "status exited non-zero"; }
grep -q '^Channel vendor' "$LOG" || { cat "$LOG" >&2; fail "status does not report the vendor channel"; }
say "ok status accepts the delivered skills"

say "PASS"
