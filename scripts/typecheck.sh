#!/usr/bin/env bash
# typecheck.sh — pinned pyright over every packages/*/lib (config in pyrightconfig.json, mode basic).
# Usage: scripts/typecheck.sh [pyright args...]                    plain pyright (config pyrightconfig.json)
#        scripts/typecheck.sh --baseline                           the gate: per-package error counts against
#                                                                  configs/typecheck-baseline.json, strict paths clean
#        scripts/typecheck.sh --update-baseline [--allow-growth "<reason>"]
#                                                                  rewrite the baseline: only smaller counts, a larger
#                                                                  count (or a new baseline) needs --allow-growth
# pyright is a development tool, not a runtime dependency. The version is pinned (PYRIGHT_VERSION, the baseline holds its
# counts): a pyright of another version on PATH is not used. The order is pyright on PATH at the pinned version, then
# `uvx pyright==VERSION`, then `pipx run pyright==VERSION`; exit 2 and TYPECHECK_TOOL_MISSING when none is there.
# Exit: 0 ok, 1 TYPECHECK_REGRESSION / TYPECHECK_STRICT / TYPECHECK_BASELINE_*, 2 usage or no tool.
# Changing PYRIGHT_VERSION moves every count: update the baseline in the same commit with a reason (--allow-growth).
set -euo pipefail

PYRIGHT_VERSION="1.1.414"
CONFIG="${TYPECHECK_CONFIG:-pyrightconfig.json}"  # relative to the hub root; the override is for tests and trials
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYRIGHT=()
select_pyright() {
  if command -v pyright >/dev/null 2>&1 \
    && [ "$(pyright --version 2>/dev/null | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' | head -1)" = "$PYRIGHT_VERSION" ]; then
    PYRIGHT=(pyright)
  elif command -v uvx >/dev/null 2>&1; then
    PYRIGHT=(uvx "pyright==$PYRIGHT_VERSION")
  elif command -v pipx >/dev/null 2>&1; then
    PYRIGHT=(pipx run "pyright==$PYRIGHT_VERSION")
  else
    echo "TYPECHECK_TOOL_MISSING: need pyright $PYRIGHT_VERSION on PATH, uvx or pipx." >&2
    echo "  install:  uv tool install pyright==$PYRIGHT_VERSION   (or: pipx install pyright==$PYRIGHT_VERSION)" >&2
    exit 2
  fi
}

MODE=""
REASON=""
HAVE_REASON=0
ARGS=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    --baseline) MODE="baseline" ;;
    --update-baseline) MODE="update" ;;
    --allow-growth)
      if [ "$#" -lt 2 ] || [ -z "$2" ]; then
        echo "TYPECHECK_USAGE: --allow-growth needs a reason" >&2
        exit 2
      fi
      REASON="$2"; HAVE_REASON=1; shift ;;
    *) ARGS+=("$1") ;;
  esac
  shift
done

if [ -z "$MODE" ]; then
  if [ "$HAVE_REASON" -eq 1 ]; then
    echo "TYPECHECK_USAGE: --allow-growth goes with --update-baseline" >&2
    exit 2
  fi
  select_pyright
  exec "${PYRIGHT[@]}" ${ARGS[@]+"${ARGS[@]}"}
fi
if [ "${#ARGS[@]}" -gt 0 ] || { [ "$MODE" = "baseline" ] && [ "$HAVE_REASON" -eq 1 ]; }; then
  echo "TYPECHECK_USAGE: --baseline and --update-baseline take no pyright arguments (--allow-growth only with --update-baseline)" >&2
  exit 2
fi

select_pyright
WORK="$(mktemp -d "${TMPDIR:-/tmp}/typecheck.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
# pyright exits 1 when it finds errors: the report is what counts, so only a missing or unreadable report is a failure
"${PYRIGHT[@]}" --outputjson -p "$CONFIG" >"$WORK/report.json" 2>"$WORK/stderr.txt" || true

python3 -I - "$MODE" "$WORK/report.json" "$WORK/stderr.txt" "$PYRIGHT_VERSION" "$HAVE_REASON" "$REASON" "$ROOT" "$CONFIG" <<'PY'
import json
import os
import sys

mode, report_path, stderr_path, pinned, have_reason, reason, root, CONFIG = sys.argv[1:9]
BASELINE = "configs/typecheck-baseline.json"


def fail(message, code=1):
    print(message, file=sys.stderr)
    sys.exit(code)


def load(path, label):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError) as exc:
        return fail(f"TYPECHECK_{label}: {path}: {exc}")


def package_of(include_path):
    parts = include_path.strip("/").split("/")
    return parts[1] if len(parts) >= 3 and parts[0] == "packages" and parts[2] == "lib" else None


def count(report, config):
    """({package: errors} over the included libs, [(file, line, message)] of errors in strict paths)."""
    packages = {}
    for entry in config.get("include", []):
        name = package_of(entry)
        if name:
            packages[name] = 0
    strict = [path.rstrip("/") for path in config.get("strict", [])]
    strict_errors = []
    for item in report.get("generalDiagnostics", []):
        if item.get("severity") != "error":
            continue
        path = os.path.relpath(item.get("file", ""), root).replace(os.sep, "/")
        line = item.get("range", {}).get("start", {}).get("line", 0) + 1
        message = (item.get("message") or "").splitlines()[0] if item.get("message") else ""
        if any(path == s or path.startswith(s + "/") for s in strict):
            strict_errors.append((path, line, message))
            continue
        parts = path.split("/")
        name = parts[1] if len(parts) > 1 and parts[0] == "packages" else "(outside packages)"
        packages[name] = packages.get(name, 0) + 1
    return packages, strict_errors


try:
    with open(report_path, encoding="utf-8") as handle:
        report = json.load(handle)
    if not isinstance(report, dict) or "generalDiagnostics" not in report:
        raise ValueError("no generalDiagnostics")
except (OSError, ValueError) as exc:
    try:
        with open(stderr_path, encoding="utf-8", errors="replace") as handle:
            tail = handle.read()[-600:]
    except OSError:
        tail = ""
    fail(f"TYPECHECK_NO_REPORT: pyright gave no JSON report ({exc}) {tail}".rstrip())

config = load(os.path.join(root, CONFIG), "CONFIG")
counts, strict_errors = count(report, config)
for path, line, message in strict_errors:
    print(f"TYPECHECK_STRICT: {path}:{line}: {message}", file=sys.stderr)

baseline_path = os.path.join(root, BASELINE)
baseline = None
if os.path.exists(baseline_path):
    baseline = load(baseline_path, "BASELINE_INVALID")
    if not isinstance(baseline, dict) or not isinstance(baseline.get("errors"), dict):
        fail(f"TYPECHECK_BASELINE_INVALID: {BASELINE}: expected an object with an errors object")
old = baseline["errors"] if baseline else {}

if mode == "baseline":
    if baseline is None:
        fail(f"TYPECHECK_BASELINE_MISSING: {BASELINE} (create it: scripts/typecheck.sh --update-baseline --allow-growth \"<reason>\")")
    if baseline.get("pyright") != pinned:
        fail(f"TYPECHECK_BASELINE_VERSION: {BASELINE} holds pyright {baseline.get('pyright')}, the pin is {pinned}; "
             "counts of two versions are not comparable (update: scripts/typecheck.sh --update-baseline --allow-growth \"<reason>\")")
    bad = bool(strict_errors)
    for name in sorted(counts):
        before, now = old.get(name, 0), counts[name]
        if now > before:
            print(f"TYPECHECK_REGRESSION: {name} {before} -> {now}", file=sys.stderr)
            bad = True
        elif now < before:
            print(f"TYPECHECK_IMPROVED: {name} {before} -> {now} (lock it in: scripts/typecheck.sh --update-baseline)")
    for name in sorted(set(old) - set(counts)):
        print(f"TYPECHECK_IMPROVED: {name} {old[name]} -> 0 (package left the checked set)")
    if bad:
        sys.exit(1)
    print("typecheck: ok (" + ", ".join(f"{name} {counts[name]}" for name in sorted(counts)) + ")")
    sys.exit(0)

# --update-baseline: only smaller counts, growth (or a first baseline) needs the reason
if strict_errors:
    fail("TYPECHECK_STRICT: the baseline is not updated while a strict path has errors")
grown = [(name, old.get(name, 0), counts[name]) for name in sorted(counts) if counts[name] > old.get(name, 0)]
if baseline is None and not have_reason == "1":
    fail("TYPECHECK_REGRESSION: no baseline yet; the first one needs --allow-growth \"<reason>\"")
if grown and have_reason != "1":
    for name, before, now in grown:
        print(f"TYPECHECK_REGRESSION: {name} {before} -> {now}", file=sys.stderr)
    sys.exit(1)
document = {
    "errors": {name: counts[name] for name in sorted(counts)},
    "mode": "basic",
    "pyright": pinned,
}
with open(baseline_path, "w", encoding="utf-8") as handle:
    json.dump(document, handle, indent=2)
    handle.write("\n")
for name in sorted(counts):
    before = old.get(name)
    if before is None or before != counts[name]:
        print(f"TYPECHECK_BASELINE: {name} {before if before is not None else '-'} -> {counts[name]}")
if have_reason == "1":
    print(f"TYPECHECK_BASELINE_REASON: {reason}")
print(f"typecheck: wrote {BASELINE}")
PY
