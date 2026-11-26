"""Private hook cache, audit spool and local Git facts; never evaluates shell payloads."""

from __future__ import annotations

import fcntl
import json
import os
import stat
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast, override
from uuid import UUID

if TYPE_CHECKING:
    from skm.modules.policy.domain.operations import PathOrigin

    from .runner import GitRunner

__all__ = ["LocalHookState"]


class HookCheckoutError(ValueError):
    """The checkout cannot serve hooks; ``detail`` is a stable, value-free code a denial may show."""

    def __init__(self, message: str, detail: str) -> None:
        super().__init__(message)
        self.detail = detail


def _is_git_worktree_root(root: Path) -> bool:
    dot_git = root / ".git"
    try:
        st = os.lstat(dot_git)
    except OSError:
        return False
    if stat.S_ISDIR(st.st_mode):
        gitdir = dot_git
    elif stat.S_ISREG(st.st_mode):
        try:
            text = dot_git.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            return False
        if not text.startswith("gitdir:"):
            return False
        target = Path(text[len("gitdir:") :].strip())
        gitdir = target if target.is_absolute() else (root / target)
    else:
        return False
    try:
        return stat.S_ISREG(os.lstat(gitdir / "HEAD").st_mode)
    except OSError:
        return False


def _checkout_git(root: str) -> GitRunner:
    from .runner import GitRunner

    return GitRunner(checkout_root=Path(root).resolve(strict=True))


def _default_home() -> str:
    # Path.home() reads the process HOME (the same source the shell uses for ~).
    home = str(Path.home())
    if os.path.isabs(home):
        return home
    import pwd

    return pwd.getpwuid(os.geteuid()).pw_dir


class LocalHookState:
    def __init__(
        self,
        state_dir: Path,
        query_factory: Callable[[str, dict[str, Any]], object],
        *,
        instance_id: UUID | None = None,
        home: str | None = None,
    ) -> None:
        self.folder = state_dir / "hooks"
        self._query_factory = query_factory
        self._instance_id = instance_id
        # The agent's shell expands ``~`` from the same HOME this hook process inherited.
        self.home = str(Path(home if home is not None else _default_home()).resolve())

    def query(self, name: str, payload: dict[str, Any]) -> object:
        return self._query_factory(name, payload)

    def _private_dir(self) -> None:
        self.folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.folder.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ValueError("unsafe hook state directory")

    def _path(self, project: str, target: str) -> Path:
        UUID(project)
        if not target.isidentifier():
            raise ValueError("unsafe cache key")
        return self.folder / f"{project}-{target}.json"

    def _read_cached(
        self, project: str, target: str, max_age: int | None = None
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        self._private_dir()
        try:
            fd = os.open(self._path(project, target), os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "r") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o077:
                    return None
                raw = stream.read(1_048_577)
            if len(raw.encode()) > 1_048_576:
                return None
            cached = json.loads(raw)
            raw_policy = cached["policy"]
            if not isinstance(raw_policy, dict):
                return None
            typed_policy = cast("dict[str, Any]", raw_policy)
            if set(typed_policy) != {
                "hook_modes",
                "permissions",
                "reserved_paths",
                "managed_file_paths",
                "changelog",
                "subscriptions",
                "generation",
                "ttl_seconds",
            }:
                return None
            policy = dict(typed_policy)
            generation, ttl_val = policy["generation"], policy["ttl_seconds"]
            if isinstance(generation, bool) or not isinstance(generation, int):
                return None
            if isinstance(ttl_val, bool) or not isinstance(ttl_val, int):
                return None
            age = time.time() - cached["received_at"]
            ttl = ttl_val if max_age is None else min(max_age, ttl_val)
            if 0 <= age < ttl and cached["generation"] == generation:
                return cached, policy
        except (OSError, ValueError, TypeError, KeyError):
            pass
        return None

    def load(self, project: str, target: str, max_age: int | None = None) -> dict[str, Any] | None:
        loaded = self._read_cached(project, target, max_age=max_age)
        return None if loaded is None else loaded[1]

    def load_with_snapshot(
        self, project: str, target: str, max_age: int | None = None
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        loaded = self._read_cached(project, target, max_age=max_age)
        if loaded is None:
            return None, None
        cached, policy = loaded
        context = cached.get("context")
        return policy, cast("dict[str, Any]", context) if isinstance(context, dict) else None

    def save(self, project: str, target: str, policy: dict[str, Any]) -> None:
        from skm.modules.integrations.generated.views import hook_policy_view_from_json
        from skm.platform.fs.atomic_write import atomic_write

        self._private_dir()
        validated = dict(hook_policy_view_from_json(policy))
        document = {"received_at": time.time(), "generation": validated["generation"], "policy": validated}
        atomic_write(self._path(project, target), json.dumps(document).encode(), private=True)

    def remember(self, project: str, target: str, context: dict[str, Any]) -> None:
        from skm.platform.fs.atomic_write import atomic_write

        loaded = self._read_cached(project, target)
        if loaded is None:
            return
        cached, _ = loaded
        merged = {**cached.get("context", {}), **context}
        if cached.get("context") == merged:
            return
        cached["context"] = merged
        atomic_write(self._path(project, target), json.dumps(cached).encode(), private=True)

    def snapshot(self, project: str, target: str) -> dict[str, Any] | None:
        _, context = self.load_with_snapshot(project, target)
        return context

    def call(self, action: Callable[[], Any], timeout_ms: int) -> Any:
        from queue import Empty, Queue
        from threading import Thread

        result: Queue[tuple[bool, Any]] = Queue(maxsize=1)

        def invoke() -> None:
            try:
                result.put((True, action()))
            except Exception as exc:  # noqa: BLE001 - forward the exception without its text
                result.put((False, exc))

        Thread(target=invoke, daemon=True).start()
        try:
            ok, value = result.get(timeout=timeout_ms / 1000)
        except Empty:
            raise TimeoutError("hook backend timeout") from None
        if not ok:
            raise value
        return value

    def checkout(self, root: str, cwd: str, project: str, binding: str, repository: str, mount: str) -> None:
        from skm.adapters.git._checkout_marker import read_marker_at
        from skm.adapters.git.runner import validate_repository_trust

        cwd_path = Path(cwd)
        if not cwd_path.is_absolute() or "\0" in cwd:
            raise ValueError("invalid cwd")
        real = Path(root).resolve(strict=True)
        validate_repository_trust(cwd_path, checkout_root=real)
        if not _is_git_worktree_root(real):
            raise HookCheckoutError("foreign repository", "checkout_foreign")
        marker = read_marker_at(real, checkout_root=real)
        if marker is None:
            raise HookCheckoutError("checkout marker missing", "checkout_marker_missing")
        if (
            (self._instance_id is not None and marker.instance_id != self._instance_id)
            or str(marker.project_id) != project
            or str(marker.repository_id) != repository
            or marker.mount_name.value != mount
        ):
            raise HookCheckoutError("checkout marker mismatch", "checkout_marker_mismatch")
        # The binding is resolved by the control plane, never trusted from payload.
        UUID(binding)

    def resolve(self, path: str, cwd: str) -> str:
        if "\0" in path:
            raise ValueError("invalid path")
        # Expand ``~`` like the shell would; ``~user``, ``~+`` and ``~-`` stay opaque in the shell parser.
        if path == "~" or path.startswith("~/"):
            path = self.home + path[1:]
        return str((Path(cwd) / path).resolve())

    def facts(self, root: str) -> Any:
        from skm.modules.policy.domain.operations import PathOrigin, StaticPathFacts

        del root
        owner = self

        class Facts(StaticPathFacts):
            @override
            def resolve(self, path: str, cwd: str) -> str:
                return owner.resolve(path, cwd)

            @override
            def origins(self, path: str) -> frozenset[PathOrigin]:
                del path
                # Interactive calls do not receive task-created provenance.
                return frozenset({PathOrigin.TRACKED, PathOrigin.FOREIGN_UNTRACKED, PathOrigin.IGNORED})

        return Facts(home=owner.home)

    def staged(self, root: str, mount: str, repository: str) -> tuple[str, tuple[str, ...]]:
        from skm.kernel.ids import RepositoryId
        from skm.modules.execution.domain.output import OutputMount

        from .fingerprint import object_format, output_digest
        from .repo_inspect import GitRepositoryInspector
        from .status import changed_paths

        git = _checkout_git(root)
        tree = git.run(root, ["write-tree"]).stdout.strip()
        head = GitRepositoryInspector(git).resolve_commit(root, "HEAD")
        paths = changed_paths(git, Path(root), head, head=tree, mount=mount)
        identity = OutputMount(
            mount, RepositoryId(UUID(repository)), object_format(git, Path(root)), head, head, tree
        )
        return output_digest((identity,), paths), tuple(path.path for path in paths)

    def review_digest(self, root: str, mount: str, repository: str, base: str, head: str) -> str:
        """Use the reviewed output's immutable commit metadata with the current index tree."""
        from skm.kernel.ids import RepositoryId
        from skm.modules.execution.domain.output import OutputMount

        from .fingerprint import object_format, output_digest
        from .status import changed_paths

        git = _checkout_git(root)
        tree = git.run(root, ["write-tree"]).stdout.strip()
        paths = changed_paths(git, Path(root), base, head=tree, mount=mount)
        identity = OutputMount(
            mount, RepositoryId(UUID(repository)), object_format(git, Path(root)), base, head, tree
        )
        return output_digest((identity,), paths)

    def commit_text(self, command: str, cwd: str, root: str) -> str:
        from skm.modules.integrations.domain.hook_rules import commit_message
        from skm.modules.policy.domain.git_guard import split_globals
        from skm.modules.policy.domain.shell_words import parse

        from .host_inputs import GitCheckoutReader

        parsed = parse(command)
        _, _, args = split_globals(parsed.commands[0].argv[1:])
        messages = [commit_message(command) or ""]
        remaining = iter(args)
        for arg in remaining:
            filename = None
            if arg in {"-F", "--file"}:
                filename = next(remaining, "")
            elif arg.startswith("--file="):
                filename = arg.partition("=")[2]
            elif arg.startswith("-F"):
                filename = arg[2:]
            if filename is None:
                continue
            if not filename or filename == "-":
                raise ValueError("commit message stdin cannot be inspected")
            path = Path(cwd) / filename
            relative = path.absolute().relative_to(Path(root).resolve()).as_posix()
            result = GitCheckoutReader({"main": root}).read(
                "main", relative, max_bytes=65_536, follow_symlinks=False
            )
            if result.status != "ok" or result.data is None:
                raise ValueError("commit message file is not safely readable")
            messages.append(result.data.decode("utf-8"))
        return "\n".join(messages).strip()

    def observe(self, project: str, surface: str, kind: str, session: str | None) -> None:
        """Persist metadata only; commands, prompts, transcripts and provider secrets are excluded."""
        from skm.platform.system_clock import SystemClock

        UUID(project)
        self._private_dir()
        path = self.folder / "observations.jsonl"
        record = {
            "project_id": project,
            "surface": surface,
            "kind": kind,
            "session_bound": session is not None,
            "at": SystemClock().now().isoformat(),
        }
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "ab") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o077:
                raise ValueError("unsafe hook observation file")
            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.write(json.dumps(record).encode() + b"\n")
            stream.flush()
            os.fsync(stream.fileno())

    def verify_commit(self, command: str, cwd: str, root: str) -> None:
        """The inspected index must be exactly the index this command will commit."""
        from skm.modules.policy.domain.git_guard import split_globals
        from skm.modules.policy.domain.shell_words import parse

        parsed = parse(command)
        if not parsed.supported or len(parsed.commands) != 1:
            raise ValueError("cannot prove staged tree for a composite command")
        simple = parsed.commands[0]
        config, subcommand, args = split_globals(simple.argv[1:])
        if simple.head != "git" or subcommand != "commit" or config or simple.depth:
            raise ValueError("cannot prove staged tree for an indirect commit")
        if any(item.startswith("GIT_") for item in simple.assignments):
            raise ValueError("Git environment changes index identity")
        location = cwd
        for change in simple.chdirs:
            location = self.resolve(change.value, location)
        globals_ = iter(simple.argv[1:])
        for word in globals_:
            if word == "commit":
                break
            if word == "-C":
                location = self.resolve(next(globals_, ""), location)
            elif word.startswith("-C"):
                location = self.resolve(word[2:], location)
            else:
                raise ValueError("Git global option changes checkout identity")
        toplevel = _checkout_git(root).run(location, ("rev-parse", "--show-toplevel")).stdout.rstrip("\r\n")
        if toplevel != self.resolve(root, cwd):
            raise ValueError("commit targets another checkout")
        _verify_index_args(args)

    def _audit_fd(self) -> int:
        self._private_dir()
        fd = os.open(self.folder / "audit.jsonl", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o077:
            os.close(fd)
            raise ValueError("unsafe hook audit file")
        return fd

    def audit(self, project: str, surface: str, reason: str) -> None:
        from skm.platform.system_clock import SystemClock

        UUID(project)
        record = {
            "scope_id": project,
            "key": "hook_" + os.urandom(16).hex(),
            "records": [
                {
                    "at": SystemClock().now().isoformat(),
                    "tool": "hook",
                    "call_summary": surface,
                    "outcome": "deny",
                    "code": "operation_denied",
                    "rule": reason,
                    "operation": None,
                    "source": "hook",
                }
            ],
        }
        with os.fdopen(self._audit_fd(), "r+b") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.seek(0, 2)
            stream.write(json.dumps(record).encode() + b"\n")
            stream.flush()
            os.fsync(stream.fileno())

    def flush(self, client: Any) -> None:
        from skm.modules.policy.generated.commands import RecordToolDecisions

        with os.fdopen(self._audit_fd(), "r+b") as stream:
            # An audit drain must never wait behind another hook process.
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            lines = stream.readlines()
            fcntl.flock(stream, fcntl.LOCK_UN)
            completed: set[str] = set()
            for line in lines[:200]:
                item = json.loads(line)
                command = RecordToolDecisions.from_json(
                    {"scope_id": item["scope_id"], "records": item["records"]}
                )
                client.dispatch(command, idempotency_key=item["key"])
                completed.add(item["key"])
            # Backend IO holds no file lock. Preserve decisions appended during delivery.
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            stream.seek(0)
            remaining = [line for line in stream.readlines() if json.loads(line)["key"] not in completed]
            stream.seek(0)
            stream.writelines(remaining)
            stream.truncate()
            stream.flush()
            os.fsync(stream.fileno())


def _verify_index_args(args: list[str]) -> None:
    value_options = {
        "-m",
        "--message",
        "-F",
        "--file",
        "-C",
        "--reuse-message",
        "-c",
        "--reedit-message",
        "--author",
        "--date",
        "--trailer",
        "--fixup",
        "--squash",
    }
    changes_index = {"--all", "--include", "--only", "--interactive", "--patch", "--pathspec-from-file"}
    remaining = iter(args)
    for word in remaining:
        if word in value_options:
            next(remaining, None)
        elif word.startswith("--"):
            option = word.partition("=")[0]
            if option != "--" and any(name.startswith(option) for name in changes_index):
                raise ValueError("commit would change the inspected index")
        elif word.startswith("-"):
            flags = word[1:]
            for value_flag in ("m", "F", "C", "c"):
                flags = flags.partition(value_flag)[0]
            if set(flags) & {"a", "i", "o", "p"}:
                raise ValueError("commit would change the inspected index")
        else:
            raise ValueError("path-limited commit differs from the inspected index")
