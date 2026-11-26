"""compat — quarantine checks of an imported (vendored) skill (PLAN4 P8.6).

`check_skill` is deterministic and offline: licence, provenance, dangerous-instruction patterns, token budget
and `allowed-tools` assumptions over every text file of the skill. A reviewed example catalogue (a security reference)
is accepted per file and check through `compat_accepted: [{file, checks, reason}]` in `upstream.json` and shows as a
warning. The result is `compat-report.json` beside `upstream.json`:
`{checks: [{id, status, detail}], verdict: clean|quarantine}` with status `ok|warn|fail`; one `fail` quarantines the
skill, `skiller registry` then writes `quarantined: true` into `skills.json` and `skiller select` and the resolver
leave it out. There is no LLM scan."""
import argparse
import json
import re
import sys
from pathlib import Path

from aicore.content.budget import estimate_tokens
from aicore.content.skill import read_frontmatter, split_frontmatter

REPORT = "compat-report.json"
LICENSES_FILE = Path(__file__).resolve().parents[3] / "configs" / "licenses.json"
DEFAULT_MAX_TOKENS = 8000
KNOWN_TOOLS = frozenset({"Bash", "Edit", "Glob", "Grep", "MultiEdit", "NotebookEdit", "Read", "Skill", "Task", "Agent",
                         "TodoWrite", "WebFetch", "WebSearch", "Write"})
_SIDECARS = ("upstream.json", "compat-report.json", "selection.json")
_MAX_FILE_BYTES = 1_000_000
_HEX64 = re.compile(r"^[0-9a-f]{64}$")

_SECRET = (r"(?:(?:~|\$HOME|/home/[\w.-]+|/root)/\.(?:ssh|aws|gnupg|kube)\b|\bid_(?:rsa|ed25519)\b"
           r"|(?<![\w/.])\.env(?:\.\w+)?\b)")
_VERBS = r"(?:read|cat|print|show|dump|send|upload|post|copy|include|прочита\w*|выведи|отправ\w*|покажи)"
# id → (pattern, negatable): a negatable pattern is ignored on a line that forbids the action ("never ...").
PATTERNS = {
    "secret-read": (re.compile(rf"\b{_VERBS}\b.{{0,80}}?{_SECRET}", re.I | re.S), True),
    "disable-checks": (re.compile(r"--no-verify|--no-gpg-sign|--insecure\b|NODE_TLS_REJECT_UNAUTHORIZED\s*=\s*0|"
                                  r"verify\s*=\s*False|(?:disable|turn off|отключи)\s+(?:the\s+)?(?:safety|security|sandbox|"
                                  r"ssl|tls|certificate|hooks?|проверк\w+)", re.I), True),
    "pipe-to-shell": (re.compile(r"\b(?:curl|wget)\b[^|\n]*\|\s*(?:sudo\s+)?(?:ba|z)?sh\b", re.I), False),
    "hide-actions": (re.compile(r"(?:do not|don't|never)\s+(?:tell|mention|inform|show|reveal)[^.\n]{0,40}\b(?:user|human|owner)\b"
                                r"|hide\s+(?:this|these|the)\b[^.\n]{0,30}\bfrom\b[^.\n]{0,20}\b(?:user|human)\b"
                                r"|без ведома пользователя|не сообщай пользователю|скрой от пользователя", re.I), False),
    "prompt-injection": (re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions|rules)"
                                    r"|disregard\s+(?:the\s+)?(?:system|previous)\s+(?:prompt|instructions)"
                                    r"|игнорируй\s+(?:все\s+)?(?:предыдущие|прошлые)\s+(?:инструкции|правила)", re.I), False),
}
# A negation counts only right before the matched action ("never read ~/.ssh"), never elsewhere on the line.
_NEGATION_BEFORE = re.compile(r"(?:\bnever|\bdo not|\bdon't|\bmust not|\bavoid|\bне|\bнельзя)\s+(?:\w+\s+){0,2}$", re.I)


def _check(check_id, status, detail):
    return {"id": check_id, "status": status, "detail": detail}


def read_licenses(path=LICENSES_FILE):
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if document.get("schema") != "licenses/v1":
        raise ValueError(f"{path}: must be a licenses/v1 object")
    return document


def _license(upstream, licenses):
    value = str(upstream.get("license") or "").strip()
    if not value:
        return _check("license", "fail", "upstream.json names no license")
    if value in licenses["allowed"]:
        return _check("license", "ok", value)
    if value.startswith(licenses.get("not_applicable_prefix", "N/A")):
        if upstream.get("kind") == "reference-only":
            return _check("license", "warn", f"no vendored code: {value}")
        return _check("license", "fail", f"{value}: N/A is only for kind reference-only, not for vendored files")
    return _check("license", "fail", f"{value} is not in configs/licenses.json")


def _provenance(upstream):
    if upstream.get("kind") == "reference-only":
        return _check("provenance", "warn", "reference-only: files[] are links to specs, nothing is vendored")
    anchor = (upstream.get("audit") or {}).get("upstream_sha")
    if not isinstance(anchor, str) or not _HEX64.match(anchor):
        return _check("provenance", "fail", "audit.upstream_sha is missing or not a sha256 hex")
    files = upstream.get("files")
    if not isinstance(files, list) or not files:
        return _check("provenance", "fail", "files[] is empty")
    for row in files:
        if not isinstance(row, dict) or not row.get("url") or not _HEX64.match(str(row.get("sha256", ""))):
            return _check("provenance", "fail", f"files[] entry without url or sha256: {row.get('path') if isinstance(row, dict) else row}")
    if anchor in {row["sha256"] for row in files}:
        return _check("provenance", "ok", "upstream_sha equals the sha256 of a fetched file")
    return _check("provenance", "ok", "upstream_sha is well-formed; it is an anchor of the upstream, not recomputable offline")


def _scan(text, name="SKILL.md"):
    """`{pattern id: first match as "file line N: text"}` over one file's text."""
    found = {}
    for pid, (pattern, negatable) in PATTERNS.items():
        for match in pattern.finditer(text):
            line_start = text.rfind("\n", 0, match.start()) + 1
            if negatable and _NEGATION_BEFORE.search(text[line_start:match.start()]):
                continue
            found[pid] = f"{name} line {text.count(chr(10), 0, match.start()) + 1}: {' '.join(match.group(0).split())[:80]}"
            break
    return found


def _texts(skill_dir):
    """`(relative name, text)` of every text file of the skill that is content (not the maintainer-side sidecars)."""
    for path in sorted(Path(skill_dir).rglob("*")):
        parts = path.relative_to(skill_dir).parts
        if (not path.is_file() or path.is_symlink() or path.name in _SIDECARS or "__pycache__" in parts
                or path.stat().st_size > _MAX_FILE_BYTES):
            continue
        try:
            yield "/".join(parts), path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            continue


def _tools(frontmatter):
    raw = frontmatter.get("allowed-tools", "")
    tools = raw if isinstance(raw, list) else str(raw).replace(",", " ").split()
    unknown = sorted(t for t in tools if t.split("(")[0] not in KNOWN_TOOLS and not t.startswith("mcp__"))
    if unknown:
        return _check("tools", "warn", "unknown allowed-tools: " + ", ".join(unknown))
    return _check("tools", "ok", f"{len(tools)} allowed-tools, all known")


def check_skill(skill_dir, licenses=None, default_max_tokens=DEFAULT_MAX_TOKENS):
    """The compat report of one vendored skill directory (it needs `upstream.json`)."""
    skill_dir = Path(skill_dir)
    upstream = json.loads((skill_dir / "upstream.json").read_text(encoding="utf-8"))
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8-sig")
    frontmatter, body = read_frontmatter(skill_dir / "SKILL.md"), split_frontmatter(text)[1]
    checks = [_license(upstream, licenses or read_licenses()), _provenance(upstream)]
    accepted = {(row.get("file"), pid): row.get("reason") for row in upstream.get("compat_accepted") or []
                if isinstance(row, dict) and row.get("reason") for pid in row.get("checks") or []}
    hits, waived = {}, []
    for name, content in _texts(skill_dir):
        for pid, where in _scan(content, name).items():
            if (name, pid) in accepted:
                waived.append(f"{pid} in {name}: {accepted[(name, pid)]}")
            else:
                hits.setdefault(pid, where)
    if hits:
        checks.append(_check("injection", "fail", "; ".join(f"{pid} ({where})" for pid, where in sorted(hits.items()))))
    elif waived:
        checks.append(_check("injection", "warn", "accepted by upstream.json compat_accepted: " + "; ".join(waived)))
    else:
        checks.append(_check("injection", "ok", "no dangerous-instruction pattern"))
    try:
        sidecar = json.loads((skill_dir / "selection.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        sidecar = {}
    limit, tokens = sidecar.get("max_tokens") or default_max_tokens, estimate_tokens(body)
    checks.append(_check("budget", "fail" if tokens > limit else "ok", f"{tokens} tokens of {limit}"))
    checks.append(_tools(frontmatter))
    return {"checks": checks, "verdict": "quarantine" if any(c["status"] == "fail" for c in checks) else "clean"}


def read_report(skill_dir):
    """The saved report of a skill directory, or None."""
    path = Path(skill_dir) / REPORT
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def is_quarantined(skill_dir):
    report = read_report(skill_dir)
    return bool(report) and report.get("verdict") == "quarantine"


def write_report(skill_dir, report):
    path = Path(skill_dir) / REPORT
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def vendored_dirs(root):
    return sorted(p.parent for p in Path(root).glob("skills/*/*/upstream.json"))


def cmd_compat(env, argv):
    parser = argparse.ArgumentParser(prog="skiller compat",
                                     description="Quarantine checks of vendored skills; --write saves compat-report.json.")
    parser.add_argument("skills", nargs="*", metavar="SKILL", help="bucket/folder (default: every vendored skill)")
    parser.add_argument("--write", action="store_true", help="write compat-report.json beside upstream.json")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    dirs = vendored_dirs(env.root)
    if args.skills:
        wanted = set(args.skills)
        dirs = [d for d in dirs if f"{d.parent.name}/{d.name}" in wanted]
        unknown = wanted - {f"{d.parent.name}/{d.name}" for d in dirs}
        if unknown:
            print("not a vendored skill: " + ", ".join(sorted(unknown)), file=sys.stderr)
            raise SystemExit(1)
    licenses, reports = read_licenses(), {}
    for skill_dir in dirs:
        report = check_skill(skill_dir, licenses)
        reports[f"{skill_dir.parent.name}/{skill_dir.name}"] = report
        if args.write:
            write_report(skill_dir, report)
    quarantined = sorted(sid for sid, r in reports.items() if r["verdict"] == "quarantine")
    if args.json_output:
        print(json.dumps({"reports": reports, "quarantined": quarantined}, ensure_ascii=False, indent=2))
    else:
        for sid in quarantined:
            reasons = "; ".join(f"{c['id']}: {c['detail']}" for c in reports[sid]["checks"] if c["status"] == "fail")
            print(f"quarantine  {sid}  {reasons}")
        print(f"{len(reports)} vendored skills, {len(quarantined)} quarantined")
    if quarantined and not args.write:
        raise SystemExit(1)
