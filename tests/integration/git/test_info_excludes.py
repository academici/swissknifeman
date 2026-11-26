"""Exercise the exclude and index boundaries against local Git repositories."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest

from skm.adapters.git import excludes
from skm.adapters.git.excludes import GitInfoExcludes
from skm.adapters.git.runner import GitRunner
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, PreconditionFailed, ValidationFailed
from skm.modules.integrations.domain.conflict_names import conflict_path
from support.git_repo import GitRepoFixture, init_git_repo


@pytest.fixture
def repo(tmp_path: Path) -> GitRepoFixture:
    return init_git_repo(tmp_path / "repository")


def test_updates_only_the_managed_block_and_matches_literal_paths(repo: GitRepoFixture) -> None:
    exclude = repo.path / ".git/info/exclude"
    user = b"# user\r\n/user-only\r\n/foreign\xff"
    exclude.write_bytes(user)
    adapter = GitInfoExcludes(repo.runner)
    checkout = str(repo.path)
    source = "nested/[x]* guide.md"
    conflict = conflict_path(source, suffix=".reconcile")
    assert adapter.update(
        checkout, add=(".skm", ".skm-dev", conflict), conflict_sources=(source,), conflict_suffix=".reconcile"
    )
    first = exclude.read_bytes()
    assert first.endswith(user)
    assert not adapter.update(
        checkout, add=(conflict, ".skm", ".skm-dev"), conflict_sources=(source,), conflict_suffix=".reconcile"
    )
    assert exclude.read_bytes() == first

    ignored = (".skm/project.json", ".skm-dev/state", conflict, "user-only")
    for path in ignored:
        assert repo.runner.run(repo.path, ("check-ignore", "--", path), check=False).exit_code == 0
    visible = ("x/.skm/project.json", ".skm-settings", "nested/xabc guide.md.reconcile", "other.reconcile")
    for path in visible:
        assert repo.runner.run(repo.path, ("check-ignore", "--", path), check=False).exit_code == 1

    assert adapter.update(
        checkout, remove=(conflict,), conflict_sources=(source,), conflict_suffix=".reconcile"
    )
    assert not adapter.update(
        checkout, remove=(conflict,), conflict_sources=(source,), conflict_suffix=".reconcile"
    )
    assert adapter.update(checkout, remove=(".skm", ".skm-dev"))
    assert exclude.read_bytes() == user


@pytest.mark.parametrize(
    ("path", "sources", "suffix"),
    [
        ("README.md", (), ".skm-new"),
        ("README.md.skm-new", (), ".skm-new"),
        ("elsewhere.md.skm-new", ("README.md",), ".skm-new"),
        ("*.skm-new", (), ".skm-new"),
        ("/.skm", (), ".skm-new"),
        (".skm/../README.md", (), ".skm-new"),
        ("../README.md.skm-new", ("../README.md",), ".skm-new"),
        (".git/config.skm-new", (".git/config",), ".skm-new"),
        ("file\npattern.skm-new", ("file\npattern",), ".skm-new"),
        ("file/escape", ("file",), "/escape"),
    ],
)
def test_rejects_unlisted_and_unsafe_paths(
    repo: GitRepoFixture, path: str, sources: tuple[str, ...], suffix: str
) -> None:
    exclude = repo.path / ".git/info/exclude"
    user = exclude.read_bytes()
    adapter = GitInfoExcludes(repo.runner)
    for add, remove in (((path,), ()), ((), (path,))):
        with pytest.raises(ValidationFailed) as rejected:
            adapter.update(
                str(repo.path), add=add, remove=remove, conflict_sources=sources, conflict_suffix=suffix
            )
        assert rejected.value.code is ErrorCode.INTEGRATION_UNSAFE_TARGET
        assert exclude.read_bytes() == user


def test_linked_worktrees_update_the_same_block(repo: GitRepoFixture, tmp_path: Path) -> None:
    repo.commit_file()
    worktree = repo.add_worktree(tmp_path / "linked", "linked")
    adapter = GitInfoExcludes(repo.runner)
    assert adapter.update(str(repo.path), add=(".skm",))
    assert not adapter.update(str(worktree), add=(".skm",))
    assert adapter.update(str(worktree), add=(".skm-dev",))
    assert adapter.update(str(worktree), add=(".codegraph/",))
    assert not adapter.update(str(repo.path), add=(".codegraph/",))
    content = (repo.path / ".git/info/exclude").read_bytes()
    assert b"/.skm\n" in content
    assert b"/.skm-dev\n" in content
    assert b"/.codegraph/\n" in content
    for checkout in (worktree, repo.path):
        assert repo.runner.run(checkout, ("check-ignore", "--", ".codegraph/codegraph.db")).exit_code == 0
        for outside in (".codegraph", "nested/.codegraph/codegraph.db"):
            assert repo.runner.run(checkout, ("check-ignore", "--", outside), check=False).exit_code == 1


def test_writes_excludes_in_a_repository_initialized_without_templates(tmp_path: Path) -> None:
    runner = GitRunner()
    runner.run(tmp_path, ("init", "--template="))
    exclude = tmp_path / ".git/info/exclude"
    adapter = GitInfoExcludes(runner)
    assert not adapter.update(str(tmp_path), remove=(".skm",))
    assert not exclude.parent.exists()
    assert adapter.update(str(tmp_path), add=(".skm",))
    assert b"/.skm\n" in exclude.read_bytes()


def test_concurrent_writers_respect_the_lock(repo: GitRepoFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    started, release = Event(), Event()
    merge = excludes._merge

    def hold(before: bytes, add: set[bytes], remove: set[bytes]) -> bytes:
        started.set()
        assert release.wait(5)
        return merge(before, add, remove)

    monkeypatch.setattr(excludes, "_merge", hold)
    adapter = GitInfoExcludes(repo.runner)
    checkout = str(repo.path)
    exclude = repo.path / ".git/info/exclude"
    original = exclude.read_bytes()
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(adapter.update, checkout, add=(".skm",))
        try:
            assert started.wait(5)
            with pytest.raises(Conflict, match="locked") as rejected:
                adapter.update(checkout, add=(".skm-dev",))
            assert rejected.value.code is ErrorCode.VERSION_CONFLICT
            assert exclude.read_bytes() == original
        finally:
            release.set()
        assert first.result(timeout=5)
    assert adapter.update(checkout, add=(".skm-dev",))
    result = exclude.read_bytes()
    assert b"/.skm\n" in result
    assert b"/.skm-dev\n" in result
    assert not exclude.with_name("exclude.lock").exists()


def test_cas_preserves_edits_by_a_writer_without_the_lock(
    repo: GitRepoFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    exclude = repo.path / ".git/info/exclude"
    merge = excludes._merge

    def edit(before: bytes, add: set[bytes], remove: set[bytes]) -> bytes:
        exclude.write_bytes(b"user-edited\n")
        return merge(before, add, remove)

    monkeypatch.setattr(excludes, "_merge", edit)
    with pytest.raises(Conflict, match="changed during update"):
        GitInfoExcludes(repo.runner).update(str(repo.path), add=(".skm",))
    assert exclude.read_bytes() == b"user-edited\n"
    assert not exclude.with_name("exclude.lock").exists()


def test_unsafe_exclude_symlink_and_malformed_block_are_preserved(
    repo: GitRepoFixture, tmp_path: Path
) -> None:
    exclude = repo.path / ".git/info/exclude"
    outside = tmp_path / "outside"
    outside.write_bytes(b"private\n")
    exclude.unlink()
    exclude.symlink_to(outside)
    adapter = GitInfoExcludes(repo.runner)
    with pytest.raises(ValidationFailed) as rejected:
        adapter.update(str(repo.path), add=(".skm",))
    assert rejected.value.code is ErrorCode.REPOSITORY_UNSAFE
    assert exclude.is_symlink()
    assert outside.read_bytes() == b"private\n"

    exclude.unlink()
    malformed = b"user-entry\n# BEGIN SKM MANAGED EXCLUDES\n"
    exclude.write_bytes(malformed)
    with pytest.raises(Conflict, match="malformed"):
        adapter.update(str(repo.path), add=(".skm",))
    assert exclude.read_bytes() == malformed


def test_untracks_only_service_paths_and_leaves_worktree_contents(repo: GitRepoFixture) -> None:
    project = ".skm/project.json"
    private = ".skm-dev/[local]* state"
    foreign = "nested/.skm/project.json"
    for path in (project, private, foreign, "foreign.skm-new", ".skm-config"):
        repo.commit_file(path)
    (repo.path / project).write_bytes(b"local edits")
    adapter = GitInfoExcludes(repo.runner)
    checkout = str(repo.path)

    with pytest.raises(PreconditionFailed) as tracked:
        adapter.require_untracked(checkout)
    assert tracked.value.code is ErrorCode.TRACKED_SERVICE_FILE
    assert tracked.value.details["paths"] == [private, project]

    assert adapter.untrack_service_files(checkout) == (private, project)
    assert (repo.path / project).read_bytes() == b"local edits"
    assert (repo.path / private).read_bytes() == b"initial\n"
    assert repo.runner.run(repo.path, ("ls-files",)).stdout.splitlines() == [
        ".skm-config",
        "foreign.skm-new",
        foreign,
    ]
    assert adapter.untrack_service_files(checkout) == ()
    adapter.require_untracked(checkout)


def test_untrack_refuses_to_discard_divergent_staged_bytes(repo: GitRepoFixture) -> None:
    path = ".skm/project.json"
    repo.commit_file(path)
    file = repo.path / path
    file.write_bytes(b"staged content")
    repo.runner.run(repo.path, ("add", "--", path))
    file.write_bytes(b"worktree content")
    with pytest.raises(PreconditionFailed) as rejected:
        GitInfoExcludes(repo.runner).untrack_service_files(str(repo.path))
    assert rejected.value.code is ErrorCode.TRACKED_SERVICE_FILE
    assert repo.runner.run_bytes(repo.path, ("show", ":" + path)).stdout == b"staged content"
    assert file.read_bytes() == b"worktree content"
