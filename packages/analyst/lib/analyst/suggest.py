"""analyst suggest (P4) — cross-project pattern → DRAFT skill (draft SKILL.ru.md).

Deterministic (stdlib, on-demand — without daemon) bridge between `scan` and reusable
skill. Reads the pattern index ONLY (`~/.swissknifeman/analyst/index/by_pattern/<id>.json`,
writes it `scan`) and generates staged-draft in `~/.swissknifeman/analyst/drafts/<pattern_id>/`:

    drafts/<pattern_id>/
      SKILL.ru.md      — RU-source-BLANK (ruled by man) with frontmatter-skeleton
      draft.meta.json  — provenance passport of the draft + seed_sha256 (detection of manual edits)

INVARIANT (analyst): auto-recording to skills is PROHIBITED — suggest does NOT write to skills/, DOES NOT generate
EN-canon (this is a casual person skiller after modification), DOES NOT register, DOES NOT disclose raw/secrets.
Promoting a draft into a bucket - by human hands (see handoff in the output). Privacy IS STRUCTURED:
index by_pattern/ — already abstracted projection (trigger/action/kind), there are no raw materials in it.

Code model (like digest/scan): PURE generators (pattern→text) + writer with I/O in cmd_suggest.

A note on determinism: provenance stamp in SKILL.ru.md does NOT carry timestamp (he lives only in
draft.meta.json) — otherwise the body would be non-deterministic and seed_sha256-detection of manual edits (D6)
would trigger falsely for every re-suggest.
"""
import hashlib
import re

from .common import (atomic_write_json, atomic_write_text, die, now_iso,
                     parse_args, safe_load_json, warn)

DRAFT_SCHEMA_VERSION = 1
RESERVED_NAME_WORDS = ("claude", "anthropic")   # official. ban in name skills Claude Code
NAME_MAX = 64                                    # official. limit name (lowercase/numbers/hyphens)
DESC_SOFT_MAX = 150                              # soft target resident description


# ── pure generators (without I/O/hours) ────────────────────────────────────────
def _slug_name(representative):
    """kebab-name-candidate from representative (trigger→action fallback): lowercase, only
    [a-z0-9-], without leading/trailing hyphens, without reserved (claude/anthropic), ≤64. Man
    finalizes so that name == name of the final skill directory."""
    base = (representative.get("trigger") or representative.get("action") or "skill").lower()
    parts = [p for p in re.sub(r"[^a-z0-9]+", "-", base).split("-")
             if p and p not in RESERVED_NAME_WORDS]
    slug = "-".join(parts)[:NAME_MAX].strip("-")
    return slug or "skill"


def _draft_description(representative):
    """RU-blank description (≤~150 char, soft target; man rules). Screening `\\` and `"`
    — description is placed in YAML double-quoted scalar (e.g. `App\\Domain` otherwise broken YAML)."""
    action = (representative.get("action") or "").strip()
    trigger = (representative.get("trigger") or "").strip()
    body = " — ".join(x for x in (action, trigger) if x) or "reused lesson"
    if len(body) > DESC_SOFT_MAX:
        body = body[:DESC_SOFT_MAX - 1].rstrip() + "…"
    return body.replace("\\", "\\\\").replace('"', '\\"')


def _provenance_stamp(pattern):
    """Inert HTML-provenance stamp in the body SKILL.ru.md (WITHOUT timestamp — determinism).
    Carried with the file; a man films before a promotion. SSOT provenance — draft.meta.json."""
    projs = ", ".join(pattern.get("projects") or [])
    return (f"<!-- analyst-provenance: generated `analyst suggest` from pattern "
            f"{pattern['pattern_id']} · ns {pattern['namespace']} · "
            f"{pattern.get('weight', 0)} project(ov) ({projs}) · {pattern.get('lessons', 0)} lesson(ov). "
            f"Source: index/by_pattern/{pattern['pattern_id']}.json. "
            f"REMOVE this block before promotion. -->")


def build_skill_ru(pattern, bucket):
    """CLEAR: full text of the blank SKILL.ru.md (frontmatter-skeleton + provenance + body).
    Determined from (pattern, bucket) — timestamp does NOT go here (see modular docstring).
    Body abstracted: only representative + members-triggers from index (raw not in the index)."""
    rep = pattern.get("representative") or {}
    name = _slug_name(rep)
    projs = pattern.get("projects") or []
    fm = [
        "---",
        f"name: {name}",
        f"bucket: {bucket}",
        "version: 0.1.0",
        f'description: "{_draft_description(rep)} (draft; ≤150 char, ruled by man)"',
        "risk: read                     # TODO: specify (read|draft|write|external)",
        'persona: ""',
        "tags: []",
        "requires: []",
        "produces_for: []",
        "outputs: []",
        "---",
    ]
    heading = rep.get("trigger") or rep.get("action") or pattern["pattern_id"]
    body = [
        _provenance_stamp(pattern),
        "",
        f"# {heading} (draft)",
        "",
        "## Context (when to use)",
        f"The pattern was repeated in **{pattern.get('weight', len(projs))} projects** "
        f"namespace `{pattern['namespace']}`: {', '.join(projs)}.",
        f"- **trigger:** {rep.get('trigger') or '—'}",
        f"- **action:**  {rep.get('action') or '—'}",
        f"- **kind:**    {rep.get('kind') or '—'}",
        "",
        "## Observed instances (abstracted)",
    ]
    for m in pattern.get("members") or []:
        body.append(f"- `{m.get('project', '—')}` — {m.get('trigger') or '—'}")
    body += [
        "",
        "## Algorithm",
        "TODO — issue action into reused steps.",
        "",
        "## Checklist",
        "TODO",
        "",
    ]
    return "\n".join(fm + [""] + body)


def _seed_hash(text):
    """sha256-blank hash - marker «generated» states for detecting manual edits."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_meta(pattern, bucket, seed_sha256, generated_at):
    """CLEAR: provenance passport draft.meta.json (SSOT draft provenance)."""
    return {
        "schema_version": DRAFT_SCHEMA_VERSION,
        "generated_by": "analyst suggest",
        "pattern_id": pattern["pattern_id"],
        "namespace": pattern["namespace"],
        "projects": list(pattern.get("projects") or []),
        "weight": pattern.get("weight", 0),
        "lessons": pattern.get("lessons", 0),
        "bucket": bucket,
        "source_index": f"index/by_pattern/{pattern['pattern_id']}.json",
        "seed_sha256": seed_sha256,
        "generated_at": generated_at,
    }


def filter_by_weight(patterns, min_weight):
    """PURE: patterns with weight ≥ min_weight (None → without filter). The order is maintained."""
    if min_weight is None:
        return list(patterns)
    return [p for p in patterns if p.get("weight", 0) >= min_weight]


# ── reading pattern index (I/O, read-only) ────────────────────────────────
def _index_dir(env):
    return env.state_dir / "index" / "by_pattern"


def load_patterns(env):
    """Full dict's patterns from index/by_pattern/*.json, sorted by pattern_id
    (determinism). Broken JSON / without pattern_id|namespace → SKIP (like list_existing_patterns)."""
    idx_dir = _index_dir(env)
    out = []
    if not idx_dir.is_dir():
        return out
    for path in sorted(idx_dir.glob("*.json")):
        data = safe_load_json(path, None)
        if isinstance(data, dict) and data.get("pattern_id") and data.get("namespace"):
            out.append(data)
    return out


def load_pattern(env, pattern_id):
    """One pattern per id or None."""
    data = safe_load_json(_index_dir(env) / f"{pattern_id}.json", None)
    if isinstance(data, dict) and data.get("pattern_id") and data.get("namespace"):
        return data
    return None


def list_draft_ids(env):
    """pattern_id existing drafts (drafts/<id>/ with draft.meta.json), sorted."""
    drafts = env.state_dir / "drafts"
    if not drafts.is_dir():
        return []
    return sorted(d.name for d in drafts.iterdir()
                  if d.is_dir() and (d / "draft.meta.json").is_file())


def orphan_draft_ids(env, current_ids):
    """Drafts whose pattern has disappeared from the index (current_ids). For WARN — DO NOT delete (D6:
    draft human-editable, auto-delete = loss of labor; ≠ scan-prune)."""
    return [d for d in list_draft_ids(env) if d not in set(current_ids)]


# ── writer with edit-safety (I/O) ───────────────────────────────────────────────
def write_draft(env, pattern, bucket, *, force=False):
    """Write/update draft pattern in drafts/<id>/. Edit-safe (D6):
    - directory/no file           → create (status="created");
    - body matches the generated one   → nothing to change (status="unchanged");
    - body == past seed (did not correct) or --force → regenerate (status="updated"/"forced");
    - body != past seed (ruled with their hands) → we DO NOT touch the body, we only update the provenance meta
      (status="skipped-edited").
    Returns (status, ru_path). Atomic; directories are created."""
    pid = pattern["pattern_id"]
    draft_dir = env.state_dir / "drafts" / pid
    ru_path = draft_dir / "SKILL.ru.md"
    meta_path = draft_dir / "draft.meta.json"
    ru_text = build_skill_ru(pattern, bucket)
    new_seed = _seed_hash(ru_text)

    def _persist(seed):
        atomic_write_text(ru_path, ru_text)
        atomic_write_json(meta_path, build_meta(pattern, bucket, seed, now_iso()))

    if not ru_path.exists():
        _persist(new_seed)
        return "created", ru_path

    current = ru_path.read_text(encoding="utf-8")
    if current == ru_text:
        return "unchanged", ru_path

    prev_seed = (safe_load_json(meta_path, {}) or {}).get("seed_sha256")
    if force or _seed_hash(current) == prev_seed:
        _persist(new_seed)
        return ("forced" if force and _seed_hash(current) != prev_seed else "updated"), ru_path

    # ruled with their hands → the body is not overwritten; We update only the provenance passport (seed = past,
    # so that the edit detection continues to work against the last GENERATED state).
    atomic_write_json(meta_path, build_meta(pattern, bucket, prev_seed, now_iso()))
    return "skipped-edited", ru_path


# ── CLI ──────────────────────────────────────────────────────────────────────
def _resolve_bucket(env, opts):
    """bucket from --bucket or placeholder TODO. namespace→bucket NO auto-mapping
    (namespace — insulation, bucket — topic). Returns (bucket, hint[]): hint — available
    buckets from the registry skiller (best-effort, if reachable), to give a hint to a person."""
    if opts["bucket"]:
        return opts["bucket"], []
    hint = []
    buckets_json = env.monorepo_root / "packages" / "skiller" / "buckets.json"
    data = safe_load_json(buckets_json, None)
    if isinstance(data, dict):
        hint = sorted(data.keys())
    return "TODO", hint


def _handoff_lines(env, pid, bucket, name):
    """Accurate (repo-grounded) sequence of draft promotion in skill - printed
    person. NOT `skiller integrate` (he sews skills into the project, does not register a new one)."""
    b = bucket if bucket != "TODO" else "<bucket>"
    return [
        f"  Draft: {env.state_dir / 'drafts' / pid / 'SKILL.ru.md'}",
        "  Promotion in skill - human (analyst does NOT write to skills/, DOES NOT generate EN, DOES NOT register):",
        f"    1. mkdir -p <skiller>/skills/{b}/{name}/  and move it there SKILL.ru.md (name == directory)",
        "    2. generate EN-canon: promt packages/skiller/prompts/generate/claude-canon-from-ru.md → SKILL.md",
        "    3. bash packages/skiller/scripts/check-translations.sh --stamp",
        "    4. bash packages/skiller/scripts/validate.sh",
        "    5. skiller registry",
    ]


def cmd_suggest(env, argv):
    """analyst suggest <pattern_id> | --all [--bucket B] [--min-weight N] [--dry-run] [--json] [--force]
    — cross-project pattern (index/by_pattern/) → DRAFT SKILL.ru.md in ~/.swissknifeman/analyst/drafts/."""
    import json
    opts, pos = parse_args(argv, {"--all": "bool", "--bucket": "str", "--min-weight": "str",
                                  "--dry-run": "bool", "--json": "bool", "--force": "bool"},
                           max_pos=1)
    if opts["help"] or (not pos and not opts["all"]):
        print("analyst suggest <pattern_id> | --all [--bucket B] [--min-weight N] "
              "[--dry-run] [--json] [--force]\n"
              "  Cross-project pattern → DRAFT SKILL.ru.md in ~/.swissknifeman/analyst/drafts/.\n"
              "  does NOT write to skills/, DOES NOT generate EN, DOES NOT register. Promot is a person.\n"
              "  --all for all patterns; --min-weight N — only weight≥N; --force — overwrite\n"
              "  draft, edited by hand; --dry-run/--json — without entry.")
        return
    if pos and opts["all"]:
        die("indicate <pattern_id> OR --all, not both")

    min_weight = None
    if opts["min_weight"]:
        try:
            min_weight = int(opts["min_weight"])
        except ValueError:
            die(f"--min-weight is waiting for a number, received: {opts['min_weight']}")

    if opts["all"]:
        patterns = filter_by_weight(load_patterns(env), min_weight)
    else:
        p = load_pattern(env, pos[0])
        if p is None:
            die(f"pattern not found: {pos[0]} (see analyst scan — index/by_pattern/)")
        patterns = filter_by_weight([p], min_weight)

    bucket, bucket_hint = _resolve_bucket(env, opts)

    # orphans (there is a draft, the pattern has disappeared) — full view only (--all); WARN, not delete.
    orphans = orphan_draft_ids(env, [p["pattern_id"] for p in load_patterns(env)]) if opts["all"] else []

    results = []
    for p in patterns:
        name = _slug_name(p.get("representative") or {})
        if opts["dry_run"]:            # only dry-run suppresses writing; --json writes (like scan)
            status = "dry-run"
        else:
            status, _ = write_draft(env, p, bucket, force=opts["force"])
        results.append({"pattern_id": p["pattern_id"], "namespace": p["namespace"],
                        "weight": p.get("weight", 0), "name": name, "bucket": bucket,
                        "status": status})

    if opts["json"]:
        print(json.dumps({"drafts_dir": str(env.state_dir / "drafts"),
                          "min_weight": min_weight,
                          "results": results,
                          "orphans": orphans,
                          "dry_run": bool(opts["dry_run"])}, ensure_ascii=False, indent=2))
        return

    if not patterns:
        print("\nanalyst suggest — there are no suitable patterns "
              + (f"(weight≥{min_weight})" if min_weight is not None else "(index/by_pattern/ empty - run analyst scan)")
              + "\n")
        return

    verb = "drafts for entry (dry-run)" if opts["dry_run"] else "draft(ov)"
    print(f"\nanalyst suggest — {len(results)} {verb}"
          + (f" · bucket={bucket}" if bucket != "TODO" else "") + "\n")
    for r in results:
        print(f"  ⚑ [{r['namespace']}] {r['pattern_id']}  · weight {r['weight']} · "
              f"name-candidate: {r['name']}  ({r['status']})")
    if bucket == "TODO":
        tip = (", ".join(bucket_hint[:12]) + ", …") if bucket_hint else "see skiller buckets.json"
        print(f"\n  bucket not specified - select by person (--bucket B). Available: {tip}")
    # handoff — based on the first draft as a sample (for --all details are identical, catalogs are their own).
    print()
    for line in _handoff_lines(env, results[0]["pattern_id"], bucket, results[0]["name"]):
        print(line)
    if orphans:
        warn(f"orphaned drafts (pattern disappeared, NOT deleted - correct/clean manually): {', '.join(orphans)}")
    if opts["dry_run"]:
        print("\n  (dry-run — nothing recorded)")
    print()
