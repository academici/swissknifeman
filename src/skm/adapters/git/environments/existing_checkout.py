"""Interactive exclusive checkout: preserve user HEAD/index/bytes and persist synthetic B."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast, override

from skm.adapters.git.commit import ExcludeRules, snapshot_commit
from skm.adapters.git.fingerprint import checkout_guard
from skm.adapters.git.host_inputs import CheckoutDescriptor
from skm.adapters.git.runner import GitRunner
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.modules.execution.domain.environment import EnvironmentKind
from skm.modules.execution.domain.ids import EnvironmentId
from skm.modules.execution.ports import ExecutionEnvironmentManager
from skm.platform.fs.atomic_write import atomic_write
from skm.platform.fs.file_lock import FileLock

from .worktree import CleanupProof, Prepared, Removed, SpecView, WorktreeManager, no_cleanup

__all__ = ["existing_checkout_environments"]


class ExistingCheckoutEnvironments(WorktreeManager):
    kind = EnvironmentKind.EXISTING_CHECKOUT

    def __init__(
        self,
        git: GitRunner,
        *,
        worktrees_root: Path,
        exclusive: Callable[[Path], bool],
        interactive: bool,
        cleanup_proof: Callable[[Prepared], CleanupProof] = no_cleanup,
    ) -> None:
        super().__init__(git, worktrees_root=worktrees_root, cleanup_proof=cleanup_proof)
        self.exclusive, self.interactive = exclusive, interactive
        self._locks: dict[str, list[FileLock]] = {}
        (self.root / "_locks").mkdir(mode=0o700, exist_ok=True)

    def _acquire(self, spec: SpecView) -> None:
        self._acquire_paths(str(spec.attempt_id), tuple(Path(m.checkout_locator) for m in spec.mounts))

    def _acquire_paths(self, key: str, paths: tuple[Path, ...]) -> None:
        if not self.interactive:
            raise error_for(
                ErrorCode.CHECKOUT_BUSY, "existing_checkout requires interactive exclusive ownership"
            )
        if key in self._locks:
            return
        acquired: list[FileLock] = []
        try:
            for path in sorted(paths):
                if not self.exclusive(path):
                    raise error_for(ErrorCode.CHECKOUT_BUSY, "external checkout exclusivity is unproven")
                slug = hashlib.sha256(str(path).encode()).hexdigest()[:16]
                lock = FileLock(self.root / "_locks" / f"checkout-{slug}.lock")
                try:
                    acquired_lock = lock.acquire()
                except RuntimeError as error:
                    raise error_for(ErrorCode.CHECKOUT_BUSY, "checkout already in use") from error
                if not acquired_lock:
                    raise error_for(ErrorCode.CHECKOUT_BUSY, "checkout already in use")
                acquired.append(lock)
        except BaseException:
            for lock in reversed(acquired):
                lock.release()
            raise
        self._locks[key] = acquired

    @override
    def prepare(self, spec: SpecView) -> Prepared:
        self._request(spec)
        self._acquire(spec)
        try:
            return super().prepare(spec)
        except BaseException:
            self.release_locks(str(spec.attempt_id))
            raise

    def release_locks(self, key: str) -> None:
        for lock in reversed(self._locks.pop(key, [])):
            lock.release()

    @override
    def reopen(self, environment_id: EnvironmentId, locator: str) -> Prepared:
        record = self._load(self._key(locator))
        self._verify(record)
        if not record.get("parent_environment_id"):
            self._acquire_paths(
                str(record["attempt_id"]), tuple(Path(str(i["source"])) for i in self._items(record))
            )
        return super().reopen(environment_id, locator)

    @override
    def _verify(self, record: dict[str, object]) -> None:
        super()._verify(record)
        if record.get("parent_environment_id"):
            return
        if not self.interactive:
            raise error_for(ErrorCode.CHECKOUT_BUSY, "interactive exclusivity required")
        for item in self._items(record):
            path = Path(str(item["source"]))
            if not self.exclusive(path):
                raise error_for(ErrorCode.CHECKOUT_BUSY, "checkout exclusivity lost")
            if "user_head" in item:
                current = checkout_guard(self.git, path)
                index_digest = hashlib.sha256(current.index or b"").hexdigest()
                if current.head.decode().strip() != item["user_head"] or index_digest != item["user_index"]:
                    raise error_for(ErrorCode.CHECKOUT_BUSY, "user HEAD or index changed since preparation")

    @override
    def _prepare_mount(self, record: dict[str, object], item: dict[str, object]) -> None:
        self._verify(record)
        root = Path(str(item["source"]))
        guard = checkout_guard(self.git, root)
        head = guard.head.decode("ascii").strip()
        snap = snapshot_commit(
            self.git,
            root,
            head,
            state_dir=self.root / "_snapshots",
            message=f"skm: initial checkout snapshot {record['attempt_id']}\n",
            ref=f"refs/skm/baselines/{record['attempt_id']}/{item['mount']}",
            exclude=ExcludeRules(),
            binding=CheckoutDescriptor.from_json(cast("dict[str, object]", item["source_binding"])),
        )
        guard.verify(self.git)
        patch = self.root / str(record["key"]) / (str(item["mount"]) + ".dirty.patch")
        if snap.patch:
            atomic_write(patch, snap.patch, mode=0o600, private=True)
        item.update(
            {
                "path": str(root),
                "baseline": snap.commit,
                "source_head": head,
                "binding": item["source_binding"],
                "owned_branch": None,
                "user_head": head,
                "user_index": hashlib.sha256(guard.index or b"").hexdigest(),
                "dirty_patch": str(patch) if snap.patch else None,
            }
        )

    @override
    def _prepared(self, record: dict[str, object]) -> Prepared:
        prepared = super()._prepared(record)
        return replace(prepared, mounts={str(i["mount"]): Path(str(i["path"])) for i in self._items(record)})

    def dirty_patches(self, prepared: Prepared) -> tuple[tuple[str, Path], ...]:
        record = self._load(Path(prepared.locator).name)
        self._verify(record)
        return tuple(
            (str(i["mount"]), Path(str(i["dirty_patch"])))
            for i in self._items(record)
            if i.get("dirty_patch")
        )

    @override
    def _remove_mount(self, item: dict[str, object]) -> None:
        # Rechecks are owned detached worktrees; the interactive checkout itself is never deleted.
        if str(item["path"]) != str(item["source"]):
            super()._remove_mount(item)

    @override
    def remove(self, locator: str) -> Removed:
        key = self._key(locator)
        record = self._load(key)
        if record.get("parent_environment_id"):
            return super().remove(locator)
        self._verify(record)
        if record["state"] == "removed":
            return Removed(locator, 0)
        if not self.cleanup_proof(self._prepared(record)).permits_removal:
            raise error_for(ErrorCode.CHECKOUT_BUSY, "checkout is busy until confirmed reap/reconciliation")
        # Keep the baseline refs, dirty patches and reconcile bytes. Only release the busy marker/lock.
        record["state"] = "removed"
        self._save(record)
        self.release_locks(key)
        return Removed(locator, 0)


def existing_checkout_environments(
    git: GitRunner,
    *,
    worktrees_root: Path,
    exclusive: Callable[[Path], bool],
    interactive: bool,
    cleanup_proof: Callable[[Prepared], CleanupProof] = no_cleanup,
) -> ExecutionEnvironmentManager:
    return cast(
        "ExecutionEnvironmentManager",
        ExistingCheckoutEnvironments(
            git,
            worktrees_root=worktrees_root,
            exclusive=exclusive,
            interactive=interactive,
            cleanup_proof=cleanup_proof,
        ),
    )
