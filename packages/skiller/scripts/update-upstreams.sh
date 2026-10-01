#!/usr/bin/env bash
# Check/apply upstream updates for externally-sourced skills.
# A skill is upstream-tracked when its folder contains upstream.json.
# Skills without upstream.json are self-written and never touched.
#
# body_path (P7.3 thin-navigator, additive): sha/drift is always computed per
# files[].path — that already works for ANY local path, not just "SKILL.md" (see
# strategy=fork, whose files[].path conventionally points at a pristine mirror in
# references/). body_path just names, explicitly, WHICH files[].path entry is "the
# body" when SKILL.md itself has become a hand-written navigator that this script
# must never overwrite. No dedicated sha/drift code path exists (or is needed) for
# it — the generic per-file loop below already does the right thing once the entry
# points at body_path instead of SKILL.md.
#
# Exit codes (total order: 2 > 10 > 11 > 0 — code is one, so the older one extinguishes
# junior; machine consumer takes the FULL picture from --json, where blocks
# triage/stale_verdicts are always present):
#   0  everything up to date (--check) / all eligible changes applied (--apply)
#   1  usage error or malformed upstream.json
#   2  one or more fetch failures (other results still printed/applied)
#  10  --check only: at least one update/notify/conflict found
#  11  --check only: triage findings in bundle CONTENT (see block triage below);
#      intentionally NOT 10 — «upstream has changed» and «in the bundle there is a suspicious pattern»
#      different events, merging would make it impossible for the operator to distinguish between them
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
                     Additionally drives TRIAGE of the bundle contents (local,
                     without network): rough patterns of four threat classes. Nakhodki →
                     exit code 11 (not 10). Triage is NOT a trust boundary -
                     no findings != safe, the only limit is human
                     bundle audit (docs/guide/vendored-skills.md). Gate there
                     verdict: AUDIT_MISSING (block audit no) and AUDIT_STALE
                     (verdict against other bytes; --apply does not extinguish it).
  --apply            strategy=replace: overwrite local file, record sha256/fetched_at.
                     strategy=notify: record the seen upstream sha (file untouched).
                     strategy=fork: stage upstream as upstream/<name>.incoming and set
                     review_pending=true (mirror + wrapper SKILL.md untouched) for manual port.
                     strategy=merge: on ANY origin drift set merge.review_pending=true
                     (SKILL.md untouched) — composite is re-merged by the agent manually.
  --resolve          strategy=fork: promote staged incoming to the mirror; strategy=merge:
                     record fresh sha256/fetched_at for all origins. Both clear
                     review_pending + set last_review. Run AFTER porting/merging upstream
                     changes into the (wrapper/composite) SKILL.md.

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
    --resolve) MODE="resolve"; shift ;;
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
import hashlib, json, os, re, shutil, subprocess, sys, time, urllib.request, urllib.error
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
           "notify": [], "applied": [], "noted": [], "failures": [],
           "triage": [], "stale_verdicts": [], "reference_only": []}

# Verbatim disclaimer. Printed in BOTH channels: human and --json
# (in a separate key, not just in prose) — to «scan green» was impossible
# quote as «bundles are safe» neither man nor machine.
TRIAGE_DISCLAIMER = (
    "no findings != safe: triage is a pattern scan, NOT a trust boundary. "
    "An empty result does not mean that the bundle is safe: RAG:v 2026-06 CSA/Trail of Bits "
    "«AI Agent Skill Scanners: Bypassed Across the Board» — scanners bypassed "
    "(whitespace inflation, precompiled bytecode, archive indirection, social engineering "
    "LLM-steps), output verbatim «Don't outsource trust to a scanner». The only one "
    "border - human audit of ALL bundle files (docs/guide/vendored-skills.md)."
)


def skill_id(skill_dir):
    """Bucket-relative id: imported/ai-agents, devops/docker/php, generate-skill."""
    rel = skill_dir.relative_to(root)
    parts = rel.parts
    return "/".join(parts[1:]) if parts[0] == "skills" else str(rel)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


_HAS_GH = shutil.which("gh") is not None and \
    os.environ.get("UPSTREAM_NO_GH", "") != "1"
_RAW_RE = re.compile(
    r"^https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.+)$")


def _normalize(raw):
    return raw.decode("utf-8").replace("\r\n", "\n").encode("utf-8")


def fetch_gh(owner, repo, ref, path):
    """Spot fetch one file via GitHub CLI: one file, auto-authentication
    (gh auth), respects rate-limit — saves context vs. full loading.
    Returns bytes or raises an exception (caller will roll back to urllib)."""
    out = subprocess.run(
        ["gh", "api", f"repos/{owner}/{repo}/contents/{path}",
         "-f", f"ref={ref}", "-q", ".content"],
        capture_output=True, text=True, timeout=timeout, check=True)
    import base64
    return _normalize(base64.b64decode(out.stdout))


def fetch(url):
    """Return CRLF-normalized UTF-8 bytes. Raises on failure.

    For GitHub raw-URL and available `gh` pulls through `gh api .../contents`
    (auto-authentication, rate-limit). Otherwise/on failure - urllib with GITHUB_TOKEN."""
    m = _RAW_RE.match(url)
    if m and _HAS_GH:
        try:
            return fetch_gh(*m.groups())
        except Exception:
            pass  # gh not available/error - silent rollback to urllib below
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
    return _normalize(raw)  # UnicodeDecodeError -> caller reports [fail]


def line(tag, sid, fname, msg):
    print(f"[{tag}]".ljust(11) + sid.ljust(28) + fname.ljust(22) + " " + msg, file=report)


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
    if data.get("schema_version") != 1 \
            or data.get("strategy") not in ("replace", "notify", "fork", "merge") \
            or not isinstance(data.get("files"), list) or not data["files"]:
        print(f"ERROR: {cfg.relative_to(root)}: malformed (run scripts/validate.sh)",
              file=sys.stderr)
        sys.exit(1)
    # body_path (P7.3 thin-navigator): if specified MUST match path one of
    # files[]-records - otherwise declared «body» is not actually tracked either sha, neither
    # drift (quiet hole). Not a file check (existence/escape — validate.sh),
    # structural only: files[] really tracks what body_path declares as a body.
    bp = data.get("body_path")
    if bp is not None and bp not in {f.get("path") for f in data["files"]}:
        print(f"ERROR: {cfg.relative_to(root)}: body_path '{bp}' not in files[].path "
              f"(run scripts/validate.sh)", file=sys.stderr)
        sys.exit(1)
    parsed.append((cfg, sid, data))

# --- triage: informative scan of the bundle --------------------------------
# WHAT IS THIS. The stage reads the LOCAL contents of the bundle (all files next to
# upstream.json, except himself) and looks for crude patterns of four threat classes.
# No network needed: drift catches the main loop, triage catches the content.
#
# WHAT IT IS NOT. The limit of trust. First-party skill scanner
# Anthropic no, its instructions are «thoroughly audit it before use», that is
# HUMAN reading of all bundle files
# (https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills).
# CSA/Trail of Bits (2026-06) showed a bypass ClawHub/Cisco/skills.sh simple
# techniques; conclusion verbatim «Don't outsource trust to a scanner»
# (https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-agent-skill-scanner-bypass-20260610-csa/).
# Therefore: PATTERN set (not IOC — public IOC-sheet exactly according Agent Skills
# no), LLM-stage and YARA are not entered (first named CSA required social
# engineering'ohm, the second is an external dependency, prohibited root.engineering-invariants).
#
# PROVENANCE OF RULES. The set was derived from a one-time human audit of 56 vendors
# bundles (P5.1), and not
# made up before reading: rule PRM_REMOTE_INSTRUCTIONS exists precisely because
# audit found a living carrier of this pattern. Pattern Sources - docs/reference.md.
#
# Each rule carries a threat class; a rule without a named class is not added.
TRIAGE_RULES = [
    # --- Class 1: prompt injection ------------------------------------------
    # Hidden instruction inside a trusted artifact (prose, commentary, fan):
    # «skill-based prompt injection». Class source: Anthropic engineering post +
    # heeler.com/resource/introducing-agent-skills-security-...
    ("INJ_IGNORE", "prompt-injection",
     r"(?i)ignore\s+(?:all\s+|the\s+)*(?:previous|prior|preceding|above)\s+"
     r"(?:instructions|prompts|rules)",
     "instructions «forget previous instructions» — classic interception"),
    ("INJ_DISREGARD", "prompt-injection",
     r"(?i)disregard\s+(?:all\s+|the\s+)*(?:previous|prior|above|your)\s+"
     r"(?:instructions|rules|system|prompt)",
     "instructions «ignore your rules» — interception via synonym"),
    ("INJ_HIDE_FROM_USER", "prompt-injection",
     r"(?i)(?:do not|don't|never)\s+(?:tell|inform|show|reveal|mention)\s+"
     r"(?:the\s+)?user",
     "requirement to hide an action from the user - a sign of hidden behavior"),
    ("INJ_ROLE_OVERRIDE", "prompt-injection",
     r"(?i)(?:you\s+are\s+now\s+\w|new\s+system\s+prompt\s*:|system\s+override\s*:)",
     "role substitution/system prompt directly in the body of the skill"),
    ("INJ_INVISIBLE_CHAR", "prompt-injection",
     "[​-‏⁠-⁤‪-‮﻿]",
     "invisible/formatting symbols - a carrier of text hidden from the reader"),

    # --- Class 2: data exfiltration -----------------------------------------
    # Conjunctive rules (access secret AND network output in one line):
    # lone mention `.env` — is normal for docks and produces noise, not a signal.
    ("EXF_SUSPECT_HOST", "data-exfiltration",
     r"(?i)https?://[^\s\"'`)<>]*"
     r"(?:webhook\.site|\.ngrok\.|ngrok\.io|pastebin\.com|transfer\.sh|0x0\.st|"
     r"requestbin|burpcollaborator|oast\.|interact\.sh)",
     "ephemeral/tunnel data receiver - typical exfiltration drain"),
    ("EXF_CRED_TO_NET", "data-exfiltration",
     r"(?i)(?:~/\.ssh/id_|\.aws/credentials|\.netrc|/etc/(?:passwd|shadow)|"
     r"API_KEY|SECRET_KEY|PRIVATE_KEY)[^\n]{0,120}"
     r"(?:curl|wget|requests\.(?:post|put)|fetch\(|axios\.(?:post|put)|nc\s+-)",
     "read secret and network call in one line - upload credentials"),
    ("EXF_ENV_DUMP", "data-exfiltration",
     r"(?i)(?:printenv|\benv\b)\s*\|\s*(?:curl|wget|nc\b|base64)",
     "environment dump going to the network or encoding - collection env-variables"),

    # --- Class 3: malicious code execution ----------------------------------
    ("EXE_PIPE_TO_SHELL", "code-execution",
     r"(?i)(?:curl|wget)\s[^\n|]*\|\s*(?:sudo\s+)?(?:ba|z|k)?sh\b",
     "remote code execution: deleted payload directly to the interpreter"),
    ("EXE_B64_EXEC", "code-execution",
     r"(?i)(?:eval|exec)\s*\(\s*(?:base64|b64decode|atob|codecs\.decode)|"
     r"base64\s+(?:-d|--decode)[^\n]{0,60}\|\s*(?:ba)?sh\b",
     "execution base64-obfuscated code - hiding payload"),
    ("EXE_OBFUSC_BLOB", "code-execution",
     r"[A-Za-z0-9+/]{240,}={0,2}",
     "long base64-such a blob is a carrier of hidden code/data"),

    # --- Class 4: over-permissive tool use ----------------------------------
    ("PRM_TOOL_WILDCARD", "over-permissive-tools",
     r"(?im)^\s*allowed[-_]tools\s*:.*(?:\*|Bash\s*\()",
     "skill requires rights wider than assignment (wildcard/Bash in allowed-tools)"),
    ("PRM_PERMISSION_BYPASS", "over-permissive-tools",
     r"(?i)--dangerously-skip-permissions|bypassPermissions",
     "agent permission gate bypass"),
    # Found by audit P5.1 on the live bundle: the skill instructs to GO ONLINE and
    # apply what was received AS RULES. The instruction channel then lives outside the bundle,
    # sha256 does not cover it, the version is not pinned - exactly rug-pull-class which
    # CSA recommends closing with a version pin.
    ("PRM_REMOTE_INSTRUCTIONS", "over-permissive-tools",
    # Cyrillic branch remains defense-in-depth for upstream-content in Russian.
     r"(?i)(?:(?:fetch|load|download|retrieve)[^\n]{0,80}"
     r"(?:latest|fresh|current)[^\n]{0,60}(?:guidelines|rules|instructions)"
     r"|fetched\s+(?:content|guidelines|file)[^\n]{0,80}"
     r"(?:contains|are)\s+(?:all\s+)?the\s+(?:rules|instructions)"
     r"|(?:received|loading|jumping)\w*[^\n]{0,80}(?:relevant|fresh)\w*[^\n]{0,60}"
     r"(?:rules|instructions|specified)\w*"
     r"|(?:loaded|received)\w*\s+(?:content|contents|file)[^\n]{0,80}"
     r"(?:contains|carries)[^\n]{0,40}(?:rules|instructions)\w*)",
     "executable instructions are pulled from the network - out of coverage sha256"),
]

TRIAGE_COMPILED = [(code, cls, re.compile(rx), why)
                   for code, cls, rx, why in TRIAGE_RULES]


def triage_bundle(skill_dir, sid):
    """Run rules against ALL local bundle files. Returns a list of finds.

    Binary/unreadable files are not silently skipped: they are found
    class `unreadable` — «could not read» and «clean» are not the same thing."""
    found = []
    for path in sorted(p for p in skill_dir.rglob("*") if p.is_file()):
        if path.name == "upstream.json":
            continue
        rel = str(path.relative_to(skill_dir))
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as e:
            found.append({"skill": sid, "file": rel, "rule": "BIN_UNREADABLE",
                          "class": "unreadable", "hits": 1,
                          "why": f"file not read as UTF-8 ({e.__class__.__name__}) — "
                                 f"content NOT verified"})
            continue
        for code, cls, rx, why in TRIAGE_COMPILED:
            hits = len(rx.findall(text))
            if hits:
                found.append({"skill": sid, "file": rel, "rule": code,
                              "class": cls, "hits": hits, "why": why})
    return found


# --- human verdict: the carrier and its gate (P5.11, thread (B) OQ-6) ------------
# WHY. The triage above is a pattern scan, the limit of trust remains HUMAN
# bundle audit (TRIAGE_DISCLAIMER). One-time audit without machine media
# is depreciated structurally: «not checked» and «clean» are machine indistinguishable, and
# mark «the verdict is rotten» was a DERIVATIVE from drift and died from the first
# --apply (boundary named in block stale_verdicts below). Media - additive
# block `audit` in upstream.json next to the bundle: he survives the plan (plan file
# is mortal, the skill is heard further) and does not establish connections «skiller reads plans/**».
# Provenance rules and branch parsing - docs/guide/vendored-skills.md,
#.
#
# THREE DIFFERENT EVENTS - three different signals (the same principle that code 11 does not
# merged with 10): «upstream has moved» (updates/notify) · «no verdict NEVER
# was» (AUDIT_MISSING) · «verdict against OTHER bytes» (AUDIT_STALE).
#
# ANCHOR. audit.upstream_sha is stored SEPARATELY from files[].sha256 and is not updated
# neither --apply, neither --resolve — this is why the mark survives application
# upstream. It describes those bytes against which the verdict was made: sha256
# NAMED body (body_path), when the bundle calls it, otherwise - convolution of the entire
# provenance base (pairs path:sha256 from files[]/origins[]).
AUDIT_VERDICTS = ("clean", "attention", "risk")


def is_reference_only(data):
    """Bundle that does not vendor ANYTHING: everything files[].path are empty - records are
    provenance LINKS to external specs, there are no local mirrors. Machine sign
    (not an opinion); for such a bundle there is no need to anchor the verdict, and the gate does not
    requires - otherwise the rule would lie in the class, for the sake of whose honesty it was created."""
    files = data.get("files") or []
    return bool(files) and all(not e.get("path") for e in files)


def audit_anchor(data):
    """Bytes against which the verdict was given. None — nothing to anchor (reference-only)."""
    if is_reference_only(data):
        return None
    body_path = data.get("body_path")
    if body_path:
        for entry in data.get("files", []):
            if entry.get("path") == body_path:
                return entry.get("sha256", "")
    entries = list(data.get("files", [])) + list(data.get("origins", []))
    base = "".join(f"{e.get('path', '')}:{e.get('sha256', '')}\n"
                   for e in sorted(entries, key=lambda x: x.get("path", "")))
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def audit_findings(sid, data):
    """Findings of the verdict gate. The shape is the same as the triage (code 11, --json)."""
    audit = data.get("audit")
    if not isinstance(audit, dict):
        return [{"skill": sid, "file": "upstream.json", "rule": "AUDIT_MISSING",
                 "class": "unaudited", "hits": 1,
                 "why": "there is no human verdict on the bundle - «not checked» and "
                        "«clean» are not the same thing; read the entire bundle and "
                        "write block audit (docs/guide/vendored-skills.md)"}]
    anchor = audit_anchor(data)
    if anchor is None:
        return []
    stored = audit.get("upstream_sha", "")
    if stored == anchor:
        return []
    verdict = audit.get("verdict", "?")
    at = audit.get("at", "?")
    seen = f"{stored[:8]}.." if stored else "anchor not recorded"
    return [{"skill": sid, "file": "upstream.json", "rule": "AUDIT_STALE",
             "class": "stale-verdict", "hits": 1,
             "why": f"verdict '{verdict}' from {at} moved against other bytes "
                    f"({seen} -> {anchor[:8]}..) — re-read the bundle and update the block "
                    f"audit; mark does NOT go out from --apply"}]


# --- process -----------------------------------------------------------------
today = date.today().isoformat()

if mode == "check":
    for cfg, sid, data in parsed:
        if is_reference_only(data):
            results["reference_only"].append(sid)
        for finding in triage_bundle(cfg.parent, sid) + audit_findings(sid, data):
            results["triage"].append(finding)
            line("triage", sid, finding["file"],
                 f"{finding['rule']} ({finding['class']}) x{finding['hits']} — "
                 f"{finding['why']}")

for cfg, sid, data in parsed:
    skill_dir = cfg.parent
    strategy = data["strategy"]
    changed = False

    # --- merge: composite of origins[] (base + supplement). Drift of ANY source →
    #     manual agent-merge: --check reports, --apply raises merge.review_pending
    #     (gate in validate.sh), --resolve captures fresh sha and removes the flag. Mirror
    #     is not overwritten by one file - the composite is glued together by the agent manually. ---
    if strategy == "merge":
        mp = data.setdefault("merge", {})
        for k, org in enumerate(data.get("origins", [])):
            results["checked"] += 1
            label = org.get("repo", f"origin{k}")
            role = org.get("role", "?")
            try:
                remote = fetch(org["url"])
            except Exception as e:
                code = getattr(e, "code", None)
                err = f"HTTP {code}" if code else str(e)
                line("fail", sid, label, f"fetch failed: {err}")
                results["failures"].append({"skill": sid, "file": label, "error": err})
                continue
            remote_sha = sha256_bytes(remote)
            stored = org.get("sha256", "")
            if mode == "resolve":
                org["sha256"] = remote_sha
                org["fetched_at"] = today
                changed = True
                line("resolved", sid, label, f"origin sha updated ({role})")
            elif remote_sha == stored:
                line("ok", sid, label, f"up-to-date (merge/{role})")
            else:
                what = "baseline missing" if not stored \
                    else f"origin changed ({stored[:8]}.. -> {remote_sha[:8]}..)"
                if mode == "apply":
                    mp["review_pending"] = True
                    changed = True
                    line("staged", sid, label,
                         f"{what}; merge.review_pending=true — re-merge "
                         f"sources in SKILL.md manually, then --resolve")
                    results["noted"].append({"skill": sid, "file": label,
                                             "new_sha": remote_sha, "url": org["url"]})
                else:  # check
                    line("notify", sid, label,
                         f"{what}; strategy=merge — manual agent-merge")
                    results["notify"].append({"skill": sid, "file": label,
                                              "old_sha": stored, "new_sha": remote_sha})
        if mode == "resolve" and changed:
            mp["review_pending"] = False
            mp["last_review"] = today

    for entry in ([] if strategy == "merge" else data["files"]):
        fname = entry["path"]
        local_path = skill_dir / fname
        stored = entry.get("sha256", "")
        results["checked"] += 1

        # Entry with empty path — provenance-LINK (url leads to spec/doku, alien
        # code is not vendored), and not a local mirror. The scheme allows such a notation
        # (path without minLength), and she lives in the registry (skills/voice-ai/voice-ai).
        # Previously `skill_dir / ""` resolved to the CATALOG ITSELF and `read_bytes()` dropped
        # entire run IsADirectoryError'ohm - a quiet pit that extinguished --check in its entirety.
        # Check by sha there is nothing here: we inform it explicitly and move on (not «ok»).
        if not fname:
            line("ref", sid, "(no mirror)",
                 f"reference-only provenance, sha is not verified: {entry['url']}")
            continue

        # --- fork --resolve: advance pre-prepared incoming in the mirror and remove
        #     flag. No network needed (work with already downloaded upstream/<name>.incoming). ---
        if mode == "resolve":
            if strategy != "fork":
                line("skip", sid, fname, "--resolve only applies to strategy=fork")
                continue
            incoming_path = skill_dir / "upstream" / \
                f"{Path(fname).stem}.incoming{Path(fname).suffix}"
            if not incoming_path.exists():
                line("skip", sid, fname, "no staged incoming (first --apply)")
                continue
            new_bytes = incoming_path.read_bytes()
            local_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = local_path.with_suffix(local_path.suffix + ".tmp")
            tmp.write_bytes(new_bytes); os.replace(tmp, local_path)
            entry["sha256"] = sha256_bytes(new_bytes)
            entry["fetched_at"] = today
            data["review_pending"] = False
            data["last_review"] = today
            incoming_path.unlink()
            changed = True
            line("resolved", sid, fname, "mirror updated, review_pending removed")
            results["applied"].append({"skill": sid, "file": fname,
                                        "new_sha": entry["sha256"], "resolved": True})
            continue

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

        if strategy == "fork":
            # Mirror (= files[].path, pristine-copy of upstream) and wrapper SKILL.md DO NOT touch.
            # On the drift we put a fresh upstream in upstream/<name>.incoming and raise the flag -
            # agent verifies diff, transfers changes to the wrapper, then --resolve.
            incoming_path = skill_dir / "upstream" / \
                f"{Path(fname).stem}.incoming{Path(fname).suffix}"
            if remote_sha == stored:
                line("ok", sid, fname, "up-to-date (fork)")
            else:
                what = "baseline missing" if not stored \
                    else f"upstream changed ({stored[:8]}.. -> {remote_sha[:8]}..)"
                if mode == "apply":
                    incoming_path.parent.mkdir(parents=True, exist_ok=True)
                    tmp = incoming_path.with_suffix(incoming_path.suffix + ".tmp")
                    tmp.write_bytes(remote); os.replace(tmp, incoming_path)
                    data["review_pending"] = True
                    changed = True
                    line("staged", sid, fname,
                         f"{what}; incoming staged + review_pending=true — "
                         f"move changes to SKILL.md, then --resolve")
                    results["noted"].append({"skill": sid, "file": fname, "new_sha": remote_sha,
                                             "incoming": str(incoming_path.relative_to(root)),
                                             "url": entry["url"]})
                else:  # check
                    line("notify", sid, fname,
                         f"{what}; strategy=fork — needs manual modification")
                    results["notify"].append({"skill": sid, "file": fname,
                                              "old_sha": stored, "new_sha": remote_sha})
            continue

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

# --- the verdict is rotten ----------------------------------------------
# One-time human audit of the bundle recorded AGAINST SPECIFIC BYTES: column
# `audited_at` verdict table is carried by the same sha256, which at the time of the audit
# lay in files[].sha256. This means that the drift is relative to the recorded sha AND THERE IS drift
# regarding audited_at: verdict no longer describes what lies in the tree.
# Without this mark, a one-time audit ceases to mean anything after the first
# upstream updates, and --check continues to report only integrity.
#
# BORDER (named, not imitated): after `--apply` fresh sha is written to
# upstream.json, the drift disappears - and the mark along with it, although the human verdict
# remained rancid. The script does not read the verdict table (she lives in the plane/docks,
# there should be no cross-packet communication here), therefore «rotten» detectable only up to
# --apply. Procedure: --check → reread marked bundles → update table.
#
# P5.11: mechanism NOT removed, but narrowed to bundles WITHOUT block `audit` — that is exactly
# to those it catches AUDIT_MISSING and who does not have their own anchor. The bundle has
# block `audit` decay counts AUDIT_STALE by its anchor (is worried
# --apply), and two sources of the same mark do not mix: reason is printed
# is distinguishable, and `reason` in --json calls the mechanism by name.
if mode == "check":
    _audited = {sid for _cfg, sid, data in parsed if isinstance(data.get("audit"), dict)}
    _drifted = {e["skill"] for key in ("updates", "drift", "conflicts", "notify")
                for e in results[key]} - _audited
    for sid in sorted(_drifted):
        results["stale_verdicts"].append(
            {"skill": sid, "reason": "bytes drifted from audited_at (derived: "
                                     "no audit block — see AUDIT_MISSING)"})
        line("stale", sid, "(verdict)",
             "bytes diverged from audited_at — human verdict of the bundle is ROTTEN, "
             "re-read the bundle before considering it verified "
             "(derived mark: block audit there is no bundle)")

# --- summary -----------------------------------------------------------------
s = results
print(f"Summary: {s['checked']} checked | {len(s['updates'])} update | "
      f"{len(s['drift'])} drift | {len(s['conflicts'])} conflict | "
      f"{len(s['notify'])} notify | {len(s['applied'])} applied | "
      f"{len(s['noted'])} noted | {len(s['failures'])} failed", file=report)
if mode == "check":
    print(f"Triage: {len(s['triage'])} finding(s) in "
          f"{len({f['skill'] for f in s['triage']})} bundle(s) | "
          f"{len(s['stale_verdicts'])} stale verdict(s) | "
          f"{len(s['reference_only'])} reference-only bundle(s)", file=report)
    print(f"NOTE: {TRIAGE_DISCLAIMER}", file=report)

if (s["applied"] or s["noted"]) and not json_out:
    print("Run ./sync.sh --update-registry to refresh skills.json", file=report)

if json_out:
    # Disclaimer - in a SEPARATE key, and not just in prose in a human channel:
    # the machine consumer must see it in the same way as the operator.
    if mode == "check":
        results["triage_disclaimer"] = TRIAGE_DISCLAIMER
    print(json.dumps(results, indent=2, ensure_ascii=False))

if s["failures"]:
    sys.exit(2)
if mode == "check" and (s["updates"] or s["notify"] or s["conflicts"]):
    sys.exit(10)
if mode == "apply" and s["conflicts"] and not force:
    sys.exit(10)
# Triage - OWN code (11), not 10: «upstream has changed» and «in the bundle is suspicious
# pattern» — miscellaneous events. 10 is older than 11 only because the code is one scalar;
# the full picture of both is always in --json.
if mode == "check" and s["triage"]:
    sys.exit(11)
sys.exit(0)
PY
