"""Fail-closed, identity-bound linked-worktree operations for Artifex slices."""
from __future__ import annotations

import fcntl
import os
import re
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


_IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_MAX_OUTPUT = 256 * 1024
_GIT_ENV = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LANG": "C"}


class WorktreeRefusal(ValueError):
    """A named refusal that leaves the target and any foreign worktree untouched."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason, self.detail = reason, detail


@dataclass(frozen=True)
class WorktreeIdentity:
    run_id: str
    slice_id: str
    attempt: int

    def __post_init__(self) -> None:
        if not all(_IDENTITY.fullmatch(value) for value in (self.run_id, self.slice_id)) or self.attempt < 1:
            raise WorktreeRefusal("WORKTREE_IDENTITY_INVALID")

    @property
    def reason(self) -> str:
        return f"artifex:{self.run_id}:{self.slice_id}:{self.attempt}"


@dataclass(frozen=True)
class LinkedWorktree:
    path: Path
    base: str
    identity: WorktreeIdentity
    files: tuple[str, ...]


def _path(value: str | Path) -> Path:
    return Path(value).resolve(strict=False)


def _relative_files(files: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    if not files or len(set(files)) != len(files):
        raise WorktreeRefusal("WORKTREE_SCOPE_INVALID", "files")
    result = []
    for value in files:
        candidate = Path(value)
        if (not isinstance(value, str) or not value or candidate.is_absolute() or ".." in candidate.parts
                or candidate.as_posix() in {".", ""}):
            raise WorktreeRefusal("WORKTREE_SCOPE_INVALID", str(value))
        result.append(candidate.as_posix())
    return tuple(sorted(result))


class WorktreeManager:
    """Runs only explicit Git argv in controlled repositories and owned paths."""

    def __init__(self, repository: str | Path) -> None:
        self.repository = _path(repository)
        if not self.repository.is_dir() or not (self.repository / ".git").exists():
            raise WorktreeRefusal("WORKTREE_REPOSITORY_INVALID", str(self.repository))

    def _git(self, cwd: Path, *argv: str, input: bytes | None = None) -> bytes:
        env = dict(_GIT_ENV)
        result = subprocess.run(
            ["git", *argv], cwd=str(cwd), input=input, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, shell=False, check=False,
        )
        if len(result.stdout) + len(result.stderr) > _MAX_OUTPUT:
            raise WorktreeRefusal("GIT_OUTPUT_LIMIT")
        if result.returncode:
            detail = result.stderr.decode("utf-8", "replace").strip()
            raise WorktreeRefusal("GIT_COMMAND_FAILED", detail or " ".join(argv))
        return result.stdout

    def _git_text(self, cwd: Path, *argv: str) -> str:
        return self._git(cwd, *argv).decode("utf-8", "strict").strip()

    def _head(self, root: Path) -> str:
        return self._git_text(root, "rev-parse", "HEAD")

    def _clean(self, root: Path) -> bool:
        return self._git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all") == b""

    def inventory(self) -> list[dict[str, str | bool]]:
        """Parse only documented porcelain-z records, never human Git output."""
        records = self._git(self.repository, "worktree", "list", "--porcelain", "-z").split(b"\0")
        rows: list[dict[str, str | bool]] = []
        current: dict[str, str | bool] = {}
        for raw in records:
            if not raw:
                if current:
                    if "worktree" not in current or "HEAD" not in current:
                        raise WorktreeRefusal("WORKTREE_INVENTORY_INVALID")
                    rows.append(current)
                    current = {}
                continue
            text = raw.decode("utf-8", "strict")
            key, _, value = text.partition(" ")
            if key == "worktree":
                if current:
                    raise WorktreeRefusal("WORKTREE_INVENTORY_INVALID")
                current["worktree"] = value
            elif key in {"HEAD", "branch", "locked", "prunable"}:
                if key == "locked":
                    current[key] = value if value else True
                else:
                    current[key] = value
            elif key == "detached":
                current[key] = True
            else:
                raise WorktreeRefusal("WORKTREE_INVENTORY_INVALID", key)
        if current:
            raise WorktreeRefusal("WORKTREE_INVENTORY_INVALID")
        return rows

    def _row(self, path: Path) -> dict[str, str | bool]:
        target = str(path.resolve(strict=False))
        rows = [row for row in self.inventory() if row["worktree"] == target]
        if len(rows) != 1:
            raise WorktreeRefusal("WORKTREE_OWNERSHIP_MISMATCH", target)
        return rows[0]

    def create(self, *, root: str | Path, identity: WorktreeIdentity, base: str,
               files: list[str] | tuple[str, ...]) -> LinkedWorktree:
        """Create a new detached, locked worktree below one explicit empty root."""
        owned_root = _path(root)
        scope = _relative_files(files)
        if not base or not _IDENTITY.fullmatch(base.replace("/", "-")):
            raise WorktreeRefusal("WORKTREE_BASE_INVALID", base)
        if owned_root.exists() and not owned_root.is_dir():
            raise WorktreeRefusal("WORKTREE_ROOT_INVALID", str(owned_root))
        owned_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        attempt_path = owned_root / identity.run_id / identity.slice_id / str(identity.attempt)
        if attempt_path.exists():
            raise WorktreeRefusal("WORKTREE_PATH_OCCUPIED", str(attempt_path))
        attempt_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        resolved_parent = attempt_path.parent.resolve(strict=True)
        if owned_root.resolve(strict=True) not in (resolved_parent, *resolved_parent.parents):
            raise WorktreeRefusal("WORKTREE_PATH_EXTERNAL", str(attempt_path))
        self._git(self.repository, "rev-parse", "--verify", f"{base}^{{commit}}")
        self._git(self.repository, "worktree", "add", "--detach", "--lock", "--reason", identity.reason,
                  "--", str(attempt_path), base)
        row = self._row(attempt_path)
        if row.get("HEAD") != self._git_text(attempt_path, "rev-parse", "HEAD") or not row.get("detached"):
            raise WorktreeRefusal("WORKTREE_CREATE_INVALID")
        if row.get("locked") != identity.reason:
            raise WorktreeRefusal("WORKTREE_OWNERSHIP_MISMATCH", "lock reason")
        if not self._clean(attempt_path):
            raise WorktreeRefusal("WORKTREE_DIRTY", str(attempt_path))
        return LinkedWorktree(attempt_path, self._head(attempt_path), identity, scope)

    def _require_owned(self, attempt: LinkedWorktree) -> None:
        row = self._row(attempt.path)
        if row.get("locked") != attempt.identity.reason or row.get("HEAD") != self._head(attempt.path):
            raise WorktreeRefusal("WORKTREE_OWNERSHIP_MISMATCH")
        if row.get("branch") or not row.get("detached"):
            raise WorktreeRefusal("WORKTREE_REF_UNSAFE")

    def delta(self, attempt: LinkedWorktree) -> tuple[str, ...]:
        """Return every changed tracked or untracked path; reject submodule drift."""
        self._require_owned(attempt)
        names = self._git(attempt.path, "diff", "--name-only", "-z", attempt.base, "--").split(b"\0")
        changed = {name.decode("utf-8", "strict") for name in names if name}
        status = self._git(attempt.path, "status", "--porcelain=v1", "-z", "--untracked-files=all").split(b"\0")
        index = 0
        while index < len(status):
            item = status[index]
            index += 1
            if not item:
                continue
            if len(item) < 4:
                raise WorktreeRefusal("WORKTREE_STATUS_INVALID")
            code, name = item[:2], item[3:].decode("utf-8", "strict")
            changed.add(name)
            if code[:1] in {b"R", b"C"} or code[1:] in {b"R", b"C"}:
                if index >= len(status) or not status[index]:
                    raise WorktreeRefusal("WORKTREE_STATUS_INVALID")
                changed.add(status[index].decode("utf-8", "strict"))
                index += 1
        submodules = self._git(attempt.path, "submodule", "status", "--recursive")
        if any(line[:1] in {b"+", b"-", b"U"} for line in submodules.splitlines()):
            raise WorktreeRefusal("WORKTREE_SUBMODULE_CHANGED")
        outside = sorted(path for path in changed if path not in attempt.files)
        if outside:
            raise WorktreeRefusal("WORKTREE_SCOPE_VIOLATION", ",".join(outside))
        return tuple(sorted(changed))

    def commit(self, attempt: LinkedWorktree) -> str:
        """Commit an already validated exact-scope attempt with a deterministic identity."""
        changed = self.delta(attempt)
        if not changed:
            raise WorktreeRefusal("WORKTREE_DELTA_EMPTY")
        if self._head(attempt.path) != attempt.base:
            raise WorktreeRefusal("WORKTREE_BASE_DRIFT")
        self._git(attempt.path, "add", "--", *changed)
        self._git(attempt.path, "-c", "user.name=Artifex", "-c", "user.email=artifex@local.invalid",
                  "commit", "--no-gpg-sign", "-m", f"artifex: worktree attempt {attempt.identity.reason}")
        commit = self._head(attempt.path)
        parent = self._git_text(attempt.path, "rev-parse", f"{commit}^")
        if parent != attempt.base:
            raise WorktreeRefusal("WORKTREE_COMMIT_INVALID")
        return commit

    @contextmanager
    def _integration_lock(self, target: Path) -> Iterator[None]:
        git_dir = Path(self._git_text(target, "rev-parse", "--git-dir"))
        if not git_dir.is_absolute():
            git_dir = (target / git_dir).resolve(strict=True)
        lock_path = git_dir / "artifex-integration.lock"
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass

    def integrate(self, attempt: LinkedWorktree, commit: str, *, target: str | Path) -> str:
        """Serially cherry-pick a checked attempt into an exact clean controlled target."""
        self._require_owned(attempt)
        target_path = _path(target)
        if target_path != self.repository or not self._clean(target_path):
            raise WorktreeRefusal("INTEGRATION_TARGET_DIRTY")
        if self._head(target_path) != attempt.base:
            raise WorktreeRefusal("INTEGRATION_BASE_DRIFT")
        self._git(attempt.path, "rev-parse", "--verify", f"{commit}^{{commit}}")
        preimage = self._head(target_path)
        with self._integration_lock(target_path):
            if not self._clean(target_path) or self._head(target_path) != preimage:
                raise WorktreeRefusal("INTEGRATION_TARGET_CHANGED")
            try:
                self._git(target_path, "cherry-pick", "--no-edit", commit)
            except WorktreeRefusal as exc:
                try:
                    self._git(target_path, "cherry-pick", "--abort")
                except WorktreeRefusal as abort_exc:
                    # A subprocess can fail before Git starts the pick.  Its only safe
                    # equivalent to an abort is the exact original clean preimage.
                    if self._head(target_path) != preimage or not self._clean(target_path):
                        raise WorktreeRefusal("INTEGRATION_ABORT_FAILED", abort_exc.detail) from exc
                if self._head(target_path) != preimage or not self._clean(target_path):
                    raise WorktreeRefusal("INTEGRATION_PREIMAGE_MISMATCH") from exc
                raise WorktreeRefusal("INTEGRATION_CONFLICT_ROLLED_BACK", exc.detail) from exc
        if not self._clean(target_path):
            raise WorktreeRefusal("INTEGRATION_POSTIMAGE_DIRTY")
        return self._head(target_path)

    def remove(self, attempt: LinkedWorktree) -> None:
        """Remove only a clean, still identity-locked linked worktree without force/prune."""
        self._require_owned(attempt)
        if not self._clean(attempt.path):
            raise WorktreeRefusal("WORKTREE_DIRTY", str(attempt.path))
        self._git(self.repository, "worktree", "unlock", "--", str(attempt.path))
        self._git(self.repository, "worktree", "remove", "--", str(attempt.path))
        if any(row["worktree"] == str(attempt.path) for row in self.inventory()):
            raise WorktreeRefusal("WORKTREE_REMOVE_INCOMPLETE")
