"""Run prepared checks against one immutable candidate, retaining full evidence."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Literal, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.execution.domain.check_execution import (
    SUMMARY_MAX_CHARS,
    CheckKind,
    CheckState,
    check_summary,
    classify_check_result,
)
from skm.modules.execution.domain.ids import CheckExecutionId
from skm.modules.execution.domain.stage_record import StageOutcomeKind
from skm.modules.execution.host.checks import CheckDeps, CheckRequest
from skm.modules.execution.host.evidence import EvidenceFile
from skm.modules.execution.host.isolation import IsolationSpec
from skm.modules.execution.host.stages.base import StageOutcome, StageRequest
from skm.platform.logging.redaction import Redactor

if TYPE_CHECKING:
    from skm.modules.execution.domain.ids import StageRecordId
    from skm.modules.execution.host.environment import PreparedEnvironment
    from skm.modules.execution.ports import ExecutionEnvironmentManager, StageDeps


class RunChecksStage:
    stage_type: Literal["run_checks"] = "run_checks"
    side: Literal["host"] = "host"
    params_schema_urn = "urn:skm:execution:workflow:v1#/$defs/params"

    @staticmethod
    def invalidated(request: StageRequest, files: tuple[EvidenceFile, ...] = ()) -> StageOutcome:
        results: list[JsonValue] = [
            {
                "check_execution_id": str(raw["check_execution_id"]),
                "check_spec_id": str(raw["check_spec_id"]),
                "state": "unknown",
                "exit_code": None,
                "summary": "candidate tree changed; evidence invalidated",
            }
            for raw in cast("list[JsonObject]", request.begin.get("checks", []))
        ]
        return StageOutcome(
            StageOutcomeKind.TREE_CHANGED,
            {
                "round_no": getattr(request.instruction, "round_no", None) or 1,
                "results": results,
                "tree_changed": True,
                "error_code": "CHECK_TREE_CHANGED",
            },
            files,
        )

    def __init__(
        self,
        *,
        isolation: Callable[[JsonObject, Any, StageRequest, StageDeps], IsolationSpec],
        read_capture: Callable[[Any], bytes],
        verify_environment: Callable[[PreparedEnvironment], None],
        candidate_marks: Callable[[StageRequest, StageDeps], Mapping[str, Mapping[str, str]]],
        environment_manager: ExecutionEnvironmentManager | None = None,
        current_tips: Callable[[StageRequest, StageDeps], Mapping[str, str]] | None = None,
    ) -> None:
        self.isolation, self.read_capture, self.verify_environment = (
            isolation,
            read_capture,
            verify_environment,
        )
        self.candidate_marks = candidate_marks
        self.environment_manager, self.current_tips = environment_manager, current_tips

    def run(self, request: StageRequest, deps: StageDeps) -> StageOutcome:
        params = request.instruction.params or {}
        if params.get("scope") != "rerun_after_integration":
            return self._run_checks(request, deps)
        commits = params.get("recheck_commits")
        environment = deps.environment
        if (
            not isinstance(commits, dict)
            or not commits
            or environment is None
            or self.environment_manager is None
            or set(commits) != set(environment.mounts)
            or any(not isinstance(sha, str) for sha in commits.values())
            or any(
                cast("JsonObject", raw).get("reused")
                for raw in cast("list[Any]", request.begin.get("checks", []))
            )
        ):
            return self._recheck_failed()
        exact = cast("Mapping[str, str]", commits)
        if request.instruction.mode == "retry" and (
            self.current_tips is None or dict(self.current_tips(request, deps)) != dict(exact)
        ):
            return self._recheck_failed()
        prepared = self.environment_manager.prepare_recheck(
            environment.environment_id,
            stage_record_id=cast("StageRecordId", UUID(str(request.begin["stage_record_id"]))),
            commit_shas=exact,
        )
        outcome = None
        try:
            if any(deps.vcs.head(prepared.mounts[mount]) != sha for mount, sha in exact.items()):
                return self._recheck_failed()
            outcome = self._run_checks(request, replace(deps, environment=prepared))
            if outcome.kind is not StageOutcomeKind.SUCCESS:
                outcome = replace(
                    outcome, payload={**outcome.payload, "error_code": "INTEGRATION_RECHECK_FAILED"}
                )
            return outcome
        finally:
            # Exceptions and unknown containment retain diagnostics and inputs until proven safe.
            if outcome is not None and outcome.reaped:
                try:
                    self.environment_manager.discard(prepared, retain=False)
                except SkmError as error:
                    if error.code is not ErrorCode.CHECKOUT_BUSY:
                        raise
                    # DB terminal/reconciliation proof may arrive after this result is recorded.

    @staticmethod
    def _recheck_failed() -> StageOutcome:
        return StageOutcome(StageOutcomeKind.RUNTIME_ERROR, {"error_code": "INTEGRATION_RECHECK_FAILED"})

    def _run_checks(self, request: StageRequest, deps: StageDeps) -> StageOutcome:  # noqa: PLR0912, PLR0915 - canonical check outcome and candidate fence
        environment = deps.environment
        if environment is None:
            raise ValueError("checks require a prepared environment")
        self.verify_environment(environment)
        # Record the complete baseline-relative raw delta, including untracked entries/modes.
        before = {
            b.mount: deps.vcs.changed_paths(environment.mounts[b.mount], b.commit_sha)
            for b in environment.baseline
        }
        actual = {mount: {p.path_bytes: p.fingerprint for p in paths} for mount, paths in before.items()}
        recheck = (request.instruction.params or {}).get("scope") == "rerun_after_integration"
        marks: Mapping[str, Mapping[str, str]] = (
            {mount: {} for mount in environment.mounts} if recheck else self.candidate_marks(request, deps)
        )
        if actual != marks:
            return self.invalidated(request)
        results: list[JsonValue] = []
        files: list[EvidenceFile] = []
        states: list[CheckState] = []
        checks = cast("list[JsonObject]", request.begin.get("checks", []))
        for index, raw in enumerate(checks):
            if raw.get("reused"):
                # Reuse is a server decision before Begin, never authorized by host environment names.
                continue
            definition = raw.get("definition")
            if not isinstance(definition, dict):
                raise ValueError("prepared check definition is missing")
            kind = CheckKind(str(raw["kind"]))
            check_id = CheckExecutionId(UUID(str(raw["check_execution_id"])))
            cwd_spec = definition.get("cwd", {})
            if not isinstance(cwd_spec, dict):
                raise ValueError("invalid check cwd")
            mount = str(cwd_spec.get("mount", next(iter(environment.mounts))))
            if mount not in environment.mounts:
                raise ValueError("unknown check mount")
            relative = str(cwd_spec.get("path", "."))
            if (
                relative.startswith(("/", "~"))
                or "\0" in relative
                or "\\" in relative
                or ".." in relative.split("/")
            ):
                raise ValueError("check cwd must be mount-relative")
            # Only path construction here. The check adapter resolves and bounds it before wrap/spawn.
            cwd = environment.mounts[mount] / relative
            timeout = definition.get("timeout_seconds", 300)
            idle = definition.get("idle_timeout_seconds", 60)
            if not isinstance(timeout, int) or not isinstance(idle, int):
                raise ValueError("invalid check timeouts")
            output_limits = raw.get("output_limits", {})
            if not isinstance(output_limits, dict):
                raise ValueError("invalid prepared check output limits")
            check = CheckRequest(
                check_id,
                definition,
                cwd,
                {},
                timeout,
                idle,
                self.isolation(raw, cwd, request, deps),
                output_limits,
            )
            self.verify_environment(environment)
            result = deps.check_runners.get(kind.value).run(
                check,
                CheckDeps(environment, deps.uploader, deps.clock, deps.monotonic, deps.log, deps.cancel),
            )
            state, code = classify_check_result(
                kind,
                result.exit_code,
                result.timed_out,
                result.spawn_error,
                result.interrupted,
                expected_exit=cast("int", definition.get("expected_exit", 0)),
            )
            if result.exit_code is not None and result.exit_code < 0 and state is not CheckState.UNKNOWN:
                state, code = CheckState.ERROR, "CHECK_KILLED"
            if result.interrupted:
                state, code = CheckState.UNKNOWN, "CHECK_CLEANUP_UNCONFIRMED"
            elif result.spawn_error:
                code = result.spawn_error
            elif result.timed_out:
                code = "CHECK_TIMEOUT"
            summary = str(definition.get("instructions_md", ""))[:500] if kind is CheckKind.MANUAL else ""
            owner = "check_execution:" + str(check_id)
            if kind in {CheckKind.COMMAND, CheckKind.SHELL}:
                summary = (
                    self.read_capture(result.stdout_path) + self.read_capture(result.stderr_path)
                ).decode("utf-8", "replace")
                files.extend(
                    (
                        EvidenceFile(result.stdout_path, owner, "evidence", "stdout.txt", "text/plain"),
                        EvidenceFile(result.stderr_path, owner, "evidence", "stderr.txt", "text/plain"),
                    )
                )
            files.extend(
                EvidenceFile(p, owner, "report", p.name, "application/octet-stream")
                for p in result.report_files
            )
            summary = check_summary(Redactor().text(summary))
            prefix = str(code) + ": " if code else ""
            summary = prefix + summary[: SUMMARY_MAX_CHARS - len(prefix)]
            states.append(state)
            results.append(
                {
                    "check_execution_id": str(check_id),
                    "check_spec_id": str(raw["check_spec_id"]),
                    "state": state.value,
                    "exit_code": result.exit_code,
                    "summary": summary,
                    "duration_ms": max(0, round(result.duration_seconds * 1000)),
                }
            )
            if result.interrupted:
                # A live/unknown containment can still change the candidate. Do not start another check
                # or read a new tree snapshot; include every unstarted check as unknown for the server.
                results.extend(
                    {
                        "check_execution_id": str(pending["check_execution_id"]),
                        "check_spec_id": str(pending["check_spec_id"]),
                        "state": "unknown",
                        "exit_code": None,
                        "summary": "CHECK_CLEANUP_UNCONFIRMED: environment blocked pending reap/reconcile",
                    }
                    for pending in checks[index + 1 :]
                )
                return StageOutcome(
                    StageOutcomeKind.CHECKS_UNKNOWN,
                    {
                        "round_no": getattr(request.instruction, "round_no", None) or 1,
                        "results": results,
                        "error_code": "CHECK_CLEANUP_UNCONFIRMED",
                    },
                    tuple(files),
                    reaped=False,
                )
            self.verify_environment(environment)
            after = {
                b.mount: deps.vcs.changed_paths(environment.mounts[b.mount], b.commit_sha)
                for b in environment.baseline
            }
            if after != before:
                return self.invalidated(request, tuple(files))
        if CheckState.UNKNOWN in states:
            outcome = StageOutcomeKind.CHECKS_UNKNOWN
        elif CheckState.ERROR in states:
            outcome = StageOutcomeKind.CHECKS_ERROR
        elif CheckState.FAILED in states:
            outcome = StageOutcomeKind.CHECKS_FAILED
        elif CheckState.MANUAL_PENDING in states:
            outcome = StageOutcomeKind.MANUAL_PENDING
        else:
            outcome = StageOutcomeKind.SUCCESS
        return StageOutcome(
            outcome,
            {"round_no": getattr(request.instruction, "round_no", None) or 1, "results": results},
            tuple(files),
        )

    def __call__(self, request: StageRequest, deps: StageDeps) -> StageOutcome:
        return self.run(request, deps)
