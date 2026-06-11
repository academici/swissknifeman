#!/usr/bin/env bash
# Check/apply upstream updates for externally-sourced skills.
# A skill is upstream-tracked when its folder contains upstream.json.
# Skills without upstream.json are self-written and never touched.
#
# Exit codes:
#   0  everything up to date (--check) / all eligible changes applied (--apply)
#   1  usage error or malformed upstream.json
#   2  one or more fetch failures (other results still printed/applied)
#  10  --check only: at least one update/notify/conflict found
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

MODE="check"
FORCE=false
JSON_OUT=false
TIMEOUT=30
SKILLS=()

usage() {
  cat <<'EOF'
Usage: scripts/update-upstreams.sh [--check|--apply] [options]

Modes (default --check):
  --check            Fetch upstreams, compare, report. Never writes to the repo.
  --apply            strategy=replace + state=update: overwrite local file,
                     record sha256/fetched_at. strategy=notify: record the seen
                     upstream sha (file untouched) so future runs only report
                     new changes.

Options:
  --skill PATH       Limit to one skill, e.g. imported/ai-agents (repeatable)
  --force            In --apply, also overwrite files in conflict state
  --json             Machine-readable JSON to stdout (human report to stderr)
  --timeout SEC      Fetch timeout per file (default 30)
  -h, --help         Show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check) MODE="check"; shift ;;
    --apply) MODE="apply"; shift ;;
    --skill) SKILLS+=("$2"); shift 2 ;;
    --force) FORCE=true; shift ;;
    --json) JSON_OUT=true; shift ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

export UPSTREAM_MODE="$MODE" UPSTREAM_FORCE="$FORCE" UPSTREAM_JSON="$JSON_OUT" \
       UPSTREAM_TIMEOUT="$TIMEOUT" UPSTREAM_SKILLS="${SKILLS[*]:-}"

python3 - "$REPO_ROOT" <<'PY'
import hashlib, json, os, sys, time, urllib.request, urllib.error
from datetime import date
from pathlib import Path

root = Path(sys.argv[1])
mode = os.environ["UPSTREAM_MODE"]
force = os.environ["UPSTREAM_FORCE"] == "true"
json_out = os.environ["UPSTREAM_JSON"] == "true"
timeout = int(os.environ["UPSTREAM_TIMEOUT"])
only = set(filter(None, os.environ["UPSTREAM_SKILLS"].split()))

report = sys.stderr if json_out else sys.stdout
results = {"checked": 0, "updates": [], "drift": [], "conflicts": [],
           "notify": [], "applied": [], "noted": [], "failures": []}


def skill_id(skill_dir):
    """Bucket-relative id: imported/ai-agents, devops/docker/php, generate-skill."""
    rel = skill_dir.relative_to(root)
    parts = rel.parts
    return "/".join(parts[1:]) if parts[0] == "skills" else str(rel)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def fetch(url):
    """Return CRLF-normalized UTF-8 bytes. Raises on failure."""
    headers = {"User-Agent": "swissknifeman-upstream-sync"}
    token = os.environ.get("GITHUB_TOKEN", "")
    if token and url.startswith("https://raw.githubusercontent.com/"):
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            break
        except urllib.error.HTTPError as e:
            if attempt == 1 and (e.code == 429 or 500 <= e.code < 600):
                time.sleep(2)
                continue
            raise
    text = raw.decode("utf-8")  # UnicodeDecodeError -> caller reports [fail]
    return text.replace("\r\n", "\n").encode("utf-8")


def line(tag, sid, fname, msg):
    print(f"[{tag}]".ljust(11) + sid.ljust(28) + fname.ljust(16) + msg, file=report)


# --- discover ---------------------------------------------------------------
configs = sorted(root.glob("skills/**/upstream.json"))
meta = root / "generate-skill/upstream.json"
if meta.exists():
    configs.append(meta)

if only:
    configs = [c for c in configs if skill_id(c.parent) in only]
    missing = only - {skill_id(c.parent) for c in configs}
    if missing:
        print(f"ERROR: no upstream.json for skill(s): {', '.join(sorted(missing))}",
              file=sys.stderr)
        sys.exit(1)

# --- validate configs before any fetching ------------------------------------
parsed = []
for cfg in configs:
    sid = skill_id(cfg.parent)
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"ERROR: {cfg.relative_to(root)}: invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)
    if data.get("schema_version") != 1 or data.get("strategy") not in ("replace", "notify") \
            or not isinstance(data.get("files"), list) or not data["files"]:
        print(f"ERROR: {cfg.relative_to(root)}: malformed (run scripts/validate.sh)",
              file=sys.stderr)
        sys.exit(1)
    parsed.append((cfg, sid, data))

# --- process -----------------------------------------------------------------
today = date.today().isoformat()

for cfg, sid, data in parsed:
    skill_dir = cfg.parent
    strategy = data["strategy"]
    changed = False

    for entry in data["files"]:
        fname = entry["path"]
        local_path = skill_dir / fname
        stored = entry.get("sha256", "")
        results["checked"] += 1

        try:
            remote = fetch(entry["url"])
        except Exception as e:
            code = getattr(e, "code", None)
            err = f"HTTP {code}" if code else str(e)
            line("fail", sid, fname, f"fetch failed: {err}")
            results["failures"].append({"skill": sid, "file": fname, "error": err})
            continue

        remote_sha = sha256_bytes(remote)
        local_sha = sha256_bytes(local_path.read_bytes()) if local_path.exists() else ""

        def record():
            entry["sha256"] = remote_sha
            entry["fetched_at"] = today

        def write_local():
            tmp = local_path.with_suffix(local_path.suffix + ".tmp")
            tmp.write_bytes(remote)
            os.replace(tmp, local_path)

        if strategy == "notify":
            if remote_sha == stored:
                line("ok", sid, fname, "up-to-date")
            else:
                what = "baseline missing" if not stored \
                    else f"upstream changed ({stored[:8]}.. -> {remote_sha[:8]}..)"
                if mode == "apply":
                    record(); changed = True
                    line("noted", sid, fname,
                         f"{what}; sha recorded, file untouched — review manually: {entry['url']}")
                    results["noted"].append({"skill": sid, "file": fname,
                                             "new_sha": remote_sha, "url": entry["url"]})
                else:
                    line("notify", sid, fname, f"{what}; strategy=notify, review manually")
                    results["notify"].append({"skill": sid, "file": fname,
                                              "old_sha": stored, "new_sha": remote_sha})
            continue

        # strategy == replace
        local_clean = (local_sha == stored) or not stored or not local_path.exists()
        upstream_new = remote_sha != stored
        in_sync = local_path.exists() and local_sha == remote_sha

        if in_sync:
            if remote_sha != stored:  # content matches but sha never recorded
                if mode == "apply":
                    record(); changed = True
                    line("noted", sid, fname, "sha recorded (content already in sync)")
                    results["noted"].append({"skill": sid, "file": fname, "new_sha": remote_sha})
                else:
                    line("update", sid, fname, "sha not recorded yet (content in sync)")
                    results["updates"].append({"skill": sid, "file": fname,
                                               "old_sha": stored, "new_sha": remote_sha})
            else:
                line("ok", sid, fname, "up-to-date")
        elif upstream_new and local_clean:
            if mode == "apply":
                write_local(); record(); changed = True
                line("applied", sid, fname, f"replaced ({remote_sha[:8]}..)")
                results["applied"].append({"skill": sid, "file": fname, "new_sha": remote_sha})
            else:
                line("update", sid, fname,
                     f"upstream changed ({stored[:8] or 'none'}.. -> {remote_sha[:8]}..)")
                results["updates"].append({"skill": sid, "file": fname,
                                           "old_sha": stored, "new_sha": remote_sha})
        elif upstream_new and not local_clean:
            if mode == "apply" and force:
                write_local(); record(); changed = True
                line("applied", sid, fname, f"replaced with --force ({remote_sha[:8]}..)")
                results["applied"].append({"skill": sid, "file": fname,
                                           "new_sha": remote_sha, "forced": True})
            else:
                line("conflict", sid, fname,
                     "local drift + upstream change (use --apply --force)")
                results["conflicts"].append({"skill": sid, "file": fname})
        else:  # upstream unchanged, local edited
            line("drift", sid, fname, "local modified since last fetch")
            results["drift"].append({"skill": sid, "file": fname})

    if changed:
        tmp = cfg.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        os.replace(tmp, cfg)

# --- summary -----------------------------------------------------------------
s = results
print(f"Summary: {s['checked']} checked | {len(s['updates'])} update | "
      f"{len(s['drift'])} drift | {len(s['conflicts'])} conflict | "
      f"{len(s['notify'])} notify | {len(s['applied'])} applied | "
      f"{len(s['noted'])} noted | {len(s['failures'])} failed", file=report)

if (s["applied"] or s["noted"]) and not json_out:
    print("Run ./sync.sh --update-registry to refresh skills.json", file=report)

if json_out:
    print(json.dumps(results, indent=2, ensure_ascii=False))

if s["failures"]:
    sys.exit(2)
if mode == "check" and (s["updates"] or s["notify"] or s["conflicts"]):
    sys.exit(10)
if mode == "apply" and s["conflicts"] and not force:
    sys.exit(10)
sys.exit(0)
PY
