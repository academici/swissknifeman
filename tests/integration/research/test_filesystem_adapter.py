"""Local research uses git visibility, content bounds and no-follow descriptors."""

import os

import pytest

from skm.adapters.research.command import ProcessSession
from skm.adapters.research.filesystem import FilesystemResearchSource
from skm.adapters.research.retry import SourceFailed
from skm.kernel.cancel import CancelSource

from ._support import config, query


def git(root, *argv):
    session = ProcessSession(
        ("git", "-C", str(root), *argv),
        {"PATH": os.defpath, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"},
        CancelSource().token,
        10,
    )
    try:
        return session.exchange(b"")
    finally:
        session.close()


@pytest.fixture
def tree(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/guide.md").write_text("research architecture\nmore research\npassword=veryprivatevalue")
    (tmp_path / "docs/weak.md").write_text("architecture only")
    (tmp_path / ".env").write_text("research hidden")
    (tmp_path / ".gitignore").write_text("ignored.md\n")
    (tmp_path / "ignored.md").write_text("research ignored")
    (tmp_path / "oversized.md").write_bytes(b"research" + b"x" * 1_000_000)
    (tmp_path / "binary.md").write_bytes(b"research\0bytes")
    (tmp_path / "link.md").symlink_to(tmp_path / "docs/guide.md")
    return tmp_path


def test_filesystem_scores_visible_files_and_filters_secrets_ignored_binary_large_symlinks(tree):
    adapter = FilesystemResearchSource()
    result = adapter.search(
        config(kind="filesystem", roots=["repo:."]),
        query("research architecture", mounts={"repo": str(tree)}),
        cancel=CancelSource().token,
    )
    assert [doc.origin for doc in result.documents] == ["repo:repo/docs/guide.md", "repo:repo/docs/weak.md"]
    assert result.documents[0].locator == {"line_from": 1, "line_to": 2}
    redacted = adapter.search(
        config(kind="filesystem", roots=["repo:docs"]),
        query("password", mounts={"repo": str(tree)}),
        cancel=CancelSource().token,
    )
    assert "veryprivatevalue" not in (redacted.documents[0].text or "")


def test_filesystem_absolute_roots_require_host_allowlist_and_stay_external(tree):
    cfg = config(kind="filesystem", roots=[str(tree / "docs")])
    with pytest.raises(SourceFailed):
        FilesystemResearchSource().search(cfg, query(), cancel=CancelSource().token)
    result = FilesystemResearchSource(fs_roots_allow=(str(tree),)).search(
        cfg, query(), cancel=CancelSource().token
    )
    assert result.documents[0].origin.startswith("mcp:filesystem/")


def test_filesystem_never_exceeds_match_and_document_budgets(tree):
    (tree / "docs/many.md").write_text("research\n" * 100)
    result = FilesystemResearchSource().search(
        config(kind="filesystem", roots=["repo:."]),
        query(max_documents=1, mounts={"repo": str(tree)}),
        cancel=CancelSource().token,
    )
    assert len(result.documents) == 1
    assert sum(len((doc.text or "").splitlines()) for doc in result.documents) <= 50


def test_checkout_cache_fingerprint_changes_for_dirty_bytes_and_head(tree):
    git(tree, "add", "docs")
    git(tree, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture")
    adapter = FilesystemResearchSource()
    mounts = {"repo": str(tree)}
    first = adapter.checkout_state(mounts, CancelSource().token)
    # Unknown snapshots (symlinks/oversized files) conservatively bypass the cache.
    assert first is None
    (tree / "link.md").unlink()
    (tree / "oversized.md").unlink()
    first = adapter.checkout_state(mounts, CancelSource().token)
    assert first
    (tree / "docs/guide.md").write_text("changed research")
    assert adapter.checkout_state(mounts, CancelSource().token) != first
