"""Controlled clones with durable local integration tips, including unpublished objects."""

from __future__ import annotations

import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast, override
from urllib.parse import urlsplit

from skm.adapters.git.host_inputs import capture_checkout
from skm.adapters.git.runner import GitRunner, validate_repository_trust
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.modules.execution.domain.environment import EnvironmentKind
from skm.modules.execution.ports import ExecutionEnvironmentManager
from skm.platform.fs.file_lock import FileLock

from .worktree import CleanupProof, Prepared, SpecView, WorktreeManager, no_cleanup

__all__ = ["managed_clone_environments"]


@dataclass(frozen=True)
class CloneSource:
    canonical_remote: str
    integration_repository: Path
    integration_branch: str
    initial_branch: str


class ManagedCloneEnvironments(WorktreeManager):
    kind = EnvironmentKind.MANAGED_CLONE

    def __init__(
        self,
        git: GitRunner,
        *,
        worktrees_root: Path,
        sources: Mapping[str, CloneSource],
        enabled: bool,
        clone_depth: int = 50,
        allow_file_remote: bool = False,
        cleanup_proof: Callable[[Prepared], CleanupProof] = no_cleanup,
    ) -> None:
        super().__init__(git, worktrees_root=worktrees_root, cleanup_proof=cleanup_proof)
        if not enabled or clone_depth < 0:
            raise error_for(ErrorCode.CAPABILITY_UNAVAILABLE, "managed_clone must be explicitly enabled")
        self.sources, self.depth, self.allow_file = dict(sources), clone_depth, allow_file_remote

    def _transport(self, remote: str) -> str:
        parsed = urlsplit(remote)
        if parsed.username or parsed.password or remote.startswith("-") or "\0" in remote:
            raise ValueError("canonical remote must not contain credentials or options")
        if parsed.scheme == "https":
            return "https"
        if self.allow_file and (parsed.scheme == "file" or Path(remote).is_absolute()):
            return "file"
        raise error_for(ErrorCode.REPOSITORY_UNSAFE, "remote transport is not approved by host policy")

    def _bootstrap(self, source: CloneSource) -> None:
        protocol = self._transport(source.canonical_remote)
        repo = source.integration_repository
        validate_repository_trust(repo.parent, allow_missing=True)
        repo.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with FileLock(repo.parent / (repo.name + ".bootstrap.lock")).hold(timeout_seconds=1):
            if repo.exists():
                capture_checkout(repo)
                return
            args = [
                "-c",
                f"protocol.{protocol}.allow=always",
                "clone",
                "--no-tags",
                "--single-branch",
                "--branch",
                source.initial_branch,
            ]
            if self.depth:
                args.extend(["--depth", str(self.depth)])
            self.git.run(repo.parent, [*args, "--", source.canonical_remote, str(repo)], timeout_s=600)
            # This checkout is owned by SKM; canonical targets must never be checked out by a writer.
            self.git.run(repo, ["checkout", "--detach"])
            if source.integration_branch != source.initial_branch:
                base = self.git.run(repo, ["rev-parse", "HEAD"]).stdout.strip()
                self.git.run(
                    repo, ["update-ref", "refs/heads/" + source.integration_branch, base, "0" * len(base)]
                )

    def history_tips(self, repository_id: str) -> dict[str, str | None]:
        source = self.sources[repository_id]
        repo = source.integration_repository

        def tip(ref: str) -> str | None:
            result = self.git.run(repo, ["rev-parse", "--verify", "--quiet", ref], check=False)
            return result.stdout.strip() if result.exit_code == 0 else None

        return {
            "remote_tip": tip("refs/remotes/origin/" + source.initial_branch),
            "local_integration_tip": tip("refs/heads/" + source.integration_branch),
            "last_pushed_tip": tip("refs/skm/last-pushed/" + source.integration_branch),
        }

    def fetch_remote(self, repository_id: str) -> dict[str, str | None]:
        source = self.sources[repository_id]
        protocol = self._transport(source.canonical_remote)
        self.git.run(
            source.integration_repository,
            [
                "-c",
                f"protocol.{protocol}.allow=always",
                "fetch",
                "--no-tags",
                "--",
                source.canonical_remote,
                "+refs/heads/" + source.initial_branch + ":refs/remotes/origin/" + source.initial_branch,
            ],
        )
        tips = self.history_tips(repository_id)
        remote, local = tips["remote_tip"], tips["local_integration_tip"]
        if (
            remote
            and local
            and self.git.run(
                source.integration_repository, ["merge-base", "--is-ancestor", remote, local], check=False
            ).exit_code
        ):
            raise error_for(
                ErrorCode.OUTCOME_UNKNOWN, "remote advance requires writer CAS/deepen/reconciliation"
            )
        return tips

    @override
    def prepare(self, spec: SpecView) -> Prepared:
        # Existing markers must verify the old bindings before any remote operation.
        if self._marker(str(spec.attempt_id)).exists():
            return super().prepare(spec)
        for mount in spec.mounts:
            source = self.sources.get(str(mount.repository_id))
            if source is None or mount.checkout_locator != str(source.integration_repository):
                raise error_for(
                    ErrorCode.CHECKOUT_MISMATCH, "managed clone lacks the pinned integration repository"
                )
            self._bootstrap(source)
        return super().prepare(spec)

    @override
    def _prepare_mount(self, record: dict[str, object], item: dict[str, object]) -> None:
        self._verify(record)
        source = self.sources[str(item["repository_id"])]
        repo, target = source.integration_repository, Path(str(item["path"]))
        base = self.git.run(
            repo, ["rev-parse", "--verify", "refs/heads/" + source.integration_branch + "^{commit}"]
        ).stdout.strip()
        protocol = self._transport(source.canonical_remote)
        args = [
            "-c",
            f"protocol.{protocol}.allow=always",
            "clone",
            "--no-tags",
            "--single-branch",
            "--branch",
            source.initial_branch,
        ]
        if self.depth:
            args.extend(["--depth", str(self.depth)])
        self.git.run(target.parent, [*args, "--", source.canonical_remote, str(target)], timeout_s=600)
        self._verify(record)
        # Object import is from the pinned host repository, never a reset to the observed remote tip.
        self.git.run(
            target,
            ["-c", "protocol.file.allow=always", "fetch", "--no-tags", "--", str(repo), base],
            timeout_s=600,
        )
        branch = str(record["branch"]) + "/" + str(item["mount"])
        self.git.run(target, ["checkout", "-b", branch, base])
        item.update(
            {
                **self.history_tips(str(item["repository_id"])),
                "baseline": base,
                "source_head": base,
                "owned_branch": branch,
                "binding": capture_checkout(target).to_json(),
            }
        )

    @override
    def _recheck_repository(self, item: dict[str, object], commit: str) -> Path:
        repo = Path(str(item["path"]))
        source = self.sources[str(item["repository_id"])].integration_repository
        self.git.run(
            repo, ["-c", "protocol.file.allow=always", "fetch", "--no-tags", "--", str(source), commit]
        )
        return repo

    @override
    def _remove_mount(self, item: dict[str, object]) -> None:
        if item.get("owned_branch") is None:
            super()._remove_mount(item)
            return
        target = Path(str(item["path"]))
        if target.parent.parent != self.root:
            raise error_for(ErrorCode.CHECKOUT_MISMATCH, "attempt clone outside owned root")
        shutil.rmtree(target)


def managed_clone_environments(
    git: GitRunner,
    *,
    worktrees_root: Path,
    sources: Mapping[str, CloneSource],
    enabled: bool,
    clone_depth: int = 50,
    allow_file_remote: bool = False,
    cleanup_proof: Callable[[Prepared], CleanupProof] = no_cleanup,
) -> ExecutionEnvironmentManager:
    return cast(
        "ExecutionEnvironmentManager",
        ManagedCloneEnvironments(
            git,
            worktrees_root=worktrees_root,
            sources=sources,
            enabled=enabled,
            clone_depth=clone_depth,
            allow_file_remote=allow_file_remote,
            cleanup_proof=cleanup_proof,
        ),
    )
