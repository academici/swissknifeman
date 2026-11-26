"""Attempt-owned worktrees, durable bindings, and proof-gated cleanup."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from skm.adapters.git.host_inputs import CheckoutDescriptor, capture_checkout, read_metadata
from skm.adapters.git.runner import GitRunner, validate_repository_trust
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ids import AttemptId, RepositoryId
from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain.environment import BaselineEntry, EnvironmentKind, attempt_branch
from skm.modules.execution.domain.ids import EnvironmentId, StageRecordId
from skm.modules.execution.ports import ExecutionEnvironmentManager
from skm.platform.fs.atomic_write import atomic_write
from skm.platform.fs.file_lock import FileLock
from skm.platform.fs.safe_paths import safe_join

__all__ = ["GitWorktreeEnvironments", "git_worktree_environments"]


class GitWorktreeEnvironments(ExecutionEnvironmentManager, Protocol):
    """Binding of the environment gateway, constructed by git_worktree_environments()."""


class MountView(Protocol):
    @property
    def mount(self) -> str: ...
    @property
    def repository_id(self) -> RepositoryId: ...
    @property
    def checkout_locator(self) -> str: ...
    @property
    def baseline_ref(self) -> str: ...


class SpecView(Protocol):
    @property
    def attempt_id(self) -> AttemptId: ...
    @property
    def kind(self) -> EnvironmentKind: ...
    @property
    def mounts(self) -> tuple[MountView, ...]: ...
    @property
    def branch(self) -> str: ...
    @property
    def root(self) -> Path: ...
    @property
    def range(self) -> JsonObject | None: ...
    @property
    def review_target(self) -> object | None: ...


@dataclass(frozen=True)
class Prepared:
    environment_id: EnvironmentId
    locator: str
    mounts: Mapping[str, Path]
    baseline: tuple[BaselineEntry, ...]
    branch: str


@dataclass(frozen=True)
class Removed:
    locator: str
    freed_bytes: int


@dataclass(frozen=True)
class CleanupProof:
    terminal: bool
    containment_empty: bool
    reconciled: bool

    @property
    def permits_removal(self) -> bool:
        return self.terminal and self.containment_empty and self.reconciled


def no_cleanup(_prepared: Prepared) -> CleanupProof:
    return CleanupProof(False, False, False)


def _name(value: str) -> str:
    if not value or value in {".", ".."} or "/" in value or "\\" in value or "\0" in value:
        raise ValueError("unsafe environment path component")
    return value


class WorktreeManager:
    kind = EnvironmentKind.GIT_WORKTREE

    def __init__(
        self,
        git: GitRunner,
        *,
        worktrees_root: Path,
        cleanup_proof: Callable[[Prepared], CleanupProof] = no_cleanup,
    ) -> None:
        self.git, self.root, self.cleanup_proof = git, worktrees_root, cleanup_proof
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        validate_repository_trust(self.root)

    def _marker(self, key: str) -> Path:
        return safe_join(self.root, _name(key) + ".skm-environment.json")

    def _save(self, record: dict[str, object]) -> None:
        atomic_write(
            self._marker(str(record["key"])),
            json.dumps(record, sort_keys=True).encode(),
            mode=0o600,
            private=True,
        )

    def _load(self, key: str) -> dict[str, object]:
        marker = self._marker(key)
        info = marker.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ValueError("unsafe environment marker")
        record = cast("dict[str, object]", json.loads(read_metadata(marker)))
        if record["key"] != key or record["kind"] != self.kind.value or record["root"] != str(self.root):
            raise error_for(ErrorCode.CHECKOUT_MISMATCH, "environment marker differs from binding")
        return record

    def _items(self, record: dict[str, object]) -> list[dict[str, object]]:
        return cast("list[dict[str, object]]", record["mounts"])

    def _verify(self, record: dict[str, object]) -> None:
        validate_repository_trust(self.root)
        info = self.root.stat()
        if list(cast("list[int]", record["root_identity"])) != [info.st_dev, info.st_ino]:
            raise error_for(ErrorCode.CHECKOUT_MISMATCH, "environment root changed")
        for item in self._items(record):
            CheckoutDescriptor.from_json(cast("dict[str, object]", item["source_binding"])).verify()
            if item.get("binding") is not None:
                CheckoutDescriptor.from_json(cast("dict[str, object]", item["binding"])).verify()

    def _prepared(self, record: dict[str, object]) -> Prepared:
        return Prepared(
            EnvironmentId(UUID(str(record["environment_id"]))),
            str(record.get("directory", self.root / str(record["key"]))),
            {str(item["mount"]): Path(str(item["path"])) for item in self._items(record)},
            tuple(
                BaselineEntry(
                    str(item["mount"]),
                    RepositoryId(UUID(str(item["repository_id"]))),
                    str(item["baseline"]),
                    str(item["source_head"]),
                    None,
                )
                for item in self._items(record)
            ),
            str(record["branch"]),
        )

    def _request(self, spec: SpecView) -> list[dict[str, object]]:
        if (
            spec.kind is not self.kind
            or spec.root != self.root
            or spec.branch != attempt_branch(spec.attempt_id)
        ):
            raise ValueError("environment request differs from admitted host configuration")
        if not spec.mounts or len({m.mount for m in spec.mounts}) != len(spec.mounts):
            raise ValueError("unique environment mounts required")
        for mount in spec.mounts:
            _name(mount.mount)
        return [
            {
                "mount": m.mount,
                "repository_id": str(m.repository_id),
                "source": m.checkout_locator,
                "baseline_ref": m.baseline_ref,
            }
            for m in spec.mounts
        ]

    def prepare(self, spec: SpecView) -> Prepared:
        requested = self._request(spec)
        key = str(spec.attempt_id)
        with FileLock(self.root / f"{key}.environment.lock").hold(timeout_seconds=1):
            if self._marker(key).exists():
                record = self._load(key)
                if record["requested"] != requested or record["branch"] != spec.branch:
                    raise error_for(ErrorCode.CHECKOUT_MISMATCH, "replayed environment request changed")
                self._verify(record)
                if record["state"] != "ready":
                    raise error_for(ErrorCode.CHECKOUT_BUSY, "incomplete prepare requires reconciliation")
                return self._prepared(record)
            directory = self.root / key
            if directory.exists() or directory.is_symlink():
                raise error_for(ErrorCode.CHECKOUT_MISMATCH, "foreign attempt directory")
            items: list[dict[str, object]] = []
            for mount in spec.mounts:
                descriptor = capture_checkout(Path(mount.checkout_locator))
                items.append(
                    {
                        "mount": mount.mount,
                        "repository_id": str(mount.repository_id),
                        "source": mount.checkout_locator,
                        "source_binding": descriptor.to_json(),
                        "path": str(directory / mount.mount),
                        "baseline_ref": mount.baseline_ref,
                    }
                )
            info = self.root.stat()
            record: dict[str, object] = {
                "key": key,
                "attempt_id": key,
                "environment_id": str(uuid5(NAMESPACE_URL, str(directory))),
                "root": str(self.root),
                "root_identity": [info.st_dev, info.st_ino],
                "kind": self.kind.value,
                "branch": spec.branch,
                "state": "preparing",
                "requested": requested,
                "mounts": items,
            }
            self._save(record)
            directory.mkdir(mode=0o700)
            for item in items:
                self._prepare_mount(record, item)
                self._save(record)
            record["state"] = "ready"
            self._save(record)
            return self._prepared(record)

    def _prepare_mount(self, record: dict[str, object], item: dict[str, object]) -> None:
        self._verify(record)
        source = Path(str(item["source"]))
        if self.git.run(source, ["rev-parse", "--show-toplevel"]).stdout.strip() != str(source):
            raise error_for(ErrorCode.CHECKOUT_MISMATCH, "source is not the authorized checkout root")
        base = self.git.run(
            source, ["rev-parse", "--verify", str(item["baseline_ref"]) + "^{commit}"]
        ).stdout.strip()
        branch = str(record["branch"]) + "/" + str(item["mount"])
        self.git.run(source, ["worktree", "add", "-b", branch, str(item["path"]), base])
        item.update(
            {
                "baseline": base,
                "source_head": base,
                "owned_branch": branch,
                "binding": capture_checkout(Path(str(item["path"]))).to_json(),
            }
        )

    def _key(self, locator: str) -> str:
        path = Path(locator)
        if path.parent == self.root:
            return _name(path.name)
        if len(path.parents) > 2 and path.parent.parent == self.root / "_recheck":
            key = "recheck-" + _name(path.name)
            record = self._load(key)
            if record.get("directory") == locator:
                return key
        raise error_for(ErrorCode.CHECKOUT_MISMATCH, "locator outside managed root")

    def reopen(self, environment_id: EnvironmentId, locator: str) -> Prepared:
        record = self._load(self._key(locator))
        self._verify(record)
        if record["environment_id"] != str(environment_id) or record["state"] != "ready":
            raise error_for(ErrorCode.CHECKOUT_BUSY, "environment unavailable")
        return self._prepared(record)

    def _recheck_repository(self, item: dict[str, object], commit: str) -> Path:
        del commit
        return Path(str(item["path"]))

    def prepare_recheck(
        self, environment_id: EnvironmentId, *, stage_record_id: StageRecordId, commit_shas: Mapping[str, str]
    ) -> Prepared:
        originals = [
            self._load(p.name.removesuffix(".skm-environment.json"))
            for p in self.root.glob("*.skm-environment.json")
        ]
        original = next((r for r in originals if r["environment_id"] == str(environment_id)), None)
        if original is None:
            raise ValueError("unknown parent environment")
        self._verify(original)
        items = self._items(original)
        if set(commit_shas) != {str(i["mount"]) for i in items}:
            raise ValueError("recheck requires an exact commit for every mount")
        if any(re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", sha) is None for sha in commit_shas.values()):
            raise ValueError("recheck commits must be exact object IDs")
        key = "recheck-" + str(stage_record_id)
        directory = self.root / "_recheck" / str(original["attempt_id"]) / str(stage_record_id)
        with FileLock(self.root / f"{key}.environment.lock").hold(timeout_seconds=1):
            if self._marker(key).exists():
                record = self._load(key)
                if record.get("commits") != dict(commit_shas):
                    raise error_for(ErrorCode.CHECKOUT_MISMATCH, "recheck commits changed")
                return self.reopen(EnvironmentId(UUID(str(record["environment_id"]))), str(directory))
            if directory.exists() or directory.is_symlink():
                raise error_for(ErrorCode.CHECKOUT_MISMATCH, "foreign recheck directory")
            rechecks: list[dict[str, object]] = []
            record = {
                **original,
                "key": key,
                "environment_id": str(uuid5(environment_id, key)),
                "parent_environment_id": str(environment_id),
                "commits": dict(commit_shas),
                "directory": str(directory),
                "state": "preparing",
                "mounts": rechecks,
            }
            self._save(record)
            validate_repository_trust(directory, allow_missing=True)
            directory.mkdir(mode=0o700, parents=True)
            for source in items:
                self._verify(original)
                mount = str(source["mount"])
                repo = self._recheck_repository(source, commit_shas[mount])
                base = self.git.run(
                    repo, ["rev-parse", "--verify", commit_shas[mount] + "^{commit}"]
                ).stdout.strip()
                path = directory / mount
                rechecks.append(
                    {
                        "mount": mount,
                        "repository_id": source["repository_id"],
                        "source": str(repo),
                        "source_binding": capture_checkout(repo).to_json(),
                        "path": str(path),
                        "baseline": base,
                        "source_head": base,
                        "owned_branch": None,
                    }
                )
                self._save(record)
                self.git.run(repo, ["worktree", "add", "--detach", str(path), base])
                rechecks[-1]["binding"] = capture_checkout(path).to_json()
                self._save(record)
            record["state"] = "ready"
            self._save(record)
            return self._prepared(record)

    def discard(self, prepared: Prepared, *, retain: bool) -> None:
        record = self._load(self._key(prepared.locator))
        self._verify(record)
        if record["environment_id"] != str(prepared.environment_id):
            raise error_for(ErrorCode.CHECKOUT_MISMATCH, "wrong environment identity")
        if not retain:
            self.remove(prepared.locator)

    def _remove_mount(self, item: dict[str, object]) -> None:
        source, target = Path(str(item["source"])), Path(str(item["path"]))
        self.git.run(source, ["worktree", "remove", "--force", str(target)])
        if item.get("owned_branch"):
            self.git.run(source, ["branch", "-D", str(item["owned_branch"])])

    def remove(self, locator: str) -> Removed:
        target = Path(locator)
        key = self._key(locator)
        with FileLock(self.root / f"{key}.environment.lock").hold(timeout_seconds=1):
            record = self._load(key)
            if record["state"] == "removed":
                if target.exists() or target.is_symlink():
                    raise error_for(ErrorCode.CHECKOUT_MISMATCH, "removed locator was replaced")
                return Removed(locator, 0)
            self._verify(record)
            if record["state"] != "ready" or not self.cleanup_proof(self._prepared(record)).permits_removal:
                raise error_for(
                    ErrorCode.CHECKOUT_BUSY, "terminal/reap/reconciliation proof required for cleanup"
                )
            freed = sum(p.lstat().st_size for p in target.rglob("*") if p.is_file() and not p.is_symlink())
            for item in self._items(record):
                self._verify(record)
                self._remove_mount(item)
                item["binding"] = None
                self._save(record)
            target.rmdir()
            record["state"] = "removed"
            self._save(record)
            return Removed(locator, freed)

    def disk_free_bytes(self, root: Path) -> int:
        return shutil.disk_usage(root).free


def git_worktree_environments(
    git: GitRunner, *, worktrees_root: Path, cleanup_proof: Callable[[Prepared], CleanupProof] = no_cleanup
) -> ExecutionEnvironmentManager:
    return cast(
        "ExecutionEnvironmentManager",
        WorktreeManager(git, worktrees_root=worktrees_root, cleanup_proof=cleanup_proof),
    )
