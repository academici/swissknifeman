"""analyst ingest — reception findings agent-analyst (/analyst:deep) in ephemeral-lessons.

Agent - reasoning layer (causal narrative, resolve CONFLICT, texts remediation);
this module is its only door to the lesson store, and the door is narrow (package invariants):

- **validation BEFORE the first side effect**: entire file findings is disassembled and checked
  whole; invalid JSON or schema → die WITHOUT a single entry (neither lesson nor audit-lines);
- **only ephemeral** — enforced code, not convention: `state` ≠ ephemeral or
  `detector` ≠ agent-finding in the file → die; recording occurs only through add_candidate
  (ephemeral) + safety assert;
- **man at the gate**: `promote_candidate` agent - just a marker PROMOTE-CANDIDATE in
  evidence (visible on `analyst review`), no progress here;
- provenance - using the existing mechanism: audit_append for each lesson accepted.

events.ndjson here we DO NOT write deliberately: finding agent - hypothesis, not verified
success signal (unlike digest, where the test actually took place); confidence lesson will begin
accumulate from subsequent observations digest/promote."""
import json
import os
from pathlib import Path

from .common import die, parse_args
from .lessons import (ACTIVE_STATES, KINDS, add_candidate, audit_append,
                      classify_consolidation, new_lesson, similar_lessons)

DETECTOR = "agent-finding"   # the only valid agent lesson detector
PROMOTE_MARK = "PROMOTE-CANDIDATE"

# Schema (strict: unknown key = die — catching the agent's contract drift rather than swallowing it)
_TOP_KEYS = {"source", "session", "findings"}
_FINDING_KEYS = {"trigger", "action", "kind", "scope", "evidence", "meta",
                 "review_hint", "session_id", "promote_candidate",
                 "detector", "state", "source"}


# ── validation (clean: payload → normalized findings | ValueError) ──────
def validate_findings(payload):
    """Check schema findings-of the entire file and return a normalized list of findings.

    Any violation → ValueError (the caller turns into die) — BEFORE any entries.
    Ephemeral-only and detector=agent-finding are protected by code here: attempt to convey otherwise
    status/detector - circuit error, not silent overwrite."""
    if not isinstance(payload, dict):
        raise ValueError("file root is not an object")
    unknown = set(payload) - _TOP_KEYS
    if unknown:
        raise ValueError(f"unknown top level keys: {', '.join(sorted(unknown))}")
    if payload.get("source") not in (None, "agent"):
        raise ValueError(f"source only allows 'agent', received: {payload.get('source')!r}")
    session = payload.get("session", "")
    if not isinstance(session, str):
        raise ValueError("session — is not a string")
    findings = payload.get("findings")
    if not isinstance(findings, list):
        raise ValueError("findings — not a list")

    out = []
    for i, f in enumerate(findings):
        where = f"findings[{i}]"
        if not isinstance(f, dict):
            raise ValueError(f"{where}: not an object")
        unknown = set(f) - _FINDING_KEYS
        if unknown:
            raise ValueError(f"{where}: unknown keys: {', '.join(sorted(unknown))}")
        trigger = f.get("trigger")
        action = f.get("action")
        if not isinstance(trigger, str) or not trigger.strip():
            raise ValueError(f"{where}: trigger is empty or not a string")
        if not isinstance(action, str) or not action.strip():
            raise ValueError(f"{where}: action is empty or not a string")
        kind = f.get("kind", "heuristic")
        if kind not in KINDS:
            raise ValueError(f"{where}: kind '{kind}' (valid: {', '.join(KINDS)})")
        # ephemeral-only / agent-finding-only — enforced scheme (die, not a silent fix)
        if "state" in f and f["state"] != "ephemeral":
            raise ValueError(f"{where}: agent writes ONLY ephemeral, received state={f['state']!r}")
        if "detector" in f and f["detector"] != DETECTOR:
            raise ValueError(f"{where}: detector only allows '{DETECTOR}', "
                             f"received: {f['detector']!r}")
        if "source" in f and f["source"] != "agent":
            raise ValueError(f"{where}: source only allows 'agent', received: {f['source']!r}")
        scope = f.get("scope", "")
        if not isinstance(scope, str):
            raise ValueError(f"{where}: scope — is not a string")
        evidence = f.get("evidence", [])
        if not (isinstance(evidence, list) and all(isinstance(e, str) for e in evidence)):
            raise ValueError(f"{where}: evidence — is not a list of strings")
        meta = f.get("meta", {})
        if not isinstance(meta, dict):
            raise ValueError(f"{where}: meta — not an object")
        review_hint = f.get("review_hint", "")
        if not isinstance(review_hint, str):
            raise ValueError(f"{where}: review_hint — is not a string")
        session_id = f.get("session_id", "")
        if not isinstance(session_id, str):
            raise ValueError(f"{where}: session_id — is not a string")
        out.append({
            "trigger": trigger, "action": action, "kind": kind, "scope": scope,
            "evidence": list(evidence), "meta": dict(meta), "review_hint": review_hint,
            "session_id": session_id or session,
            "promote_candidate": bool(f.get("promote_candidate", False)),
        })
    return out


def build_lessons(findings, *, scope_default, project):
    """Normalized findings → dictionaries lessons (clean: without IO). detector/source
    are protected by constants - the agent has nowhere to replace the provenance."""
    out = []
    for f in findings:
        evidence = list(f["evidence"])
        sid = f["session_id"]
        if sid and f"session:{sid}" not in evidence:
            evidence.append(f"session:{sid}")
        if f["promote_candidate"] and PROMOTE_MARK not in evidence:
            evidence.append(PROMOTE_MARK)   # marker to a person on review; promotion - not here
        out.append(new_lesson(
            trigger=f["trigger"], action=f["action"], kind=f["kind"],
            scope=f["scope"] or scope_default, session_id=sid, project=project,
            detector=DETECTOR, source="agent", evidence=evidence,
            meta=f["meta"], review_hint=f["review_hint"]))
    return out


# ── CLI ──────────────────────────────────────────────────────────────────────
def cmd_ingest(env, argv):
    """analyst ingest --file F [--dry-run] [--json]
    — accept findings agent-analyst in .claude/analyst/lessons/ephemeral/."""
    opts, _ = parse_args(argv, {"--file": "str", "--dry-run": "bool",
                                "--json": "bool", "--project": "str"})
    if opts["help"]:
        print("analyst ingest --file F [--dry-run] [--json]\n"
              "  Accept findings agent (/analyst:deep) in ephemeral-lessons. Schema Validation\n"
              "  before first entry (invalid file → no entries); only ephemeral,\n"
              "  detector=agent-finding — enforced code. Promot is a person (analyst review).")
        return
    if not opts["file"]:
        die("--file is required: analyst ingest --file findings.json")
    path = Path(os.path.expanduser(opts["file"]))
    if not path.is_file():
        die(f"file findings not found: {path}")

    # validation ENTIRELY up to the first side effect: broken JSON/diagram → die without entries
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        die(f"invalid JSON findings ({path}): {e} — no entries made")
    try:
        findings = validate_findings(payload)
    except ValueError as e:
        die(f"diagram findings failed validation: {e} — no entries made")

    ppath = os.getcwd()
    project = Path(os.path.abspath(ppath)).name
    cands = build_lessons(findings, scope_default=f"project:{project}", project=project)

    if opts["dry_run"] or opts["json"]:
        payload_out = {"session": payload.get("session", ""), "project": project,
                       "findings": [{"id": c["id"], "kind": c["kind"],
                                     "trigger": c["trigger"],
                                     "promote_candidate": PROMOTE_MARK in c["evidence"]}
                                    for c in cands]}
        if opts["json"]:
            print(json.dumps(payload_out, ensure_ascii=False, indent=2))
        else:
            print(f"\nanalyst ingest (dry-run) — {len(cands)} finding(ov) from {path.name}\n")
            for c in payload_out["findings"]:
                mark = "  ★ PROMOTE-CANDIDATE" if c["promote_candidate"] else ""
                print(f"  • [{c['kind']}] {c['trigger']}{mark}")
            print()
        return

    created = skipped = 0
    for L in cands:
        assert L["state"] == "ephemeral", "invariant ingest: only ephemeral"
        # semantic dedupe as in digest: NOOP by mem0-classifications → not prolific
        sim = similar_lessons(ppath, L["trigger"], L["action"],
                              states=ACTIVE_STATES, threshold=0.4)
        cons = classify_consolidation(L["trigger"], L["action"], sim)
        if cons["action"] == "NOOP":
            skipped += 1
            continue
        _lesson, was_new = add_candidate(ppath, L)
        if not was_new:
            skipped += 1
            continue
        created += 1
        audit_append(ppath, {"action": "ingest", "id": L["id"], "detector": DETECTOR,
                             "session": L["provenance"]["session_id"],
                             "state": "ephemeral", "consolidation": cons["action"]})

    marks = sum(1 for L in cands if PROMOTE_MARK in L["evidence"])
    print(f"\nanalyst ingest — {created} new(s) lesson(ov) in ephemeral"
          f"{f', {skipped} missing (take/similar to existing)' if skipped else ''}"
          f"{f'; {marks} with marker {PROMOTE_MARK}' if marks else ''}.")
    if created:
        print("  See: analyst review   ·   promoter (human only): analyst promote <id>\n")
    else:
        print("  New lessons from findings not accepted.\n")
