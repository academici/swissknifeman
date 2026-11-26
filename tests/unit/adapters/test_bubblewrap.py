import os
import platform
import shutil
from dataclasses import replace
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace

import pytest

from skm.adapters.sandbox import bubblewrap
from skm.adapters.sandbox.bubblewrap import BubblewrapSandbox
from skm.kernel.errors import CapabilityUnavailable


@pytest.fixture
def layout(tmp_path, monkeypatch):
    work, tmp = tmp_path / "checkout", tmp_path / "step" / "tmp"
    work.mkdir()
    tmp.mkdir(mode=0o700, parents=True)
    (work / ".git").mkdir()
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(shutil, "which", lambda *a, **kw: "/usr/bin/bwrap")
    monkeypatch.setattr(bubblewrap, "run", lambda *a, **kw: SimpleNamespace(exit_code=0))
    monkeypatch.setattr(bubblewrap, "_mount_points", lambda: ())
    return work, tmp


def test_namespace_topology_and_order(layout):
    work, tmp = layout
    sandbox = BubblewrapSandbox()
    state = work / "private"
    state.mkdir()
    command = sandbox.filesystem_argv(
        ["/bin/echo", "--bind"], worktree=work, step_tmp=tmp, protected=(state, tmp.parent)
    )
    args = command[: command.index("--")]
    assert command[-3:] == ("--", "/bin/echo", "--bind")
    assert {"--unshare-user", "--disable-userns", "--unshare-all"}.issubset(args)
    assert args[args.index("--tmpfs") + 1] == "/"
    assert args[args.index("--cap-drop") + 1] == "ALL"
    assert [(args[i + 1], args[i + 2]) for i, arg in enumerate(args) if arg == "--bind"] == [
        (str(work), str(work)),
        (str(tmp), str(tmp)),
    ]
    read_only = [(args[i + 1], args[i + 2]) for i, arg in enumerate(args) if arg == "--ro-bind"]
    assert ("/usr/bin", "/usr/bin") in read_only
    assert all(src == dest and Path(src) in bubblewrap._SYSTEM for src, dest in read_only)
    for hidden in (state, work / ".git"):
        assert args.index(str(hidden)) > args.index("--bind")
        index = args.index(str(hidden))
        assert args[index - 1 : index + 3] == ("--tmpfs", str(hidden), "--remount-ro", str(hidden))
    assert args[args.index("--chdir") + 1] == str(work)
    assert ("--remount-ro", "/") in pairwise(args)


@pytest.mark.parametrize("missing", [True, False])
def test_probe_and_launch_fail_closed(layout, monkeypatch, missing):
    work, tmp = layout
    if missing:
        monkeypatch.setattr(shutil, "which", lambda *a, **kw: None)
    else:

        def denied(argv, **kwargs):
            assert "--unshare-user" in argv
            assert kwargs["env"] == {}
            return SimpleNamespace(exit_code=1, stderr=b"user namespace unavailable")

        monkeypatch.setattr(bubblewrap, "run", denied)
    sandbox = BubblewrapSandbox()
    assert sandbox.available()["available"] is False
    with pytest.raises(CapabilityUnavailable) as caught:
        sandbox.filesystem_argv(["true"], worktree=work, step_tmp=tmp)
    assert caught.value.code.value == "SANDBOX_UNAVAILABLE"


def test_hookd_runtime_cannot_be_bound_even_before_startup(layout, monkeypatch):
    work, tmp = layout
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(work / "runtime"))
    with pytest.raises(CapabilityUnavailable, match="overlaps hookd runtime"):
        BubblewrapSandbox().filesystem_argv(["true"], worktree=work, step_tmp=tmp)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(work.parent / "host-runtime"))
    argv = BubblewrapSandbox().filesystem_argv(["true"], worktree=work, step_tmp=tmp)
    assert ("--unsetenv", "XDG_RUNTIME_DIR") in pairwise(argv)
    assert str(work.parent / "host-runtime") not in argv


def test_grant_cannot_alias_external_inode_or_protected_metadata(layout):
    work, tmp = layout
    sandbox = BubblewrapSandbox()
    secret = tmp.parent / "private"
    secret.write_text("original")
    os.link(secret, work / "alias")
    with pytest.raises(CapabilityUnavailable, match="multiply linked"):
        sandbox.filesystem_argv(["true"], worktree=work, step_tmp=tmp)
    (work / "alias").unlink()
    (work / ".git").rmdir()
    (work / ".git").write_text(f"gitdir: {tmp.parent}\n")
    with pytest.raises(CapabilityUnavailable, match="Git metadata"):
        sandbox.filesystem_argv(["true"], worktree=work, step_tmp=tmp)


@pytest.mark.parametrize("name", [".git", "protected"])
def test_masked_regular_files_cannot_be_hard_links(layout, name):
    work, tmp = layout
    external = tmp.parent / "external"
    external.write_text("fixture")
    nested = work / "sub"
    nested.mkdir()
    alias = nested / name
    os.link(external, alias)
    protected = (alias,) if name == "protected" else ()
    with pytest.raises(CapabilityUnavailable, match="multiply linked") as caught:
        BubblewrapSandbox().filesystem_argv(["true"], worktree=work, step_tmp=tmp, protected=protected)
    assert caught.value.details["reason"] == "linked_file"


def test_only_top_level_worktree_git_pointer_is_bound_verbatim(layout):
    work, tmp = layout
    git_dir = tmp.parent / "metadata"
    git_dir.mkdir()
    git_entry = work / ".git"
    git_entry.rmdir()
    git_entry.write_text(f"gitdir: {git_dir}\n")
    nested = work / "sub"
    nested.mkdir()
    masked = (nested / ".git", tmp / ".git", work / "protected")
    for path in masked:
        path.write_text("fixture")

    args = BubblewrapSandbox().filesystem_argv(["true"], worktree=work, step_tmp=tmp, protected=(masked[-1],))
    binds = {args[i + 2]: args[i + 1] for i, arg in enumerate(args) if arg == "--ro-bind"}
    assert binds[str(git_entry)] == str(git_entry)
    assert all(binds[str(path)] == "/dev/null" for path in masked)


@pytest.mark.parametrize("location", ["worktree", "step_tmp", "git_dir"])
def test_missing_protected_path_inside_grant_fails_closed(layout, location):
    work, tmp = layout
    missing = (work if location == "worktree" else tmp) / "missing"
    protected = (missing,)
    if location == "git_dir":
        git_entry = work / ".git"
        git_entry.rmdir()
        git_entry.write_text(f"gitdir: {missing}\n")
        protected = ()

    with pytest.raises(CapabilityUnavailable, match="protected path does not exist") as caught:
        BubblewrapSandbox().filesystem_argv(["true"], worktree=work, step_tmp=tmp, protected=protected)
    assert caught.value.details["reason"] == "unsafe_mask"


def test_malformed_worktree_git_pointer_fails_closed(layout):
    work, tmp = layout
    git_entry = work / ".git"
    git_entry.rmdir()
    git_entry.write_text("invalid Git metadata\n")
    with pytest.raises(CapabilityUnavailable, match="Git metadata") as caught:
        BubblewrapSandbox().filesystem_argv(["true"], worktree=work, step_tmp=tmp)
    assert caught.value.details["reason"] == "unsafe_git"


def test_private_disjoint_roots_required(layout):
    work, tmp = layout
    with pytest.raises(CapabilityUnavailable, match="disjoint"):
        BubblewrapSandbox().filesystem_argv(["true"], worktree=work, step_tmp=work)
    tmp.chmod(0o755)
    with pytest.raises(CapabilityUnavailable, match="private"):
        BubblewrapSandbox().filesystem_argv(["true"], worktree=work, step_tmp=tmp)


def test_wrap_requires_the_lifecycle_companion_and_refuses_extra_grants(layout):
    from security.test_sandbox_profiles import make_owner
    from skm.modules.execution.host.isolation import IsolationSpec

    work, tmp = layout
    spec = IsolationSpec(
        work, (), (work, tmp), (), True, "none", (), {"TMPDIR": str(tmp)}, None, (), make_owner()
    )
    with pytest.raises(CapabilityUnavailable, match="lifecycle"):
        BubblewrapSandbox().wrap(["/bin/true"], spec)
    spec = replace(spec, writable=(work, tmp, work.parent))
    with pytest.raises(CapabilityUnavailable, match="worktree and private step_tmp"):
        BubblewrapSandbox().wrap(["/bin/true"], spec)


def test_recursive_host_bind_refused(layout, monkeypatch):
    work, tmp = layout
    alias = work / "data"
    alias.mkdir()
    monkeypatch.setattr(bubblewrap, "_mount_points", lambda: (alias,))
    with pytest.raises(CapabilityUnavailable, match="unexpected host mount"):
        BubblewrapSandbox().filesystem_argv(["true"], worktree=work, step_tmp=tmp)
