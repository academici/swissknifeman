"""analyst scan — cross-project aggregator (P2): lesson patterns across projects.

The package discovers projects through the maind project registry (`maind projects list --json`,
contract projects-list/v1): projects[].{local_path, namespaces, enabled}. Reading per-project lessons
(<project>/.swissknifeman/analyst/lessons/),
clusters by Jaccard (stdlib) and detects patterns that repeat in ≥N projects → writes
draft-OFFERS (not skills!) in ~/.swissknifeman/analyst/suggestions/ + index by_pattern/.

Namespace-insulation (inherits from maind): lessons are clustered ONLY among projects sharing
namespace — pattern from ns:axioma does not flow into someone else's namespace. Project without namespace isolated
(a cluster from it will never become cross-project). Clustering - greedy single-link (determinism:
input lessons are sorted by id before the passage). Demona/no network; everything stdlib, read-only by project."""
import json
import os
from pathlib import Path

from . import lessons
from aicore.util.io import atomic_write_json, atomic_write_text, safe_load_json
from aicore.util.partners import PartnerError, PartnerUnavailable, run_partner_json
from aicore.util.term import die, now_iso
from aicore.util.text import sanitize

# Lessons involved in pattern detection (deprecated is excluded - we do not replicate the demoted one).
SCAN_STATES = ("curated", "candidate", "ephemeral")
DEFAULT_MIN_PROJECTS = 3     # cross-project pattern - only when ≥N projects (DoD P2)
DEFAULT_THRESHOLD = 0.5      # Jaccard-threshold «same pattern»


# ── project registry (maind `projects list --json`, contract projects-list/v1) ──────
def normalize_projects(rows):
    """[{id, local_path, namespaces, enabled}] from registry records; malformed rows are skipped."""
    out = []
    for pr in (rows if isinstance(rows, list) else []):
        if not isinstance(pr, dict) or not pr.get("id"):
            continue
        out.append({
            "id": pr["id"],
            "local_path": pr.get("local_path") or "",
            "namespaces": list(pr.get("namespaces") or []),
            "enabled": bool(pr.get("enabled", True)),
        })
    return out


def registry_rows():
    """Raw registry records from the maind partner. Without maind: PARTNER_UNAVAILABLE and exit."""
    try:
        rows = run_partner_json("maind", ["projects", "list", "--json"], legacy_env=("MAIND_BIN",))
    except PartnerUnavailable as exc:
        die(f"{exc}; the cross-project scan needs the project registry")
    except PartnerError as exc:
        die(str(exc))
    if not isinstance(rows, list):
        die("PARTNER_BAD_OUTPUT: maind projects printed a non-list registry")
    return rows


def load_projects():
    """Normalized registry projects (see normalize_projects) of the maind partner."""
    return normalize_projects(registry_rows())


def enabled_projects(projects, namespace=None):
    """enabled-projects with non-empty local_path; namespace filters by membership."""
    out = []
    for pr in projects:
        if not pr["enabled"] or not pr["local_path"]:
            continue
        if namespace and namespace not in pr["namespaces"]:
            continue
        out.append(pr)
    return out


# ── collection of lessons on namespace (insulation) ──────────────────────────────────────
def _lesson_text(lesson):
    return f"{lesson.get('trigger', '')} {lesson.get('action', '')}"


def gather_by_namespace(projects, *, states=SCAN_STATES):
    """{namespace: [{project, lesson, text}]} — the lessons of the project fall into EVERY of it namespace.
    Project without namespace doesn't hit anywhere (is isolated - cannot become cross-project)."""
    buckets = {}
    for pr in projects:
        ppath = os.path.expanduser(pr["local_path"])
        items = []
        for st in states:
            for lesson in [L for L, _s in lessons.list_lessons(ppath, st)]:
                items.append({"project": pr["id"], "lesson": lesson, "text": _lesson_text(lesson)})
        if not items:
            continue
        for ns in pr["namespaces"]:
            buckets.setdefault(ns, []).extend(items)
    return buckets


# ── clustering (greedy single-link, deterministic) ─────────────────────
def cluster(items, threshold=DEFAULT_THRESHOLD):
    """[[item,...], ...] greedy single-link by Jaccard(text). Input sorted by
    (lesson.id) → determinism regardless of the order in which directories are read."""
    ordered = sorted(items, key=lambda it: it["lesson"].get("id", ""))
    clusters = []
    for it in ordered:
        placed = False
        for cl in clusters:
            if any(lessons.jaccard(it["text"], m["text"]) >= threshold for m in cl):
                cl.append(it)
                placed = True
                break
        if not placed:
            clusters.append([it])
    return clusters


def _pattern_id(namespace, rep_text):
    slug = sanitize(rep_text)[:40] or "pattern"
    import hashlib
    h = hashlib.sha1(f"{namespace}\x00{rep_text}".encode("utf-8")).hexdigest()[:8]
    return f"{sanitize(namespace) or 'ns'}-{slug}-{h}"


def detect_patterns(buckets, *, min_projects=DEFAULT_MIN_PROJECTS, threshold=DEFAULT_THRESHOLD):
    """Cross-project patterns by namespace. Pattern - cluster covering ≥min_projects
    DIFFERENT projects. Returns [pattern] sorted by weight (number of projects) descending"""
    patterns = []
    for ns in sorted(buckets):
        for cl in cluster(buckets[ns], threshold):
            projs = sorted({it["project"] for it in cl})
            if len(projs) < min_projects:
                continue
            rep = min(cl, key=lambda it: it["lesson"].get("id", ""))   # deterministic representative
            patterns.append({
                "pattern_id": _pattern_id(ns, rep["text"]),
                "namespace": ns,
                "projects": projs,
                "weight": len(projs),
                "lessons": len(cl),
                "representative": {
                    "trigger": rep["lesson"].get("trigger", ""),
                    "action": rep["lesson"].get("action", ""),
                    "kind": rep["lesson"].get("kind", ""),
                },
                "members": [{"project": it["project"], "id": it["lesson"].get("id"),
                             "trigger": it["lesson"].get("trigger", "")} for it in cl],
            })
    patterns.sort(key=lambda p: (p["weight"], p["lessons"]), reverse=True)
    return patterns


# ── recording artifacts (cross-project layer ~/.swissknifeman/analyst) ───────────
def _suggestion_md(pattern):
    rep = pattern["representative"]
    lines = [
        f"# Offer (draft) — pattern `{pattern['pattern_id']}`",
        "",
        f"> **Not a skill.** Promotion draft: pattern repeated in **{pattern['weight']} projects** "
        f"namespace `{pattern['namespace']}`. Skill draft - `analyst suggest {pattern['pattern_id']}`; "
        f"promotion to the bucket - a person.",
        "",
        f"- **kind:** {rep.get('kind') or '—'}",
        f"- **trigger:** {rep.get('trigger') or '—'}",
        f"- **action:** {rep.get('action') or '—'}",
        f"- **projects ({pattern['weight']}):** {', '.join(pattern['projects'])}",
        f"- **lessons in the cluster:** {pattern['lessons']}",
        "",
        "## Instances by Project",
    ]
    for m in pattern["members"]:
        lines.append(f"- `{m['project']}` · {m['id']} — {m['trigger']}")
    lines.append("")
    return "\n".join(lines)


def write_artifacts(env, patterns):
    """Write index/by_pattern/<id>.json + suggestions/<id>.md. Returns paths.
    Atomic; directories are created. Only for found patterns (empty list - no-op)."""
    idx_dir = env.state_dir / "index" / "by_pattern"
    sug_dir = env.state_dir / "suggestions"
    written = []
    for p in patterns:
        atomic_write_json(idx_dir / f"{p['pattern_id']}.json",
                          {**p, "generated_at": now_iso()})
        atomic_write_text(sug_dir / f"{p['pattern_id']}.md", _suggestion_md(p))
        written.append(p["pattern_id"])
    return written


# ── reconcile: prun of orphaned artifacts (strictly in scope run) ───────────
def list_existing_patterns(env):
    """Existing pattern artifacts on disk: [{pattern_id, namespace, index_path,
    suggestion_path}]. namespace is taken from the FIELD 'namespace' index (file name is not reversible).
    Broken/unread index or without pattern_id/namespace → SKIP (do not delete
    unclassified). Sorted by pattern_id — determinism."""
    idx_dir = env.state_dir / "index" / "by_pattern"
    sug_dir = env.state_dir / "suggestions"
    out = []
    if not idx_dir.is_dir():
        return out
    for idx_path in sorted(idx_dir.glob("*.json")):
        data = safe_load_json(idx_path, None)
        if not isinstance(data, dict):
            continue                       # broken JSON → SKIP
        pid = data.get("pattern_id")
        ns = data.get("namespace")
        if not pid or not ns:
            continue                       # without classifying fields → SKIP
        out.append({
            "pattern_id": pid,
            "namespace": ns,
            "index_path": idx_path,
            "suggestion_path": sug_dir / f"{pid}.md",
        })
    return out


def stale_pattern_ids(existing, written_ids, scanned_namespaces):
    """NET (without I/O): id orphan artifacts for removal. Orphan = existing pattern whose
    namespace IS included in the scanned by this run scope, but which is NOT among written
    (regenerated). namespace OUT scope → DO NOT touch: alien ns not rescanned → its absence
    in written ≠ 'deprecated'. Yes scoped-run (scan --namespace X) will only prunt ns X."""
    written = set(written_ids)
    scoped = set(scanned_namespaces)
    return {e["pattern_id"] for e in existing
            if e["namespace"] in scoped and e["pattern_id"] not in written}


def prune_artifacts(env, stale_ids):
    """Remove index+suggestion files for stale_ids — BOTH together (missing_ok, synchronously).
    Returns removed[] — sorted list of removed pattern_id. Deterministic."""
    idx_dir = env.state_dir / "index" / "by_pattern"
    sug_dir = env.state_dir / "suggestions"
    removed = []
    for pid in sorted(stale_ids):
        (idx_dir / f"{pid}.json").unlink(missing_ok=True)
        (sug_dir / f"{pid}.md").unlink(missing_ok=True)
        removed.append(pid)
    return removed


# ── CLI ──────────────────────────────────────────────────────────────────────
def cmd_scan(env, argv):
    """analyst scan [--min-projects N] [--namespace NS] [--threshold T] [--no-prune] [--dry-run] [--json]
    — cross-project lesson patterns (maind project registry) → suggestions/ (namespace-isolated)."""
    from aicore.util.cli import parse_args
    from aicore.util.term import warn
    opts, _ = parse_args(argv, {"--min-projects": "str", "--namespace": "str",
                                "--threshold": "str", "--no-prune": "bool",
                                "--dry-run": "bool", "--json": "bool"})
    if opts["help"]:
        print("analyst scan [--min-projects N] [--namespace NS] [--threshold T] [--no-prune] [--dry-run] [--json]\n"
              "  Bypass the maind project registry → per-project lessons → Jaccard-clusters → patterns in ≥N\n"
              "  projects (namespace-isolated) → draft-sentences in ~/.swissknifeman/analyst/.\n"
              "  Reconciliation: Orphaned index+suggestion files (disappeared patterns) are removed\n"
              "  STRICTLY in scope run (--no-prune turns off; --dry-run does not write anything and\n"
              "  shows would-prune RELATIVE would-be-written patterns of this run).")
        return

    try:
        min_projects = int(opts["min_projects"]) if opts["min_projects"] else DEFAULT_MIN_PROJECTS
    except ValueError:
        die(f"--min-projects is waiting for a number, received: {opts['min_projects']}")
    try:
        threshold = float(opts["threshold"]) if opts["threshold"] else DEFAULT_THRESHOLD
    except ValueError:
        die(f"--threshold is waiting for a number, received: {opts['threshold']}")

    projects = enabled_projects(load_projects(), opts["namespace"] or None)
    if not projects:
        warn("no enabled-projects in the registry"
             + (f" for namespace {opts['namespace']}" if opts["namespace"] else ""))

    buckets = gather_by_namespace(projects)
    patterns = detect_patterns(buckets, min_projects=min_projects, threshold=threshold)
    current_ids = {p["pattern_id"] for p in patterns}   # that MUST exist in scope run

    written = [] if opts["dry_run"] else write_artifacts(env, patterns)

    # ── reconcile: remove orphaned artifacts STRICTLY in scope of this run ──
    # scope: {namespace} when --namespace X (only he is regenerated), ELSE union ns all
    # enabled-projects (full bypass). Alien ns not rescanned → we do not touch its files.
    scanned_namespaces = ({opts["namespace"]} if opts["namespace"]
                          else {ns for pr in projects for ns in pr["namespaces"]})
    prune_enabled = not opts["no_prune"]
    params_default = (min_projects == DEFAULT_MIN_PROJECTS and threshold == DEFAULT_THRESHOLD)
    pruned = []
    if prune_enabled and not params_default:
        # [POSSIBLE-DEFECT] non-standard parameters do written stricter → auto-prun would remove
        # what is default scan will leave (churn: deleted now - recreated with the following default).
        # We deliberately limit auto-pruning to default parameters (data is more important than autocleaning).
        warn("[POSSIBLE-DEFECT] non-standard --min-projects/--threshold — auto-pruning of orphans missed "
             "(risk churn). Drive away scan with default parameters for cleaning orphans.")
    elif prune_enabled:
        # list_existing_patterns — AFTER write_artifacts: current ones will be included in current_ids
        # (will not go out), orphans do not. B dry-run write was not there → show would-prune.
        stale = stale_pattern_ids(list_existing_patterns(env), current_ids, scanned_namespaces)
        pruned = sorted(stale) if opts["dry_run"] else prune_artifacts(env, stale)

    if opts["json"]:
        print(json.dumps({"projects_scanned": len(projects),
                          "namespaces": sorted(buckets),
                          "min_projects": min_projects,
                          "patterns": patterns,
                          "written": written,
                          "pruned": pruned,
                          "dry_run": bool(opts["dry_run"])}, ensure_ascii=False, indent=2))
        return

    ns_count = len(buckets)
    print(f"\nanalyst scan — projects: {len(projects)} · namespace with lessons: {ns_count} · "
          f"threshold ≥{min_projects} projects\n")
    if not patterns:
        print("  ✓ GREEN — no cross-project patterns found "
              "(few lessons / are not repeated in ≥N projects). Collect more: analyst digest by project.")
    else:
        for p in patterns:
            print(f"  ⚑ [{p['namespace']}] {p['pattern_id']}  · {p['weight']} project(ov), "
                  f"{p['lessons']} lesson(ov)")
            print(f"      {p['representative']['trigger']}")
            print(f"      projects: {', '.join(p['projects'])}")
        dest = env.state_dir / "suggestions"
        print(f"\n  {len(patterns)} pattern(ov) → {'(dry-run, not recorded)' if opts['dry_run'] else dest}")
        print("  Skill draft: analyst suggest <pattern_id> (P4). The promotion to the bucket is a person, not an auto-record.")
    if pruned:
        label = "orphans for withdrawal (dry-run)" if opts["dry_run"] else "filmed orphans"
        print(f"  {label}: {len(pruned)}")
    print()

