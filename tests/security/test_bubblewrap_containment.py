"""Live Linux canaries. The independent namespace probe skips only an unavailable host."""

import os
import platform
import shutil
import subprocess
from pathlib import Path

import pytest

from skm.adapters.sandbox.bubblewrap import BubblewrapSandbox


@pytest.fixture(scope="module")
def linux_bwrap():
    binary = shutil.which("bwrap", path=os.defpath)
    if platform.system() != "Linux" or binary is None:
        pytest.skip("requires Linux bubblewrap")
    # Independent of the adapter command so a broken mount list fails the test on a capable host.
    result = subprocess.run(
        [
            binary,
            "--unshare-user",
            "--unshare-pid",
            "--unshare-net",
            "--ro-bind",
            "/usr",
            "/usr",
            "--ro-bind",
            "/lib",
            "/lib",
            "--ro-bind-try",
            "/lib64",
            "/lib64",
            "--",
            "/usr/bin/true",
        ],
        cwd="/",
        env={},
        capture_output=True,
        timeout=10,
        check=False,
    )
    if result.returncode:
        diagnostic = result.stderr.decode().strip()
        if any(reason in diagnostic.lower() for reason in ("not permitted", "permission", "namespace")):
            pytest.skip(f"host does not allow bubblewrap namespaces: {diagnostic}")
        pytest.fail(f"independent bwrap probe failed: {diagnostic}")


@pytest.mark.parametrize("linked", [False, True], ids=["checkout", "linked-worktree"])
def test_agent_writes_only_worktree_and_step_tmp(linux_bwrap, tmp_path, linked, monkeypatch):
    work = tmp_path / "worktrees" / "attempt" / "repo"
    tmp = tmp_path / "state" / "steps" / "one" / "tmp"
    sibling = work.parent / "other"
    state = work / ".skm"
    protected = work / "host-state"
    for path in (work, tmp, sibling, state, protected):
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    gitdir = tmp_path / "host-git" if linked else work / ".git"
    gitdir.mkdir()
    if linked:
        (work / ".git").write_text(f"gitdir: {gitdir}\n")
    runtime = tmp_path / "runtime"
    hookd = runtime / "skm"
    hookd.mkdir(mode=0o700, parents=True)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    secrets = [p / "canary" for p in (gitdir, state, protected, sibling, tmp.parent, hookd)]
    for secret in secrets:
        secret.write_text("host-only")
    (work / "link-to-sibling").symlink_to(sibling, target_is_directory=True)
    argv = BubblewrapSandbox().filesystem_argv(
        [
            "/bin/sh",
            "-eu",
            "-c",
            """
            mkdir .skm-dev
            echo task > result
            echo scratch > .skm-dev/note
            echo tmp > "$TMPDIR/result"
            for secret do
                test ! -r "$secret"
                if (echo changed > "$secret") 2>/dev/null; then exit 1; fi
            done
            if (echo changed > .git) 2>/dev/null; then exit 1; fi
            if mv .git git-moved 2>/dev/null; then exit 1; fi
            test ! -e /etc/passwd
            test -z "${XDG_RUNTIME_DIR+x}"
        """,
            "sh",
            *(str(p) for p in secrets),
            ".git/canary",
            "link-to-sibling/canary",
        ],
        worktree=work,
        step_tmp=tmp,
        protected=(protected, tmp.parent),
    )
    result = subprocess.run(
        argv,
        cwd=Path("/"),
        env={"PATH": os.defpath, "XDG_RUNTIME_DIR": str(runtime)},
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode()
    assert (work / "result").read_text() == "task\n"
    assert (work / ".skm-dev/note").read_text() == "scratch\n"
    assert (tmp / "result").read_text() == "tmp\n"
    assert [p.read_text() for p in secrets] == ["host-only"] * len(secrets)
