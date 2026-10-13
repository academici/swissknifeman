#!/usr/bin/env bash
# smoke-installed.sh — smoke test of the installed form: the CLIs from the bin directory and the plugins from a copy of
# the plugin cache, not from the checkout.
#
# Usage:
#   scripts/dev-sandbox.sh run "$SB" -- bash scripts/smoke-installed.sh
#   smoke-installed.sh --check-plugin DIR [--name NAME]   check one plugin copy (used by the tests)
#   smoke-installed.sh -h|--help
#
# Steps (inside a sandbox only):
#   1. `swissknifeman install --profile full --bin-dir $HOME/.local/bin --force`; every CLI of the profile answers
#      `--help` with exit 0 from an empty temporary directory.
#   2. `swissknifeman doctor --json` from a temporary directory yields an umbrella-doctor/v1 document (failed checks
#      are allowed; unparsable output or a document off the schema is not).
#   3. Every marketplace entry whose source is not ./ is copied as `git archive HEAD <source>` into
#      $HOME/.claude/plugins/cache/swissknifeman/<name>/<version>/ and checked there: plugin.json parses, every manifest
#      path and every ${CLAUDE_PLUGIN_ROOT} path of plugin.json, hooks/hooks.json and commands/*.md exists inside the
#      copy, no executable reference leaves the plugin root, and every hook script of hooks.json runs with
#      CLAUDE_PLUGIN_ROOT set to the copy and `{}` on stdin without a missing-file error (exit 126 and 127 fail).
#   4. Entries with source ./ and skills[]: every path of skills[] exists in `git archive HEAD`.
#
# It refuses to run unless HOME is not the real home and SKM_HOME is set inside the temporary directory. The plugin
# copies are made from HEAD: commit changes of plugin files before the run. No provider CLI (claude, codex, grok) runs.
# Output: `smoke-installed OK (<n> cli, <m> plugins)` or `FAIL <what>` lines.
# Exit: 0 ok, 1 a check failed, 2 usage, 3 refused (not a sandbox).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"

usage() { sed -n '2,/^set -euo pipefail$/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//' >&2; exit 2; }

MODE=smoke
CHECK_DIR=""
CHECK_NAME=""
while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) usage ;;
    --check-plugin) [ $# -ge 2 ] || usage; MODE=plugin; CHECK_DIR="$2"; shift 2 ;;
    --name) [ $# -ge 2 ] || usage; CHECK_NAME="$2"; shift 2 ;;
    *) echo "smoke-installed: unknown argument: $1" >&2; usage ;;
  esac
done
[ -z "$CHECK_NAME" ] || [ "$MODE" = plugin ] || usage

# Refuse anything but a sandbox: the real HOME, or SKM_HOME unset or outside the temporary directory.
real_home="$(python3 -c 'import os, pwd; print(pwd.getpwuid(os.getuid()).pw_dir)' 2>/dev/null || true)"
tmp_root="$(readlink -f "${TMPDIR:-/tmp}")"
skm_home="${SKM_HOME:-}"
refuse() { echo "SKM_DEV_GUARD: smoke-installed.sh $1; run it inside scripts/dev-sandbox.sh" >&2; exit 3; }
[ -n "$real_home" ] || refuse "cannot find the real home"
[ "$(readlink -f "${HOME:-/}")" != "$(readlink -f "$real_home")" ] || refuse "would use the real HOME"
[ -n "$skm_home" ] || refuse "needs SKM_HOME in a temporary directory"
case "$(readlink -m "$skm_home")" in
  "$tmp_root"/*) ;;
  *) refuse "needs SKM_HOME in a temporary directory (got $skm_home)" ;;
esac
case "$(readlink -f "$HOME")" in
  "$tmp_root"/*) ;;
  *) refuse "needs HOME in a temporary directory (got $HOME)" ;;
esac

export SMOKE_REPO_ROOT="$REPO_ROOT" SMOKE_MODE="$MODE" SMOKE_CHECK_DIR="$CHECK_DIR" SMOKE_CHECK_NAME="$CHECK_NAME"
unset PYTHONPATH
exec python3 -I - <<'PY'
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

REPO = Path(os.environ["SMOKE_REPO_ROOT"])
HOME = Path(os.environ["HOME"])
FAILS = []
REF = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}(/[^\s\"'`)\]<>|;&,]*)?")
CLIMB = re.compile(r"[^\s\"'()=;|&<>]*\.\.(?:/[^\s\"'()=;|&<>]*)*")
MANIFEST_KEYS = ("commands", "skills", "agents", "hooks", "mcpServers", "lspServers", "outputStyles")


def fail(text):
    FAILS.append(text)
    print("FAIL " + text, flush=True)


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return exc


def inside(root, path):
    try:
        Path(os.path.normpath(path)).relative_to(os.path.normpath(root))
        return True
    except ValueError:
        return False


def manifest_paths(doc):
    """String paths named by the manifest keys (a string, a list or an object value)."""
    for key in MANIFEST_KEYS:
        value = doc.get(key)
        items = value if isinstance(value, list) else [value]
        for item in items:
            if isinstance(item, str) and (item.startswith("./") or item.startswith("../")):
                yield key, item


def hook_commands(doc):
    """Command strings of a hooks.json document (any nesting)."""
    if isinstance(doc, dict):
        for key, value in doc.items():
            if key == "command" and isinstance(value, str):
                yield value
            else:
                yield from hook_commands(value)
    elif isinstance(doc, list):
        for value in doc:
            yield from hook_commands(value)


def climbs_out(line, start, token, depth):
    """True when a `..` path in the line leaves the plugin root (the base variable counts as the root)."""
    before = line[:start]
    if token.startswith("/") and re.search(r"(dirname|BASH_SOURCE|\$0)[^)]*\)\"?$", before):
        level = depth
    else:
        level = 0
    for part in token.split("/"):
        if part == "..":
            level -= 1
            if level < 0:
                return True
        elif part not in ("", "."):
            level += 1
    return False


def executable_climbs(root, path):
    """Lines of an executable file that climb out of the plugin root, minus the D32 locator block."""
    depth = len(path.relative_to(root).parts) - 1
    hits = []
    skipping = False
    for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if "# --- aicore locator ---" in line:
            skipping = True
        if not skipping:
            for match in CLIMB.finditer(line):
                if climbs_out(line, match.start(), match.group(0), depth):
                    hits.append((number, line.strip()[:120]))
                    break
        if "# --- end aicore locator ---" in line:
            skipping = False
    return hits


def check_plugin(name, root):
    """Check one plugin copy; return the number of failures it added."""
    before = len(FAILS)
    root = Path(root)
    manifest = root / ".claude-plugin" / "plugin.json"
    doc = load_json(manifest) if manifest.is_file() else {}
    if isinstance(doc, Exception):
        fail(f"{name}: plugin.json does not parse: {doc}")
        return len(FAILS) - before
    for key, rel in manifest_paths(doc):
        target = root / rel
        if not inside(root, target):
            fail(f"{name}: plugin.json {key} path leaves the plugin root: {rel}")
        elif not target.exists():
            fail(f"{name}: plugin.json {key} path does not exist in the copy: {rel}")
    sources = [(manifest, manifest.read_text(encoding="utf-8"))] if manifest.is_file() else []
    hooks_file = root / "hooks" / "hooks.json"
    hooks_doc = None
    if hooks_file.is_file():
        hooks_doc = load_json(hooks_file)
        if isinstance(hooks_doc, Exception):
            fail(f"{name}: hooks/hooks.json does not parse: {hooks_doc}")
            hooks_doc = None
        else:
            sources.append((hooks_file, hooks_file.read_text(encoding="utf-8")))
    for md in sorted((root / "commands").glob("*.md")) if (root / "commands").is_dir() else []:
        sources.append((md, md.read_text(encoding="utf-8")))
    for path, text in sources:
        shown = path.relative_to(root)
        for match in REF.finditer(text):
            rel = (match.group(1) or "").lstrip("/")
            target = root / rel
            if not inside(root, target):
                fail(f"{name}: {shown} reference leaves the plugin root: {match.group(0)}")
            elif rel and not target.exists():
                fail(f"{name}: {shown} references a missing path: {match.group(0)}")
    scripts = sorted(p for p in (root / "bin").glob("*") if p.is_file()) if (root / "bin").is_dir() else []
    if hooks_doc is not None:
        for command in hook_commands(hooks_doc):
            for word in command.replace("${CLAUDE_PLUGIN_ROOT}", str(root)).split():
                candidate = Path(word)
                if candidate.is_file() and inside(root, candidate) and candidate not in scripts:
                    scripts.append(candidate)
    for script in scripts:
        for number, text in executable_climbs(root, script):
            fail(f"{name}: {script.relative_to(root)}:{number} leaves the plugin root: {text}")
    installer = root / "install.sh"
    if installer.is_file():
        # the installer runs from a checkout, not from the cache: reported, not failed
        for number, text in executable_climbs(root, installer):
            print(f"WARN {name}: install.sh:{number} climbs out of the plugin root (installer, checkout only): {text}", flush=True)
    if hooks_doc is not None:
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(root))
        for command in hook_commands(hooks_doc):
            expanded = command.replace("${CLAUDE_PLUGIN_ROOT}", str(root))
            try:
                run = subprocess.run(["bash", "-c", expanded], input="{}", capture_output=True, text=True,
                                     cwd=tempfile.gettempdir(), env=env, timeout=60)
            except (OSError, subprocess.SubprocessError) as exc:
                fail(f"{name}: hook did not run ({command}): {exc}")
                continue
            if run.returncode in (126, 127) or "No such file" in run.stderr:
                fail(f"{name}: hook cannot run from the copy ({command}): exit {run.returncode} {run.stderr.strip()[:200]}")
    return len(FAILS) - before


def run(argv, **kwargs):
    return subprocess.run(argv, capture_output=True, text=True, timeout=300, **kwargs)


def smoke():
    cli_count = 0
    plugin_count = 0
    umbrella = REPO / "bin" / "swissknifeman"
    bin_dir = HOME / ".local" / "bin"
    # 1. install the profile, then --help of every CLI from an empty directory
    install = run([str(umbrella), "install", "--profile", "full", "--bin-dir", str(bin_dir), "--force"])
    if install.returncode != 0:
        fail(f"install --profile full exited {install.returncode}: {(install.stderr or install.stdout).strip()[-300:]}")
    profiles = load_json(REPO / "configs" / "install-profiles.json")
    wanted = set(profiles["profiles"]["full"]["units"]) if isinstance(profiles, dict) else set()
    names = ["swissknifeman"]
    for unit_file in sorted((REPO / "packages").glob("*/unit.json")):
        unit = load_json(unit_file)
        if isinstance(unit, dict) and unit.get("id") in wanted:
            names += [Path(cli).name for cli in (unit.get("provides") or {}).get("cli") or ()]
    here = tempfile.mkdtemp(prefix="smoke-cwd-", dir=HOME)
    for cli in sorted(set(names)):
        path = bin_dir / cli
        if not path.exists():
            fail(f"{cli}: not found in {bin_dir}")
            continue
        cli_count += 1
        try:
            help_run = run([str(path), "--help"], cwd=here)
        except (OSError, subprocess.SubprocessError) as exc:
            fail(f"{cli} --help did not run: {exc}")
            continue
        if help_run.returncode != 0:
            fail(f"{cli} --help exited {help_run.returncode}: {(help_run.stderr or help_run.stdout).strip()[-200:]}")
    # 2. doctor --json by schema
    doctor = run([str(bin_dir / "swissknifeman"), "doctor", "--json"], cwd=here)
    try:
        doc = json.loads(doctor.stdout)
    except ValueError:
        doc = None
        fail(f"doctor --json printed no JSON (exit {doctor.returncode}): {(doctor.stderr or doctor.stdout).strip()[-200:]}")
    schema = load_json(REPO / "configs" / "schemas" / "umbrella-doctor.schema.json")
    if doc is not None and not isinstance(schema, Exception):
        item = schema["properties"]["results"]["items"]
        if not isinstance(doc, dict) or doc.get("schema") != "umbrella-doctor/v1":
            fail("doctor --json is not an umbrella-doctor/v1 document")
        else:
            if not set(schema["required"]) <= set(doc) or not set(doc) <= set(schema["properties"]):
                fail("doctor --json keys differ from the schema")
            for row in doc.get("results") or ():
                if not isinstance(row, dict) or not set(item["required"]) <= set(row) \
                        or not set(row) <= set(item["properties"]) \
                        or row.get("status") not in item["properties"]["status"]["enum"]:
                    fail(f"doctor --json result off the schema: {json.dumps(row)[:200]}")
    # 3 and 4. plugins from a copy of the cache layout; skills[] of source ./ entries from git archive
    market = load_json(REPO / ".claude-plugin" / "marketplace.json")
    cache = HOME / ".claude" / "plugins" / "cache" / "swissknifeman"
    for entry in market["plugins"]:
        name, source = entry["name"], entry["source"]
        if source == "./":
            for rel in entry.get("skills") or ():
                if run(["git", "cat-file", "-e", "HEAD:" + rel[2:]], cwd=REPO).returncode != 0:
                    fail(f"{name}: skills[] path is not in git archive HEAD: {rel}")
            continue
        rel = source[2:] if source.startswith("./") else source
        manifest = load_json(REPO / rel / ".claude-plugin" / "plugin.json")
        version = manifest.get("version") if isinstance(manifest, dict) else None
        version = str(version or entry.get("version") or "0.0.0")
        dest = cache / name / version
        dest.mkdir(parents=True, exist_ok=True)
        archive = subprocess.run(["git", "archive", "--format=tar", "HEAD:" + rel], cwd=REPO,
                                 capture_output=True, timeout=300)
        if archive.returncode != 0:
            fail(f"{name}: git archive HEAD:{rel} failed: {archive.stderr.decode(errors='replace').strip()[:200]}")
            continue
        tar_path = dest.parent / (version + ".tar")
        tar_path.write_bytes(archive.stdout)
        with tarfile.open(tar_path) as tar:
            tar.extractall(dest)
        tar_path.unlink()
        plugin_count += 1
        check_plugin(name, dest)
    return cli_count, plugin_count


if os.environ["SMOKE_MODE"] == "plugin":
    target = Path(os.environ["SMOKE_CHECK_DIR"])
    check_plugin(os.environ["SMOKE_CHECK_NAME"] or target.name, target)
    if FAILS:
        sys.exit(1)
    print("smoke-installed plugin OK")
    sys.exit(0)

clis, plugins = smoke()
if FAILS:
    print(f"smoke-installed FAILED ({len(FAILS)} problems)", flush=True)
    sys.exit(1)
print(f"smoke-installed OK ({clis} cli, {plugins} plugins)")
PY
