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
_EXECUTION_COMMANDS = frozenset(("plan-exec", "plan-run", "plan-close", "plan-audit"))
OBSERVATION_RESULTS = frozenset((
    "no-op", "routing-rejected", "decision-pending", "local-repair", "rag-pending", "block-candidate",
))
OBSERVATION_NEXT_STEPS = {
    "routing-rejected": "Retry the same command after route correction.",
    "decision-pending": "Continue after the recorded decision is available.",
    "local-repair": "Repeat the original validation after local repair.",
    "rag-pending": "Gather required RAG evidence; do not terminalize.",
    "block-candidate": "Run isolated block confirmation; do not terminalize.",
}

def _read(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ItemStateError(f"вход слепка не читается: {path}") from exc

def _event_rows(plan_dir, item_id):
    path = plan_layout.carrier_path(plan_dir, "journal")
    result = []
    for number, line in enumerate(_read(path).splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ItemStateError(f"{path}:{number}: журнал невалиден") from exc
        if event.get("item_id") == item_id:
            if event.get("result") not in RESULT_STATUS:
                raise ItemStateError(f"{path}:{number}: неизвестный result")
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
        raise ItemStateError(f"вход слепка не читается: {spec_path}") from exc
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

def _validate(model):
    schema = Path(__file__).resolve().parents[2] / "configs" / "item-state-projection-v1.schema.json"
    try:
        source = json.loads(_read(schema))
    except json.JSONDecodeError as exc:
        raise ItemStateError(f"схема невалидна: {schema}") from exc
    if set(model) != set(source["required"]):
        raise ItemStateError("слепок не соответствует закрытой корневой схеме")
    meta, state = model["projection_meta"], model["state"]
    if set(meta) != set(source["properties"]["projection_meta"]["required"]):
        raise ItemStateError("слепок не соответствует схеме метаданных")
    if set(state) != set(source["properties"]["state"]["required"]):
        raise ItemStateError("слепок не соответствует схеме состояния")
    if meta["projection"] != "item-state" or meta["projection_version"] != "1.0.0":
        raise ItemStateError("неподдерживаемая версия слепка")
    if "routing" in json.dumps(model, ensure_ascii=False).lower() or "маршрут" in json.dumps(model, ensure_ascii=False).lower():
        raise ItemStateError("слепок содержит запрещённый маршрут")

def state_model(plan_dir, item_id, *, _legacy_freshness=False):
    plan_dir = Path(plan_dir)
    if not _ITEM.fullmatch(item_id):
        raise ItemStateError("item должен иметь форму Pn.m")
    if plan_layout.layout_version(plan_dir) != "v2":
        raise ItemStateError("слепок состояния существует только для Layout v2")
    spec_path = plan_layout.carrier_path(plan_dir, "item-spec", item_id=item_id)
    event_rows = _event_rows(plan_dir, item_id)
    events = [event for _number, _raw, event in event_rows]
    execution_events = [event for event in events
                        if event.get("command") in _EXECUTION_COMMANDS
                        and event.get("result") not in OBSERVATION_RESULTS]
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
        "through": ({"journal_line": len(_read(journal_path).splitlines()),
                     "ts": last.get("ts", "1970-01-01T00:00:00Z")}
                    if _legacy_freshness else
                    {"journal_line": last_event[0],
                     "ts": last_event[2].get("ts", "1970-01-01T00:00:00Z")}),
        "inputs_sha256": (plan_projection.inputs_sha256((spec_path, journal_path), root=plan_dir)
                          if _legacy_freshness else
                          _inputs_sha256(plan_dir, spec_path, item_id, event_rows)),
        "generated_by": {"name": "task.plan-views", "version": "1.0.0"},
    }, "state": {
        "world": {"paths": [], "commits": []},
        "position": {"status": RESULT_STATUS[result] if result else "⬜ Not started", "attempt": len(execution_events), "last_result": result},
        "next_step": (OBSERVATION_NEXT_STEPS.get(events[-1].get("result"))
                      if events and events[-1].get("result") in OBSERVATION_NEXT_STEPS
                      else "Continue item execution." if result in (None, "in-progress")
                      else "Proceed according to the plan."),
        "active_context": {"risks": [], "workarounds": [], "decisions": []},
        "history_pointer": {"view": f".plan-cache/history/{item_id}.md", "command": f"python3 packages/task/scripts/plan-views.py history --item {item_id}"},
    }}
    _validate(model)
    return model, note, friction

def _render_state(plan_dir, item_id, *, legacy_freshness=False):
    model, note, friction = state_model(
        plan_dir, item_id, _legacy_freshness=legacy_freshness)
    meta, state = model["projection_meta"], model["state"]
    block = plan_projection.metadata_block(projection=meta["projection"], projection_version=meta["projection_version"], source_scope=json.dumps(meta["source_scope"], sort_keys=True), through=json.dumps(meta["through"], sort_keys=True), inputs_sha256_value=meta["inputs_sha256"], generated_by="task plan-views state")
    result = state["position"]["last_result"]
    fields = (("Status", state["position"]["status"]),
              ("Completion Notes", note if result and result.startswith("closed-") else "—"),
              ("Pending Work", "—"), ("Known Deviations", note if "deviation" in friction else "—"),
              # A blocked position has the same mandatory escalation triple as an
              # explicit ``escalated`` event.  The event enum retains ``blocked``
              # for historical/procedural provenance, but the generated carrier
              # must never emit a status that its own plan linter rejects.
              ("Escalation Needed", "yes" if state["position"]["status"] == "🔴 Blocked" else "no"))
    return plan_projection.rendered_file(metadata=block, title=f"Состояние {item_id}", body="\n".join(f"**{k}:** {v}" for k, v in fields))

def render_state(plan_dir, item_id):
    return _render_state(plan_dir, item_id)

def build_states(plan_dir, *, item_id=None, check=False):
    plan_dir = Path(plan_dir)
    identifiers = [item_id] if item_id else [path.stem for phase in plan_layout.phase_paths(plan_dir) for path in plan_layout.item_spec_paths(plan_dir, phase)]
    targets = []
    for identifier in identifiers:
        target = plan_layout.carrier_path(plan_dir, "item-state", item_id=identifier)
        expected = render_state(plan_dir, identifier)
        try:
            plan_projection.write_or_check(target, expected, check=check)
        except plan_projection.ProjectionError as exc:
            if not check:
                raise ItemStateError(str(exc)) from exc
            try:
                legacy = _render_state(plan_dir, identifier, legacy_freshness=True)
                legacy_matches = target.read_bytes() == legacy.encode("utf-8")
            except OSError:
                legacy_matches = False
            if not legacy_matches:
                raise ItemStateError(str(exc)) from exc
        targets.append(target)
    return tuple(targets)
