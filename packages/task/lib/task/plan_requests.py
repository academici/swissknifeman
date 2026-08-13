"""Durable append-only decision queue for Layout-v2 executable plans (P5.4)."""
from __future__ import annotations

import hashlib
import json
import copy
import re
from datetime import datetime, timezone
from pathlib import Path

from task import journal, plan_authority, plan_layout, plan_projection

QUEUE_NAME = "queue.jsonl"
GATES_NAME = "_gates.md"
RECORD_MAX_BYTES = 16384
EVENT_TYPES = frozenset(("request", "claim", "response", "auto_answer"))
_CONTRACT_PATH = Path(__file__).resolve().parents[2] / "configs" / "decision-request-v1.schema.json"
_SCHEMA_KEYWORDS = frozenset(("additional_properties", "properties", "required", "type", "const",
                              "enum", "enum_ref", "const_ref", "pattern", "minimum", "min_length",
                              "items", "format", "unique_by", "required_when", "source", "description"))


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


def _schema() -> dict:
    try:
        value = json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RequestError(f"decision-request contract is unreadable: {_CONTRACT_PATH}") from exc
    if value.get("contract_version") != "v1":
        raise RequestError("unsupported decision-request contract")
    return value


def _path_value(value: dict, dotted: str):
    current = value
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            raise RequestError(f"contract reference is unresolved: {dotted}")
        current = current[part]
    return current


def _type_matches(value, declared) -> bool:
    values = declared if isinstance(declared, list) else [declared]
    checks = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "null": lambda item: item is None,
        "boolean": lambda item: isinstance(item, bool),
    }
    return any(name in checks and checks[name](value) for name in values)


def _date_time(value) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return True


def _shape_errors(value, spec: dict, schema: dict, path: str) -> list[str]:
    unknown = set(spec) - _SCHEMA_KEYWORDS
    if unknown:
        return [f"unsupported frozen schema keyword at {path}: {sorted(unknown)[0]}"]
    errors: list[str] = []
    if "type" in spec and not _type_matches(value, spec["type"]):
        return [f"{path} has invalid type"]
    if "const" in spec and value != spec["const"]:
        errors.append(f"{path} must equal frozen constant")
    if "enum" in spec and value not in spec["enum"]:
        errors.append(f"{path} is outside frozen enum")
    if "enum_ref" in spec and value not in _path_value(schema, spec["enum_ref"]):
        errors.append(f"{path} is outside frozen enum")
    if "const_ref" in spec and value != _path_value(schema, spec["const_ref"]):
        errors.append(f"{path} differs from frozen constant")
    if "pattern" in spec and (not isinstance(value, str) or not re.fullmatch(spec["pattern"], value)):
        errors.append(f"{path} fails frozen pattern")
    if "minimum" in spec and (not isinstance(value, int) or isinstance(value, bool) or value < spec["minimum"]):
        errors.append(f"{path} is below frozen minimum")
    if "min_length" in spec and (not isinstance(value, str) or len(value) < spec["min_length"]):
        errors.append(f"{path} is too short")
    if spec.get("format") == "date-time" and not _date_time(value):
        errors.append(f"{path} is not ISO date-time")
    if isinstance(value, dict):
        properties = spec.get("properties", {})
        required = spec.get("required", [])
        errors.extend(f"missing {path}.{name}" for name in required if name not in value)
        if spec.get("additional_properties") is False:
            errors.extend(f"unexpected {path}.{name}" for name in value if name not in properties)
        for name, child in properties.items():
            if name in value:
                errors.extend(_shape_errors(value[name], child, schema, f"{path}.{name}"))
    if isinstance(value, list):
        child = spec.get("items")
        if isinstance(child, dict):
            for index, item in enumerate(value):
                errors.extend(_shape_errors(item, child, schema, f"{path}[{index}]"))
        unique_by = spec.get("unique_by")
        if unique_by:
            keys = [item.get(unique_by) for item in value if isinstance(item, dict)]
            if len(keys) != len(value) or len(set(keys)) != len(keys):
                errors.append(f"{path} violates frozen unique_by {unique_by}")
    return errors


def _contains_forbidden(value, forbidden: frozenset[str]) -> bool:
    if isinstance(value, dict):
        return any(key in forbidden or _contains_forbidden(item, forbidden) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_forbidden(item, forbidden) for item in value)
    return False


def _request_errors(request: dict) -> list[str]:
    if not isinstance(request, dict):
        return ["request must be an object"]
    schema = _schema()
    errors = _shape_errors(request, schema["request"], schema, "request")
    forbidden = frozenset(schema["record"]["forbidden"])
    if _contains_forbidden(request, forbidden):
        errors.append("P5_DECISION_FORBIDDEN_CONTENT")
    if errors:
        return errors
    try:
        frame = plan_authority.load_frame()
        definition = frame["decision_classes"].get(request["decision_class"])
        if not isinstance(definition, dict):
            return ["P5_DECISION_UNCLASSIFIED_KIND"]
        if request["on_timeout"] != definition["on_timeout"] or request["on_timeout"] not in schema["timeout_policy"][request["kind"]]["allowed"]:
            return ["request timeout does not match authority envelope"]
        if request["subject"]["plan_id"] != request["continuation"]["target"]["plan_id"] or request["subject"]["item_id"] != request["continuation"]["target"]["item_id"]:
            return ["request continuation target mismatches subject"]
        option_ids = [row["id"] for row in request["options"]]
        mandatory = frozenset(schema["options"]["mandatory"])
        if not mandatory.issubset(option_ids):
            return ["request options omit frozen mandatory choices"]
        substantive = [option_id for option_id in option_ids if option_id not in mandatory]
        if not schema["options"]["min_substantive"] <= len(substantive) <= schema["options"]["max_substantive"]:
            return ["request options violate frozen bounds"]
        if request["default_option"] is not None and request["default_option"] not in option_ids:
            return ["request default option is undeclared"]
        trusted = copy.deepcopy(request)
        trusted["action"] = request["canonical_action"]["action"]
        canonical = plan_authority.canonical_action(trusted, frame)
        if canonical != request["canonical_action"]:
            return ["request canonical action is not tool-derived"]
        if request["action_digest"] != plan_authority.action_digest(trusted, frame):
            return ["request action digest is not tool-derived"]
        if request["policy_digest"] != plan_authority.policy_digest(frame):
            return ["request policy digest is not current authority frame"]
    except (KeyError, TypeError, plan_authority.AuthorityFrameError, plan_authority.AuthorityRequestError):
        return ["request authority projection is invalid"]
    return []


def prepare_request(value: dict) -> dict:
    """Create the durable closed request from a transient construction action (D145)."""
    if not isinstance(value, dict) or not isinstance(value.get("action"), dict):
        raise RequestError("request construction requires an action object")
    try:
        frame = plan_authority.load_frame()
        raw = copy.deepcopy(value)
        canonical = plan_authority.canonical_action(raw, frame)
        digest = plan_authority.action_digest(raw, frame)
        policy = plan_authority.policy_digest(frame)
    except (plan_authority.AuthorityFrameError, plan_authority.AuthorityRequestError, KeyError, TypeError) as exc:
        raise RequestError("request construction authority projection is invalid") from exc
    durable = copy.deepcopy(raw)
    durable.pop("action", None)
    computed = {
        "contract_version": "v1", "canonical_action": canonical,
        "action_digest": digest,
        "material_fields": _path_value(_schema(), "canonical_action.material_fields"),
        "policy_digest": policy,
    }
    mismatched = [name for name, expected in computed.items()
                  if name in durable and durable[name] != expected]
    if mismatched:
        raise RequestError(f"request tool-computed field mismatch: {mismatched[0]}")
    durable.update(computed)
    errors = _request_errors(durable)
    if errors:
        raise RequestError("; ".join(errors))
    return durable


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
    maximum = _schema()["record"]["max_bytes"]
    if len(payload) > maximum:
        raise RequestError(f"P5_DECISION_RECORD_TOO_LARGE: {len(payload)} > {maximum}")
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
                                   "response": None, "auto_answer": None}
        elif decision_id not in result:
            raise RequestError(f"event before request for {decision_id}")
        elif event["type"] == "claim":
            if semantic_outcome(result[decision_id]) not in ("pending", "pending-authorization"):
                raise RequestError(f"decision is already resolved: {decision_id}")
            result[decision_id]["claims"].append(event)
        elif event["type"] == "response":
            if result[decision_id]["response"] is not None:
                raise RequestError(f"duplicate response for {decision_id}")
            if semantic_outcome(result[decision_id]) not in ("pending", "pending-authorization"):
                raise RequestError(f"decision is already resolved: {decision_id}")
            errors = _response_errors(event.get("response"), result[decision_id]["request"])
            if errors:
                raise RequestError("; ".join(errors))
            result[decision_id]["response"] = event
        else:
            if result[decision_id]["response"] is not None or result[decision_id]["auto_answer"] is not None:
                raise RequestError(f"duplicate response for {decision_id}")
            errors = _auto_answer_errors(event.get("event"), event.get("response"), result[decision_id]["request"])
            if errors:
                raise RequestError("; ".join(errors))
            result[decision_id]["auto_answer"] = event
    return result


def semantic_outcome(state: dict) -> str:
    """Reduce one durable queue state to its only permission/pending verdict."""
    request_value = state.get("request")
    if not isinstance(request_value, dict):
        raise RequestError("decision state has no request")
    response_event = state.get("response")
    auto_event = state.get("auto_answer")
    if response_event is None and auto_event is None:
        return "pending"
    if response_event is not None:
        response = response_event.get("response")
    else:
        response = auto_event.get("response")
        if isinstance(response, dict) and response.get("reclassified_to") == "authorization":
            return "pending-authorization"
    if not isinstance(response, dict):
        raise RequestError("decision terminal event has no response")
    selected_option = response.get("selected_option")
    for option in request_value.get("options", ()):
        if isinstance(option, dict) and option.get("id") == selected_option:
            outcome = option.get("outcome")
            if outcome in ("apply", "park", "reject", "escalate"):
                return outcome
    raise RequestError("decision terminal event has unknown outcome")


def _response_errors(response: dict, request: dict) -> list[str]:
    if not isinstance(response, dict):
        return ["response must be an object"]
    schema = _schema()
    errors = _shape_errors(response, schema["response"], schema, "response")
    if errors:
        return errors
    if request["kind"] == "clarification" and "reclassified_to" not in response:
        return ["clarification response misses reclassified_to"]
    if response["decision_id"] != request["decision_id"] or response["action_version"] != request["action_version"]:
        return ["response identity mismatch"]
    if response["action_digest"] != request["action_digest"] or response["policy_digest"] != request["policy_digest"]:
        return ["response digest mismatch"]
    if response["selected_option"] not in {row["id"] for row in request["options"]}:
        return ["P5_DECISION_UNKNOWN_OPTION"]
    return []


def _auto_answer_errors(event: dict, response: dict, request: dict) -> list[str]:
    if not isinstance(event, dict):
        return ["auto answer event must be an object"]
    schema = _schema()
    missing = [name for name in schema["auto_answer_event"]["required"] if name not in event]
    if missing:
        return [f"missing auto answer field {missing[0]}"]
    if event.get("decision_id") != request["decision_id"] or event.get("policy_digest") != request["policy_digest"]:
        return ["auto answer identity mismatch"]
    if event.get("provenance_verified") is not True:
        return ["auto answer provenance is not verified"]
    if not isinstance(response, dict):
        return ["response must be an object"]
    errors = _shape_errors(response, schema["response"], schema, "response")
    if errors:
        return errors
    if request["kind"] != "clarification":
        return ["auto answer is only valid for clarification"]
    if response["decision_id"] != request["decision_id"] or response["action_version"] != request["action_version"]:
        return ["auto answer response identity mismatch"]
    if response["policy_digest"] != request["policy_digest"]:
        return ["auto answer policy digest mismatch"]
    if response["selected_option"] not in {row["id"] for row in request["options"]}:
        return ["P5_DECISION_UNKNOWN_OPTION"]
    if "reclassified_to" not in response:
        return ["auto answer misses reclassified_to"]
    if response["resolver"] != "policy" or response["reclassified_to"] != event["reclassified_to"]:
        return ["auto answer lacks policy reclassification"]
    if response["provenance"]["source_system"] != event["source_system"] or response["provenance"]["record_id"] != event["source_record_id"] or response["provenance"]["record_version"] != event["source_record_version"]:
        return ["auto answer provenance mismatch"]
    if event["before_digest"] != request["action_digest"] or response["action_digest"] != event["after_digest"] or event["reclassified_action_digest"] != event["after_digest"]:
        return ["auto answer digest mismatch"]
    return []


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
    """Persist P5 transport and refresh the subject-local decision projection."""
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


def _transition_result(outcome: str) -> str:
    if outcome in ("pending", "pending-authorization"):
        return "decision-pending"
    return "in-progress" if outcome == "apply" else "blocked"


def _refresh_views(plan_dir, item_id: str, *, check: bool) -> None:
    from task import plan_item_state, plan_status
    plan_item_state.build_states(plan_dir, item_id=item_id, check=check)
    plan_status.build_status(plan_dir, check=check)
    render(plan_dir, check=check)


def _repair_transition(plan_dir, request: dict, *, actor: str, outcome: str) -> None:
    """Converge journal and generated views without duplicating queue events."""
    result = _transition_result(outcome)
    prior = journal_path_events(plan_dir, request["subject"]["item_id"])
    if prior and prior[-1].get("result") == result:
        try:
            _refresh_views(plan_dir, request["subject"]["item_id"], check=True)
            return
        except Exception:
            # The durable event is authoritative; regenerate below rather than accepting stale views.
            pass
    try:
        _journal_transition(plan_dir, request, actor=actor, result=result)
        _refresh_views(plan_dir, request["subject"]["item_id"], check=False)
        _refresh_views(plan_dir, request["subject"]["item_id"], check=True)
    except Exception as exc:
        raise RequestError("decision transition projection failed; exact retry must repair views") from exc


def journal_path_events(plan_dir, item_id: str) -> list[dict]:
    path = Path(plan_dir) / journal.FILENAME
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and json.loads(line).get("item_id") == item_id]


def request(plan_dir, value: dict, *, actor: str = "owner") -> dict:
    value = prepare_request(value)
    if value["subject"]["plan_id"] != Path(plan_dir).name:
        raise RequestError("request subject plan_id does not match queue plan")
    existing = states(plan_dir).get(value["decision_id"])
    if existing is not None:
        if _canonical(existing["request"]) != _canonical(value):
            raise RequestError(f"decision already exists: {value['decision_id']}")
        _repair_transition(plan_dir, existing["request"], actor=actor,
                           outcome=semantic_outcome(existing))
        return existing["request_event"]
    event = {"type": "request", "at": _now(), "actor": actor, "decision_id": value["decision_id"],
             "request": value, **_frame_metadata(value)}
    _append(plan_dir, event)
    _repair_transition(plan_dir, value, actor=actor, outcome=semantic_outcome(states(plan_dir)[value["decision_id"]]))
    return event


def _active_claim(state: dict, now: str) -> dict | None:
    for claim in reversed(state["claims"]):
        if claim.get("lease_expires_at", "") > now:
            return claim
    return None


def claim(plan_dir, decision_id: str, *, resolver_id: str, lease_expires_at: str, actor: str = "owner") -> dict:
    state = states(plan_dir).get(decision_id)
    if state is None or semantic_outcome(state) not in ("pending", "pending-authorization"):
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
    if state is None:
        raise RequestError("decision is absent or already resolved")
    request_value = state["request"]
    errors = _response_errors(response, request_value)
    if errors:
        raise RequestError("; ".join(errors))
    if response["resolver_id"] != resolver_id:
        raise RequestError("response resolver identity mismatch")
    if state["response"] is not None:
        existing = state["response"]
        if (existing.get("resolver_id") != resolver_id
                or _canonical(existing.get("response")) != _canonical(response)):
            raise RequestError("decision response is already resolved")
        outcome = semantic_outcome(state)
        _repair_transition(plan_dir, request_value, actor=actor, outcome=outcome)
        if outcome != "apply":
            return existing
        return {**existing, "continuation": _continuation(
            request_value, current=current_continuation, resume_available=resume_available,
            fallback_reason=fallback_reason)}
    if semantic_outcome(state) not in ("pending", "pending-authorization"):
        raise RequestError("decision is absent or already resolved")
    lease = _active_claim(state, _now())
    if lease is None or lease.get("resolver_id") != resolver_id:
        raise RequestError("resolver has no active lease")
    selected = next(row for row in request_value["options"] if row["id"] == response["selected_option"])
    outcome = selected["outcome"]
    if outcome == "apply":
        application = plan_authority.apply_response(
            {**request_value, "action": request_value["canonical_action"]["action"]}, response)
        if not isinstance(application, dict) or application.get("verdict") != "applied":
            raise RequestError("response application rejected")
        _continuation(request_value, current=current_continuation,
                      resume_available=resume_available, fallback_reason=fallback_reason)
    event = {"type": "response", "at": _now(), "actor": actor, "decision_id": decision_id,
             "resolver_id": resolver_id, "response": response, "outcome": outcome}
    _append(plan_dir, event)
    outcome = semantic_outcome(states(plan_dir)[decision_id])
    _repair_transition(plan_dir, request_value, actor=actor, outcome=outcome)
    if outcome == "apply":
        return {**event, "continuation": _continuation(
            request_value, current=current_continuation, resume_available=resume_available,
            fallback_reason=fallback_reason)}
    return event


def append_auto_answer(plan_dir, event: dict, *, response: dict | None = None,
                       actor: str = "policy") -> dict:
    decision_id = event.get("decision_id")
    if not isinstance(decision_id, str) or decision_id not in states(plan_dir):
        raise RequestError("auto answer refers to an unknown decision")
    if response is None:
        raise RequestError("auto answer requires response and provenance pair")
    state = states(plan_dir)[decision_id]
    if state["response"] is not None or state["auto_answer"] is not None:
        raise RequestError("decision is absent or already resolved")
    errors = _auto_answer_errors(event, response, state["request"])
    if errors:
        raise RequestError("; ".join(errors))
    record = {"type": "auto_answer", "at": _now(), "actor": actor, "decision_id": decision_id,
              "event": event, "response": response}
    _append(plan_dir, record)
    outcome = semantic_outcome(states(plan_dir)[decision_id])
    _repair_transition(plan_dir, state["request"], actor=actor, outcome=outcome)
    return record


def pending_groups(plan_dir) -> dict[tuple[str, str, str], list[dict]]:
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for decision_id, state in states(plan_dir).items():
        if semantic_outcome(state) not in ("pending", "pending-authorization"):
            continue
        event = state["request_event"]
        key = (state["request"]["decision_class"], event["attention_class"], event["required_approver"])
        groups.setdefault(key, []).append({"decision_id": decision_id, **state})
    return groups


def unresolved_for_phase(plan_dir, phase_id: str) -> list[str]:
    return sorted(decision_id for decision_id, state in states(plan_dir).items()
                  if semantic_outcome(state) in ("pending", "pending-authorization")
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
