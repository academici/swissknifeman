"""Durable Git writes and the target writer's journal-bound, pidfd-owned ref helper."""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast, override
from uuid import UUID, uuid4, uuid5

from skm.adapters.git.host_inputs import read_metadata
from skm.adapters.git.runner import GitBytesResult, GitCommandFailed, GitRunner, validate_repository_trust
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, error_for
from skm.modules.execution.domain.external_effect import commit_request
from skm.modules.execution.domain.ids import ExternalEffectId
from skm.modules.runtimes.public import ProcessOwner, ProcessOwnership
from skm.platform.fs.atomic_write import atomic_write
from skm.platform.fs.file_lock import FileLock
from skm.platform.process import runner as processes
from skm.platform.process.identity import ProcessIdentity
from skm.platform.process.markers import claim_marker, remove_marker, update_marker
from skm.platform.process.ownership import require_support
from skm.platform.process.streams import BoundedCapture

__all__: list[str] = []


class DurableGitRunner(GitRunner):
    """Keep the injected runner's trust/env policy and fsync objects as well as references."""

    def __init__(self, delegate: GitRunner) -> None:
        super().__init__(delegate.git_binary)
        self.delegate = delegate

    @override
    def run_bytes(self, cwd: str | Path, args: Sequence[str], **kwargs: Any) -> GitBytesResult:
        return self.delegate.run_bytes(cwd, ["-c", "core.fsync=all", *args], **kwargs)

    @override
    def build_argv(self, cwd: str | Path, args: Sequence[str]) -> list[str]:
        return self.delegate.build_argv(cwd, ["-c", "core.fsync=all", *args])

    @override
    def build_environment(
        self, base_env: Mapping[str, str] | None = None, *, allow_ssh_agent: bool = False
    ) -> dict[str, str]:
        return self.delegate.build_environment(base_env, allow_ssh_agent=allow_ssh_agent)


def writer_ownership(raw: Mapping[str, Any], effect_id: UUID, attempt_id: str) -> ProcessOwnership:
    data = dict(raw["owner"])
    for key in ("host_id", "worker_id", "attempt_id", "stage_record_id", "unit_id"):
        data[key] = UUID(str(data[key]))
    owner = ProcessOwner(**data)
    ownership = ProcessOwnership(owner, raw["kind"], raw["ref"], raw.get("daemon_identity"))
    if owner.unit_kind != "git_effect" or owner.unit_id != effect_id or str(owner.attempt_id) != attempt_id:
        raise ValueError("Git helper ownership differs from the effect/attempt")
    # This trusted Git launcher owns a new process group through a child-provided pidfd. It must
    # never claim an unrelated cgroup/container; those require their matching host launcher.
    if ownership.kind != "pgroup_best_effort" or ownership.ref != f"pgroup:{effect_id}":
        raise error_for(ErrorCode.CAPABILITY_UNAVAILABLE, "Git helper containment launcher unavailable")
    require_support()
    return ownership


def run_ref_transaction(
    git: GitRunner,
    repo: Path,
    ownership: ProcessOwnership,
    transaction: bytes,
    *,
    persist_spawn: Callable[[ProcessIdentity, int], None],
) -> GitBytesResult:
    """No ref command reaches Git until the ownership binding and spawned identity are fsynced.

    The platform launcher creates a new session/process group and acquires the child's own pidfd
    before returning. Spawn/identity-write failure leaves the prepared journal unresolved; a
    supervisor restart cannot treat a missing PID or an expired slot as containment-empty proof.
    Git hooks are disabled by GitRunner, and this helper runs only the fixed update-ref command.
    """
    validate_repository_trust(repo)
    if ownership.kind != "pgroup_best_effort" or ownership.ref != f"pgroup:{ownership.owner.unit_id}":
        raise ValueError("Git helper requires its prepared process-group ownership")
    out, err = BoundedCapture(1_048_576), BoundedCapture(65_536)
    started = time.monotonic()
    process = processes.spawn(
        git.build_argv(repo, ["update-ref", "--stdin"]),
        cwd=repo,
        env=git.build_environment(),
        on_stdout=out.feed,
        on_stderr=err.feed,
        line_mode=False,
    )
    try:
        persist_spawn(process.identity, process.pgid)
        process.write_stdin(transaction)
        process.close_stdin()
        code = process.wait(60)
        if code is None or not process.terminate(grace_seconds=0).exited:
            raise error_for(ErrorCode.OUTCOME_UNKNOWN, "Git ref helper did not confirm reap")
        if out.truncated or err.truncated:
            raise error_for(ErrorCode.OUTCOME_UNKNOWN, "Git ref helper output exceeded capture limit")
    except BaseException as primary:
        # Termination uses the retained kernel ownership, never a numeric PID read from disk.
        # Even a successful cleanup here does not guess the outcome of a failed journal write.
        try:
            process.terminate(grace_seconds=0)
        except Exception as cleanup:  # noqa: BLE001 - preserve the uncertain publication failure
            primary.add_note(f"Git helper cleanup failed: {cleanup}")
        raise
    return GitBytesResult(code, bytes(out.data), bytes(err.data), round((time.monotonic() - started) * 1000))


def run_owned_git(
    git: GitRunner,
    repo: Path,
    args: Sequence[str],
    *,
    persist_spawn: Callable[[ProcessIdentity, int], None],
    before_release: Callable[[], None] = lambda: None,
    timeout_s: float = 60,
) -> GitBytesResult:
    """Release a same-PID exec gate only after durable ownership and current admission."""
    validate_repository_trust(repo)
    gate = "import os,sys; os.read(0,1)==b'1' or sys.exit(1); os.execvp(sys.argv[1],sys.argv[1:])"
    out, err = BoundedCapture(1_048_576), BoundedCapture(65_536)
    started = time.monotonic()
    process = processes.spawn(
        [sys.executable, "-I", "-S", "-c", gate, *git.build_argv(repo, args)],
        cwd=repo,
        env=git.build_environment(),
        on_stdout=out.feed,
        on_stderr=err.feed,
        line_mode=False,
    )
    try:
        persist_spawn(process.identity, process.pgid)
        before_release()
        process.write_stdin(b"1")
        process.close_stdin()
        code = process.wait(timeout_s)
        if code is None or not process.terminate(grace_seconds=0).exited:
            raise error_for(ErrorCode.OUTCOME_UNKNOWN, "Git helper did not confirm reap")
        if out.truncated or err.truncated:
            raise error_for(ErrorCode.OUTCOME_UNKNOWN, "Git helper output exceeded capture limit")
    finally:
        process.terminate(grace_seconds=0)
    return GitBytesResult(code, bytes(out.data), bytes(err.data), round((time.monotonic() - started) * 1000))


class InspectionGitRunner(GitRunner):
    """Each read helper is durably bound to the current admin claim before Git can execute.

    Stage process identities are immutable per unit. Each helper therefore receives a unique unit,
    derived from the bound effect and its owner nonce; RenewLease verifies that relation server-side.
    An unresolved helper blocks all later reads until the exact containment has an empty proof.
    """

    def __init__(self, writer: Any, effect: Any, binding: Any, client: Any) -> None:
        super().__init__(writer.git.git_binary)
        self.reaped = True
        self.delegate, self.writer, self.client = writer.git, writer, client
        self.effect, self.claim, self.ownership = effect, binding["claim"], binding["ownership"]
        owner = self.ownership["owner"]
        writer_ownership(self.ownership, UUID(effect["effect_id"]), self.claim["attempt_id"])
        for key in ("host_id", "worker_id", "attempt_id", "stage_record_id"):
            if owner[key] != self.claim[key]:
                raise error_for(ErrorCode.FORBIDDEN, "inspection ownership differs from admin claim")
        UUID(self.claim["assignment_id"])
        token = self.claim["fencing_token"]
        if isinstance(token, bool) or not isinstance(token, int) or token < 1:
            raise ValueError("inspection requires a fencing token")
        self.folder = writer.root / "_inspection" / str(UUID(effect["effect_id"]))
        self.folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        validate_repository_trust(self.folder)

    @override
    def run_bytes(self, cwd: str | Path, args: Sequence[str], **kwargs: Any) -> GitBytesResult:
        command = list(args)
        while command[:1] == ["-c"]:
            command = command[2:]
        if not command or command[0] not in {
            "rev-parse",
            "show",
            "rev-list",
            "merge-base",
            "remote",
            "config",
            "check-ref-format",
            "ls-remote",
        }:
            raise ValueError("inspection only supports Git reads")
        if (command[0] == "remote" and command[1:2] != ["get-url"]) or (
            command[0] == "config" and command[1:2] != ["--get-regexp"]
        ):
            raise ValueError("inspection cannot mutate Git configuration")
        if kwargs.get("stdin") is not None or kwargs.get("env"):
            raise ValueError("inspection cannot accept mutation input")
        # No lookup result proves cleanup. Keep this false across swallowed lookup errors,
        # unresolved earlier journals, and any failure before the durable helper reap completes.
        self.reaped = False
        with FileLock(self.folder / "helpers.lock").hold(timeout_seconds=1):
            for path in self.folder.glob("*.json"):
                prior = json.loads(read_metadata(path))
                if not prior["reaped"] and not self.writer.quiescent(prior["ownership"]):
                    raise error_for(
                        ErrorCode.OUTCOME_UNKNOWN, "previous inspection helper has no empty proof"
                    )
            nonce = uuid4().hex
            unit = uuid5(UUID(self.effect["effect_id"]), nonce)
            ownership = {
                **self.ownership,
                "ref": f"pgroup:{unit}",
                "owner": {**self.ownership["owner"], "owner_nonce": nonce, "unit_id": str(unit)},
            }
            journal = {
                "effect_id": self.effect["effect_id"],
                "request_digest": self.effect["request_digest"],
                "claim": self.claim,
                "ownership": ownership,
                "reaped": False,
            }
            path = self.folder / (nonce + ".json")
            bound = writer_ownership(ownership, unit, self.claim["attempt_id"])

            def save() -> None:
                atomic_write(path, json.dumps(journal).encode(), mode=0o600, private=True)

            def spawned(identity: ProcessIdentity, pgid: int) -> None:
                progress = {
                    **asdict(identity),
                    "pgid": pgid,
                    "ownership": ownership,
                    "started_at": self.writer.now().isoformat(),
                }
                journal["process"] = progress
                update_marker(marker, identity, pgid=pgid, ownership=asdict(bound))
                save()
                reply = self.client.report_progress(
                    {"stage_record_id": self.claim["stage_record_id"], "process": progress}
                )
                if reply.get("cancel_requested") or reply.get("refusal"):
                    raise error_for(ErrorCode.LEASE_LOST, "inspection admission refused")

            save()
            marker = claim_marker(Path(bound.owner.identity_dir), asdict(bound))
            result = run_owned_git(
                self.delegate,
                Path(cwd),
                args,
                persist_spawn=spawned,
                timeout_s=min(float(kwargs.get("timeout_s") or 30), 30),
            )
            journal["reaped"] = True
            save()
            remove_marker(marker)
            self.reaped = True
            if kwargs.get("check", True) and result.exit_code:
                raise GitCommandFailed(args, result.exit_code, result.stderr.decode("utf-8", "replace"))
            return result


def inspect_effect(writer: Any, repo: Path, effect: Any, binding: Any, client: Any) -> Any:
    """Use a scoped reader so simultaneous work never changes the shared writer's runner."""
    unknown = {
        "state": "outcome_unknown",
        "effect_id": effect["effect_id"],
        "request_digest": effect["request_digest"],
    }
    inspector: InspectionGitRunner | None = None
    result = unknown
    try:
        reader: Any = object.__new__(cast("type[Any]", type(writer)))
        reader.__dict__.update(vars(writer))
        inspector = InspectionGitRunner(writer, effect, binding, client)
        reader.git = inspector
        if effect["kind"] == "git_commit":
            result = reader.reconcile_integration(
                repo, ExternalEffectId(UUID(effect["effect_id"])), commit_request(effect["request"])
            )
        elif effect["kind"] == "git_push":
            result = reader.inspect_push(
                repo, effect["effect_id"], effect["request"], effect["request_digest"]
            )
    except (OSError, ValueError, SkmError):
        result = unknown
    return {**result, "reaped": inspector.reaped if inspector is not None else False}
