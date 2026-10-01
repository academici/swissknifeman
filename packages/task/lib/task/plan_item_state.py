"""Deterministic generated state carriers for Layout-v2 plan items."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from task import journal, plan_layout, plan_projection

class ItemStateError(ValueError):
    pass

RESULT_STATUS = {
    "in-progress": "🟡 In progress", "closed-green": "🟢 Done",
    "closed-deviations": "🟠 Done with deviations", "blocked": "🔴 Blocked",
    "escalated": "🔴 Blocked", "no-op": "⬜ Not started",
    "audit-green": "⬜ Not started", "audit-attention": "⬜ Not started",
    "audit-red": "🔴 Blocked",
    "routing-rejected": "⬜ Not started", "decision-pending": "⬜ Not started",
    "local-repair": "⬜ Not started", "rag-pending": "⬜ Not started",
    "block-candidate": "⬜ Not started",
}
_ITEM = re.compile(r"^P\d+\.\d+$")
_WRITE_SITE = re.compile(
    r"^write-site: pre_mutation: \S+ · pre_final: \S+$")
# `plan-exec` is the legacy spelling of `plan-run`; readers accept both.
_EXECUTION_COMMANDS = frozenset(("plan-run", "plan-exec", "plan-close", "plan-audit"))
_TERMINAL_RESULTS = frozenset(("closed-green", "closed-deviations", "blocked", "escalated", "audit-red"))
OBSERVATION_RESULTS = frozenset((
    "no-op", "routing-rejected", "decision-pending", "local-repair", "rag-pending", "block-candidate",
))
OBSERVATION_NEXT_STEPS = {
    "routing-rejected": "Retry the same command after correcting execution selection.",
    "decision-pending": "Continue after the recorded decision is available.",
    "local-repair": "Repeat the original validation after local repair.",
    "rag-pending": "Gather required RAG evidence; do not terminalize.",
    "block-candidate": "Run isolated block confirmation; do not terminalize.",
}

def _read(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ItemStateError(f"nugget input not readable: {path}") from exc

def _event_rows(plan_dir, item_id):
    path = plan_layout.carrier_path(plan_dir, "journal")
    result = []
    for number, line in enumerate(_read(path).splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ItemStateError(f"{path}:{number}: log is invalid") from exc
        if event.get("item_id") == item_id:
            if event.get("result") not in RESULT_STATUS:
                raise ItemStateError(f"{path}:{number}: unknown result")
            result.append((number, line, event))
    return result

def _inputs_sha256(plan_dir, spec_path, item_id, event_rows):
    """Hash the stable spec and exact journal rows declared by ``source_scope``."""
    plan_dir, spec_path = Path(plan_dir), Path(spec_path)
    digest = hashlib.sha256()
    try:
        relative = spec_path.relative_to(plan_dir).as_posix()
        spec = spec_path.read_bytes()
    except (OSError, ValueError) as exc:
        raise ItemStateError(f"nugget input not readable: {spec_path}") from exc
    digest.update(relative.encode("utf-8"))
    digest.update(b"\0")
    digest.update(spec)
    digest.update(b"\0")
    digest.update(f"journal.jsonl:item={item_id}".encode("utf-8"))
    digest.update(b"\0")
    for _number, raw, _event in event_rows:
        digest.update(raw.encode("utf-8"))
        digest.update(b"\n")
    digest.update(b"\0")
    return digest.hexdigest()


def _latest_write_site(event_rows):
    for _number, _raw, event in reversed(event_rows):
        note = event.get("note")
        if not isinstance(note, str):
            continue
        for line in reversed(note.splitlines()):
            if _WRITE_SITE.fullmatch(line):
                return line
    return None


def _execution_events(events):
    """Return position-changing events, including explicit terminal recovery.

    ``plan-design`` ordinarily records only design provenance for an item.  Once
    a prior execution position is terminal, however, an explicit design command
    with ``in-progress`` starts the owner-directed recovery attempt.  Keeping
    that row history-only would make a terminal projection irreversible and
    reject the very continuation the plan protocol records.
    """
    result = []
    for event in events:
        if event.get("command") in _EXECUTION_COMMANDS and event.get("result") not in OBSERVATION_RESULTS:
            result.append(event)
            continue
        if (event.get("command") == "plan-design"
                and event.get("result") == "in-progress"
                and result
                and result[-1].get("result") in _TERMINAL_RESULTS):
            result.append(event)
    return result


def latest_execution_event(events):
    """Return the current position-changing event from append-only history."""
    execution = _execution_events(events)
    return execution[-1] if execution else None


def material_terminal_evidence(plan_dir, item_id):
    """Return only semantics that may invalidate a phase candidate.

    Generated projection metadata, journal line numbers, timestamps and actors are
    deliberately excluded.  The latest execution result, declared deviations and
    reducer decision remain included, so product/acceptance changes still stale an
    audit while normal view regeneration cannot stale itself.
    """
    rows = _event_rows(plan_dir, item_id)
    execution = _execution_events([event for _number, _raw, event in rows])
    if not execution:
        raise ItemStateError(f"{item_id}: no execution evidence")
    event = execution[-1]
    return {
        "result": event.get("result"),
        "friction": sorted(event.get("friction") or []),
        "note": event.get("note"),
        "fingerprint": event.get("fingerprint"),
        "decision": event.get("decision"),
    }

def _validate(model):
    schema = Path(__file__).resolve().parents[2] / "configs" / "item-state-projection-v1.schema.json"
    try:
        source = json.loads(_read(schema))
    except json.JSONDecodeError as exc:
        raise ItemStateError(f"scheme is invalid: {schema}") from exc
    if set(model) != set(source["required"]):
        raise ItemStateError("nugget does not match closed root schema")
    meta, state = model["projection_meta"], model["state"]
    if set(meta) != set(source["properties"]["projection_meta"]["required"]):
        raise ItemStateError("nugget does not match the metadata schema")
    if set(state) != set(source["properties"]["state"]["required"]):
        raise ItemStateError("nugget does not match state schema")
    if meta["projection"] != "item-state" or meta["projection_version"] != "1.0.0":
        raise ItemStateError("unsupported nugget version")
    if "routing" in json.dumps(model, ensure_ascii=False).lower() or "route" in json.dumps(model, ensure_ascii=False).lower():
        raise ItemStateError("nugget contains an illegal route")

def state_model(plan_dir, item_id):
    plan_dir = Path(plan_dir)
    if not _ITEM.fullmatch(item_id):
        raise ItemStateError("item should be of the form Pn.m")
    if plan_layout.layout_version(plan_dir) != "v2":
        raise ItemStateError("state snapshot exists only for Layout v2")
    spec_path = plan_layout.carrier_path(plan_dir, "item-spec", item_id=item_id)
    event_rows = _event_rows(plan_dir, item_id)
    events = [event for _number, _raw, event in event_rows]
    execution_events = _execution_events(events)
    # Observation rows remain durable provenance and freshness inputs, but do
    # not become an execution position or consume an attempt.
    last = execution_events[-1] if execution_events else {}
    journal_path = plan_layout.carrier_path(plan_dir, "journal")
    last_event = event_rows[-1] if event_rows else (0, "", {})
    result = last.get("result")
    note = last.get("note") or "—"
    friction = last.get("friction") or []
    model = {"projection_meta": {
        "projection": "item-state", "projection_version": "1.0.0",
        "source_scope": {"item": item_id, "event_types": ["attempt"], "subjects": [item_id], "ordering": "journal line ascending"},
        "through": {"journal_line": last_event[0],
                    "ts": last_event[2].get("ts", "1970-01-01T00:00:00Z")},
        "inputs_sha256": _inputs_sha256(plan_dir, spec_path, item_id, event_rows),
        "generated_by": {"name": "task.plan-views", "version": "1.0.0"},
    }, "state": {
        "world": {"paths": [], "commits": []},
        "position": {"status": RESULT_STATUS[result] if result else "⬜ Not started", "attempt": len(execution_events), "last_result": result},
        "next_step": (OBSERVATION_NEXT_STEPS.get(events[-1].get("result"))
                      if events and events[-1].get("result") in OBSERVATION_NEXT_STEPS
                      else "Continue item execution." if result in (None, "in-progress")
                      else "Proceed according to the plan."),
        "active_context": {"risks": [], "workarounds": [], "decisions": []},
        "history_pointer": {"view": f".plan-cache/history/{item_id}.md", "command": f"python3 packages/task/scripts/plan-views.py history --plan-dir <plan> --item {item_id}"},
    }}
    _validate(model)
    return model, note, friction

def _render_state(plan_dir, item_id):
    model, note, friction = state_model(plan_dir, item_id)
    meta, state = model["projection_meta"], model["state"]
    block = plan_projection.metadata_block(projection=meta["projection"], projection_version=meta["projection_version"], source_scope=json.dumps(meta["source_scope"], sort_keys=True), through=json.dumps(meta["through"], sort_keys=True), inputs_sha256_value=meta["inputs_sha256"], generated_by="task plan-views state")
    result = state["position"]["last_result"]
    completion_note = note
    write_site = _latest_write_site(_event_rows(plan_dir, item_id))
    if result and result.startswith("closed-") and write_site:
        lines = completion_note.splitlines() if completion_note != "—" else []
        if write_site not in lines:
            completion_note = "\n".join((*lines, write_site))
    fields = (("Status", state["position"]["status"]),
              ("Completion Notes", completion_note if result and result.startswith("closed-") else "—"),
              ("Pending Work", "—"), ("Known Deviations", note if "deviation" in friction else "—"),
              # A blocked position has the same mandatory escalation triple as an
              # explicit ``escalated`` event.  The event enum retains ``blocked``
              # for historical/procedural provenance, but the generated carrier
              # must never emit a status that its own plan linter rejects.
              ("Escalation Needed", "yes" if state["position"]["status"] == "🔴 Blocked" else "no"))
    body = "\n".join(f"**{k}:** {v}" for k, v in fields)
    if state["position"]["status"] == "🔴 Blocked":
        reason = " ".join(note.split()) if note != "—" else "See the terminal journal decision."
        body += f"\n\n> 🔴 ESCALATION {item_id}: {reason}"
    return plan_projection.rendered_file(metadata=block, title=f"Status {item_id}", body=body)

def render_state(plan_dir, item_id):
    return _render_state(plan_dir, item_id)

def build_states(plan_dir, *, item_id=None, check=False, materialize_successor=True):
    plan_dir = Path(plan_dir)
    identifiers = [item_id] if item_id else [path.stem for phase in plan_layout.phase_paths(plan_dir) for path in plan_layout.item_spec_paths(plan_dir, phase)]
    targets = []
    for identifier in identifiers:
        target = plan_layout.carrier_path(plan_dir, "item-state", item_id=identifier)
        expected = render_state(plan_dir, identifier)
        try:
            plan_projection.write_or_check(target, expected, check=check)
        except plan_projection.ProjectionError as exc:
            raise ItemStateError(str(exc)) from exc
        targets.append(target)
    if not check and materialize_successor:
        from task import plan_recovery
        for identifier in identifiers:
            plan_recovery.materialize_next_ready(plan_dir, identifier)
    return tuple(targets)
