"""audit — bucket-audit: size · overlap · usage · verdicts on the entire skill registry
(P7.1 SKM-MASTER-002).

Why: solutions for ~205 skills without metrics - fortune telling. Collects into one report:

  size - review `budget.skill_budget` (⊕tier0/↻tier1/⌥tier2); aicore.content.budget remains
             THE ONLY source of token mathematics, this module only consumes it,
             does not expand.
  overlap  — Jaccard≥0.4 by description-triggers (normalized description words) AND/OR
             5-gram word-shingle≥0.3 by body (is more resistant to reformulations than
             character-by-character diff). Their compact sets on stdlib, without lib.
  usage    — fan-out by the skiller project registry → skill_usage from JSONL-transcripts,
             as in `analyze.py` (Skill-tool calls), window `--since N` days. Transcripts
             fail-safe (log format is not guaranteed; see analyze.parse_transcript) —
             unavailable/broken logs give usage=0, and not an audit crash.
  resident - SECOND, transcript-independent source of visibility (P2.2 SKM-MASTER-003):
             skill in CORE_SKILLS (config.py, tier-0 in each project) OR included in
             active set (profile/buckets `.swissknife.json`, same resolve_active_set,
             what `analyze._active_skill_names`) at least one registered project.
             Covers the blind spot transcript-scan: transcript scan catches ONLY explicit
             Skill-tool-calls (see analyze.py) — resident/auto-trigger skills (tier-0
             description, native preload) silently do not leave such a trace and falsely
             look dead. Residence - best-effort/graceful (broken/deleted project →
             is simply skipped, the audit does not fail).
  verdict - a pure function of metrics with constant thresholds: keep/thin/retrieval-only/
             merge/dead. Resident skill WITHOUT explicit skill-calls are not marked dead —
             instead keep with honest note (auto-trigger outside detection of both
             sources - see. verdict()/usage_note()).

Honesty of wording: skill with zero downloads in the window is marked EXACTLY «not used
in the window N days» — truncated data (short window / few scanned projects) NOT
equal proven uselessness. Field `channel` in the report (skill-call/resident/none)
shows WHICH of the two sources the skill was seen at all."""
import json
import re
import time
from pathlib import Path

from .analyze import agent_stats, logs_root, parse_transcript, skill_key
from ..budget import resolve_active_set
from aicore.content.budget import budget_for_set, skill_budget
from aicore.content.skill import (
    split_frontmatter as _split_frontmatter, read_frontmatter as parse_frontmatter)
from aicore.util.cli import parse_flags
from aicore.util.term import die
from ..config import CORE_SKILLS, load_config
from ..state import load_db

# --- verdict thresholds (constants - not magic numbers in place) ----------------
OVERLAP_DESC_JACCARD = 0.4     # similarity description-triggers -> candidate merge
OVERLAP_BODY_SHINGLE = 0.3     # similarity 5-gram body shingle -> candidate merge
TIER1_MONOLITH_TOKENS = 6000   # large body (↻ on-trigger) -> candidate thin-navigator
TIER1_LARGE_TOKENS = 2000      # noticeable body + rare use -> retrieval-only
LOW_USAGE_MAX_LOADS = 1        # ≤1 loading in window - «rare» (retrieval-only), not dead
SHINGLE_N = 5
DEFAULT_SINCE_DAYS = 30
DESCRIPTION_TRIGGER_PRIORITY_VERSION = "description-trigger-priority/v1"
_DESCRIPTION_EVIDENCE_RANK = {
    "observed-skill-call": 0,
    "resident-only": 1,
    "unobserved": 2,
}


class DescriptionDebtError(ValueError):
    """The description-trigger debt ledger cannot safely be projected."""


def _description_debt_path(env):
    return env.root / "scripts" / "desc-trigger-burndown.txt"


def read_description_debt(env, registry_keys):
    """Read the ratchet as membership data, never as a second trigger policy."""
    path = _description_debt_path(env)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise DescriptionDebtError(f"DESCRIPTION_DEBT_FILE_MISSING: {path}") from exc

    result, seen = [], set()
    for line_number, raw in enumerate(lines, start=1):
        key = raw.strip()
        if not key or key.startswith("#"):
            continue
        parts = key.split("/")
        if (len(parts) != 2 or not all(parts) or key != raw
                or any(part in {".", ".."} for part in parts)):
            raise DescriptionDebtError(
                f"DESCRIPTION_DEBT_MALFORMED_ROW: {path}:{line_number}: {raw!r}")
        if key in seen:
            raise DescriptionDebtError(
                f"DESCRIPTION_DEBT_DUPLICATE_KEY: {path}:{line_number}: {key}")
        if key not in registry_keys:
            raise DescriptionDebtError(
                f"DESCRIPTION_DEBT_REGISTRY_STALE: {path}:{line_number}: {key}")
        seen.add(key)
        result.append(key)
    return tuple(result)


def _description_evidence(row):
    if row["loaded_count"] > 0:
        return "observed-skill-call"
    if row["channel"] == "resident":
        return "resident-only"
    return "unobserved"


def build_description_debt(env, since_days=DEFAULT_SINCE_DAYS):
    """Join ratchet membership to existing audit data without inferring non-use."""
    audit = build_audit(env, since_days=since_days)
    by_key = {row["key"]: row for row in audit["items"]}
    debt_keys = read_description_debt(env, set(by_key))
    tier0_denominator = sum(row["tier0"] for row in audit["items"])
    rows = []
    for key in debt_keys:
        source = by_key[key]
        evidence = _description_evidence(source)
        tier0 = source["tier0"]
        rows.append({
            "key": key,
            "trigger_debt": True,
            "tier0": tier0,
            "loaded_count": source["loaded_count"],
            "channel": source["channel"],
            "evidence": evidence,
            "listing_share": {"numerator": tier0, "denominator": tier0_denominator},
            "priority_score": {
                "numerator": source["loaded_count"] * tier0,
                "denominator": tier0_denominator,
            },
        })
    rows.sort(key=lambda row: (-row["priority_score"]["numerator"],
                               _DESCRIPTION_EVIDENCE_RANK[row["evidence"]], row["key"]))
    coverage = {evidence: sum(row["evidence"] == evidence for row in rows)
                for evidence in _DESCRIPTION_EVIDENCE_RANK}
    return {
        "contract_version": DESCRIPTION_TRIGGER_PRIORITY_VERSION,
        "since_days": audit["since_days"],
        "scanned_projects": audit["scanned_projects"],
        "tier0_denominator": tier0_denominator,
        "debt_count": len(rows),
        "signal_coverage": coverage,
        "items": rows,
    }


# --- description-triggers / body-shingles ---------------------------------------
def _words(text):
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def desc_triggers(description):
    """Many normalized words description (≥3 char) — proxy «triggers»
    skill activations by which we count Jaccard-overlap descriptions."""
    return {w for w in _words(description) if len(w) >= 3}


def body_shingles(body, n=SHINGLE_N):
    """Many word n-gram (default 5) skill body - content similarity,
    more resistant to reformulations/permutations of paragraphs than character-by-character diff.
    In short n words → empty (NOT the only one «fallback»-shingle of all words): otherwise
    any two short bodies with the same number of words (< n) silently give
    Jaccard=1.0 and false overlap regardless of the actual meaning."""
    words = _words(body)
    if len(words) < n:
        return set()
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def jaccard(a, b):
    if not a and not b:
        return 0.0
    union = len(a | b)
    return (len(a & b) / union) if union else 0.0


# --- registry collection ----------------------------------------------------------------
def iter_registry_skills(env):
    """Skills for the entire roster (skills/**/SKILL.md) with description/body/budget.

    Returns [{bucket, name, key, dir, description, triggers, shingles,
    tier0, tier1, tier2}]. key = "bucket/name" (addressing in the report/pairs overlap).
    Path layout is identical registry.build_registry (bucket = parts[1]), but without
    column/upstream — audit.py does not duplicate the assembly skills.json, reads SKILL.md himself
    (need raw description/body for triggers/shingles that are not in skills.json)."""
    items = []
    for skill_md in sorted(env.root.glob("skills/**/SKILL.md")):
        rel = skill_md.relative_to(env.root)
        parts = rel.parts
        if len(parts) < 3:
            continue
        bucket = parts[1]
        fm = parse_frontmatter(skill_md)
        text = skill_md.read_text(encoding="utf-8-sig")
        # _split_frontmatter — review budget.py (do not duplicate body parsing; see her
        # docstring about conscious non-merging with common.parse_frontmatter).
        _, body = _split_frontmatter(text)
        b = skill_budget(skill_md.parent)
        if b is None:
            continue
        description = fm.get("description", "")
        items.append({
            "bucket": bucket, "name": b["name"], "key": f"{bucket}/{b['name']}",
            "dir": skill_md.parent, "description": description,
            "triggers": desc_triggers(description), "shingles": body_shingles(body),
            "tier0": b["tier0"], "tier1": b["tier1"], "tier2": b["tier2"],
        })
    return items


# --- overlap -----------------------------------------------------------------
def find_overlaps(items):
    """Pairs of skills above the threshold Jaccard(description) OR shingle(body). O(n²) —
    registry ~200 skills → ~20K steam, cheap at stdlib-sets. Returns
    [{a, b, desc_jaccard, body_shingle}] only for pairs above at least one threshold."""
    pairs = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            ia, ib = items[i], items[j]
            dj = jaccard(ia["triggers"], ib["triggers"])
            bs = jaccard(ia["shingles"], ib["shingles"])
            if dj >= OVERLAP_DESC_JACCARD or bs >= OVERLAP_BODY_SHINGLE:
                pairs.append({"a": ia["key"], "b": ib["key"],
                             "desc_jaccard": round(dj, 3), "body_shingle": round(bs, 3)})
    return pairs


def _overlap_map(pairs):
    """key -> [partner_key, ...] — quick check «yes overlap» at the verdict."""
    out = {}
    for p in pairs:
        out.setdefault(p["a"], []).append(p["b"])
        out.setdefault(p["b"], []).append(p["a"])
    return out


# --- usage: fan-out by projects.json --------------------------------------------
def _sessions_since(root, since_days):
    """main-transcripts (*.jsonl) of the project log directory, changed during since_days
    days. root may not exist (project without logs) — is then empty."""
    if not root.is_dir():
        return []
    cutoff = time.time() - since_days * 86400
    out = []
    for p in sorted(root.glob("*.jsonl")):
        try:
            if p.stat().st_mtime >= cutoff:
                out.append(p)
        except OSError:
            continue
    return out


def collect_usage(env, since_days=DEFAULT_SINCE_DAYS):
    """Fan out by the skiller project registry (<state>/skiller/projects.json): how many times each normalized
    skill actually loaded (Skill-tool, as in analyze.agent_stats) for the last
    since_days days across ALL registered projects (main-sessions + them
    subagents). Transcripts fail-safe — parse_transcript/agent_stats are tolerant to
    broken/missing files (log format is not guaranteed between versions CLI).

    Returns (loaded: {normalized_name: count}, scanned_projects: int) —
    scanned_projects=0 means usage-there is no data for the window at all (not «everything is dead»)."""
    db = load_db(env)
    loaded = {}
    scanned = 0
    for proj in db.get("projects", []):
        path = proj.get("path")
        if not path:
            continue
        root = logs_root(env, Path(path))
        sessions = _sessions_since(root, since_days)
        if not sessions:
            continue
        scanned += 1
        for sess in sessions:
            st = agent_stats(parse_transcript(sess), sess.stem)
            for k, c in st["skills"].items():
                loaded[k] = loaded.get(k, 0) + c
            subs_dir = sess.parent / sess.stem / "subagents"
            if subs_dir.is_dir():
                for sp in sorted(subs_dir.glob("agent-*.jsonl")):
                    st = agent_stats(parse_transcript(sp), sp.stem)
                    for k, c in st["skills"].items():
                        loaded[k] = loaded.get(k, 0) + c
    return loaded, scanned


# --- resident: second visibility source (P2.2 SKM-MASTER-003) -------------------
def _core_skill_names():
    """Normalized names CORE_SKILLS (last segment "bucket/name" —
    same normalization as skill_key/collect_usage) — are loaded by tier-0
    (name+description) in EVERY project by default, see config.py."""
    return {skill_key(p) for p in CORE_SKILLS}


def resident_skill_names(env):
    """Many normalized names «resident» skills - second,
    Transcript-INDEPENDENT visibility source:

      1) CORE_SKILLS (config.py) — are resident by tier-0 in each project.
      2) active set (profile/buckets `.swissknife.json`, same
         `budget.resolve_active_set`, which uses `analyze._active_skill_names`)
         at least ONE registered project (the skiller project registry).

    A resident skill may not leave any obvious Skill-tool-call in
    transcript (auto-trigger description/native preload out of detection transcript-
    scan, see docstring analyze.py) — that does NOT mean he's dead.

    Best-effort/graceful for each project: broken/missing `.swissknife.json`,
    unknown bucket (die from inside resolve_active_set) or remote project path -
    we just skip the project, the audit does not crash entirely (same principle as
    collect_usage about broken transcripts)."""
    names = _core_skill_names()
    db = load_db(env)
    for proj in db.get("projects", []):
        path = proj.get("path")
        if not path:
            continue
        target = Path(path)
        try:
            config = load_config(env, target)
            skills, meta = resolve_active_set(env, target, config)
            b = budget_for_set(skills, meta.get("pulled"))
            names |= {skill_key(i["name"]) for i in b["items"]}
        except SystemExit:
            continue  # unknown bucket/broken config -> skip project
        except Exception:
            continue  # any other degradation (FS/JSON) -> skip project
    return names


# --- verdict ------------------------------------------------------------------------------
def verdict(item, *, overlap_partners, loaded_count, scanned_projects, resident=False):
    """Pure metrics function → verdict (keep/thin/retrieval-only/merge/dead).

    Check procedure = signal priority (first match wins). Structural
    facts (overlap/body size - calculated from the MOST content, full confidence)
    go BEFORE usage-output (dead — based on incomplete logs of one machine/windows, see
    analyze.py about partial detection «explicit only Skill-tool»): otherwise large
    famous monolith, just not caught usage-detector in the window, drowns under «dead»
    instead «thin» — exactly the signal for which the size is needed is lost:
      1) merge           — overlap with another skill above the threshold Jaccard/shingle.
      2) thin            — monolith body (tier1 >= TIER1_MONOLITH_TOKENS).
      3) dead            — usage-data IS (scanned_projects>0) And 0 downloads in the window
                            And the skill is NOT resident (see resident_skill_names) — otherwise
                            keep (: resident without skill-calls ≠ is dead, this is the second
                            source of visibility, the transcript scan simply does not catch it).
      4) retrieval-only  — noticeable body (>= TIER1_LARGE_TOKENS) with rare
                            use (<= LOW_USAGE_MAX_LOADS, including «no data»).
      5) keep            — otherwise (including dead-candidates saved by residency).

    scanned_projects==0 → usage is uninformative: dead DO NOT set (truncated data ≠
    uselessness), but structural-verdicts (merge/thin) and retrieval-only by size
    are still applicable. usage_note() — text independent of the verdict, «not used
    in the window N days» is visible in the report even when the verdict «thin»/«merge»."""
    if overlap_partners:
        return "merge"
    if item["tier1"] >= TIER1_MONOLITH_TOKENS:
        return "thin"
    if scanned_projects > 0 and loaded_count == 0:
        return "keep" if resident else "dead"
    if item["tier1"] >= TIER1_LARGE_TOKENS and loaded_count <= LOW_USAGE_MAX_LOADS:
        return "retrieval-only"
    return "keep"


def usage_note(loaded_count, scanned_projects, since_days, resident=False):
    """EXACTLY «was not used in the window N days» with zero downloads - not «is dead»/
    «is useless» (truncated data ≠ proven useless). Resident skill
    (see resident_skill_names) without downloads receives a separate fair mark -
    it is visible by the second source (CORE/active set), and not «not used»."""
    if scanned_projects == 0:
        return f"usage: no data for window {since_days} days (0 scanned projects)"
    if loaded_count == 0:
        if resident:
            return "resident, no direct calls visible (auto-trigger out of detection)"
        return f"was not used in the {since_days} day window"
    return f"{loaded_count}× in {since_days} days"


# --- report assembly ----------------------------------------------------------------
def build_audit(env, since_days=DEFAULT_SINCE_DAYS):
    items = iter_registry_skills(env)
    pairs = find_overlaps(items)
    ov_map = _overlap_map(pairs)
    loaded, scanned = collect_usage(env, since_days)
    resident = resident_skill_names(env)

    rows = []
    for it in items:
        partners = ov_map.get(it["key"], [])
        loaded_count = loaded.get(it["name"], 0)
        is_resident = it["name"] in resident
        # channel: which of two independent sources saw the skill - explicit
        # skill-call (stronger, transcript) outweighs residency (indirect
        # signal: CORE/active set), if both are missing - none.
        channel = "skill-call" if loaded_count > 0 else ("resident" if is_resident else "none")
        v = verdict(it, overlap_partners=partners, loaded_count=loaded_count,
                    scanned_projects=scanned, resident=is_resident)
        rows.append({
            "bucket": it["bucket"], "name": it["name"], "key": it["key"],
            "tier0": it["tier0"], "tier1": it["tier1"], "tier2": it["tier2"],
            "overlap_with": sorted(partners), "loaded_count": loaded_count,
            "channel": channel,
            "usage_note": usage_note(loaded_count, scanned, since_days, resident=is_resident),
            "verdict": v,
        })
    return {
        "since_days": since_days, "scanned_projects": scanned,
        "resident_skills": len(resident),
        "skills": len(rows), "overlap_pairs": pairs, "items": rows,
    }


# --- render ------------------------------------------------------------------
def render_audit(report):
    out = []
    out.append("")
    out.append("━━━ BUCKET-AUDIT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    out.append(f"Skills: {report['skills']}   usage-window: {report['since_days']} days   "
               f"projects scanned: {report['scanned_projects']}   "
               f"resident (CORE/active set): {report.get('resident_skills', 0)}")
    counts = {}
    for r in report["items"]:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    if counts:
        out.append("Verdicts: " + " · ".join(f"{k}={v}" for k, v in sorted(counts.items())))

    items = report["items"]
    width = max((len(r["key"]) for r in items), default=10)
    out.append("")
    out.append(f"  {'skill'.ljust(width)}  ⊕tier0  ↻tier1  verdict channel       usage")
    for r in sorted(items, key=lambda r: (r["verdict"], -r["tier1"])):
        out.append(f"  {r['key'].ljust(width)}  {r['tier0']:>6}  {r['tier1']:>6}  "
                   f"{r['verdict']:<17} {r.get('channel', 'none'):<11} {r['usage_note']}")

    if report["overlap_pairs"]:
        out.append("")
        out.append("─── Overlap-pairs (desc-triggers Jaccard≥0.4 / body shingle≥0.3) ─")
        for p in report["overlap_pairs"]:
            out.append(f"  {p['a']} × {p['b']}   desc={p['desc_jaccard']}  "
                       f"body={p['body_shingle']}")
    out.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    out.append("")
    return "\n".join(out)


def render_description_debt(report):
    out = ["", "━━━ DESCRIPTION-TRIGGER DEBT ━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
    out.append(f"Debt: {report['debt_count']}   ⊕tier0 denominator: {report['tier0_denominator']}   "
               f"projects scanned: {report['scanned_projects']}")
    coverage = report["signal_coverage"]
    out.append("Signal: " + " · ".join(
        f"{name}={coverage[name]}" for name in _DESCRIPTION_EVIDENCE_RANK))
    if report["items"]:
        out.append("")
        out.append("  skill  priority  evidence  listing share")
        for row in report["items"]:
            score = row["priority_score"]
            share = row["listing_share"]
            out.append(f"  {row['key']}  {score['numerator']}/{score['denominator']}  "
                       f"{row['evidence']}  {share['numerator']}/{share['denominator']}")
    out.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    out.append("")
    return "\n".join(out)


# --- CLI -----------------------------------------------------------------------
def cmd_bucket_audit(env, argv):
    opts = parse_flags(argv, {"--since": "str", "--json": "bool", "--description-debt": "bool"})
    if opts["help"]:
        print("skiller bucket-audit [--since N] [--json] [--description-debt]")
        print("  Metrics for the entire skill registry: size (⊕tier0/↻tier1/⌥tier2, review\n"
              "  budget.skill_budget) · overlap (description-triggers Jaccard≥0.4 / body\n"
              "  5-gram shingle≥0.3) · usage — TWO independent visibility sources:\n"
              "  explicit skill-call (fan-out by the project registry, window\n"
              "  --since N days, default 30) And residency (CORE_SKILLS/active\n"
              "  project set, field channel: skill-call|resident|none) · verdicts\n"
              "  keep/thin/retrieval-only/merge/dead (resident skill without\n"
              "  skill-call NOT marked dead — pure metrics function).")
        return
    since_raw = opts.get("since") or str(DEFAULT_SINCE_DAYS)
    try:
        since_days = int(since_raw)
    except ValueError:
        die(f"--since waits for an integer number of days, received: {since_raw}")
    if since_days <= 0:
        die(f"--since waits for a positive number of days, received: {since_days}")
    if opts.get("description_debt"):
        try:
            report = build_description_debt(env, since_days)
        except DescriptionDebtError as exc:
            die(str(exc))
        if opts.get("json"):
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return
        print(render_description_debt(report))
        return
    report = build_audit(env, since_days)
    if opts.get("json"):
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    print(render_audit(report))
