"""Read-only, deterministic inventory of registered Task workflow artifacts.

Field JavaScript is untrusted input.  This module reads only the two declared
plan roots of enabled registry projects, hashes bytes before interpretation and
uses a small lexical scanner; it never imports, evaluates or shells out to JS.
"""
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from .common import atomic_write_json, atomic_write_text, die, parse_args, safe_load_json

REPORT_VERSION = "workflow-fleet-report/v1"
_FEATURES = ("test", "review", "verify", "gate", "commit", "max_iteration", "judge_panel")
_META_RE = re.compile(r"\bexport\s+const\s+meta\s*=")


def load_projects(config_path):
    """Read the existing maind registry shape, retaining only enabled identities."""
    doc = safe_load_json(Path(config_path), None)
    if not isinstance(doc, dict):
        return []
    rows = []
    for row in doc.get("projects") or []:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            continue
        rows.append({
            "id": row["id"], "enabled": bool(row.get("enabled", True)),
            "local_path": row.get("local_path") or "", "vault_path": row.get("vault_path") or "",
        })
    return sorted((row for row in rows if row["enabled"]), key=lambda row: row["id"])


def _inside(path, root):
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def candidate_paths(projects):
    """Bounded active/archive workflow paths plus missing declared roots.

    No recursive vault traversal: each glob is exactly one plan directory deep.
    """
    candidates, missing = [], []
    for project in projects:
        for location in ("local_path", "vault_path"):
            value = project[location]
            if not value:
                continue
            root = Path(value).expanduser()
            if not root.is_dir():
                missing.append({"project": project["id"], "location": location[:-5], "reason": "root-missing"})
                continue
            paths = list(root.glob("plans/*/workflows/*.js"))
            paths.extend(root.glob("plans/archive/*/workflows/*.js"))
            for path in sorted(paths):
                if not _inside(path, root):
                    missing.append({"project": project["id"], "location": location[:-5], "reason": "symlink-escape"})
                    continue
                relative = path.relative_to(root).as_posix()
                parts = relative.split("/")
                plan_id = parts[2] if parts[:2] == ["plans", "archive"] else parts[1]
                candidates.append({"path": path, "project": project["id"], "location": location[:-5],
                                   "identity": f"{project['id']}:{location[:-5]}:{relative}",
                                   "plan": f"{project['id']}:{plan_id}"})
    return candidates, sorted(missing, key=lambda row: (row["project"], row["location"], row["reason"]))


def _without_comments(text):
    """Strip JS comments while preserving strings for harmless static feature reads."""
    out, i, quote = [], 0, None
    while i < len(text):
        char, nxt = text[i], text[i + 1] if i + 1 < len(text) else ""
        if quote:
            out.append(char)
            if char == "\\" and i + 1 < len(text):
                out.append(text[i + 1]); i += 2; continue
            if char == quote:
                quote = None
            i += 1; continue
        if char in ("'", '"', '`'):
            quote = char; out.append(char); i += 1; continue
        if char == "/" and nxt == "/":
            end = text.find("\n", i)
            if end < 0: break
            out.append("\n"); i = end + 1; continue
        if char == "/" and nxt == "*":
            end = text.find("*/", i + 2)
            if end < 0: return ""  # malformed comment: no trustworthy extraction
            out.append("\n" * text[i:end + 2].count("\n")); i = end + 2; continue
        out.append(char); i += 1
    return "".join(out)


def _balanced_object(text, start):
    """Return end offset of an object, respecting quoted strings and comments."""
    begin = text.find("{", start)
    if begin < 0: return None
    depth, i, quote = 0, begin, None
    while i < len(text):
        char, nxt = text[i], text[i + 1] if i + 1 < len(text) else ""
        if quote:
            if char == "\\": i += 2; continue
            if char == quote: quote = None
            i += 1; continue
        if char in ("'", '"', '`'):
            quote = char; i += 1; continue
        if char == "/" and nxt == "/":
            end = text.find("\n", i + 2); i = len(text) if end < 0 else end + 1; continue
        if char == "/" and nxt == "*":
            end = text.find("*/", i + 2)
            if end < 0: return None
            i = end + 2; continue
        if char == "{": depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0: return i + 1
        i += 1
    return None


def extract_features(text):
    """Conservative static signature; unknown input is never treated as absent."""
    clean = _without_comments(text)
    meta = _META_RE.search(clean)
    if not meta:
        return {"status": "unsupported", "reason": "export-meta-missing", "features": [], "type": "unknown"}
    if _balanced_object(text, meta.end()) is None:
        return {"status": "malformed", "reason": "meta-object-unclosed", "features": [], "type": "unknown"}
    lower = clean.lower()
    found = {
        "test": bool(re.search(r"\btests?(?:[-_ ]?to[-_ ]?green)?\b", lower)),
        "review": bool(re.search(r"\breview\b", lower)),
        "verify": bool(re.search(r"\bverify\b", lower)),
        "gate": bool(re.search(r"\bgates?\b", lower)),
        "commit": bool(re.search(r"\bcommit\b", lower)),
        "max_iteration": bool(re.search(r"\bmax[_ -]?(?:green[_ -]?)?iterations?\b", lower)),
        "judge_panel": bool(re.search(r"\bjudge[_ -]?panel\b", lower)),
    }
    if "research-fanout" in lower: kind = "research"
    elif "audit-adversarial" in lower: kind = "audit"
    elif "dev-slice" in lower or (found["test"] and found["commit"]): kind = "development"
    else: kind = "custom"
    return {"status": "qualified", "reason": None,
            "features": [name for name in _FEATURES if found[name]], "type": kind}


def inventory(projects):
    """Hash first, then extract once per exact digest; aliases and plans stay visible."""
    candidates, missing = candidate_paths(projects)
    groups, diagnostics = {}, []
    for row in candidates:
        try:
            raw = row["path"].read_bytes()
        except OSError:
            diagnostics.append({"identity": row["identity"], "status": "unsupported", "reason": "read-failed"}); continue
        digest = hashlib.sha256(raw).hexdigest()
        group = groups.setdefault(digest, {"bytes": raw, "aliases": [], "plans": set()})
        group["aliases"].append(row["identity"]); group["plans"].add(row["plan"])
    sources = []
    for digest, group in sorted(groups.items()):
        try:
            text = group["bytes"].decode("utf-8")
        except UnicodeDecodeError:
            extracted = {"status": "unsupported", "reason": "utf8-invalid", "features": [], "type": "unknown"}
        else:
            extracted = extract_features(text)
        sources.append({"digest": digest, "aliases": sorted(group["aliases"]), "plans": sorted(group["plans"]), **extracted})
    return sources, missing, sorted(diagnostics, key=lambda row: row["identity"])


def template_sources(monorepo_root):
    root = Path(monorepo_root) / "packages" / "task" / "workflows"
    records = []
    for path in sorted(root.glob("wf-*.js")):
        raw = path.read_bytes()
        try: text = raw.decode("utf-8")
        except UnicodeDecodeError: text = ""
        records.append({"template": path.name, "digest": hashlib.sha256(raw).hexdigest(), **extract_features(text)})
    return records


def synthesize(sources, templates):
    template_features = {feature for row in templates if row["status"] == "qualified" for feature in row["features"]}
    by_feature = defaultdict(set)
    for row in sources:
        if row["status"] == "qualified":
            for feature in row["features"]: by_feature[feature].update(row["plans"])
    candidates = []
    for feature in sorted(by_feature):
        plans = sorted(by_feature[feature])
        if feature in template_features: outcome = "covered"
        elif len(plans) >= 3: outcome = "refine-existing"
        else: outcome = "hold"
        candidates.append({"feature": feature, "plans": plans, "distinct_plan_count": len(plans), "outcome": outcome})
    anti_patterns = []
    for row in sources:
        if row["status"] == "qualified" and row.get("type") == "development" and "review" not in row["features"]:
            anti_patterns.append({"digest": row["digest"], "plans": row["plans"], "kind": "development-without-review"})
    return candidates, anti_patterns


def build_report(projects, templates, sources, missing_roots, diagnostics, now):
    candidates, anti_patterns = synthesize(sources, templates)
    outcomes = {row["outcome"] for row in candidates}
    overall = "refine-existing" if "refine-existing" in outcomes else ("hold" if "hold" in outcomes else "covered")
    return {
        "schema_version": REPORT_VERSION, "generated_at": now,
        "registry": {"enabled_projects": [row["id"] for row in projects]},
        "missing_roots": missing_roots, "diagnostics": diagnostics,
        "sources": sources, "canonical_templates": templates,
        "coverage": candidates, "anti_patterns": anti_patterns,
        "outcome": overall,
    }


def render_markdown(report):
    lines = ["# Workflow fleet report", "", f"Schema: `{report['schema_version']}`", f"Generated: `{report['generated_at']}`", "",
             f"Outcome: **{report['outcome']}**", "", "## Inventory", "",
             f"- Enabled projects: {len(report['registry']['enabled_projects'])}",
             f"- Unique content digests: {len(report['sources'])}",
             f"- Missing/escaped roots: {len(report['missing_roots'])}", "", "## Feature coverage", "",
             "| Feature | Distinct plans | Outcome |", "|:--|--:|:--|"]
    for row in report["coverage"]:
        lines.append(f"| `{row['feature']}` | {row['distinct_plan_count']} | {row['outcome']} |")
    if not report["coverage"]: lines.append("| — | 0 | hold |");
    lines.extend(["", "## Boundaries", "", "- JavaScript was read as untrusted text and was never executed.",
                  "- Paths are normalized project-relative identities; no absolute home paths or script bodies are reported.",
                  "- A fifth template family or mandatory-stage-matrix change remains report-only.", ""])
    return "\n".join(lines)


def _output_paths(value):
    path = Path(value)
    if path.suffix == ".json": return path, path.with_suffix(".md")
    return path / "workflow-fleet-report.json", path / "workflow-fleet-report.md"


def cmd_workflow_scan(env, argv):
    opts, _ = parse_args(argv, {"--project": "str", "--output": "str", "--now": "str", "--json": "bool"})
    if opts["help"]:
        print("analyst workflow-scan [--project ID] [--output DIR|FILE.json] [--now ISO] [--json]")
        return
    if not opts["now"]: die("workflow-scan requires --now for the reproducible report")
    projects = load_projects(env.default_config)
    if opts["project"]:
        projects = [row for row in projects if row["id"] == opts["project"]]
        if not projects: die(f"enabled project not found: {opts['project']}")
    sources, missing, diagnostics = inventory(projects)
    report = build_report(projects, template_sources(env.monorepo_root), sources, missing, diagnostics, opts["now"])
    if opts["output"]:
        json_path, md_path = _output_paths(opts["output"])
        atomic_write_json(json_path, report)
        atomic_write_text(md_path, render_markdown(report))
    if opts["json"]:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print(f"workflow-scan: {len(sources)} digest(s), outcome={report['outcome']}")
