"""Read-only planning and bounded cleanup of local storage targets."""

import json
import os
import shutil
import stat
from collections.abc import Callable, Iterator, Mapping
from contextlib import suppress
from datetime import datetime, timedelta
from fcntl import LOCK_EX, LOCK_NB, flock
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

from skm.adapters.git.environments.worktree import CleanupProof, Prepared, WorktreeManager
from skm.adapters.git.host_inputs import read_metadata
from skm.adapters.git.runner import GitRunner
from skm.adapters.git.status import changed_paths
from skm.application_bus.client import SkmClient
from skm.application_bus.host import HostServices
from skm.bootstrap.lifecycle import LocalProcesses
from skm.kernel.cancel import CancelSource
from skm.kernel.errors import NotFound, SkmError
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import HostId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.module_manifest import HostOperationSpec
from skm.kernel.ports_uow import Surface
from skm.modules.execution.domain.ids import EnvironmentId
from skm.modules.execution.host.clean_environments import PAGE_SIZE, CleanEnvironmentsOperation
from skm.modules.execution.ports import ExecutionEnvironmentManager
from skm.modules.execution.public import (
    AttemptView,
    ExecutionEnvironmentsView,
    GetAttempt,
    ListExecutionEnvironments,
    MarkEnvironmentsRemovedCommand,
)
from skm.platform.config.bootstrap import BootstrapConfig, validate_worker_host
from skm.platform.process.markers import read_marker
from skm.platform.system_clock import SystemClock

__all__ = ["clean_files", "clean_worktrees", "terminal_attempt"]

_TERMINAL = frozenset({"completed", "ownership_lost", "abandoned"})
_OPERATION = "execution.host.clean_environments"


def terminal_attempt(client: SkmClient, attempt: UUID) -> bool:
    try:
        view = cast("AttemptView", client.ask(GetAttempt(attempt)))
    except NotFound:
        return False
    return view.state in _TERMINAL


def _uuid(name: str) -> UUID | None:
    try:
        value = UUID(name)
    except ValueError:
        return None
    return value if str(value) == name else None


def _directory(path: Path) -> bool:
    return path.resolve() == path.absolute() and path.is_dir()


def _entries(path: Path) -> list[Path]:
    return sorted(path.iterdir()) if _directory(path) else []


def _old_file(path: Path, cutoff: float) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISREG(info.st_mode) and info.st_mtime < cutoff


def _staged_files(root: Path, cutoff: float, *, dry_run: bool) -> Iterator[Path]:
    for path in _entries(root):
        if _uuid(path.name) is None:
            continue
        if _old_file(path, cutoff):
            if not dry_run:
                path.unlink(missing_ok=True)
            yield path
            continue
        try:
            fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except (FileNotFoundError, NotADirectoryError):
            continue
        try:
            with suppress(BlockingIOError):
                flock(fd, LOCK_EX | LOCK_NB)
                for name in sorted(os.listdir(fd)):
                    if not name.endswith(".part") or _uuid(name.removesuffix(".part")) is None:
                        continue
                    with suppress(FileNotFoundError):
                        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                        if stat.S_ISREG(info.st_mode) and info.st_mtime < cutoff:
                            if not dry_run:
                                os.unlink(name, dir_fd=fd)
                            yield path / name
        finally:
            os.close(fd)


def clean_files(
    config: BootstrapConfig,
    processes: LocalProcesses,
    client: SkmClient | None,
    *,
    log_age: timedelta | None,
    staging_age: timedelta | None,
    materialized: bool,
    dry_run: bool,
) -> dict[str, list[str]]:
    now = SystemClock().now()
    result: dict[str, list[str]] = {}
    blobs = config.blobs_root.resolve()
    if log_age is not None:
        logs = processes.logs.resolve()
        active = {f"{role}.log" for role in ("serve", "worker") if processes.lookup(role) is not None}
        result["logs"] = []
        if not (logs.is_relative_to(blobs) or blobs.is_relative_to(logs)):
            for path in _entries(processes.logs):
                if path.name not in active and _old_file(path, (now - log_age).timestamp()):
                    if not dry_run:
                        path.unlink(missing_ok=True)
                    result["logs"].append(str(path))
    if staging_age is not None:
        result["staging"] = [
            str(path)
            for path in _staged_files(
                config.blobs_root / "staging", (now - staging_age).timestamp(), dry_run=dry_run
            )
        ]
    if materialized and client is not None:
        result["materialized"] = []
        root = config.materialized_root.resolve()
        if not (root.is_relative_to(blobs) or blobs.is_relative_to(root)):
            for path in _entries(config.materialized_root):
                if (
                    (attempt := _uuid(path.name)) is not None
                    and _directory(path)
                    and terminal_attempt(client, attempt)
                ):
                    if not dry_run:
                        shutil.rmtree(path)
                    result["materialized"].append(str(path))
    return result


def _present(path: Path) -> bool:
    # A dangling symlink or an unreadable directory is uncertainty, not an absent receipt.
    if path.resolve() != path.absolute():
        raise ValueError("unexpected link in cleanup evidence")
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _containment_empty(target: Path, state: Path, attempt: AttemptView) -> bool:
    identities = state / "identities"
    if _present(identities):
        for marker in identities.iterdir():
            if (
                marker.suffix == ".json"
                and UUID(read_marker(marker)["owner"]["attempt_id"]) == attempt.attempt_id
            ):
                return False
    proc = Path("/proc")
    boot = int(
        next(line[6:] for line in (proc / "stat").read_text().splitlines() if line.startswith("btime "))
    )
    ticks = os.sysconf("SC_CLK_TCK")
    for pid in proc.iterdir():
        if not pid.name.isdecimal():
            continue
        try:
            if pid.stat().st_uid != os.geteuid():
                continue
            for link in (pid / "cwd", *(pid / "fd").iterdir()):
                with suppress(FileNotFoundError):
                    path = os.readlink(link).removesuffix(" (deleted)")
                    if Path(path).is_relative_to(target):
                        return False
        except PermissionError:
            # Non-dumpable user services can predate the attempt. A process that could have
            # been launched by it must be inspectable or we cannot establish containment.
            with suppress(FileNotFoundError, ProcessLookupError):
                fields = (pid / "stat").read_text().rsplit(")", 1)[1].split()
                if (
                    attempt.started_at is None
                    or boot + int(fields[19]) / ticks + 1 >= attempt.started_at.timestamp()
                ):
                    return False
        except (FileNotFoundError, ProcessLookupError):
            continue
    return True


def _ownership_settled(state: Path, attempt: AttemptView, steps: Mapping[str, str]) -> bool:
    # A surviving launch record must correspond to a step with a settled journal.
    # A queued reaper receipt still needs acknowledgement by the control plane.
    for directory, pending in ((state / "ownership-facts", False), (state / "recovery" / "reaped", True)):
        if not _present(directory):
            continue
        for path in directory.iterdir():
            if path.suffix != ".json":
                continue
            record = json.loads(read_metadata(path))
            facts = record["identity"] if pending else record
            owner = facts["ownership"]["owner"]
            if UUID(owner["attempt_id"]) != attempt.attempt_id:
                continue
            if (
                pending
                or owner["host_id"] != str(attempt.host_id)
                or steps.get(owner["stage_record_id"]) != owner["unit_id"]
            ):
                return False
    return True


def _evidence_settled(state: Path, attempt: AttemptView) -> bool:
    stages = {str(s["stage_record_id"]) for s in attempt.stages}
    evidence = state / "evidence" / str(attempt.attempt_id)
    steps = {str(step["stage_record_id"]): str(step["step_id"]) for step in attempt.steps}
    found = set[str]()
    for stage in evidence.iterdir() if _present(evidence) else ():
        if stage.name not in stages or not _directory(stage):
            return False
        if not any(stage.iterdir()) and stage.name not in steps:
            continue
        document = json.loads(read_metadata(stage / "journal.json"))
        if not isinstance(document, dict):
            return False
        journal = cast("JsonObject", document)
        if (
            journal.get("owner") != f"{attempt.attempt_id}/{stage.name}"
            or journal.get("stage_record_id") != stage.name
            or journal.get("reaped") is not True
            or journal.get("cancelled")
            or journal.get("step_id") != steps.get(stage.name)
        ):
            return False
        if not (stage / "raw.json").is_file() or not _present(stage / "raw.json"):
            return False
        found.add(stage.name)
    if steps.keys() - found or not _ownership_settled(state, attempt, steps):
        return False
    receipt = state / "sealed-outputs" / f"{attempt.attempt_id}.json"
    if _present(receipt) or attempt.outputs:
        sealed = json.loads(read_metadata(receipt))
        if sealed["stage"] not in stages or not any(
            o.get("seq") == sealed["seq"] and o.get("manifest") == sealed["manifest"]
            for o in attempt.to_json()["outputs"]
        ):
            return False
    return True


def _settled_effects(mount: Path, attempt: AttemptView, git: GitRunner) -> set[str]:
    common = Path(git.run(mount, ["rev-parse", "--path-format=absolute", "--git-common-dir"]).stdout.strip())
    journals = common / "skm-integration"
    if not _present(journals):
        return set()
    effects = {str(e["effect_id"]): e["state"] for e in attempt.effects}
    verified: set[str] = set()
    for folder in journals.iterdir():
        for path in folder.iterdir():
            if path.suffix != ".json":
                continue
            record = json.loads(read_metadata(path))
            if record["inputs"]["attempt_id"] != str(attempt.attempt_id):
                continue
            expected = {"succeeded": "published", "failed": "failed"}.get(str(effects.get(path.stem)))
            if not expected or record["state"] != expected or record.get("reaped") is not True:
                raise ValueError("unsettled integration journal")
            verified.add(path.stem)
    return verified


def _recovery_settled(state: Path, prepared: Prepared, attempt: AttemptView, git: GitRunner) -> bool:
    if (
        any(s.get("state") not in {"completed", "failed", "skipped"} for s in attempt.stages)
        or any(e.get("state") not in {"succeeded", "failed"} for e in attempt.effects)
        or any(r.get("outcome") not in {"retried", "new_attempt", "not_needed"} for r in attempt.recoveries)
        or any(s.get("state") not in {"succeeded", "failed", "cancelled"} for s in attempt.steps)
        or any(c.get("state") not in {"passed", "failed", "error", "cancelled"} for c in attempt.checks)
        or not _evidence_settled(state, attempt)
    ):
        return False
    if set(Path(prepared.locator).iterdir()) != set(prepared.mounts.values()):
        return False
    verified_effects: set[str] = set()
    outputs = attempt.to_json()["outputs"]
    for baseline in prepared.baseline:
        mount = prepared.mounts[baseline.mount]
        if git.run(mount, ["rev-parse", "HEAD"]).stdout.strip() != baseline.commit_sha:
            return False
        latest = baseline.commit_sha
        for output in outputs:
            ref = f"refs/skm/outputs/{attempt.attempt_id}/{output['seq']}"
            (entry,) = (m for m in output["manifest"]["mounts"] if m["mount"] == baseline.mount)
            latest = entry["head_commit"]
            if git.run(mount, ["rev-parse", "--verify", ref]).stdout.strip() != latest:
                return False
        dirty = git.run_bytes(mount, ["status", "--porcelain", "--ignored", "--untracked-files=all"]).stdout
        if dirty and (
            not outputs
            or git.run_bytes(mount, ["ls-files", "--others", "--ignored", "--exclude-standard", "-z"]).stdout
            or git.run(mount, ["diff", "--cached", "--quiet"], check=False).exit_code
            or changed_paths(git, mount, latest)
        ):
            return False
        verified_effects.update(_settled_effects(mount, attempt, git))
    return verified_effects == {str(e["effect_id"]) for e in attempt.effects}


def clean_worktrees(
    config: BootstrapConfig, client: SkmClient, values: Mapping[str, JsonValue], *, dry_run: bool
) -> object:
    root = config.worktrees_root
    blobs = config.blobs_root.resolve()
    if not _directory(root) or root.is_relative_to(blobs) or blobs.is_relative_to(root):
        return {"marked": 0, "freed_bytes": 0}
    retain = str(values.get("worker.environments.retain", "failed"))
    if retain == "always":
        return {"marked": 0, "freed_bytes": 0}
    host = cast("HostId", validate_worker_host(config).host_id)
    days = int(cast("int", values.get("worker.environments.retain_days", 0)))
    cutoff = SystemClock().now() - timedelta(days=days)
    selected: tuple[str, str] | None = None
    skipped: dict[str, str] = {}
    git = GitRunner()

    def proof(prepared: Prepared) -> CleanupProof:
        if selected != (str(prepared.environment_id), prepared.locator):
            return CleanupProof(False, False, False)
        attempt_id = UUID(Path(prepared.locator).name)
        attempt = cast("AttemptView", client.ask(GetAttempt(attempt_id)))
        terminal = (
            attempt.attempt_id == attempt_id
            and attempt.host_id == host
            and attempt.state in _TERMINAL
            and (retain != "failed" or attempt.end_reason == "ACCEPTED")
        )
        if not terminal:
            skipped[prepared.locator] = "terminal ownership unconfirmed"
            return CleanupProof(False, False, False)
        try:
            settled = _recovery_settled(config.state_dir, prepared, attempt, git)
            empty = _containment_empty(Path(prepared.locator), config.state_dir, attempt)
        except (OSError, LookupError, ValueError, TypeError, RuntimeError, StopIteration, SkmError):
            skipped[prepared.locator] = "host cleanup proof unavailable"
            return CleanupProof(terminal, False, False)
        if not settled or not empty:
            skipped[prepared.locator] = (
                "containment unconfirmed" if not empty else "recovery evidence unsettled"
            )
        return CleanupProof(terminal, empty, settled)

    manager = WorktreeManager(git, worktrees_root=root, cleanup_proof=proof)

    def skip(row: JsonObject) -> None:
        skipped.setdefault(str(row["local_locator"]), "environment binding or cleanup proof unavailable")

    def eligible(row: JsonObject) -> bool:
        nonlocal selected
        if (
            row.get("kind") != "git_worktree"
            or row.get("state") != "discarded"
            or row.get("removable") is not True
            or not isinstance(discarded := row.get("discarded_at"), str)
            or datetime.fromisoformat(discarded) > cutoff
        ):
            return False
        locator = str(row["local_locator"])
        try:
            attempt_id = UUID(str(row["attempt_id"]))
            if Path(locator) != root / str(attempt_id):
                raise ValueError("attempt locator mismatch")
            key = (str(row["environment_id"]), locator)
            selected = key
            if not dry_run and not os.path.lexists(locator):
                # A previous removal may have committed to disk before the bus mark was acknowledged.
                marker = read_marker(root / f"{attempt_id}.skm-environment.json")
                if (
                    marker["state"] == "removed"
                    and marker["environment_id"] == key[0]
                    and marker["attempt_id"] == str(attempt_id)
                    and marker["root"] == str(root)
                ):
                    return True
            prepared = manager.reopen(EnvironmentId(UUID(key[0])), locator)
            return proof(prepared).permits_removal
        except (KeyError, TypeError, ValueError, RuntimeError, OSError, SkmError):
            skip(row)
            return False

    if dry_run:
        planned = _plan_worktrees(client, host, eligible)
        return {"planned": planned, "skipped": skipped} if skipped else planned
    run = CleanEnvironmentsOperation(
        managers={"git_worktree": cast("ExecutionEnvironmentManager", manager)},
        eligible=eligible,
        on_skip=skip,
        idempotency_key=lambda _: "idem_" + uuid4().hex,
        command_factory=MarkEnvironmentsRemovedCommand.from_json,
    )
    op = HostOperationSpec(_OPERATION, run, dict, dict, frozenset({Surface.CLI}))
    host_services = HostServices(
        host, Surface.CLI, GatewayTable(entries={}, kind="host_gateway"), lambda: values, {_OPERATION: op}
    )
    result = host_services.run(_OPERATION, {"retain": retain}, client=client, cancel=CancelSource().token)
    return {**cast("JsonObject", result), "skipped": skipped} if skipped else result


def _plan_worktrees(client: SkmClient, host: HostId, eligible: Callable[[JsonObject], bool]) -> list[str]:
    paths: list[str] = []
    after = None
    while True:
        page = cast(
            "ExecutionEnvironmentsView",
            client.ask(
                ListExecutionEnvironments(host_id=host, removable_only=True, limit=PAGE_SIZE, after=after)
            ),
        )
        paths.extend(item["local_locator"] for item in page.to_json()["items"] if eligible(item))
        after = page.next_after
        if after is None:
            return paths
