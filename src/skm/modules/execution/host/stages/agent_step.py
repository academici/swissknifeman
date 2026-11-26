"""One runtime and result pipeline for all seven roles, including early M3 triage."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import asdict
from typing import TYPE_CHECKING, Any, Literal, cast

from skm.kernel.cancel import Cancelled
from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain.repair import extract_result, extraction_errors, heal, schema_errors
from skm.modules.execution.domain.role_contracts import ROLE_CONTRACTS
from skm.modules.execution.domain.semantics import drift
from skm.modules.execution.domain.stage_record import StageOutcomeKind
from skm.modules.execution.domain.step import RoleId
from skm.modules.execution.domain.triage import reverify_decision, trivial_command
from skm.modules.execution.host.checks import CheckDeps
from skm.modules.execution.host.evidence import EvidenceFile
from skm.modules.execution.host.reproduce import run_reproduction
from skm.modules.execution.host.stages.base import (
    CleanupUnconfirmed,
    StageOutcome,
    StageRequest,
)
from skm.modules.runtimes.public import (
    ToolCompleted,
    ToolRequested,
    UsageReported,
    merge_usage,
    observation_to_json,
    process_ownership_to_json,
    session_event_to_json,
    unknown_usage,
)

if TYPE_CHECKING:
    from skm.modules.execution.domain.finding import Finding
    from skm.modules.execution.host.heartbeat import EventFlag, HostConcurrency
    from skm.modules.execution.ports import StageDeps
    from skm.modules.runtimes.public import AgentRuntime, RuntimeResult, UsageReport


def usage_json(usage: UsageReport) -> JsonObject:
    return cast("JsonObject", asdict(usage))


def role_result(
    role: str,
    structured: JsonObject | None,
    text: str,
    *,
    validate: Callable[[str, object], tuple[JsonObject, ...]],
) -> tuple[JsonObject | None, JsonObject]:
    contract = ROLE_CONTRACTS[RoleId(role)]
    extracted = extract_result(structured, text)
    errors = extraction_errors(extracted)
    raw = extracted.get("doc")
    if errors or not isinstance(raw, dict):
        return None, {"error_code": "RESULT_INVALID", "detail": json.dumps({"schema_errors": errors})}
    issues = validate(contract.result_schema_urn, raw)
    if not issues:
        return raw, {"repairs": []}
    errors = schema_errors(issues)
    repaired = heal(contract.result_kind.value, raw)
    result = repaired.get("document")
    if repaired["kind"] != "healed" or not isinstance(result, dict):
        return None, {"error_code": "RESULT_INVALID", "detail": json.dumps({"schema_errors": errors})}
    if drift(contract.result_kind.value, raw, result):
        return None, {"error_code": "REPAIR_SEMANTIC_DRIFT", "detail": json.dumps({"schema_errors": errors})}
    if validate(contract.result_schema_urn, result):
        return None, {"error_code": "RESULT_INVALID", "detail": json.dumps({"schema_errors": errors})}
    return result, {"repairs": repaired["notes"]}


def _report_progress(deps: StageDeps, progress: JsonObject) -> None:
    # The bound client owns the renewal threshold and cancellation latch.
    # Keep draining after delivery failures; runtime/event-stream failures are handled separately.
    with suppress(Exception):
        deps.worker.report_progress(progress)


def _collect(
    runtime: AgentRuntime,
    handle: Any,
    request: StageRequest,
    deps: StageDeps,
    done: EventFlag,
    results: list[RuntimeResult],
    failures: list[BaseException],
) -> None:
    usage = unknown_usage()
    try:
        for event in runtime.events(handle):
            if deps.cancel.cancelled:
                continue  # drain bytes without using a revoked lease or retaining unbounded events
            progress: JsonObject = {
                "stage_record_id": request.begin["stage_record_id"],
                "step_id": handle.request_id,
                "last_runtime_event_at": event.at.isoformat(),
            }
            if isinstance(event, UsageReported):
                usage = merge_usage(usage, event.usage, cumulative=event.cumulative)
                progress["usage_so_far"] = usage_json(usage)
            if isinstance(event, ToolRequested | ToolCompleted):
                call: JsonObject = {
                    "call_id": event.call_id,
                    "duration_ms": event.duration_ms if isinstance(event, ToolCompleted) else None,
                }
                if isinstance(event, ToolRequested):
                    tool = request.capture.redactor.text(event.tool) if request.capture else event.tool
                    call["tool"] = tool[:300]
                progress["tool_calls"] = {"coverage": "partial", "calls": [call]}
            _report_progress(deps, progress)
            if request.offer_live is not None:
                request.offer_live(json.dumps(session_event_to_json(event)).encode())
        results.append(runtime.result(handle))
    except BaseException as error:  # noqa: BLE001 - propagate thread failure to its owning stage
        failures.append(error)
    finally:
        done.set()


def _run_runtime(
    request: StageRequest, deps: StageDeps, concurrency: HostConcurrency
) -> tuple[RuntimeResult, bool]:
    agent = request.runtime_request
    if agent is None:
        raise ValueError("agent stage requires an admitted runtime request")
    deps.cancel.raise_if_cancelled()
    runtime = deps.runtimes.get(agent.runtime_id)
    handle = runtime.start(agent)
    done = concurrency.event()
    results: list[RuntimeResult] = []
    failures: list[BaseException] = []
    thread = concurrency.thread(
        lambda: _collect(runtime, handle, request, deps, done, results, failures), "skm-runtime-events"
    )
    thread.start()
    stopped = False
    try:
        request.process_started(handle)
        process: JsonObject = {
            "pid": handle.pid,
            "pgid": handle.pid,
            "started_at": handle.started_at.isoformat(),
            "start_ticks": handle.process_start_ticks,
            "ownership": process_ownership_to_json(handle.ownership) if handle.ownership else {},
        }
        _report_progress(
            deps,
            {
                "stage_record_id": request.begin["stage_record_id"],
                "step_id": handle.request_id,
                "process": process,
            },
        )
        while not done.wait(0.05):
            if deps.cancel.cancelled:
                break
    finally:
        # Even completed leaders require containment cleanup; the adapter owns escalation/reaping.
        stopped = runtime.cancel(handle, grace_seconds=1).stopped
        thread.join(timeout=2)
    if (not stopped or thread.is_alive()) and not results:
        raise CleanupUnconfirmed("runtime containment did not confirm an empty unit")
    if failures and not deps.cancel.cancelled:
        raise failures[0]
    if not results:
        raise Cancelled(deps.cancel.reason or "user_cancel")
    return results[0], stopped


class AgentStepStage:
    stage_type: str = "agent_step"
    side: Literal["host"] = "host"
    params_schema_urn = "urn:skm:execution:workflow:v1#/$defs/params"

    def __init__(
        self,
        *,
        concurrency: HostConcurrency,
        validate_result: Callable[[str, object], tuple[JsonObject, ...]],
        output_manifest: Callable[[StageRequest, StageDeps], JsonObject] | None = None,
        seal_snapshot: Callable[[StageRequest, StageDeps], str | None] | None = None,
        read_transcript: Callable[[str, int], bytes] | None = None,
        registrar_llm: bool = False,
        triage_findings: Callable[[StageRequest], Sequence[Finding]] = lambda _: (),
    ) -> None:
        self.output_manifest = output_manifest
        self.seal_snapshot = seal_snapshot
        self.read_transcript = read_transcript
        self.concurrency, self.validate_result = concurrency, validate_result
        self.registrar_llm, self.triage_findings = registrar_llm, triage_findings

    def run(self, request: StageRequest, deps: StageDeps) -> StageOutcome:  # noqa: PLR0912 - one evidence/cancellation/result lifecycle
        agent, capture = request.runtime_request, request.capture
        if agent is not None and capture is not None:
            for secret in agent.secret_env.values():
                capture.redactor.register_secret(secret.reveal())
        step = request.begin.get("step")
        role = agent.role.value if agent else step.get("role") if isinstance(step, dict) else None
        if role == "registrar" and not self.registrar_llm:
            return self._registrar(request, deps)
        if agent is None or request.context is None or capture is None:
            raise ValueError("agent stage needs final context, runtime request and reserved capture")
        started = deps.monotonic.monotonic()
        result, reaped = _run_runtime(request, deps, self.concurrency)
        # Late evidence remains local. No upload, mutation, approval, observation or result admission here.
        raw_value = capture.redactor.document(result.structured)
        raw = raw_value if isinstance(raw_value, dict) else None
        extracted = extract_result(raw, capture.redactor.text(result.final_text))
        raw_doc = extracted.get("doc")
        text = (
            json.dumps(raw_doc, ensure_ascii=False)
            if isinstance(raw_doc, dict)
            else capture.redactor.text(result.final_text)
        )
        raw_path = capture.write("raw.json", text, limit=capture.max_bytes // 2)
        patch = b""
        if deps.environment is not None:
            patch = b"\n".join(deps.vcs.dirty_patch(p) for p in deps.environment.mounts.values())
        capture.write("environment.patch", patch.decode("utf-8", "replace"), limit=capture.max_bytes // 4)
        capture.journal(
            stage_record_id=request.begin["stage_record_id"],
            step_id=agent.request_id,
            cancelled=deps.cancel.cancelled,
            reaped=reaped,
        )
        files = (
            EvidenceFile(raw_path, f"step:{agent.request_id}", "raw_result", "raw.json", "application/json"),
        )
        if result.transcript_path is not None and self.read_transcript is not None:
            try:
                transcript = self.read_transcript(result.transcript_path, capture.max_bytes // 8).decode(
                    "utf-8", "replace"
                )
            except OSError:
                pass  # Missing provider visibility is unavailable, never fabricated evidence.
            else:
                transcript_path = capture.write("transcript.txt", transcript, limit=capture.max_bytes // 8)
                files += (
                    EvidenceFile(
                        transcript_path,
                        f"step:{agent.request_id}",
                        "transcript",
                        "transcript.txt",
                        "text/plain",
                    ),
                )
        observations: tuple[JsonObject, ...] = ()
        if result.observation is not None:
            observations = (
                {
                    "step_id": agent.request_id,
                    "observation": capture.redactor.document(observation_to_json(result.observation)),
                },
            )
        if deps.cancel.cancelled:
            return StageOutcome(
                StageOutcomeKind.RUNTIME_ERROR,
                {"error_code": "SESSION_CANCELLED"},
                files,
                result.usage,
                observations=observations,
                reaped=reaped,
            )
        if result.outcome != "completed":
            return StageOutcome(
                StageOutcomeKind.RUNTIME_ERROR,
                {
                    "error_code": result.failure.code.value if result.failure else "RUNTIME_ERROR",
                    "error_class": result.failure.error_class.value if result.failure else "runtime_error",
                },
                files,
                result.usage,
                observations=observations,
                reaped=reaped,
            )
        if not reaped:
            raise CleanupUnconfirmed(
                "result cannot authorize reproduction before runtime containment is empty"
            )
        document, metadata = role_result(
            agent.role.value, raw, capture.redactor.text(result.final_text), validate=self.validate_result
        )
        kind = StageOutcomeKind.SUCCESS if document is not None else StageOutcomeKind.RESULT_INVALID
        payload: JsonObject = {"step_id": agent.request_id, "session_ref": result.session_ref, **metadata}
        if document is not None:
            if agent.role.value == "triager":
                document, receipts, evidence = self._triage(request, deps, document, started)
                if receipts:
                    payload["detail"] = json.dumps({"triage": {**document, "reverify": receipts}})
                files += evidence
            payload["role_result"] = document
        manifest = None
        if document is not None and agent.role.value == "executor":
            if self.seal_snapshot is not None:
                output_id = self.seal_snapshot(request, deps)
                if output_id is None:
                    raise ValueError("executor stage requires a sealed output")
                payload["output_id"] = output_id
            elif self.output_manifest is not None:
                manifest = self.output_manifest(request, deps)
            else:
                raise ValueError("executor stage requires a real output sealer")
        return StageOutcome(
            kind,
            payload,
            files,
            result.usage,
            output_manifest=manifest,
            observations=observations,
            reaped=reaped,
        )

    def __call__(self, request: StageRequest, deps: StageDeps) -> StageOutcome:
        return self.run(request, deps)

    def _registrar(self, request: StageRequest, deps: StageDeps) -> StageOutcome:
        deps.cancel.raise_if_cancelled()
        capture = request.capture
        if request.context is None or capture is None:
            raise ValueError("registrar requires finalized context and reserved evidence")
        task = request.task
        title = task.get("title") or task.get("display_key") or task.get("entity_id") or "Task"
        title = " ".join(str(title).split())
        title = title if len(title) >= 3 else f"Task {title}".strip()
        kind = {"docs": "docs", "test": "test", "config": "build"}.get(
            str(task.get("work_kind") or task.get("kind")), "chore"
        )
        prefix = re.fullmatch(
            r"(feat|fix|refactor|docs|test|build|chore)(?:\(([a-z0-9-]{1,40})\))?: (.+)", title
        )
        scope = deps.config.get("execution.integration.commit_scope")
        if prefix:
            kind, scope, title = prefix[1], scope or prefix[2], prefix[3]
        commit: JsonObject = {"type": kind, "subject": title[:72], "body": ""}
        if scope:
            commit["scope"] = str(scope)
        raw: JsonObject = {"schema": ROLE_CONTRACTS[RoleId.REGISTRAR].result_schema_urn, "commit": commit}
        raw = cast("JsonObject", capture.redactor.document(raw))
        path = capture.write("raw.json", json.dumps(raw, ensure_ascii=False))
        step = request.begin.get("step")
        step_id = (
            request.runtime_request.request_id
            if request.runtime_request
            else str(step["step_id"])
            if isinstance(step, dict)
            else ""
        )
        document, metadata = role_result("registrar", raw, "", validate=self.validate_result)
        capture.journal(stage_record_id=request.begin["stage_record_id"], step_id=step_id, reaped=True)
        return StageOutcome(
            StageOutcomeKind.SUCCESS if document else StageOutcomeKind.RESULT_INVALID,
            {"step_id": step_id, **metadata, **({"role_result": document} if document else {})},
            (EvidenceFile(path, f"step:{step_id}", "raw_result", "raw.json", "application/json"),),
        )

    def _triage(
        self,
        request: StageRequest,
        deps: StageDeps,
        document: JsonObject,
        started: float,
    ) -> tuple[JsonObject, list[JsonObject], tuple[EvidenceFile, ...]]:
        source = tuple(self.triage_findings(request))
        names = [f.local_id for f in source]
        findings = {f.local_id: f for f in source if names.count(f.local_id) == 1}
        confirmed = list(cast("list[JsonObject]", document["confirmed"]))
        rejected: list[JsonObject] = []
        receipts: list[JsonObject] = []
        files: tuple[EvidenceFile, ...] = ()
        for row in cast("list[JsonObject]", document["rejected"]):
            name = str(row["finding_id"])
            finding = findings.get(name)
            repro = row.get("reproduction")
            facts: JsonObject = {"verified": False}
            argv = repro.get("argv") if isinstance(repro, dict) else None
            if (
                finding
                and finding.severity.value in {"blocker", "major"}
                and isinstance(argv, list)
                and not trivial_command([str(a) for a in argv])
            ):
                agent = request.runtime_request
                limit = agent.limits.timeout_seconds if agent else None
                remaining = (
                    None if limit is None else max(0, int(limit - (deps.monotonic.monotonic() - started)))
                )
                facts, evidence = run_reproduction(
                    request,
                    CheckDeps(
                        deps.environment, deps.uploader, deps.clock, deps.monotonic, deps.log, deps.cancel
                    )
                    if deps.environment
                    else None,
                    cast("JsonObject", repro),
                    run_check=lambda check, check_deps: deps.check_runners.get("command").run(
                        check, check_deps
                    ),
                    timeout_seconds=deps.config.get("execution.triage.repro_timeout_seconds"),
                    finding_id=name,
                    remaining_seconds=remaining,
                )
                files += evidence
            decision: JsonObject = {**row, "decision": "rejected", "verification": facts}
            receipt = (
                reverify_decision(finding, decision)
                if finding
                else {**decision, "decision": "confirmed", "code": "TRIAGE_REPRO_UNVERIFIED"}
            )
            receipts.append(receipt)
            if receipt["decision"] == "rejected":
                rejected.append(row)
            else:
                restored: JsonObject = {"finding_id": name, "decision": "fix_now"}
                if isinstance(repro, dict):
                    restored["reproduction"] = repro
                confirmed.append(restored)
        return cast("JsonObject", {**document, "confirmed": confirmed, "rejected": rejected}), receipts, files
