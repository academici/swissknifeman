"""Run host-local turns through leased runtime, schema and command gateways."""

from __future__ import annotations

import json
import shlex
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, ValidationFailed
from skm.modules.execution.ports import GateCommandRunner, LocalRuntimePool, UserSchemaValidator

if TYPE_CHECKING:
    from skm.kernel.gateways import Gateways
    from skm.kernel.json_types import JsonValue
    from skm.modules.runtimes.public import RuntimeResult, SessionRef
    from skm.platform.logging.redaction import Redactor

_SCHEMA_RETRIES = 3
_GATE_TAIL_LINES = 40


@dataclass(frozen=True, slots=True)
class AskRequest:
    prompt: str
    slot: str | None
    schema: UserSchemaValidator.SchemaPath | None
    schema_json: str | None = None


@dataclass(frozen=True, slots=True)
class DoRequest:
    prompt: str
    slot: str | None
    cwd: GateCommandRunner.Workdir
    gate: str | None
    gate_shell: bool
    max_gate_retries: int
    allow_fresh_retry: bool
    redactor: Redactor


@dataclass(frozen=True, slots=True)
class DeliberateRequest:
    prompt: str
    slots: tuple[str, ...]
    allow_partial: bool


@dataclass(frozen=True, slots=True)
class LocalAnswer:
    slot: str | None
    answer: str | None = None
    structured: JsonValue | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class DeliberateResult:
    answers: tuple[LocalAnswer, ...]
    exit_code: int


def _runtime_error(result: RuntimeResult) -> str | None:
    if result.denials:
        return "runtime reported tool denials"
    if result.failure is not None:
        return f"runtime failed ({result.failure.code.value})"
    if result.outcome != "completed":
        return f"runtime ended with outcome {result.outcome}"
    return None


def _json_payload(result: RuntimeResult) -> JsonValue:
    value = result.structured
    if value is None:
        value = cast("JsonValue", json.loads(result.final_text))
    json.dumps(value, allow_nan=False)
    return value


def _runtime_pool(gateways: Gateways) -> LocalRuntimePool[RuntimeResult]:
    # The host table keys gateways by protocol. Its runtime binding returns RuntimeResult.
    return cast("LocalRuntimePool[RuntimeResult]", gateways.get(LocalRuntimePool))


def local_ask(gateways: Gateways, request: AskRequest) -> LocalAnswer:
    pool = _runtime_pool(gateways)
    with pool.open(request.slot) as session:
        instructions = request.prompt
        if request.schema is not None:
            instructions += "\n\nReturn only JSON that matches the requested JSON Schema."
            if request.schema_json is not None:
                instructions += f"\n{request.schema_json}"
        prompt = instructions
        error = None
        for _ in range(1 + _SCHEMA_RETRIES):
            result = session.run(prompt, read_only=True)
            if (error := _runtime_error(result)) is not None:
                return LocalAnswer(session.slot_id, error=error)
            if request.schema is None:
                return LocalAnswer(session.slot_id, answer=result.final_text)
            try:
                payload = _json_payload(result)
            except (ValueError, RecursionError):
                error = "response is not valid JSON"
            else:
                valid, error = gateways.get(UserSchemaValidator).validate(payload, request.schema)
                if valid:
                    return LocalAnswer(session.slot_id, answer=result.final_text, structured=payload)
            error = error or "response failed schema validation"
            prompt = (
                f"{instructions}\n\nThe previous JSON response was rejected: {error}. Return corrected JSON."
            )
        return LocalAnswer(session.slot_id, error=error)


def _gate_argv(command: str | None, *, shell: bool) -> tuple[str, ...]:
    if command is None and not shell:
        return ()
    if command is not None and command.strip() and "\0" not in command:
        try:
            argv = ("/bin/sh", "-c", command) if shell else tuple(shlex.split(command))
        except ValueError:
            argv = ()
        if argv and argv[0]:
            return argv
    raise ValidationFailed(ErrorCode.RUNTIME_INVALID_REQUEST, "invalid gate command")


def local_do(gateways: Gateways, request: DoRequest) -> LocalAnswer:
    argv = _gate_argv(request.gate, shell=request.gate_shell)
    if request.max_gate_retries < 0:
        raise ValidationFailed(ErrorCode.RUNTIME_INVALID_REQUEST, "--max-gate-retries must be non-negative")
    pool = _runtime_pool(gateways)
    with pool.open(request.slot) as session:
        return _do_turns(gateways, request, session, argv)


def _do_turns(
    gateways: Gateways,
    request: DoRequest,
    session: LocalRuntimePool.Session[RuntimeResult],
    argv: tuple[str, ...],
) -> LocalAnswer:
    resume_required = bool(argv) and request.max_gate_retries > 1
    if resume_required and not session.supports_resume and not request.allow_fresh_retry:
        return LocalAnswer(session.slot_id, error="provider slot does not support SESSION_RESUME")
    persistent = resume_required and session.supports_resume
    prompt = request.prompt
    resume: SessionRef | None = None
    for attempt in range(1 + request.max_gate_retries):
        result = session.run(
            prompt,
            read_only=False,
            session_policy="persistent" if persistent else "ephemeral",
            resume_session_ref=resume,
        )
        if (error := _runtime_error(result)) is not None:
            return LocalAnswer(session.slot_id, error=error)
        if not argv:
            return LocalAnswer(session.slot_id, answer=result.final_text)
        gate = gateways.get(GateCommandRunner).run_gate(
            argv, cwd=request.cwd, timeout_seconds=120.0, max_output_bytes=1_048_576
        )
        if gate.exit_code == 0 and not gate.timed_out:
            return LocalAnswer(session.slot_id, answer=result.final_text)
        failure = "gate timed out" if gate.timed_out else f"gate failed (exit {gate.exit_code})"
        if gate.truncated:
            failure += " (output truncated)"
        tail = "\n".join(request.redactor.text(gate.output).splitlines()[-_GATE_TAIL_LINES:])
        if attempt == request.max_gate_retries:
            return LocalAnswer(session.slot_id, error=f"{failure}\n{tail}" if tail else failure)
        persistent = persistent and session.supports_resume
        resume = result.session_ref if persistent else None
        if resume_required and resume is None and not request.allow_fresh_retry:
            reason = (
                "runtime returned no session_ref" if persistent else "runtime does not support SESSION_RESUME"
            )
            return LocalAnswer(session.slot_id, error=f"{failure}. {reason} for retry")
        prompt = f"{request.prompt}\n\n{failure}. Fix the issue shown by the gate and try again.\n{tail}"
    raise AssertionError("at least one gate attempt is required")


def _deliberate_one(pool: LocalRuntimePool[RuntimeResult], slot: str, prompt: str) -> LocalAnswer:
    try:
        with pool.open(slot) as session:
            if session.slot_id != slot or session.config_mode != "isolated":
                return LocalAnswer(slot, error="deliberate requires the requested slot in isolated mode")
            result = session.run(prompt, read_only=True)
            if (error := _runtime_error(result)) is not None:
                return LocalAnswer(slot, error=error)
            return LocalAnswer(slot, answer=result.final_text)
    except SkmError as error:
        return LocalAnswer(slot, error=f"slot failed ({error.code.value}): {error.message}")
    except OSError:
        return LocalAnswer(slot, error="slot could not run on this host")


def local_deliberate(gateways: Gateways, request: DeliberateRequest) -> DeliberateResult:
    slots = request.slots
    if len(slots) < 2 or len(set(slots)) != len(slots):
        raise ValidationFailed(
            ErrorCode.RUNTIME_INVALID_REQUEST, "deliberate needs at least two distinct slots"
        )
    pool = _runtime_pool(gateways)
    with ThreadPoolExecutor(max_workers=len(slots)) as executor:
        futures = [executor.submit(_deliberate_one, pool, slot, request.prompt) for slot in slots]
        answers = tuple(future.result() for future in futures)
    successes = sum(answer.error is None for answer in answers)
    passed = successes == len(slots) or (request.allow_partial and successes > 0)
    return DeliberateResult(answers, 0 if passed else 1)
