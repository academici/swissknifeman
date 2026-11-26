"""analyst proposals — draft SYSTEM improvement proposals.

The bridge between what analyst WATCHING (digest/scan/ingest — project-specific data/
pattern), and what would be worth improving AT THE ECOSYSTEM LEVEL: stack pack (`stack-pack`),
override target project (`project-override`) or documentation (`docs`). Writes ONLY to
your directory:

    ~/.swissknifeman/analyst/proposals/<type>/<id>/
      PROPOSAL.md            — human-readable body (deterministic, WITHOUT timestamp)
      proposal.meta.json     — provenance passport + CURRENT status (draft|accepted|rejected)
    ~/.swissknifeman/analyst/proposals/audit.ndjson
                              — append-only status change history (NOT a body - the body does not carry status)

INVARIANT (analyst): auto-apply PROHIBITED - analyst NEVER writes to agent-packs/
templates/projects. Promote `accepted`-proposals for real editing - by human hands/
plan-design; this module only saves a draft and prints handoff-sequence
«what and where to apply» (see `handoff_lines`/`build_handoff_lines`).

Writer edit-safe as in `suggest.py`: body - deterministic input function (without
timestamp — otherwise seed_sha256-detection of manual edits would trigger falsely for every re-create).
Status lives ONLY in proposal.meta.json (current pointer) — status change does NOT overwrite
body and does not move the file between directories (unlike lessons.move_lesson: `<type>/<id>/`
static), but only adds audit-line (transition history, never overwritten)."""
import hashlib
import json
import os
from pathlib import Path

from aicore.util.cli import parse_args
from aicore.util.io import atomic_write_json, atomic_write_text, read_ndjson, safe_load_json
from aicore.util.term import die, now_iso
from aicore.util.text import sanitize

PROPOSAL_SCHEMA_VERSION = 1
PROPOSAL_TYPES = ("stack-pack", "project-override", "docs")
STATUSES = ("draft", "accepted", "rejected")
TITLE_SLUG_MAX = 40

# Generic (repo-grounded) handoff-steps by type - where exactly (--target) is decided by the author
# suggestions on WHAT and HOW to apply - fixed here (analyst NEVER writes here).
_HANDOFF_STEPS = {
    "stack-pack": (
        "edits - ONLY in the harness agent-pack sources (see `harness agent-packs list`) "
        "<pack> (person, by skill system/agent-packs); analyst does NOT write to agent-packs/",
        "pack version + entry in the pack CHANGELOG.md (in the harness agent-pack sources)",
        "rollout for projects: `harness agent-packs upgrade --pack <pack> --target <project>` "
        "(user_owned-the pack will not touch project files - D11 base+overlay)",
        "the harness validation (`validate.sh` of the harness repository)",
    ),
    "project-override": (
        "edits - ONLY in override/extension-zone of the TARGET project: user_owned-files "
        "agent-pack (base+overlay, D11); analyst DOES NOT write to projects",
        "generated/managed-do NOT edit the pack files manually - they will be overwritten by the next one "
        "`harness agent-packs render`/`upgrade`",
        "verification after editing: harness agent-packs doctor --target <project>",
        "validation - standard dev-loop target project",
    ),
    "docs": (
        "edits - in target documentation: docs/reference.md · docs/roadmap.md (umbrella) or "
        "the docs/ folder of the owning module (per-module, standalone-assembly); analyst does NOT write to docs/",
        "per-package edits - run if necessary scripts/docs-sync.sh (umbrella unit)",
        "if the proposal is about the analyst module itself — note in its CLAUDE.md",
    ),
}


def handoff_steps(ptype):
    """CLEAR: [step,...] for the offer type. Unknown/broken type (e.g. from damaged
    meta.json) → fallback on 'docs' (most neutral route), we don't fall."""
    return list(_HANDOFF_STEPS.get(ptype, _HANDOFF_STEPS["docs"]))


def build_handoff_lines(ptype):
    """PURE: numbered lines handoff for tele PROPOSAL.md/print CLI."""
    return [f"{i}. {s}" for i, s in enumerate(handoff_steps(ptype), 1)]


# ── id (deterministic slug from type+contents) ──────────────────────────
def make_proposal_id(ptype, title):
    """Deterministic id: slug(title) + short hash(type|title). Same (type, title)
    → same id (idempotent create/update-loop like pattern_id in scan.py); change title
    starts a NEW offer (this is conscious - title = identity, summary/body — contents,
    evolving through edit-safe writer)."""
    slug = sanitize(title)[:TITLE_SLUG_MAX] or ptype
    h = hashlib.sha1(f"{ptype}\x00{title}".encode("utf-8")).hexdigest()[:8]
    return f"{slug}-{h}"


# ── pure generators (without I/O/hours) ────────────────────────────────────────
def build_proposal_md(ptype, pid, title, summary, body, target):
    """CLEAR: full text PROPOSAL.md. Deterministic from input - timestamp does NOT hit
    to the body (see modular docstring). The status is also NOT in the body: SSOT status - meta.json,
    status change should not trigger overwrite/body reissue."""
    lines = [
        f"# Offer (draft) — {title}",
        "",
        "> **Not automatically applied.** analyst NEVER writes to agent-packs/templates/"
        "projects - draft awaiting human review/plan-design. Status changes "
        "`analyst proposals status <id> accepted|rejected`.",
        "",
        f"- **type:** {ptype}",
        f"- **id:** {pid}",
        f"- **target:** {target or '—'}",
        "",
        "## Summary",
        summary or "TODO — briefly what is proposed.",
        "",
        "## Rationale / context",
        body or "TODO — why this is needed, what was observed.",
        "",
        "## Handoff — what and where to apply",
    ]
    lines += build_handoff_lines(ptype)
    lines.append("")
    return "\n".join(lines)


def _seed_hash(text):
    """sha256-body hash - token «generated» states for detecting manual edits."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_meta(ptype, pid, title, target, seed_sha256, status, created_at, updated_at):
    """CLEAR: provenance passport proposal.meta.json (SSOT current status)."""
    return {
        "schema_version": PROPOSAL_SCHEMA_VERSION,
        "generated_by": "analyst proposals",
        "id": pid,
        "type": ptype,
        "title": title,
        "target": target,
        "status": status,
        "seed_sha256": seed_sha256,
        "created_at": created_at,
        "updated_at": updated_at,
    }


# ── paths (cross-project layer ~/.swissknifeman/analyst) ───────────────────────
def _proposals_root(env):
    return env.state_dir / "proposals"


def _proposal_dir(env, ptype, pid):
    return _proposals_root(env) / ptype / pid


def _audit_path(env):
    return _proposals_root(env) / "audit.ndjson"


# ── read ───────────────────────────────────────────────────────────────────
def load_proposal(env, ptype, pid):
    """meta dict one sentence or None (no/broken meta.json)."""
    meta = safe_load_json(_proposal_dir(env, ptype, pid) / "proposal.meta.json", None)
    return meta if isinstance(meta, dict) else None


def find_proposal(env, pid, ptype=None):
    """(meta, ptype) first match by id; ptype narrows the search (otherwise overkill
    PROPOSAL_TYPES). (None, None), if not found."""
    for t in (ptype,) if ptype else PROPOSAL_TYPES:
        meta = load_proposal(env, t, pid)
        if meta is not None:
            return meta, t
    return None, None


def list_proposals(env, *, ptype=None, status=None):
    """[(meta, ptype)] sorted by (type, id). Broken/directorless input - SKIP."""
    out = []
    for t in (ptype,) if ptype else PROPOSAL_TYPES:
        tdir = _proposals_root(env) / t
        if not tdir.is_dir():
            continue
        for d in sorted(tdir.iterdir()):
            if not d.is_dir():
                continue
            meta = load_proposal(env, t, d.name)
            if meta is None:
                continue
            if status and meta.get("status") != status:
                continue
            out.append((meta, t))
    return out


def read_audit(env):
    """List of entries proposals/audit.ndjson (skips broken lines). [] if there is no file."""
    return read_ndjson(_audit_path(env))


# ── audit (append-only, same idiom as lessons.audit_append/read_audit) ────
def audit_append(env, record):
    """Add one entry to proposals/audit.ndjson (append-only, never overwrite).
    Adds ts, if it is not there. Creates a directory."""
    rec = dict(record)
    rec.setdefault("ts", now_iso())
    path = _audit_path(env)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


# ── writer with edit-safety (I/O, like suggest.write_draft) ──────────────────────
def write_proposal(env, ptype, title, *, summary="", body="", target="", force=False):
    """Write/update draft proposal in proposals/<type>/<id>/. Edit-safe:
    - directory/no file            → create (status="created", meta.status="draft");
    - body matches the generated one    → nothing to change (status="unchanged");
    - body == past seed (did not correct) or --force → regenerate (status="updated"/"forced");
      CURRENT status (draft/accepted/rejected) and created_at SAVED - content-update not
      rolls back review progress;
    - body != past seed (ruled with their hands) → we DO NOT touch the body, we only update the provenance meta
      (status="skipped-edited").
    Returns (status, pid, proposal_dir). Atomic; directories are created."""
    if ptype not in PROPOSAL_TYPES:
        raise ValueError(f"unknown type suggestions: {ptype}")
    pid = make_proposal_id(ptype, title)
    prop_dir = _proposal_dir(env, ptype, pid)
    md_path = prop_dir / "PROPOSAL.md"
    meta_path = prop_dir / "proposal.meta.json"
    md_text = build_proposal_md(ptype, pid, title, summary, body, target)
    new_seed = _seed_hash(md_text)

    def _persist(seed, status, created_at):
        atomic_write_text(md_path, md_text)
        atomic_write_json(meta_path,
                          build_meta(ptype, pid, title, target, seed, status,
                                     created_at, now_iso()))

    if not md_path.exists():
        _persist(new_seed, "draft", now_iso())
        return "created", pid, prop_dir

    current = md_path.read_text(encoding="utf-8")
    prev_meta = safe_load_json(meta_path, {}) or {}
    status = prev_meta.get("status") or "draft"
    created_at = prev_meta.get("created_at") or now_iso()

    if current == md_text:
        return "unchanged", pid, prop_dir

    prev_seed = prev_meta.get("seed_sha256")
    if force or _seed_hash(current) == prev_seed:
        _persist(new_seed, status, created_at)
        return ("forced" if force and _seed_hash(current) != prev_seed
                else "updated"), pid, prop_dir

    # ruled with their hands → the body is not overwritten; We update only the provenance passport (seed = past,
    # so that the edit detection continues to work against the last GENERATED state).
    atomic_write_json(meta_path,
                      build_meta(ptype, pid, title, target, prev_seed, status,
                                 created_at, now_iso()))
    return "skipped-edited", pid, prop_dir


# ── status change (separate audit-string, not overwriting history) ────────────
def set_status(env, pid, new_status, *, ptype=None, note=""):
    """Translate sentence to new_status: meta.json — CURRENT pointer (is overwritten),
    audit.ndjson — HISTORY (add-on only). Same status → no-op (without audit-take).
    Returns (meta, old_status, new_status) or (None, None, None), if not found."""
    if new_status not in STATUSES:
        raise ValueError(f"unknown status: {new_status}")
    meta, t = find_proposal(env, pid, ptype)
    if meta is None:
        return None, None, None
    old_status = meta.get("status") or "draft"
    if old_status == new_status:
        return meta, old_status, new_status
    new_meta = dict(meta, status=new_status, updated_at=now_iso())
    atomic_write_json(_proposal_dir(env, t, pid) / "proposal.meta.json", new_meta)
    audit_append(env, {"action": "status-change", "id": pid, "type": t,
                       "from": old_status, "to": new_status, "note": note})
    return new_meta, old_status, new_status


def handoff_lines(meta):
    """Human readable handoff-sequence for CLI (sentence title + steps
    by type). analyst NEVER writes here - seal/documenting the route to a person."""
    target = meta.get("target") or "<specify --target: pack/project/doc file>"
    header = [f"  Suggestion: {meta.get('title')}  [{meta.get('status')}] · "
             f"id={meta.get('id')} · type={meta.get('type')} · target={target}",
             "  Promoter - human ONLY/plan-design (analyst does NOT write to agent-packs/templates/projects):"]
    return header + [f"    {s}" for s in build_handoff_lines(meta.get("type"))]


# ── CLI ──────────────────────────────────────────────────────────────────────
def _cmd_create(env, argv):
    """analyst proposals create --type T --title TITLE [--summary S] [--body-file F]
    [--target T] [--dry-run] [--json] [--force]"""
    opts, _ = parse_args(argv, {"--type": "str", "--title": "str", "--summary": "str",
                                "--body-file": "str", "--target": "str",
                                "--dry-run": "bool", "--json": "bool", "--force": "bool"})
    if opts["help"]:
        print("analyst proposals create --type stack-pack|project-override|docs --title T\n"
              "  [--summary S] [--body-file F] [--target T] [--dry-run] [--json] [--force]\n"
              "  Draft proposal (edit-safe: seed_sha256, WITHOUT timestamp in the body).\n"
              "  Writes ONLY to ~/.swissknifeman/analyst/proposals/<type>/<id>/.")
        return
    ptype = opts["type"]
    if ptype not in PROPOSAL_TYPES:
        die(f"--type is required, one of: {', '.join(PROPOSAL_TYPES)} (received: {ptype!r})")
    title = (opts["title"] or "").strip()
    if not title:
        die("--title is required: analyst proposals create --type T --title 'header'")

    body = ""
    if opts["body_file"]:
        body_path = Path(os.path.expanduser(opts["body_file"]))
        if not body_path.is_file():
            die(f"--body-file not found: {body_path}")
        body = body_path.read_text(encoding="utf-8")
    summary = (opts["summary"] or "").strip()
    target = (opts["target"] or "").strip()

    if opts["dry_run"]:
        pid = make_proposal_id(ptype, title)
        text = build_proposal_md(ptype, pid, title, summary, body, target)
        if opts["json"]:
            print(json.dumps({"id": pid, "type": ptype, "status": "dry-run",
                              "path": str(_proposal_dir(env, ptype, pid))},
                             ensure_ascii=False, indent=2))
        else:
            print(f"\nanalyst proposals create (dry-run) — id={pid} · type={ptype}\n")
            print(text)
        return

    status, pid, prop_dir = write_proposal(env, ptype, title, summary=summary, body=body,
                                           target=target, force=opts["force"])
    meta = load_proposal(env, ptype, pid)

    if opts["json"]:
        print(json.dumps({"id": pid, "type": ptype, "write_status": status,
                          "status": meta.get("status"), "path": str(prop_dir)},
                         ensure_ascii=False, indent=2))
        return

    print(f"\nanalyst proposals create — id={pid} · type={ptype} · {status}\n  {prop_dir}\n")
    for line in handoff_lines(meta):
        print(line)
    print()


def _cmd_list(env, argv):
    """analyst proposals list [--type T] [--status draft|accepted|rejected] [--json]"""
    opts, _ = parse_args(argv, {"--type": "str", "--status": "str", "--json": "bool"})
    if opts["help"]:
        print("analyst proposals list [--type T] [--status draft|accepted|rejected] [--json]")
        return
    ptype = opts["type"] or None
    if ptype and ptype not in PROPOSAL_TYPES:
        die(f"--type is waiting for one of: {', '.join(PROPOSAL_TYPES)}")
    status = opts["status"] or None
    if status and status not in STATUSES:
        die(f"--status is waiting for one of: {', '.join(STATUSES)}")

    items = list_proposals(env, ptype=ptype, status=status)
    if opts["json"]:
        print(json.dumps({"proposals": [
            {"id": m.get("id"), "type": t, "title": m.get("title"),
             "status": m.get("status"), "target": m.get("target")}
            for m, t in items]}, ensure_ascii=False, indent=2))
        return
    if not items:
        print("\nanalyst proposals — empty (see analyst proposals create)\n")
        return
    print(f"\nanalyst proposals — {len(items)}\n")
    for m, t in items:
        tail = f" (target: {m['target']})" if m.get("target") else ""
        print(f"  [{m.get('status')}] {t}/{m.get('id')} — {m.get('title')}{tail}")
    print()


def _cmd_show(env, argv):
    """analyst proposals show <id> [--type T] [--json]"""
    opts, pos = parse_args(argv, {"--type": "str", "--json": "bool"}, max_pos=1)
    if opts["help"] or not pos:
        print("analyst proposals show <id> [--type T] [--json]")
        return
    meta, t = find_proposal(env, pos[0], opts["type"] or None)
    if meta is None:
        die(f"offer not found: {pos[0]}")
    md_text = (_proposal_dir(env, t, pos[0]) / "PROPOSAL.md").read_text(encoding="utf-8")
    if opts["json"]:
        print(json.dumps({"meta": meta, "body": md_text}, ensure_ascii=False, indent=2))
        return
    print(md_text)


def _cmd_status(env, argv):
    """analyst proposals status <id> draft|accepted|rejected [--type T] [--note N] [--json]"""
    opts, pos = parse_args(argv, {"--type": "str", "--note": "str", "--json": "bool"}, max_pos=2)
    if opts["help"] or len(pos) < 2:
        print("analyst proposals status <id> draft|accepted|rejected [--type T] [--note N] [--json]\n"
              "  Change of status - SEPARATE audit-line in proposals/audit.ndjson (story not\n"
              "  is overwritten). DOES NOT apply the clause - just changes the label.")
        return
    pid, new_status = pos[0], pos[1]
    if new_status not in STATUSES:
        die(f"status must be one of: {', '.join(STATUSES)} (received: {new_status!r})")
    meta, old, new = set_status(env, pid, new_status, ptype=opts["type"] or None,
                                note=opts["note"] or "")
    if meta is None:
        die(f"offer not found: {pid}")

    if opts["json"]:
        print(json.dumps({"id": pid, "from": old, "to": new}, ensure_ascii=False, indent=2))
        return
    if old == new:
        print(f"\nanalyst proposals status — {pid} is already in status {new} (no changes)\n")
        return
    print(f"\nanalyst proposals status — {pid}: {old} → {new} (audit-entry added)\n")
    if new == "accepted":
        for line in handoff_lines(meta):
            print(line)
        print()


def _cmd_handoff(env, argv):
    """analyst proposals handoff <id> [--type T] [--json]"""
    opts, pos = parse_args(argv, {"--type": "str", "--json": "bool"}, max_pos=1)
    if opts["help"] or not pos:
        print("analyst proposals handoff <id> [--type T] [--json]\n"
              "  Print handoff-sequences «what and where to apply» (person/plan-design).\n"
              "  analyst NEVER writes to agent-packs/templates/projects - only prints the route.")
        return
    meta, t = find_proposal(env, pos[0], opts["type"] or None)
    if meta is None:
        die(f"offer not found: {pos[0]}")
    lines = handoff_lines(meta)
    if opts["json"]:
        print(json.dumps({"id": pos[0], "type": t, "status": meta.get("status"),
                          "handoff": lines}, ensure_ascii=False, indent=2))
        return
    print()
    for line in lines:
        print(line)
    print()


_SUBCOMMANDS = {
    "create": _cmd_create,
    "list": _cmd_list,
    "show": _cmd_show,
    "status": _cmd_status,
    "handoff": _cmd_handoff,
}


def cmd_proposals(env, argv):
    """analyst proposals <create|list|show|status|handoff> [...]
    — draft system proposals (stack-pack/project-override/docs) in
    ~/.swissknifeman/analyst/proposals/. analyst NEVER writes to agent-packs/templates/
    projects - only saves a draft and prints handoff-sequence to a person."""
    if not argv or argv[0] in ("-h", "--help"):
        print("analyst proposals <create|list|show|status|handoff> [...]\n"
              "  create --type stack-pack|project-override|docs --title T [--summary S]\n"
              "         [--body-file F] [--target T] [--dry-run] [--json] [--force]\n"
              "  list   [--type T] [--status draft|accepted|rejected] [--json]\n"
              "  show   <id> [--type T] [--json]\n"
              "  status <id> draft|accepted|rejected [--type T] [--note N] [--json]\n"
              "  handoff <id> [--type T] [--json]\n"
              "  Drafts are NOT automatically applied - promote accepted does a person/\n"
              "  plan-design hands (see handoff). Catalog: ~/.swissknifeman/analyst/proposals/.")
        return
    sub, rest = argv[0], argv[1:]
    handler = _SUBCOMMANDS.get(sub)
    if handler is None:
        die(f"unknown subcommand proposals: {sub} (see analyst proposals --help)")
    handler(env, rest)
