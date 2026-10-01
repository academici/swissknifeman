"""Byte-bound terminal and handoff delivery receipts for Task plans."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from task import (command_catalog, journal, plan_bundle, plan_closure, plan_continuity,
                  plan_gates, plan_layout, plan_lint, plan_readiness, plan_repair, plan_status,
                  review_policy, terminal_policy)


class DeliveryError(ValueError):
    """A typed refusal to declare a Task delivery complete."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


TERMINAL_ITEM_STATUSES = frozenset((
    "🟢 Done", "🟠 Done with deviations", "🔴 Blocked", "⛔ Skipped by decision",
))
TERMINAL_PHASE_STATUSES = frozenset((
    "🟢 Done", "🟠 Done with deviations", "⛔ Skipped by decision",
))
_ITEM_RE = re.compile(r"^(P[0-9]+)\.[0-9]+$")
_PHASE_RE = re.compile(r"^P[0-9]+$")
_STATUS_BY_RESULT = {
    "closed-green": "🟢 Done",
    "closed-deviations": "🟠 Done with deviations",
    "blocked": "🔴 Blocked",
    "escalated": "🔴 Blocked",
}
_AUDIT_VERDICT_RE = re.compile(r"\*\*Вердикт:\s*(GREEN|ATTENTION|RED)\*\*")
_SEMANTIC_NEXT_LINE_RE = re.compile(r"^(?:Semantic Next:\s*)?`?([^`]+?)`?\.?$")
_DESIGN_TARGET_RE = re.compile(
    r"(?:^|\s|/)(?:task:)?plan-design\s+(\S+)\s+(P[0-9]+(?:\.[0-9]+)?)\b")
_EXEC_TARGET_RE = re.compile(
    r"(?:^|\s|/)(?:task:)?plan-(?:exec|run)\s+(\S+)\s+"
    r"(P[0-9]+\.[0-9]+)(?:\s*[-–]\s*(P[0-9]+\.[0-9]+))?")
_AUDIT_TARGET_RE = re.compile(
    r"(?:^|\s|/)(?:task:)?plan-audit\s+(\S+)\s+(P[0-9]+)(?:\s|$)")


def _validate_design_continuation(plan_dir: Path, next_exact: str) -> None:
    match = _DESIGN_TARGET_RE.search(next_exact)
    if match is None or match.group(1) != plan_dir.name:
        return
    target = match.group(2)
    phase_id = target.split(".", 1)[0]
    latest = plan_repair.latest_action(
        plan_dir, item_id=target if "." in target else None,
        phase_id=None if "." in target else phase_id,
    )
    if latest == "repair-in-current-attempt":
        raise DeliveryError(
            "REPAIR_CONTINUATION_REQUIRED",
            "latest repair-decision/v1 forbids a plan-design handoff",
        )
    try:
        plan_readiness.validate_design_target(plan_dir, phase_id)
        plan_readiness.validate_design_handoff_target(plan_dir, phase_id)
    except plan_readiness.ReadinessError as exc:
        raise DeliveryError("PHASE_REENTRY_UNJUSTIFIED", str(exc)) from exc


def _validate_priority_continuation(plan_dir: Path, next_exact: str) -> None:
    match = _EXEC_TARGET_RE.search(next_exact)
    if match is None or match.group(1) != plan_dir.name:
        return
    requested = [match.group(2)]
    if match.group(3):
        first_phase, first_number = match.group(2)[1:].split(".", 1)
        last_phase, last_number = match.group(3)[1:].split(".", 1)
        if first_phase == last_phase and int(first_number) <= int(last_number):
            requested = [f"P{first_phase}.{number}" for number in
                         range(int(first_number), int(last_number) + 1)]
        else:
            requested = [match.group(2), match.group(3)]
    try:
        plan_readiness.validate_execution_design(plan_dir, requested)
    except plan_readiness.ReadinessError as exc:
        raise DeliveryError("PLAN_DESIGN_GATE_BLOCKED", str(exc)) from exc
    try:
        plan_readiness.validate_execution_target(plan_dir, requested)
    except plan_readiness.ReadinessError as exc:
        raise DeliveryError("PRIORITY_FIX_TARGET_MISMATCH", str(exc)) from exc
    if plan_layout.layout_version(plan_dir) != "v2":
        return
    from task import plan_recovery
    try:
        plan_recovery.validate_request(plan_dir, requested[0])
    except plan_recovery.RecoveryError as exc:
        error = DeliveryError(exc.code, str(exc))
        error.verdict = exc.verdict
        raise error from exc
    try:
        for item_id in requested:
            if plan_readiness.design_gate_enabled(plan_dir):
                plan_bundle.model(plan_dir, item_id)
            else:
                plan_bundle.build(plan_dir, item_id, check=True)
            plan_bundle.producer_readiness(plan_dir, item_id)
    except (plan_bundle.BundleError, plan_layout.PlanLayoutError) as exc:
        raise DeliveryError(
            "NEXT_ITEM_NOT_READY", f"execution Next не готов: {exc}") from exc


def _phase_candidate(plan_dir: Path, phase_id: str) -> dict:
    """Rebuild the material phase candidate at the delivery boundary."""
    try:
        return plan_gates.phase_candidate_fingerprint(plan_dir, phase_id)
    except (OSError, ValueError) as exc:
        raise DeliveryError(
            "PHASE_ASSURANCE_CANDIDATE_UNRESOLVED",
            f"{phase_id}: material candidate не собирается: {exc}",
        ) from exc


def _validate_phase_audit_continuation(plan_dir: Path, next_exact: str) -> None:
    """Admit a phase-audit handoff only when the current policy selects it."""
    match = _AUDIT_TARGET_RE.search(next_exact)
    if match is None or match.group(1) != plan_dir.name:
        return
    phase_id = match.group(2)
    candidate = _phase_candidate(plan_dir, phase_id)
    policy = plan_gates.phase_audit_policy(
        plan_dir, phase_id, candidate_snapshot=candidate["snapshot"])
    if (policy.get("next_kind") != "audit-phase"
            or policy.get("next_exact") != next_exact):
        raise DeliveryError(
            "PHASE_AUDIT_NOT_ADMITTED",
            f"{phase_id}: policy {policy.get('code')} не допускает Next {next_exact!r}",
        )


def _continuity(route: dict, *, allow_legacy: bool) -> dict:
    try:
        if "continuity" in route:
            decision = plan_continuity.decision_from_dict(route["continuity"])
            if route.get("context") != decision.context:
                raise plan_continuity.ContinuityError("typed continuity/Context mismatch")
        else:
            decision = plan_continuity.parse_context(
                route.get("context"), allow_legacy=allow_legacy)
    except plan_continuity.ContinuityError as exc:
        raise DeliveryError(
            "CONTINUITY_CONTEXT_INVALID", "handoff Context не прошёл continuity gate") from exc
    return decision.as_dict()


def file_digest(path) -> str:
    try:
        value = Path(path).read_bytes()
    except OSError as exc:
        raise DeliveryError("DELIVERY_CARRIER_MISSING", f"носитель не читается: {path}") from exc
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _route_from_lines(lines: list[str]) -> dict:
    route = {"batch": None, "model": None, "thinking": None, "context": None, "command": None}
    text = "\n".join(lines)
    blocks = re.findall(r"^```session-continuity-decision/v1\s*\n(.*?)\n```", text,
                        flags=re.MULTILINE | re.DOTALL)
    if len(blocks) != text.count("```session-continuity-decision/v1") or len(blocks) > 1:
        raise DeliveryError("CONTINUITY_CONTEXT_INVALID", "typed continuity block неоднозначен")
    if blocks:
        try:
            route["continuity"] = plan_continuity.decision_from_dict(json.loads(blocks[0])).as_dict()
        except (json.JSONDecodeError, plan_continuity.ContinuityError) as exc:
            raise DeliveryError("CONTINUITY_CONTEXT_INVALID", "typed continuity block повреждён") from exc
    rows = []
    for line in lines:
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
        if cells and not all(set(cell) <= {":", "-"} for cell in cells):
            rows.append(cells)
    keyed = {row[0]: row[1] for row in rows if len(row) == 2}
    route.update({
        "batch": keyed.get("Batch"),
        "model": keyed.get("Model"),
        "thinking": keyed.get("Thinking"),
        "context": keyed.get("Context"),
        "command": keyed.get("Команда"),
    })
    for index, header in enumerate(rows[:-1]):
        if not {"Model", "Thinking", "Context", "Суть", "Команда"}.issubset(header):
            continue
        values = rows[index + 1]
        if len(values) != len(header):
            continue
        row = dict(zip(header, values))
        route.update({
            "batch": row.get("Batch"),
            "model": row.get("Model"),
            "thinking": row.get("Thinking"),
            "context": row.get("Context"),
            "rationale": row.get("Суть"),
            "command": row.get("Команда"),
        })
        break
    return route


def _latest_event(plan_dir: Path) -> dict | None:
    path = plan_layout.carrier_path(plan_dir, "journal")
    try:
        rows = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    latest = None
    for raw in rows:
        if not raw.strip():
            continue
        try:
            event = json.loads(raw)
            journal.validate_entry(event)
        except (json.JSONDecodeError, journal.JournalValidationError):
            continue
        latest = event
    return latest


def _latest_phase_audit_event(plan_dir: Path, subject: str) -> dict | None:
    path = plan_layout.carrier_path(plan_dir, "journal")
    try:
        rows = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    latest = None
    for raw in rows:
        if not raw.strip():
            continue
        try:
            event = json.loads(raw)
            journal.validate_entry(event)
        except (json.JSONDecodeError, journal.JournalValidationError):
            continue
        if (event.get("command") == "plan-audit"
                and review_policy.phase_audit_subject(event.get("item_id")) == subject
                and event.get("result") in {"audit-green", "audit-attention", "audit-red"}):
            # Consumers receive one canonical phase identity even when the
            # immutable historical journal still spells `Pn — режим фазы`.
            latest = {**event, "item_id": subject}
    return latest


def _semantic_next(lines: list[str]) -> str | None:
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith(("Semantic Next:", "**Next:**")):
            continue
        raw = stripped.split(":", 1)[1].strip()
        match = _SEMANTIC_NEXT_LINE_RE.fullmatch(raw)
        if match:
            return match.group(1).strip()
    return None


def _audit_handoff(plan_dir: Path, subject: str) -> dict | None:
    if not _PHASE_RE.fullmatch(subject):
        return None
    path = plan_layout.phase_path(plan_dir, subject)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise DeliveryError("HANDOFF_RECOMMENDATION_MISSING", f"audit carrier не читается: {exc}") from exc
    starts = [index for index, line in enumerate(lines) if line.startswith(f"## Audit {subject} ")]
    if not starts:
        return None
    event = _latest_phase_audit_event(plan_dir, subject)
    if event is None:
        raise DeliveryError(
            "AUDIT_TERMINAL_EVENT_MISSING", f"для latest Audit {subject} нет journal event")
    start = starts[-1]
    end = next((index for index in range(start + 1, len(lines))
                if lines[index].startswith("## Audit ")), len(lines))
    launch = next((index for index in range(start, end)
                   if lines[index].strip() == "### Что запускать"), None)
    if launch is None:
        raise DeliveryError("HANDOFF_RECOMMENDATION_MISSING", "в latest audit block нет «Что запускать»")
    body = lines[launch + 1:end]
    block_text = "\n".join(lines[start:end])
    verdict_match = _AUDIT_VERDICT_RE.search(block_text)
    verdict = verdict_match.group(1) if verdict_match else None
    expected_result = {
        "GREEN": "audit-green", "ATTENTION": "audit-attention", "RED": "audit-red",
    }.get(verdict)
    if expected_result != event.get("result"):
        raise DeliveryError(
            "AUDIT_VERDICT_EVENT_MISMATCH",
            f"latest audit verdict {verdict!r} != journal {event.get('result')!r}",
        )
    route = _route_from_lines(body)
    next_exact = _semantic_next(body) or route.get("command")
    if not next_exact or next_exact == "—":
        in_fence = False
        for line in body:
            if line.strip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence and line.strip().startswith(("$ task:", "/task:")):
                next_exact = line.strip()
                break
    if not next_exact or next_exact == "—":
        raise DeliveryError("HANDOFF_RECOMMENDATION_MISSING", "latest audit launch block не несёт команду")
    try:
        review_policy.validate_phase_audit_continuation(
            event, plan_id=plan_dir.name, next_exact=next_exact, plan_dir=plan_dir)
    except review_policy.ReviewPolicyError as exc:
        raise DeliveryError(exc.code, str(exc)) from exc
    recommendation = f"**Next:** {next_exact}\n\n" + "\n".join(body).strip()
    return {
        "next_exact": next_exact,
        "recommendation": recommendation,
        "route": route,
        "continuity": _continuity(route, allow_legacy=False),
        "rationale": {"remaining": None, "open_risks": None},
        "digest": file_digest(path),
    }


def _validate_terminal_next(plan_dir: Path, next_exact: str, continuity: dict) -> None:
    """A completed execution batch cannot erase the unfinished plan successor."""
    terminal_form = re.match(r"^(?:none|terminal)(?::|$)", next_exact)
    if continuity["outcome"] != "terminal" and terminal_form is None:
        return
    # Rebuild from item carriers; a stale status board must not hide a successor.
    unfinished = [(phase["id"], phase["status"]) for phase in
                  plan_status.status_model(plan_dir)["phases"]
                  if phase["status"] not in TERMINAL_PHASE_STATUSES]
    if unfinished:
        phase, status = min(unfinished, key=lambda row: int(row[0][1:]))
        raise DeliveryError(
            "TERMINAL_NEXT_FORBIDDEN",
            f"batch завершён, но план не terminal: {phase} — {status}; "
            "Next должен сохранять фактическое продолжение плана",
        )
    if next_exact.startswith("none:"):
        raise DeliveryError(
            "HANDOFF_NEXT_INVALID", "форма none не объявлена; используйте terminal для завершённого плана")


def _handoff(plan_dir: Path, *, closed_subject: str | None = None) -> dict:
    path = plan_dir / "handoff.md"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise DeliveryError("HANDOFF_RECOMMENDATION_MISSING", f"handoff.md не читается: {exc}") from exc
    if closed_subject is not None:
        expected = re.compile(
            rf"^# HANDOFF\s+—\s+.+\s+—\s+after\s+{re.escape(closed_subject)}\s*$")
        if not lines or not expected.fullmatch(lines[0].strip()):
            raise DeliveryError(
                "FINAL_BEFORE_TERMINAL_FORBIDDEN",
                f"handoff title не коррелирует с terminal subject {closed_subject}",
            )
    start = next((index for index, line in enumerate(lines)
                  if line.strip().startswith("**Next:**")), None)
    if start is None:
        raise DeliveryError("HANDOFF_RECOMMENDATION_MISSING", "в handoff.md нет **Next:**")
    next_exact = lines[start].split("**Next:**", 1)[1].strip()
    if not next_exact:
        raise DeliveryError("HANDOFF_RECOMMENDATION_MISSING", "Next пуст")
    _validate_design_continuation(plan_dir, next_exact)
    _validate_priority_continuation(plan_dir, next_exact)
    _validate_phase_audit_continuation(plan_dir, next_exact)
    if (closed_subject is not None and _ITEM_RE.fullmatch(closed_subject)
            and re.search(
                rf"(?:task:plan-exec|task:plan-run|task:plan-close)\s+\S+\s+"
                rf"{re.escape(closed_subject)}(?:\s|$)",
                next_exact)
            and not (next_exact.startswith("waiting:")
                     and _terminal_journal(plan_dir, closed_subject)["result"]
                     in {"blocked", "escalated"})):
        raise DeliveryError(
            "FINAL_BEFORE_TERMINAL_FORBIDDEN",
            f"Next повторно запускает terminal subject {closed_subject}",
        )
    end = next((index for index in range(start + 1, len(lines))
                if lines[index].strip().startswith("**Done:**")), len(lines))
    recommendation = "\n".join(lines[start:end]).strip()
    if not recommendation:
        raise DeliveryError("HANDOFF_RECOMMENDATION_MISSING", "recommendation пуста")

    route = _route_from_lines(lines[start:end])
    continuity = _continuity(route, allow_legacy=True)
    _validate_terminal_next(plan_dir, next_exact, continuity)

    def field(name):
        prefix = f"**{name}:**"
        return next((line.split(prefix, 1)[1].strip() for line in lines
                     if line.strip().startswith(prefix)), None)

    return {
        "next_exact": next_exact,
        "recommendation": recommendation,
        "route": route,
        "continuity": continuity,
        "rationale": {"remaining": field("Remaining"), "open_risks": field("Open risks")},
        "digest": file_digest(path),
    }


def _item_status(plan_dir: Path, item_id: str) -> tuple[str, Path]:
    phase_id = item_id.split(".", 1)[0]
    plan_layout.layout_version(plan_dir)
    state_path = plan_layout.carrier_path(plan_dir, "item-state", item_id=item_id)
    if not state_path.is_file():
        raise DeliveryError("DELIVERY_CARRIER_MISSING", f"state carrier не читается: {state_path}")
    from task import plan_item_state
    try:
        plan_item_state.build_states(plan_dir, item_id=item_id, check=True)
    except plan_item_state.ItemStateError as exc:
        raise DeliveryError("STALE_TERMINAL_RECEIPT", str(exc)) from exc
    phase_path = plan_layout.phase_path(plan_dir, phase_id)
    diagnostics = plan_lint.Diagnostics()
    phase = plan_lint.parse_phase_md(phase_path, phase_id, diagnostics, layout="v2")
    occurrences = phase["items"].get(item_id) if phase else None
    if not occurrences:
        raise DeliveryError("DELIVERY_STATE_INVALID", f"item {item_id} не найден")
    if diagnostics.errors:
        raise DeliveryError("DELIVERY_STATE_INVALID", diagnostics.errors[0])
    status = occurrences[0]["fields"].get("Status", (None, None))[0]
    return status, state_path


def _terminal_journal(plan_dir: Path, subject: str) -> dict:
    path = plan_layout.carrier_path(plan_dir, "journal")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise DeliveryError("TERMINAL_JOURNAL_MISSING", f"journal не читается: {exc}") from exc
    candidates = []
    missing_run_id_lines = []
    invalid_terminal_errors = []
    for line_number, raw in enumerate(lines, 1):
        if not raw.strip():
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        subject_matches = event.get("item_id") == subject
        if subject == "archive":
            subject_matches = event.get("item_id") == "archive" and event.get("command") == "plan-close"
        if (subject_matches and event.get("result") in journal.TERMINAL_CLOSE_RESULTS
                and not event.get("run_id")):
            missing_run_id_lines.append(line_number)
            continue
        try:
            journal.validate_entry(event)
        except journal.JournalValidationError:
            continue
        if subject_matches and event.get("result") in journal.TERMINAL_CLOSE_RESULTS:
            try:
                terminal_policy.validate_entry(event, plan_dir=plan_dir)
            except terminal_policy.TerminalPolicyError as exc:
                # A later, valid reducer close is authoritative.  Historical
                # malformed terminal attempts must remain visible to linting,
                # but cannot poison delivery of the recovered run.
                invalid_terminal_errors.append(exc)
                continue
            candidates.append((line_number, raw, event))
    if not candidates:
        if missing_run_id_lines:
            raise DeliveryError(
                "TERMINAL_RUN_ID_MISSING",
                f"journal.jsonl:{missing_run_id_lines[-1]} не несёт run_id",
            )
        if invalid_terminal_errors:
            error = invalid_terminal_errors[-1]
            raise DeliveryError(error.code, str(error)) from error
        raise DeliveryError("TERMINAL_JOURNAL_MISSING", f"для {subject} нет terminal journal event")
    line_number, raw, event = candidates[-1]
    if not event.get("run_id"):
        raise DeliveryError("TERMINAL_RUN_ID_MISSING", f"journal.jsonl:{line_number} не несёт run_id")
    receipt = {
        "line": line_number,
        "sha256": "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "run_id": event["run_id"],
        "result": event["result"],
        "command": event["command"],
    }
    if "batch_receipt" in event:
        receipt["batch_receipt"] = event["batch_receipt"]
    return receipt


def _adapter_attestation(terminal: dict | None) -> dict | None:
    if terminal is None:
        return None
    command = terminal.get("command")
    # Journal commands use the canonical basename; a legacy spelling maps to its command.
    command_id = f"task:{journal.canonical_command(command)}"
    try:
        path = command_catalog.package_command_path(command_id)
        metadata = command_catalog.load_routing_metadata(
            command_catalog.package_root() / "configs" / "command-routing.json")
    except (OSError, ValueError, command_catalog.CommandCatalogError) as exc:
        raise DeliveryError(
            "ADAPTER_ATTESTATION_MISSING", f"Task adapter identity не читается: {exc}") from exc
    return {
        "package": "task",
        "version": metadata["plugin_version"],
        "command_id": command_id,
        "canonical_command_sha256": file_digest(path),
    }


def _git_commit(plan_dir: Path) -> str | None:
    completed = subprocess.run(
        ("git", "rev-parse", "HEAD"), cwd=plan_dir, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
    )
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", value) else None


def _closure_digest(plan_dir: Path, phase_id: str) -> str | None:
    candidates = (plan_dir / "closure" / f"{phase_id}.json",
                  plan_dir / "phases" / phase_id / f"{phase_id}.closed.md")
    return next((file_digest(path) for path in candidates if path.is_file()), None)


def _require_completed_phase_before_item_handoff(plan_dir: Path, item_id: str) -> str | None:
    """Keep the last GREEN item invocation active through eligible phase close.

    Partial and non-GREEN terminal phases continue through their ordinary
    terminal-policy handoff.  Only when every item is GREEN does the rebuilt
    candidate decide between a consented audit and an inline phase close before
    the external handoff.
    """
    phase_id = item_id.split(".", 1)[0]
    from task import plan_item_state, plan_status

    statuses = []
    try:
        for spec_path in plan_layout.item_spec_paths(plan_dir, phase_id):
            model, _note, _friction = plan_item_state.state_model(plan_dir, spec_path.stem)
            statuses.append(model["state"]["position"]["status"])
    except (OSError, ValueError) as exc:
        raise DeliveryError("STALE_TERMINAL_RECEIPT", str(exc)) from exc
    if not statuses or any(status != plan_status.STATUS_DONE for status in statuses):
        return None

    candidate = _phase_candidate(plan_dir, phase_id)
    policy = plan_gates.phase_audit_policy(
        plan_dir, phase_id, candidate_snapshot=candidate["snapshot"])
    if policy.get("audit_required") or policy.get("next_kind") == "audit-phase":
        # `_handoff()` also independently rebuilds and validates an audit
        # target.  Returning the reducer output additionally forbids replacing
        # a required audit with an arbitrary external handoff.
        return policy.get("next_exact")

    close_allowed = policy.get("close_allowed")
    if close_allowed is None:  # compatibility with pre-v2 policy projections
        close_allowed = policy.get("next_kind") == "close"
    gate = plan_gates.phase_close_gate(
        plan_dir,
        phase_id,
        candidate_fingerprint=candidate["fingerprint"],
        candidate_snapshot=candidate["snapshot"],
    )
    if not close_allowed or not gate.get("allow"):
        raise DeliveryError(
            gate.get("code") or policy.get("code") or "PHASE_CLOSE_NOT_ALLOWED",
            f"{phase_id}: GREEN item completion не допускает phase close",
        )

    try:
        phase_status = plan_layout.phase_statuses(plan_dir).get(phase_id)
    except plan_layout.PlanLayoutError as exc:
        raise DeliveryError("PHASE_CLOSURE_REQUIRED", str(exc)) from exc
    if phase_status != plan_status.STATUS_DONE:
        raise DeliveryError(
            "PHASE_CLOSURE_REQUIRED",
            f"{phase_id}: terminal phase state не спроецирован ({phase_status})",
        )
    if _closure_digest(plan_dir, phase_id) is None:
        raise DeliveryError(
            "PHASE_CLOSURE_REQUIRED",
            f"{phase_id}: закрой фазу в текущем item invocation до external handoff",
        )
    try:
        plan_closure.build_closure(plan_dir, phase_id, check=True)
    except plan_closure.ClosureError as exc:
        raise DeliveryError(
            "PHASE_CLOSURE_REQUIRED",
            f"{phase_id}: phase closure carrier устарел: {exc}",
        ) from exc
    try:
        _terminal_journal(plan_dir, phase_id)
    except DeliveryError as exc:
        raise DeliveryError(
            "PHASE_CLOSURE_REQUIRED",
            f"{phase_id}: terminal phase journal не записан в текущем item invocation",
        ) from exc
    return None


def _base_receipt(plan_dir: Path, subject: str, *, schema_version: str, status: str,
                  state_digest: str | None, closure_digest: str | None,
                  terminal: dict | None, prefer_audit: bool = False,
                  required_next_exact: str | None = None) -> dict:
    handoff = ((_audit_handoff(plan_dir, subject) if prefer_audit else None)
               or _handoff(
                   plan_dir,
                   closed_subject=(subject if terminal is not None and _ITEM_RE.fullmatch(subject)
                                   else None)))
    if required_next_exact is not None and handoff["next_exact"] != required_next_exact:
        raise DeliveryError(
            "PHASE_AUDIT_CONTINUATION_REQUIRED",
            f"Next должен точно совпадать с policy: {required_next_exact}",
        )
    return {
        "schema_version": schema_version,
        "plan_id": plan_dir.name,
        "subject": subject,
        "status": status,
        "next_exact": handoff["next_exact"],
        "recommendation": handoff["recommendation"],
        "route": handoff["route"],
        "continuity": handoff["continuity"],
        "rationale": handoff["rationale"],
        "commit_sha": _git_commit(plan_dir),
        "journal": terminal,
        "adapter_attestation": _adapter_attestation(terminal),
        "digests": {
            "plan": file_digest(plan_dir / "plan.md"),
            "handoff": handoff["digest"],
            "state": state_digest,
            "closure": closure_digest,
        },
    }


def build_handoff_receipt(plan_dir, subject: str) -> dict:
    plan_dir = Path(plan_dir)
    return _base_receipt(
        plan_dir, subject,
        schema_version="handoff-recommendation-receipt/v1",
        status="handoff-persisted", state_digest=None, closure_digest=None, terminal=None,
        prefer_audit=True,
    )


def build_terminal_receipt(plan_dir, subject: str) -> dict:
    plan_dir = Path(plan_dir)
    if _ITEM_RE.fullmatch(subject):
        status, state_path = _item_status(plan_dir, subject)
        if status not in TERMINAL_ITEM_STATUSES:
            raise DeliveryError("FINAL_BEFORE_TERMINAL_FORBIDDEN", f"{subject}: {status}")
        terminal = _terminal_journal(plan_dir, subject)
        if _STATUS_BY_RESULT.get(terminal["result"]) != status:
            raise DeliveryError("STALE_TERMINAL_RECEIPT", "journal result не совпадает с item state")
        from task import plan_repeat
        repeat = plan_repeat.for_run(plan_dir, subject, terminal.get("run_id"))
        required_next_exact = (
            _require_completed_phase_before_item_handoff(plan_dir, subject)
            if status == _STATUS_BY_RESULT["closed-green"] and repeat is None else None
        )
        phase_id = subject.split(".", 1)[0]
        return _base_receipt(
            plan_dir, subject, schema_version="terminal-delivery-receipt/v1", status=status,
            state_digest=file_digest(state_path), closure_digest=_closure_digest(plan_dir, phase_id),
            terminal=terminal, required_next_exact=required_next_exact,
        )
    if _PHASE_RE.fullmatch(subject):
        status = plan_layout.phase_statuses(plan_dir).get(subject)
        if status not in TERMINAL_PHASE_STATUSES:
            raise DeliveryError("FINAL_BEFORE_TERMINAL_FORBIDDEN", f"{subject}: {status}")
        terminal = _terminal_journal(plan_dir, subject)
        if _STATUS_BY_RESULT.get(terminal["result"]) != status:
            raise DeliveryError("STALE_TERMINAL_RECEIPT", "journal result не совпадает с phase state")
        phase_path = plan_layout.phase_path(plan_dir, subject)
        return _base_receipt(
            plan_dir, subject, schema_version="terminal-delivery-receipt/v1", status=status,
            state_digest=file_digest(phase_path), closure_digest=_closure_digest(plan_dir, subject),
            terminal=terminal,
        )
    if subject == "archive":
        if plan_dir.parent.name != "archive":
            raise DeliveryError("FINAL_BEFORE_TERMINAL_FORBIDDEN", "план ещё не в archive")
        terminal = _terminal_journal(plan_dir, subject)
        return _base_receipt(
            plan_dir, subject, schema_version="terminal-delivery-receipt/v1", status="archived",
            state_digest=None, closure_digest=None, terminal=terminal,
        )
    raise DeliveryError("DELIVERY_SUBJECT_INVALID", "subject должен быть Pn.m, Pn или archive")


def verify_receipt(plan_dir, receipt: dict) -> bool:
    if not isinstance(receipt, dict):
        raise DeliveryError("STALE_TERMINAL_RECEIPT", "receipt не object")
    schema = receipt.get("schema_version")
    subject = receipt.get("subject")
    if schema == "terminal-delivery-receipt/v1":
        current = build_terminal_receipt(plan_dir, subject)
    elif schema == "handoff-recommendation-receipt/v1":
        current = build_handoff_receipt(plan_dir, subject)
    else:
        raise DeliveryError("STALE_TERMINAL_RECEIPT", "неизвестная схема receipt")
    for field in ("next_exact", "recommendation"):
        if receipt.get(field) != current[field]:
            raise DeliveryError("HANDOFF_RECOMMENDATION_MISSING", f"{field} не совпадает с handoff.md")
    # The product commit is provenance for the delivery moment.  A separate
    # bookkeeping commit necessarily advances HEAD after the receipt is written;
    # treating that unrelated movement as stale would turn every clean close into
    # a false terminal failure.  Semantic carriers below stay byte-bound.
    if schema == "terminal-delivery-receipt/v1":
        current["commit_sha"] = receipt.get("commit_sha")
    if receipt != current:
        raise DeliveryError("STALE_TERMINAL_RECEIPT", "receipt digests/state устарели")
    return True


def required_final_message(receipt: dict) -> str:
    """Render the one machine-authored terminal fragment bound by P4 admission.

    Providers may wrap this in their own transport envelope, but only this exact
    repository-owned fragment is eligible for byte comparison by terminal admission.
    """
    if not isinstance(receipt, dict) or receipt.get("schema_version") != "terminal-delivery-receipt/v1":
        raise DeliveryError("STALE_TERMINAL_RECEIPT", "terminal delivery receipt is required")
    recommendation = receipt.get("recommendation")
    if not isinstance(recommendation, str) or not recommendation:
        raise DeliveryError("HANDOFF_RECOMMENDATION_MISSING", "receipt recommendation is absent")
    return f"Рекомендация следующего шага:\n{recommendation}"


def write_receipt(path, receipt: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent,
                prefix=f".{path.name}.", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return path
