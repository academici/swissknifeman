"""Durable append-only decision queue for Layout-v2 executable plans (P5.4)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from task import journal, plan_authority, plan_layout, plan_projection

QUEUE_NAME = "queue.jsonl"
GATES_NAME = "_gates.md"
RECORD_MAX_BYTES = 16384
EVENT_TYPES = frozenset(("request", "claim", "response", "auto_answer"))
FORBIDDEN_KEYS = frozenset(("model_reasoning", "model_transcript", "raw_provider_prompt",
                             "raw_provider_stream", "secrets_or_tokens",
                             "environment_file_contents", "worker_prose",
                             "inline_evidence_payload", "return_loop_owner_packet_copy"))


class RequestError(ValueError):
    """A queue record is malformed, unsafe, or conflicts with durable state."""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _queue_path(plan_dir) -> Path:
    plan_dir = Path(plan_dir)
    if plan_layout.layout_version(plan_dir) != "v2":
        raise RequestError("очередь решений доступна только для Layout v2")
    return plan_dir / "decisions" / QUEUE_NAME


def _contains_forbidden(value) -> bool:
    if isinstance(value, dict):
        return any(key in FORBIDDEN_KEYS or _contains_forbidden(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_forbidden(item) for item in value)
    return False


def _request_errors(request: dict) -> list[str]:
    required = ("contract_version", "decision_id", "action_version", "kind", "decision_class",
                "subject", "action_digest", "canonical_action", "material_fields", "options",
                "default_option", "on_timeout", "expires_at", "evidence", "policy_digest",
                "attempted", "continuation")
    if not isinstance(request, dict):
        return ["request must be an object"]
    errors = [f"missing request field {key}" for key in required if key not in request]
    if request.get("contract_version") != "v1":
        errors.append("unsupported decision-request contract")
    subject = request.get("subject")
    if not isinstance(subject, dict) or not all(isinstance(subject.get(key), str) and subject[key]
                                                for key in ("plan_id", "phase_id", "item_id")):
        errors.append("invalid request subject")
    continuation = request.get("continuation")
    if not isinstance(continuation, dict) or continuation.get("preferred_mode") != "resume-root":
        errors.append("invalid continuation identity")
    if _contains_forbidden(request):
        errors.append("P5_DECISION_FORBIDDEN_CONTENT")
    return errors


def _read_events(plan_dir) -> list[dict]:
    path = _queue_path(plan_dir)
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise RequestError(f"queue is unreadable: {path}") from exc
    events = []
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RequestError(f"queue:{line_number}: invalid JSON") from exc
        if not isinstance(event, dict) or event.get("type") not in EVENT_TYPES:
            raise RequestError(f"queue:{line_number}: invalid event type")
        events.append(event)
    return events


def _append(plan_dir, event: dict) -> Path:
    payload = _canonical(event)
    if len(payload) > RECORD_MAX_BYTES:
        raise RequestError(f"P5_DECISION_RECORD_TOO_LARGE: {len(payload)} > {RECORD_MAX_BYTES}")
    path = _queue_path(plan_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(payload.decode("utf-8") + "\n")
    return path


def states(plan_dir) -> dict[str, dict]:
    """Reduce immutable queue events into per-decision durable state."""
    result: dict[str, dict] = {}
    for event in _read_events(plan_dir):
        decision_id = event.get("decision_id")
        if not isinstance(decision_id, str) or not decision_id:
            raise RequestError("queue event has no decision_id")
        if event["type"] == "request":
            if decision_id in result:
                raise RequestError(f"duplicate decision request {decision_id}")
            request = event.get("request")
            errors = _request_errors(request)
            if errors:
                raise RequestError("; ".join(errors))
            result[decision_id] = {"request": request, "request_event": event, "claims": [],
                                   "response": None, "auto_answers": []}
        elif decision_id not in result:
            raise RequestError(f"event before request for {decision_id}")
        elif event["type"] == "claim":
            result[decision_id]["claims"].append(event)
        elif event["type"] == "response":
            if result[decision_id]["response"] is not None:
                raise RequestError(f"duplicate response for {decision_id}")
            result[decision_id]["response"] = event
        else:
            result[decision_id]["auto_answers"].append(event)
    return result


def _frame_metadata(request: dict) -> dict:
    frame = plan_authority.load_frame()
    definition = frame["decision_classes"].get(request["decision_class"])
    if not isinstance(definition, dict):
        raise RequestError("P5_DECISION_UNCLASSIFIED_KIND")
    return {"attention_class": definition["attention"], "required_approver": definition["owner"]}


def _digest_reference(*, carrier: str, anchor: str, value: dict) -> dict:
    """Return a durable reference without embedding the referenced payload."""
    return {"carrier": carrier, "anchor": anchor,
            "digest": hashlib.sha256(_canonical(value)).hexdigest()}


def return_loop_request(plan_dir, gate: dict, *, continuation: dict, expires_at: str) -> dict:
    """Wrap one frozen P4 owner packet in the P5 DecisionRequest transport.

    The packet remains owned by ``plan_returns``. Only digest-addressed carrier
    references enter the queue, preventing divergence from the gate packet.
    """
    packet = gate.get("owner_packet")
    required_packet = {"fingerprint_tuple", "fingerprint_digest", "occurrences", "cap",
                       "history", "judgements", "resolutions_tried"}
    if gate.get("action") != "owner-gate" or gate.get("blocks") is not True:
        raise RequestError("P5_DECISION_REJECTED: return-loop не является блокирующим owner-gate")
    if not isinstance(packet, dict) or set(packet) != required_packet:
        raise RequestError("P5_DECISION_REJECTED: owner packet return-loop невалиден")
    subject_id = packet["fingerprint_tuple"].get("subject")
    if not isinstance(subject_id, str) or "." not in subject_id:
        raise RequestError("P5_DECISION_REJECTED: owner packet не несёт subject Pn.m")
    phase_id = subject_id.split(".", 1)[0]
    if not isinstance(continuation, dict) or continuation.get("target", {}).get("item_id") != subject_id:
        raise RequestError("P5_DECISION_REJECTED: continuation не соответствует subject owner-gate")
    packet_ref = _digest_reference(carrier="journal.jsonl",
                                   anchor=f"return-loop:{packet['fingerprint_digest']}", value=packet)
    evidence = [packet_ref]
    for row in packet["history"]:
        if not isinstance(row, dict) or not isinstance(row.get("return_event_id"), str):
            raise RequestError("P5_DECISION_REJECTED: history owner packet невалидна")
        evidence.append(_digest_reference(carrier="journal.jsonl", anchor=row["return_event_id"], value=row))
    attempted = packet["resolutions_tried"]
    if not isinstance(attempted, list) or not all(isinstance(row, str) for row in attempted):
        raise RequestError("P5_DECISION_REJECTED: resolutions_tried owner packet невалиден")
    raw = {
        "decision_id": f"return-loop-{packet['fingerprint_digest']}", "action_version": 1,
        "kind": "authorization", "decision_class": "authority_change",
        "subject": {"plan_id": Path(plan_dir).name, "phase_id": phase_id, "item_id": subject_id},
        "action": {"type": "return-loop-owner-gate", "requires_authorization": True,
                   "affected_surfaces": ["return-loop"], "declared_scope": ["return-loop"],
                   "frozen_contract_change": False, "closed_set_extension": False,
                   "reversible": True, "decision_recorded": True, "packet_ref": packet_ref},
        "options": [
            {"id": "continue", "outcome": "apply", "action_ref": packet_ref["anchor"],
             "evidence_refs": [packet_ref["anchor"]]},
            {"id": "park", "outcome": "park", "action_ref": None, "evidence_refs": []},
            {"id": "escalate", "outcome": "escalate", "action_ref": None, "evidence_refs": []},
            {"id": "reject", "outcome": "reject", "action_ref": None, "evidence_refs": []},
        ],
        "default_option": None, "expires_at": expires_at, "evidence": evidence,
        "attempted": attempted, "continuation": continuation,
    }
    frame = plan_authority.load_frame()
    canonical = plan_authority.canonical_action(raw, frame)
    raw.update({"contract_version": "v1", "canonical_action": canonical,
                "action_digest": plan_authority.action_digest(raw, frame),
                "material_fields": list(canonical), "on_timeout": "park",
                "policy_digest": plan_authority.policy_digest(frame)})
    return raw


def request_return_loop_gate(plan_dir, gate: dict, *, continuation: dict, expires_at: str,
                             actor: str = "return-loop") -> dict:
    """Persist P5 transport and refresh the subject-local blocked projection."""
    value = return_loop_request(plan_dir, gate, continuation=continuation, expires_at=expires_at)
    event = request(plan_dir, value, actor=actor)
    from task import plan_item_state, plan_status
    plan_item_state.build_states(plan_dir, item_id=value["subject"]["item_id"])
    plan_status.build_status(plan_dir)
    return event


def _journal_transition(plan_dir, request: dict, *, actor: str, result: str) -> None:
    item_id = request["subject"]["item_id"]
    prior = [event for event in journal_path_events(plan_dir, item_id)]
    entry = journal.new_entry(plan_id=Path(plan_dir).name, item_id=item_id, command="plan-run",
                              actor=actor, result=result, attempt=len(prior) + 1,
                              note=f"decision queue: {request['decision_id']}")
    journal.append(plan_dir, entry)


def journal_path_events(plan_dir, item_id: str) -> list[dict]:
    path = Path(plan_dir) / journal.FILENAME
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and json.loads(line).get("item_id") == item_id]


def request(plan_dir, value: dict, *, actor: str = "owner") -> dict:
    errors = _request_errors(value)
    if errors:
        raise RequestError("; ".join(errors))
    if value["subject"]["plan_id"] != Path(plan_dir).name:
        raise RequestError("request subject plan_id does not match queue plan")
    if value["decision_id"] in states(plan_dir):
        raise RequestError(f"decision already exists: {value['decision_id']}")
    event = {"type": "request", "at": _now(), "actor": actor, "decision_id": value["decision_id"],
             "request": value, **_frame_metadata(value)}
    _append(plan_dir, event)
    _journal_transition(plan_dir, value, actor=actor, result="blocked")
    return event


def _active_claim(state: dict, now: str) -> dict | None:
    for claim in reversed(state["claims"]):
        if claim.get("lease_expires_at", "") > now:
            return claim
    return None


def claim(plan_dir, decision_id: str, *, resolver_id: str, lease_expires_at: str, actor: str = "owner") -> dict:
    state = states(plan_dir).get(decision_id)
    if state is None or state["response"] is not None:
        raise RequestError("decision is absent or already resolved")
    if _active_claim(state, _now()) is not None:
        raise RequestError("decision already has an active resolver lease")
    event = {"type": "claim", "at": _now(), "actor": actor, "decision_id": decision_id,
             "resolver_id": resolver_id, "lease_expires_at": lease_expires_at}
    _append(plan_dir, event)
    return event


def _continuation(request: dict, *, current: dict | None, resume_available: bool,
                  fallback_reason: str | None) -> dict:
    expected = request["continuation"]
    if current is not None and current != expected:
        raise RequestError("continuation identity mismatch")
    if resume_available:
        return {"mode": "resume-root", "target": expected["target"],
                "root_session_id": expected["root_session_id"], "root_run_id": expected["root_run_id"]}
    if not fallback_reason:
        raise RequestError("cold-start-root requires exact fallback reason")
    return {"mode": "cold-start-root", "target": expected["target"], "reason": fallback_reason}


def resolve(plan_dir, decision_id: str, response: dict, *, resolver_id: str,
            current_continuation: dict | None = None, resume_available: bool = True,
            fallback_reason: str | None = None, actor: str = "owner") -> dict:
    state = states(plan_dir).get(decision_id)
    if state is None or state["response"] is not None:
        raise RequestError("decision is absent or already resolved")
    lease = _active_claim(state, _now())
    if lease is None or lease.get("resolver_id") != resolver_id:
        raise RequestError("resolver has no active lease")
    request_value = state["request"]
    if response.get("decision_id") != decision_id or response.get("action_version") != request_value.get("action_version"):
        raise RequestError("response identity mismatch")
    if response.get("action_digest") != request_value.get("action_digest") or response.get("policy_digest") != request_value.get("policy_digest"):
        raise RequestError("response digest mismatch")
    options = {row.get("id") for row in request_value.get("options", ()) if isinstance(row, dict)}
    if response.get("selected_option") not in options:
        raise RequestError("P5_DECISION_UNKNOWN_OPTION")
    continuation = _continuation(request_value, current=current_continuation,
                                 resume_available=resume_available, fallback_reason=fallback_reason)
    event = {"type": "response", "at": _now(), "actor": actor, "decision_id": decision_id,
             "resolver_id": resolver_id, "response": response, "continuation": continuation}
    _append(plan_dir, event)
    _journal_transition(plan_dir, request_value, actor=actor, result="in-progress")
    return event


def append_auto_answer(plan_dir, event: dict, *, response: dict | None = None,
                       actor: str = "policy") -> dict:
    decision_id = event.get("decision_id")
    if not isinstance(decision_id, str) or decision_id not in states(plan_dir):
        raise RequestError("auto answer refers to an unknown decision")
    if response is not None:
        if response.get("resolver") != "policy" or not isinstance(response.get("provenance"), dict):
            raise RequestError("auto answer requires policy resolver provenance")
        event = {**event, "resolver": response["resolver"], "provenance": response["provenance"]}
    record = {"type": "auto_answer", "at": _now(), "actor": actor, "decision_id": decision_id,
              "event": event}
    _append(plan_dir, record)
    request_value = states(plan_dir)[decision_id]["request"]
    _journal_transition(plan_dir, request_value, actor=actor, result="in-progress")
    from task import plan_item_state, plan_status
    plan_item_state.build_states(plan_dir, item_id=request_value["subject"]["item_id"])
    plan_status.build_status(plan_dir)
    return record


def pending_groups(plan_dir) -> dict[tuple[str, str, str], list[dict]]:
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for decision_id, state in states(plan_dir).items():
        if state["response"] is not None or state["auto_answers"]:
            continue
        event = state["request_event"]
        key = (state["request"]["decision_class"], event["attention_class"], event["required_approver"])
        groups.setdefault(key, []).append({"decision_id": decision_id, **state})
    return groups


def unresolved_for_phase(plan_dir, phase_id: str) -> list[str]:
    return sorted(decision_id for decision_id, state in states(plan_dir).items()
                  if state["response"] is None and not state["auto_answers"]
                  and state["request"]["subject"]["phase_id"] == phase_id)


def render_gates(plan_dir) -> str:
    plan_dir = Path(plan_dir)
    queue = _queue_path(plan_dir)
    rows = []
    for key, records in sorted(pending_groups(plan_dir).items()):
        decision_class, attention, approver = key
        rows.extend((f"## {decision_class} · {attention} · {approver}", "",
                     "| Decision | Subject | Expires |", "|:--|:--|:--|"))
        for state in sorted(records, key=lambda row: row["decision_id"]):
            request_value = state["request"]
            subject = request_value["subject"]
            rows.append(f"| {state['decision_id']} | {subject['plan_id']} {subject['item_id']} | {request_value['expires_at']} |")
        rows.append("")
    body = "\n".join(rows or ["Нет неразрешённых owner-gate запросов."])
    metadata = plan_projection.metadata_block(projection="owner-gate-view", projection_version="v1",
        source_scope="decisions/queue.jsonl", through=str(len(_read_events(plan_dir)),),
        inputs_sha256_value=plan_projection.inputs_sha256((queue,), root=plan_dir) if queue.exists() else hashlib.sha256(b"").hexdigest(),
        generated_by="task plan-decisions render")
    return plan_projection.rendered_file(metadata=metadata, title="Owner decision gates", body=body)


def render(plan_dir, *, out: str | Path | None = None, check: bool = False) -> Path:
    target = Path(out) if out is not None else Path(plan_dir) / "decisions" / GATES_NAME
    plan_projection.write_or_check(target, render_gates(plan_dir), check=check)
    return target
