"""Temporary-index snapshots and immutable, create-only output refs (G16-G25/G38-G43)."""

from __future__ import annotations

import hashlib
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ids import RepositoryId
from skm.modules.execution.domain.output import DiffStats, OutputManifest, OutputMount
from skm.modules.execution.generated.settings import WorkerGitSettings
from skm.modules.execution.ports import Vcs

from .fingerprint import object_format, output_digest, snapshot_entries, verify_entries
from .host_inputs import CheckoutDescriptor
from .output_writer import PreSealSnapshot
from .runner import GitRunner
from .scope_match import matches, outside, validate_scope
from .status import changed_paths, decode_path, tree_entries

__all__ = ["author_env", "git_output_sealer", "git_vcs", "snapshot_commit"]


def author_env(settings: WorkerGitSettings | None) -> dict[str, str]:
    """Author and committer environment of a worker commit; ``None`` uses the schema defaults."""
    fields = cast("tuple[tuple[Any, ...], ...]", vars(WorkerGitSettings)["_FIELDS"])
    defaults = {field[0]: field[4] for field in fields}
    selected = settings if settings is not None else WorkerGitSettings.from_json(defaults)
    return {
        "GIT_AUTHOR_NAME": selected.author_name,
        "GIT_AUTHOR_EMAIL": selected.author_email,
        "GIT_COMMITTER_NAME": selected.author_name,
        "GIT_COMMITTER_EMAIL": selected.author_email,
        "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+00:00",
        "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+00:00",
    }


@dataclass(frozen=True)
class ExcludeRules:
    patterns: tuple[str, ...] = (".skm/**", ".skm-dev/**")
    runtime_artifacts: tuple[str, ...] = ()
    sandbox_stubs: tuple[str, ...] = ()

    def excludes(self, path: bytes) -> bool:
        try:
            value = path.decode("utf-8")
        except UnicodeDecodeError:
            return any(
                matches(
                    path.decode("latin1"),
                    pattern.removeprefix(":(exclude,glob)").encode("utf-8").decode("latin1"),
                )
                for pattern in (*self.patterns, *self.runtime_artifacts, *self.sandbox_stubs)
            )
        return any(
            matches(value, pattern.removeprefix(":(exclude,glob)"))
            for pattern in (*self.patterns, *self.runtime_artifacts, *self.sandbox_stubs)
        )


@dataclass(frozen=True)
class SnapshotCommit:
    commit: str
    tree: str
    parent: str
    patch: bytes


_DEFAULT_EXCLUDE = ExcludeRules()


def _ref(git: GitRunner, root: Path, name: str) -> str | None:
    result = git.run(root, ["rev-parse", "--verify", "--quiet", name], check=False)
    return result.stdout.strip() if result.exit_code == 0 else None


def snapshot_commit(  # noqa: PLR0913 - complete raw snapshot and pre-publication guard
    git: GitRunner,
    root: Path,
    base: str,
    *,
    state_dir: Path,
    message: str,
    ref: str | None = None,
    exclude: ExcludeRules = _DEFAULT_EXCLUDE,
    binding: CheckoutDescriptor | None = None,
    validate: Callable[[SnapshotCommit], None] | None = None,
    author: WorkerGitSettings | None = None,
) -> SnapshotCommit:
    if binding is not None:
        binding.verify()
    if state_dir == root or state_dir.is_relative_to(root):
        raise ValueError("snapshot index must be outside the checkout")
    guard, entries = snapshot_entries(git, root)
    seed = tree_entries(git, root, base)
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="index-", dir=state_dir) as temporary:
        env = {"GIT_INDEX_FILE": str(Path(temporary) / "index"), **author_env(author)}
        git.run_bytes(root, ["read-tree", base], env=env)
        updates: list[bytes] = []
        size = 40 if object_format(git, root) == "sha1" else 64
        for path in sorted(seed.keys() | entries.keys()):
            if exclude.excludes(path):
                continue
            fingerprint = entries.get(path, "absent")
            header = ("0 " + "0" * size) if fingerprint == "absent" else fingerprint
            updates.append(header.encode("ascii") + b"\t" + path + b"\0")
        if updates:
            git.run_bytes(root, ["update-index", "-z", "--index-info"], env=env, stdin=b"".join(updates))
        tree = git.run_bytes(root, ["write-tree"], env=env).stdout.strip().decode("ascii")
        patch = git.run_bytes(
            root,
            ["diff", "--cached", "--binary", "--full-index", "--no-ext-diff", "--no-textconv", base],
            env=env,
        ).stdout
        verify_entries(git, root, guard, entries)
        if binding is not None:
            binding.verify()
        base_tree = git.run(root, ["rev-parse", f"{base}^{{tree}}"]).stdout.strip()
        commit = (
            base
            if base_tree == tree
            else git.run_bytes(
                root, ["commit-tree", tree, "-p", base], env=env, stdin=message.encode("utf-8")
            )
            .stdout.strip()
            .decode("ascii")
        )
        snapshot = SnapshotCommit(commit, tree, base, patch)
        if validate is not None:
            validate(snapshot)
        if ref is not None:
            current = _ref(git, root, ref)
            if current is not None and current != commit:
                raise error_for(
                    ErrorCode.CHECKOUT_BUSY, "owned immutable ref already names a different snapshot"
                )
            if current is None:
                git.run_bytes(root, ["update-ref", ref, commit, "0" * size])
        return snapshot


class GitOutputSealer:
    def __init__(self, git: GitRunner, *, state_dir: Path, author: WorkerGitSettings | None = None) -> None:
        self.git, self.state_dir, self.author = git, state_dir, author

    def seal(  # noqa: PLR0913 - complete output identity and fence
        self,
        root: Path,
        *,
        attempt_id: str,
        output_no: int,
        mount: str,
        repository_id: RepositoryId,
        baseline: str,
        write_scope: Sequence[str],
        previous: str | None = None,
        read_only: bool = False,
        exclude: ExcludeRules = _DEFAULT_EXCLUDE,
        binding: CheckoutDescriptor | None = None,
        writer: PreSealSnapshot | None = None,
    ) -> OutputManifest:
        if writer is not None:
            if (str(writer.attempt_id), writer.output_no, writer.mount, writer.checkout.root) != (
                attempt_id,
                output_no,
                mount,
                str(root),
            ) or (binding is not None and binding != writer.checkout):
                raise ValueError("pre-seal writer differs from the requested output or checkout")
            binding = writer.checkout
        validate_scope(write_scope, read_only=read_only)
        if output_no < 1 or "/" in attempt_id or not attempt_id:
            raise ValueError("invalid output identity")
        if binding is not None:
            binding.verify()
        # Fence before creating any immutable output ref; exclusions preserve their baseline bytes.
        live = changed_paths(self.git, root, baseline, mount=mount)
        violations = [
            p
            for p in live
            if not exclude.excludes(decode_path(p.path_bytes))
            and outside((decode_path(p.path_bytes),), write_scope)
        ]
        if violations:
            raise error_for(
                ErrorCode.WRITE_SCOPE_VIOLATION, "output changes paths outside declared_write_scope"
            )
        parent = previous or baseline

        def validate(snapshot: SnapshotCommit) -> None:
            sealed = changed_paths(self.git, root, baseline, head=snapshot.commit, mount=mount)
            if any(exclude.excludes(decode_path(p.path_bytes)) for p in sealed):
                raise ValueError("excluded runtime path entered sealed delta")
            if any(outside((decode_path(p.path_bytes),), write_scope) for p in sealed):
                raise error_for(ErrorCode.WRITE_SCOPE_VIOLATION, "sealed scope changed during snapshot")

        snap = snapshot_commit(
            self.git,
            root,
            parent,
            state_dir=self.state_dir,
            message=(
                f"skm: attempt {attempt_id} output {output_no}\n\n"
                f"SKM-Attempt: {attempt_id}\nSKM-Output-No: {output_no}\n"
            ),
            ref=f"refs/skm/outputs/{attempt_id}/{output_no}" if writer is None else None,
            exclude=exclude,
            binding=binding,
            validate=validate,
            author=self.author,
        )
        if writer is not None:
            writer.write(self.git, snap.commit)
        changed = changed_paths(self.git, root, baseline, head=snap.commit, mount=mount)
        excluded = tuple(p for p in live if exclude.excludes(decode_path(p.path_bytes)))
        identities = (
            OutputMount(
                mount, repository_id, object_format(self.git, root), baseline, snap.commit, snap.tree
            ),
        )
        raw = self.git.run_bytes(
            root,
            [
                "diff",
                "--numstat",
                "-z",
                "--no-renames",
                "--no-ext-diff",
                "--no-textconv",
                baseline,
                snap.commit,
            ],
        ).stdout
        insertions = deletions = 0
        for row in raw.split(b"\0"):
            if row:
                plus, minus, _ = row.split(b"\t", 2)
                insertions += int(plus) if plus != b"-" else 0
                deletions += int(minus) if minus != b"-" else 0
        return OutputManifest(
            "skm-output-v2",
            identities,
            changed,
            output_digest(identities, changed),
            (),
            excluded,
            None,
            DiffStats(len(changed), insertions, deletions),
            not changed,
        )

    def patch(self, root: Path, manifest: OutputManifest) -> bytes:
        if len(manifest.mounts) != 1:
            raise ValueError("patch requires the exact mount repository")
        mount = manifest.mounts[0]
        return self.git.run_bytes(
            root,
            [
                "format-patch",
                "--stdout",
                "--binary",
                "--full-index",
                "--no-ext-diff",
                "--no-textconv",
                f"{mount.base_commit}..{mount.head_commit}",
            ],
            timeout_s=600,
        ).stdout


def git_output_sealer(
    git: GitRunner, *, state_dir: Path, author: WorkerGitSettings | None = None
) -> GitOutputSealer:
    return GitOutputSealer(git, state_dir=state_dir, author=author)


class _GitVcs:
    def __init__(self, git: GitRunner, state_dir: Path) -> None:
        self.git, self.state_dir = git, state_dir

    def head(self, worktree: Path) -> str:
        return self.git.run(worktree, ["rev-parse", "--verify", "HEAD"]).stdout.strip()

    def changed_paths(self, worktree: Path, base: str):
        return changed_paths(self.git, worktree, base)

    def range_changed_paths(self, repo: Path, base: str, head: str):
        return changed_paths(self.git, repo, base, head=head)

    def commit_all(
        self, worktree: Path, message: str, trailers: Mapping[str, str], exclude: Sequence[str]
    ) -> str:
        return self.squash_commit(worktree, self.head(worktree), message, trailers, exclude)

    def squash_commit(
        self, worktree: Path, base: str, message: str, trailers: Mapping[str, str], exclude: Sequence[str]
    ) -> str:
        if any("\n" in k or "\n" in v for k, v in trailers.items()):
            raise ValueError("invalid commit trailers")
        text = message + "\n\n" + "\n".join(f"{k}: {v}" for k, v in trailers.items()) + "\n"
        return snapshot_commit(
            self.git,
            worktree,
            base,
            state_dir=self.state_dir,
            message=text,
            exclude=ExcludeRules(tuple(exclude)),
        ).commit

    def diff(self, worktree: Path, base: str, paths: Sequence[str] | None = None) -> bytes:
        snapshot = snapshot_commit(
            self.git, worktree, base, state_dir=self.state_dir, message="skm: raw diff\n"
        )
        args = [
            "--literal-pathspecs",
            "diff",
            "--binary",
            "--full-index",
            "--no-ext-diff",
            "--no-textconv",
            base,
            snapshot.commit,
        ]
        if paths is not None:
            args.extend(["--", *paths])
        return self.git.run_bytes(worktree, args).stdout

    def dirty_patch(self, worktree: Path) -> bytes:
        return self.diff(worktree, self.head(worktree))

    def tree_file_digests(self, repo: Path, commit: str) -> Mapping[str, str]:

        from .status import display_path

        return {
            display_path(p): "sha256:"
            + hashlib.sha256(
                self.git.run_bytes(repo, ["cat-file", "blob", fp.split(" ")[1]]).stdout
            ).hexdigest()
            for p, fp in tree_entries(self.git, repo, commit).items()
        }

    def update_ref(self, repo: Path, ref: str, new: str, expected_old: str) -> bool:
        if not ref.startswith("refs/skm/"):
            raise ValueError("only owned refs may be updated by the snapshot adapter")
        return self.git.run(repo, ["update-ref", ref, new, expected_old], check=False).exit_code == 0


def git_vcs(git: GitRunner, *, state_dir: Path) -> Vcs:
    return cast("Vcs", _GitVcs(git, state_dir))
