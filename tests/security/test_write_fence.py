"""Write scope and checkout identity are independent, fail-closed admission fences."""

import pytest

from integration.git.conftest import environment_spec, make_repo, safe_cleanup
from skm.adapters.git.commit import GitOutputSealer
from skm.adapters.git.environments.worktree import WorktreeManager
from skm.adapters.git.scope_match import matches, normalize_pattern, outside, validate_scope
from skm.kernel.errors import SkmError


@pytest.mark.parametrize(
    ("path", "pattern", "expected"),
    [
        ("a/b.py", "a/*.py", True),
        ("a/b/c.py", "a/*.py", False),
        ("a/b/c.py", "a/**/c.py", True),
        ("a/c.py", "a/**/c.py", True),
        ("a/b", "a/", True),
        ("ab/file", "a/", False),
        ("../escape", "**", False),
        ("/absolute", "**", False),
        ("a//b", "**", False),
        ("a/./b", "**", False),
        ("name\nline", "*", True),
    ],
)
def test_segment_globbing(path, pattern, expected):
    assert matches(path, pattern) is expected


def test_scope_normalization_empty_scope_and_nonutf8_fail_closed():
    assert normalize_pattern("./a//./b/") == "a/b/"
    assert outside((b"a/ok", b"a/\xff"), ("a/**",)) == (b"a/\xff",)
    assert outside(("a",), ()) == ("a",)
    validate_scope((), read_only=True)
    with pytest.raises(ValueError, match="non-empty"):
        validate_scope(())
    for pattern in ("../x", "/x", "a/../x", "x\0", "x\\y"):
        with pytest.raises(ValueError, match="scope"):
            normalize_pattern(pattern)


def test_read_only_change_rejected_before_output_ref(tmp_path):
    root = tmp_path / "repo"
    git, base = make_repo(root)
    (root / "file.txt").write_text("unpermitted")
    sealer = GitOutputSealer(git, state_dir=tmp_path / "state")
    with pytest.raises(SkmError, match="scope"):
        sealer.seal(
            root,
            attempt_id="attempt",
            output_no=1,
            mount="main",
            repository_id=__import__("uuid").uuid4(),
            baseline=base,
            write_scope=(),
            read_only=True,
        )
    assert not git.run(root, ["for-each-ref", "refs/skm/outputs"]).stdout
    assert (root / "file.txt").read_text() == "unpermitted"


def test_repository_swap_at_same_path_blocks_reopen_and_cleanup(tmp_path):
    root = tmp_path / "repo"
    git, _ = make_repo(root)
    spec = environment_spec(tmp_path / "state", root)
    manager = WorktreeManager(git, worktrees_root=spec.root, cleanup_proof=safe_cleanup)
    env = manager.prepare(spec)
    root.rename(tmp_path / "repo-A")
    make_repo(root)
    (root / "file.txt").write_bytes(b"repo B is private")
    with pytest.raises(SkmError, match="binding"):
        manager.reopen(env.environment_id, env.locator)
    with pytest.raises(SkmError, match="binding"):
        manager.remove(env.locator)
    assert (root / "file.txt").read_bytes() == b"repo B is private"


def test_prepared_worktree_gitdir_swap_blocks_reuse(tmp_path):
    root = tmp_path / "repo"
    git, _ = make_repo(root)
    spec = environment_spec(tmp_path / "state", root)
    manager = WorktreeManager(git, worktrees_root=spec.root)
    env = manager.prepare(spec)
    pointer = env.mounts["main"] / ".git"
    pointer.write_text("gitdir: /nonexistent-owner-repo\n")
    with pytest.raises(SkmError):
        manager.reopen(env.environment_id, env.locator)
    assert pointer.read_text() == "gitdir: /nonexistent-owner-repo\n"
