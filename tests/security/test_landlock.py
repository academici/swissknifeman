"""The Landlock wrapper (adapters §7.1, examples/adapters/sandbox/landlock.md) and its adapter.

Positive canaries need Linux with Landlock ABI >= 3 and are skipped *with the reason* otherwise; a skip is not
evidence that writes are confined. Refusals that need no kernel support (usage, protect overlap, escaping
grants, pre-spawn adapter checks with an injected ABI probe) always run.
"""

import errno
import json
import os
import resource
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from uuid import uuid4

import pytest

from skm.adapters.sandbox import landlock_exec
from skm.adapters.sandbox.backend import Companion, CompanionProof, ProofRequest
from skm.adapters.sandbox.landlock import git_metadata_dirs, landlock_isolation
from skm.adapters.sandbox.landlock_exec import (
    REFER,
    TRUNCATE,
    WrapperError,
    handled_access,
    landlock_abi,
    parse,
    probe_enforcement,
)
from skm.kernel.errors import CapabilityUnavailable
from skm.modules.policy.domain.render import IsolationProperty
from skm.modules.runtimes.domain.request import ProcessOwner, ProcessOwnership

SRC = str(Path(__file__).resolve().parents[2] / "src")
ABI = landlock_abi()
needs_landlock = pytest.mark.skipif(
    ABI < 3, reason=f"Landlock ABI >= 3 is not available on this host (ABI {ABI}); no positive evidence"
)


def run_wrapper(*args: str, pass_fds: tuple[int, ...] = ()) -> subprocess.CompletedProcess[str]:
    env = {"PATH": os.environ["PATH"], "PYTHONPATH": SRC}
    return subprocess.run(
        [sys.executable, "-P", "-m", "skm.adapters.sandbox.landlock_exec", *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=60,
        pass_fds=pass_fds,
    )


def write_script(target: Path) -> list[str]:
    return [sys.executable, "-c", f"open({str(target)!r}, 'w').write('x')"]


@needs_landlock
def test_write_inside_grant_succeeds_and_outside_fails_with_eacces(tmp_path: Path) -> None:
    allowed, denied = tmp_path / "allowed", tmp_path / "denied"
    allowed.mkdir()
    denied.mkdir()
    ok = run_wrapper("--no-default-rw", "--rw", str(allowed), "--", *write_script(allowed / "f"))
    assert ok.returncode == 0, ok.stderr
    assert (allowed / "f").read_text() == "x"
    refused = run_wrapper("--no-default-rw", "--rw", str(allowed), "--", *write_script(denied / "f"))
    assert refused.returncode != 0
    assert "PermissionError" in refused.stderr
    assert not (denied / "f").exists()


@needs_landlock
def test_child_of_wrapped_command_inherits_the_restriction(tmp_path: Path) -> None:
    allowed, denied = tmp_path / "allowed", tmp_path / "denied"
    allowed.mkdir()
    denied.mkdir()
    target = denied / "f"
    inner = f"open({str(target)!r}, 'w').write('x')"
    outer = f"import subprocess, sys; sys.exit(subprocess.run([sys.executable, '-c', {inner!r}]).returncode)"
    result = run_wrapper("--no-default-rw", "--rw", str(allowed), "--", sys.executable, "-c", outer)
    assert result.returncode != 0
    assert not target.exists()


@needs_landlock
def test_no_default_rw_leaves_shared_tmp_unwritable(tmp_path: Path) -> None:
    """Unattended runs get no legacy ``/tmp`` grant: only the explicit private directory is writable."""
    private = tmp_path / "private"
    private.mkdir()
    shared = Path("/tmp") / f"skm-canary-{uuid4().hex}"  # noqa: S108 - the canary target itself
    result = run_wrapper("--no-default-rw", "--rw", str(private), "--", *write_script(shared))
    assert result.returncode != 0
    assert not shared.exists()


@needs_landlock
def test_protect_blocks_writes_into_the_protected_directory(tmp_path: Path) -> None:
    work, step_tmp = tmp_path / "work", tmp_path / "tmp"
    work.mkdir()
    step_tmp.mkdir()
    result = run_wrapper(
        "--no-default-rw", "--rw", str(step_tmp), "--protect", str(work), "--", *write_script(work / "f")
    )
    assert result.returncode != 0
    assert not (work / "f").exists()


@needs_landlock
def test_missing_command_is_exec_failed_127(tmp_path: Path) -> None:
    result = run_wrapper("--no-default-rw", "--rw", str(tmp_path), "--", str(tmp_path / "no-such-command"))
    assert result.returncode == 127
    assert result.stderr.startswith("EXEC_FAILED:")


def test_protect_with_default_writable_inside_is_refused() -> None:
    result = run_wrapper("--protect", "/tmp", "--", "true")  # noqa: S108
    assert result.returncode == 3
    assert result.stderr.startswith("RO_RUN_PROTECT_OVERLAP:")


def test_symlinked_grant_escaping_a_protected_directory_is_refused(tmp_path: Path) -> None:
    protected, outside = tmp_path / "protected", tmp_path / "outside"
    protected.mkdir()
    outside.mkdir()
    (protected / "link").symlink_to(outside)
    result = run_wrapper(
        "--no-default-rw", "--protect", str(protected), "--rw", str(protected / "link"), "--", "true"
    )
    assert result.returncode == 3
    assert result.stderr.startswith("RO_RUN_RW_ESCAPE:")


def test_grant_that_is_an_ancestor_of_a_protected_directory_is_refused(tmp_path: Path) -> None:
    protected = tmp_path / "protected"
    protected.mkdir()
    result = run_wrapper("--no-default-rw", "--protect", str(protected), "--rw", str(tmp_path), "--", "true")
    assert result.returncode == 3
    assert result.stderr.startswith("RO_RUN_RW_ESCAPE:")


@pytest.mark.parametrize(
    "args",
    [(), ("--rw", "/x"), ("--",), ("--bogus", "--", "true"), ("--rw", "--", "true")],
    ids=["no-separator", "no-separator-rw", "empty-command", "unknown-option", "rw-without-value"],
)
def test_usage_errors_exit_2(args: tuple[str, ...]) -> None:
    result = run_wrapper(*args)
    assert result.returncode == 2
    assert result.stderr.startswith("USAGE:")


def test_parse_keeps_defaults_only_without_no_default_rw() -> None:
    assert parse(["--no-default-rw", "--", "true"]).writable == ()
    assert "/dev" in parse(["--", "true"]).writable


# -- the adapter: refusals before the spawn -----------------------------------------------------------


def owner() -> ProcessOwner:
    return ProcessOwner(
        host_id=uuid4(),
        worker_id=uuid4(),
        attempt_id=uuid4(),
        stage_record_id=uuid4(),
        unit_kind="step",
        unit_id=uuid4(),
        owner_nonce="n" * 32,
        identity_dir="/run/skm/identity",
    )


class Spec:
    def __init__(self, workdir: Path, **fields: object) -> None:
        self.workdir = workdir
        self.readable: tuple[Path, ...] = ()
        self.writable: tuple[Path, ...] = (workdir,)
        self.protected: tuple[Path, ...] = ()
        self.read_only_root = False
        self.network = "full"
        self.network_hosts: tuple[str, ...] = ()
        self.env: dict[str, str] = {}
        self.materials_dir: Path | None = None
        self.credential_mounts: tuple[dict[str, str], ...] = ()
        self.owner = owner()
        vars(self).update(fields)


COMPANION_PROPERTIES = frozenset(
    {IsolationProperty.FS_READ, IsolationProperty.LIFECYCLE, IsolationProperty.NETWORK_NONE}
)


def launcher(tmp_path: Path) -> str:
    """An executable outside every writable grant, standing in for a companion's launcher."""
    path = tmp_path / "bin" / "skm-launch"
    path.parent.mkdir(exist_ok=True)
    path.write_text('#!/bin/sh\nexec "$@"\n')
    path.chmod(0o755)
    return str(path)


def composite(tmp_path: Path, *, binding: str | None = None, run: str | None = None) -> Companion:
    """Unit-test stand-in for a read/lifecycle/network backend: it proves exactly the request it is asked."""

    def verify(request: ProofRequest) -> CompanionProof:
        owned = ProcessOwnership(owner=request.spec.owner, kind="cgroup", ref="/sys/fs/cgroup/skm/test")
        return CompanionProof(
            COMPANION_PROPERTIES, binding or request.binding, (run or launcher(tmp_path),), "probe ok", owned
        )

    return Companion("test-composite", COMPANION_PROPERTIES, verify)


def adapter(
    tmp_path: Path, *, abi: int = 3, home: Path | None = None, companion: Companion | None = None
) -> object:
    return landlock_isolation(
        companions=(companion or composite(tmp_path),),
        abi_probe=lambda: abi,
        home=home or tmp_path / "home",
        python="python3",
    )


def refusal(tmp_path: Path, spec: Spec, **kwargs: int | Path) -> CapabilityUnavailable:
    isolation = adapter(tmp_path, **kwargs)  # type: ignore[arg-type]
    with pytest.raises(CapabilityUnavailable) as caught:
        isolation.wrap(["true"], spec)  # type: ignore[attr-defined]
    assert caught.value.code.value == "SANDBOX_UNAVAILABLE"
    return caught.value


@pytest.mark.skipif(sys.platform != "linux", reason="the adapter checks Linux")
def test_wrap_builds_the_prefix_with_explicit_grants_only(tmp_path: Path) -> None:
    work, step_tmp = tmp_path / "work", tmp_path / "step-tmp"
    work.mkdir()
    step_tmp.mkdir()
    spec = Spec(work, writable=(step_tmp, work), network="none", env={"A": "1"})
    wrapped = adapter(tmp_path).wrap(["agent", "--flag"], spec)  # type: ignore[attr-defined]
    assert wrapped.argv == (
        launcher(tmp_path),  # the companion's launcher encloses the Landlock prefix
        "python3", "-P", "-m", "skm.adapters.sandbox.landlock_exec", "--no-default-rw", "--min-abi", "3",
        "--rw", str(step_tmp), "--rw", str(work), "--", "agent", "--flag",
    )  # fmt: skip
    assert wrapped.env == {"A": "1"}
    assert wrapped.cwd == work
    assert wrapped.ownership.kind == "cgroup"


@pytest.mark.skipif(sys.platform != "linux", reason="the adapter checks Linux")
def test_forged_companion_proof_is_refused_before_the_spawn(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    spec = Spec(work, network="none")
    forged = adapter(tmp_path, companion=composite(tmp_path, binding="0" * 64))
    with pytest.raises(CapabilityUnavailable) as caught:
        forged.wrap(["true"], spec)  # type: ignore[attr-defined]
    assert caught.value.code.value == "SANDBOX_UNAVAILABLE"
    assert caught.value.details["reason"] == "companion_proof_unbound"
    # a launcher the unit could replace is no enforcement either
    inside = work / "launch"
    inside.write_text("#!/bin/sh\n")
    inside.chmod(0o755)
    writable_launcher = adapter(tmp_path, companion=composite(tmp_path, run=str(inside)))
    with pytest.raises(CapabilityUnavailable) as caught:
        writable_launcher.wrap(["true"], spec)  # type: ignore[attr-defined]
    assert caught.value.details["reason"] == "companion_launch_untrusted"


@pytest.mark.skipif(sys.platform != "linux", reason="the adapter checks Linux")
def test_companion_proof_is_bound_to_the_exact_writable_grants_and_command(tmp_path: Path) -> None:
    work, step_tmp = tmp_path / "work", tmp_path / "step-tmp"
    work.mkdir()
    step_tmp.mkdir()
    seen: list[ProofRequest] = []
    owner_of_request = owner()

    def verify(request: ProofRequest) -> CompanionProof:
        seen.append(request)
        stale = seen[0].binding  # proof of the first request, replayed afterwards
        owned = ProcessOwnership(owner=owner_of_request, kind="cgroup", ref="/sys/fs/cgroup/skm/test")
        return CompanionProof(COMPANION_PROPERTIES, stale, (launcher(tmp_path),), "probe ok", owned)

    isolation = adapter(tmp_path, companion=Companion("replay", COMPANION_PROPERTIES, verify))
    first = Spec(work, network="none", owner=owner_of_request)
    assert isolation.wrap(["agent"], first)  # type: ignore[attr-defined]
    for argv, spec in (
        (["agent", "--other"], first),
        (["agent"], Spec(work, writable=(work, step_tmp), network="none", owner=owner_of_request)),
    ):
        with pytest.raises(CapabilityUnavailable) as caught:
            isolation.wrap(argv, spec)  # type: ignore[attr-defined]
        assert caught.value.details["reason"] == "companion_proof_unbound"


@pytest.mark.skipif(sys.platform != "linux", reason="the adapter checks Linux")
def test_write_only_landlock_without_companions_refuses_read_network_and_lifecycle(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    isolation = landlock_isolation(abi_probe=lambda: 8, home=tmp_path / "home")
    with pytest.raises(CapabilityUnavailable) as caught:
        isolation.wrap(["true"], Spec(work, network="none"))  # type: ignore[arg-type]
    details: dict[str, object] = dict(caught.value.details)
    assert details["reason"] == "property_unproven"
    assert set(details["missing"]) == {"fs_read", "lifecycle", "network_none"}  # type: ignore[arg-type]
    assert "fs_write" in details["coverage"]["proven"]  # type: ignore[index]


@pytest.mark.skipif(sys.platform != "linux", reason="the adapter checks Linux")
def test_unsupported_abi_or_missing_landlock_is_refused_before_spawn(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    assert refusal(tmp_path, Spec(work), abi=0).details["wrapper_code"] == "LANDLOCK_UNAVAILABLE"
    too_old = refusal(tmp_path, Spec(work, protected=(tmp_path / "git",)), abi=2)
    assert too_old.details["wrapper_code"] == "LANDLOCK_ABI_TOO_OLD"


@pytest.mark.skipif(sys.platform != "linux", reason="the adapter checks Linux")
@pytest.mark.parametrize("target", ["/", "/tmp", "/var/tmp", "/dev", "HOME", "HOME/.claude", "HOME/.grok"])  # noqa: S108
def test_grants_reaching_shared_directories_or_the_personal_home_are_refused(
    tmp_path: Path, target: str
) -> None:
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".grok").mkdir()
    grant = Path(target.replace("HOME", str(home)))
    work = tmp_path / "work"
    work.mkdir()
    error = refusal(tmp_path, Spec(work, writable=(work, grant)), home=home)
    assert error.details["reason"] == "grant_too_broad"


@pytest.mark.skipif(sys.platform != "linux", reason="the adapter checks Linux")
def test_private_directory_below_tmp_is_not_a_broad_grant(tmp_path: Path) -> None:
    private = tmp_path / "step-tmp"
    private.mkdir()
    isolation = adapter(tmp_path)
    assert isolation.wrap(["true"], Spec(private, writable=(private,)))  # type: ignore[attr-defined]


@pytest.mark.skipif(sys.platform != "linux", reason="the adapter checks Linux")
def test_symlink_grant_into_the_home_is_resolved_before_the_check(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    link = tmp_path / "innocent"
    link.symlink_to(home)
    work = tmp_path / "work"
    work.mkdir()
    assert (
        refusal(tmp_path, Spec(work, writable=(work, link)), home=home).details["reason"] == "grant_too_broad"
    )


@pytest.mark.skipif(sys.platform != "linux", reason="the adapter checks Linux")
def test_symlinked_rw_grant_inside_protected_is_refused_pre_spawn(tmp_path: Path) -> None:
    protected, outside = tmp_path / "protected", tmp_path / "outside"
    protected.mkdir()
    outside.mkdir()
    (protected / "link").symlink_to(outside)
    spec = Spec(protected, writable=(protected / "link",), protected=(protected,))
    assert refusal(tmp_path, spec).details["wrapper_code"] == "RO_RUN_RW_ESCAPE"


def init_checkout(path: Path) -> Path:
    git_dir = path / ".git"
    git_dir.mkdir(parents=True)
    return git_dir


@pytest.mark.skipif(sys.platform != "linux", reason="the adapter checks Linux")
def test_plain_checkout_git_dir_cannot_be_protected_inside_a_writable_root(tmp_path: Path) -> None:
    work = tmp_path / "work"
    git_dir = init_checkout(work)
    assert git_metadata_dirs(work) == (git_dir.resolve(),)
    assert (
        refusal(tmp_path, Spec(work, protected=(git_dir,))).details["reason"] == "git_metadata_unprotectable"
    )


def linked_worktree(tmp_path: Path) -> tuple[Path, Path, Path]:
    common = tmp_path / "repo" / ".git"
    git_dir = common / "worktrees" / "wt"
    git_dir.mkdir(parents=True)
    (git_dir / "commondir").write_text("../..\n")
    (common / "config").write_text("[core]\n")
    work = tmp_path / "wt"
    work.mkdir()
    (work / ".git").write_text(f"gitdir: {git_dir}\n")
    return work, git_dir, common


@pytest.mark.skipif(sys.platform != "linux", reason="the adapter checks Linux")
def test_linked_worktree_is_refused_with_or_without_protecting_its_external_metadata(tmp_path: Path) -> None:
    """F4: the ``.git`` locator inside the writable worktree can be replaced to redirect Git discovery and
    Landlock cannot carve one file out of a grant: protecting the external dirs does not admit it."""
    work, git_dir, common = linked_worktree(tmp_path)
    assert set(git_metadata_dirs(work)) == {git_dir.resolve(), common.resolve()}
    for protected in ((), (git_dir, common)):
        error = refusal(tmp_path, Spec(work, protected=protected))
        assert error.details["reason"] == "git_metadata_unprotectable"
        assert error.details["path"] == str(work / ".git")


@pytest.mark.skipif(sys.platform != "linux", reason="the adapter checks Linux")
def test_a_git_dir_or_a_grant_inside_one_is_never_writable(tmp_path: Path) -> None:
    bare = tmp_path / "bare.git"
    (bare / "objects").mkdir(parents=True)
    (bare / "HEAD").write_text("ref: refs/heads/main\n")
    inside = tmp_path / "repo" / ".git" / "hooks"
    inside.mkdir(parents=True)
    work = tmp_path / "work"
    work.mkdir()
    for grant in (bare, inside):
        error = refusal(tmp_path, Spec(work, writable=(work, grant)))
        assert error.details["reason"] == "git_metadata_unprotectable"


@pytest.mark.skipif(sys.platform != "linux", reason="the adapter checks Linux")
def test_protected_paths_are_refused_because_landlock_cannot_prove_same_uid_protection(
    tmp_path: Path,
) -> None:
    """F3: the ruleset does not restrict chmod/chown/utime/xattr, so no ``protected`` path is admitted."""
    work, protected = tmp_path / "work", tmp_path / "state"
    work.mkdir()
    protected.mkdir()
    error = refusal(tmp_path, Spec(work, protected=(protected,)))
    assert error.details["reason"] == "protected_metadata_unprovable"
    assert error.details["path"] == str(protected)


@needs_landlock
def test_canary_landlock_leaves_chmod_and_a_writable_locator_open(tmp_path: Path) -> None:
    """Documents the kernel gap behind F3/F4: with the external Git metadata kept out of the grants, the
    same-UID command still changes its mode and replaces the ``.git`` locator inside the writable worktree.
    The adapter must therefore refuse both (tests above) instead of crediting ``--protect``."""
    work, git_dir, common = linked_worktree(tmp_path)
    config = common / "config"
    protect = ("--protect", str(git_dir), "--protect", str(common))
    chmod = "import os,sys; os.chmod(sys.argv[1], 0o000)"
    changed = run_wrapper(
        "--no-default-rw", "--rw", str(work), *protect, "--", sys.executable, "-c", chmod, str(config)
    )
    assert changed.returncode == 0, changed.stderr
    assert (config.stat().st_mode & 0o777) == 0
    config.chmod(0o600)
    assert (
        run_wrapper("--no-default-rw", "--rw", str(work), *protect, "--", *write_script(config)).returncode
        != 0
    )
    redirect = run_wrapper("--no-default-rw", "--rw", str(work), *protect, "--", *write_script(work / ".git"))
    assert redirect.returncode == 0, redirect.stderr
    assert (work / ".git").read_text() == "x"


@pytest.mark.skipif(sys.platform != "linux", reason="the adapter checks Linux")
@pytest.mark.parametrize("abi", [1, 2])
def test_abi_below_3_proves_no_write_isolation_and_is_refused(tmp_path: Path, abi: int) -> None:
    """F7: before ABI 3 ``truncate(2)`` is not handled and empties any same-UID file outside the grants."""
    work = tmp_path / "work"
    work.mkdir()
    isolation = adapter(tmp_path, abi=abi)
    assert isolation.proven(Spec(work)) == {}  # type: ignore[attr-defined]
    available = isolation.available(None)  # type: ignore[attr-defined]
    assert available["available"] is False
    assert "proves" not in available
    error = refusal(tmp_path, Spec(work), abi=abi)
    assert error.details["wrapper_code"] == "LANDLOCK_ABI_TOO_OLD"
    assert error.details["abi"] == abi
    bare = landlock_isolation(abi_probe=lambda: abi, home=tmp_path / "home", python="python3")
    with pytest.raises(CapabilityUnavailable) as caught:
        bare.wrap(["true"], Spec(work))  # type: ignore[attr-defined]
    assert caught.value.details["reason"] == "LANDLOCK_ABI_TOO_OLD"


def test_truncate_is_handled_only_from_abi_3_and_the_adapter_requires_it() -> None:
    for abi in (1, 2):
        assert handled_access(abi) & TRUNCATE == 0
    assert handled_access(3) & TRUNCATE == TRUNCATE
    assert handled_access(1) & REFER == 0
    assert handled_access(2) & REFER == REFER


@pytest.mark.skipif(sys.platform != "linux", reason="the adapter checks Linux")
def test_the_write_proof_names_what_it_does_not_cover(tmp_path: Path) -> None:
    proof = adapter(tmp_path, abi=3).proven(Spec(tmp_path))  # type: ignore[attr-defined]
    text = proof[IsolationProperty.FS_WRITE]
    assert all(word in text for word in ("content writes", "chmod/chown/utime/xattr"))
    assert "wrapped process tree" in text
    assert "other same-UID processes are not constrained" in text


# -- the launcher fails closed ---------------------------------------------------------------------------


def test_unsupported_kernel_never_starts_the_command(tmp_path: Path) -> None:
    """``--min-abi`` above anything the kernel offers: exit 3 and the command is not executed. Runs on every
    host: without Landlock the code is ``LANDLOCK_UNAVAILABLE``, with it ``LANDLOCK_ABI_TOO_OLD``."""
    marker = tmp_path / "ran"
    result = run_wrapper(
        "--no-default-rw", "--min-abi", "99", "--rw", str(tmp_path), "--", *write_script(marker)
    )
    assert result.returncode == 3
    assert result.stderr.startswith("LANDLOCK_UNAVAILABLE:" if ABI < 1 else "LANDLOCK_ABI_TOO_OLD:")
    assert not marker.exists()


def test_min_abi_needs_a_number() -> None:
    for args in (("--min-abi", "x"), ("--min-abi", "-1"), ("--min-abi",)):
        result = run_wrapper(*args, "--", "true")
        assert result.returncode == 2
        assert result.stderr.startswith("USAGE:")


@needs_landlock
def test_explicit_grant_that_is_not_an_existing_directory_is_refused(tmp_path: Path) -> None:
    """A skipped grant would silently confine more than asked: the launcher refuses and starts nothing."""
    plain = tmp_path / "plain"
    plain.write_text("x")
    marker = tmp_path / "ran"
    for grant in (tmp_path / "missing", plain):
        result = run_wrapper("--no-default-rw", "--rw", str(grant), "--", *write_script(marker))
        assert result.returncode == 3
        assert result.stderr.startswith("LANDLOCK_GRANT_INVALID:")
    assert not marker.exists()


@needs_landlock
def test_the_probe_confines_a_canary_and_reports_a_launcher_that_cannot() -> None:
    assert probe_enforcement(sys.executable, 3) is None
    reason = probe_enforcement(sys.executable, 99)
    assert reason is not None
    assert "LANDLOCK_ABI_TOO_OLD" in reason


def test_the_probe_reports_a_launcher_that_does_not_run() -> None:
    reason = probe_enforcement("/nonexistent/python", 3)
    assert reason is not None
    assert "did not run" in reason


# -- live adversarial attempts by a confined same-UID command -----------------------------------------

ATTACKS = """
import errno, json, os, sys
allowed, denied = sys.argv[1:3]
victim = os.path.join(denied, "victim")
inside = os.path.join(allowed, "inside")
open(inside, "w").write("in")
reopen = os.open(victim, os.O_RDONLY)
attempts = {
    "truncate": lambda: os.truncate(victim, 0),
    "open_write": lambda: open(victim, "w"),
    "open_append": lambda: open(victim, "a"),
    "open_readwrite": lambda: os.open(victim, os.O_RDWR),
    "reopen_via_proc_fd": lambda: open(f"/proc/self/fd/{reopen}", "w"),
    "write_via_symlink_in_grant": lambda: open(os.path.join(allowed, "escape"), "w"),
    "create": lambda: open(os.path.join(denied, "new"), "w"),
    "unlink": lambda: os.unlink(victim),
    "rename_out_of_grant": lambda: os.rename(inside, os.path.join(denied, "moved")),
    "rename_into_grant": lambda: os.rename(victim, os.path.join(allowed, "stolen")),
    "rename_over_victim": lambda: os.rename(inside, victim),
    "hardlink_into_grant": lambda: os.link(victim, os.path.join(allowed, "hard")),
    "symlink": lambda: os.symlink("x", os.path.join(denied, "sym")),
    "mkdir": lambda: os.mkdir(os.path.join(denied, "dir")),
    "rmdir": lambda: os.rmdir(os.path.join(denied, "sub")),
    "mkfifo": lambda: os.mkfifo(os.path.join(denied, "fifo")),
}
outcome = {}
for name, attempt in attempts.items():
    try:
        attempt()
    except OSError as error:
        outcome[name] = errno.errorcode[error.errno]
    else:
        outcome[name] = "ok"
outcome["read_victim"] = open(victim).read()
print(json.dumps(outcome))
"""


@needs_landlock
def test_confined_command_cannot_alter_anything_outside_its_grant(tmp_path: Path) -> None:
    allowed, denied = tmp_path / "allowed", tmp_path / "denied"
    allowed.mkdir()
    denied.mkdir()
    (denied / "victim").write_text("kept")
    (denied / "sub").mkdir()
    (allowed / "escape").symlink_to(denied / "victim")
    result = run_wrapper(
        "--no-default-rw",
        "--rw",
        str(allowed),
        "--",
        sys.executable,
        "-c",
        ATTACKS,
        str(allowed),
        str(denied),
    )
    assert result.returncode == 0, result.stderr
    outcome = json.loads(result.stdout)
    assert outcome.pop("read_victim") == "kept"  # reads stay open: this is write confinement only
    assert outcome, "no attempt was recorded"
    assert set(outcome.values()) <= {"EACCES", "EXDEV"}, outcome
    assert (denied / "victim").read_text() == "kept"
    assert {path.name for path in denied.iterdir()} == {"victim", "sub"}
    assert {path.name for path in allowed.iterdir()} == {"inside", "escape"}
    assert (allowed / "inside").read_text() == "in"


@needs_landlock
def test_descriptor_inherited_from_the_unconfined_parent_is_not_passed_on(tmp_path: Path) -> None:
    """Landlock checks a path only when it is opened, so an inherited writable descriptor would outlive the
    ruleset: the launcher closes everything above stderr before ``exec``. The unwrapped control proves the
    descriptor works, so the denial is the launcher's doing."""
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    target = tmp_path / "outside"
    target.write_text("kept")
    script = "import os, sys; os.write(int(sys.argv[1]), b'LEAK')"
    with target.open("r+b") as handle:
        fd = handle.fileno()
        os.set_inheritable(fd, True)
        control = subprocess.run(
            [sys.executable, "-c", script, str(fd)], pass_fds=(fd,), capture_output=True, check=False
        )
        assert control.returncode == 0
        target.write_text("kept")
        wrapped = run_wrapper(
            "--no-default-rw",
            "--rw",
            str(allowed),
            "--",
            sys.executable,
            "-c",
            script,
            str(fd),
            pass_fds=(fd,),
        )
    assert wrapped.returncode != 0
    assert "OSError" in wrapped.stderr
    assert target.read_text() == "kept"


# A driver script runs in its own process: it raises the descriptor limit, opens a writable descriptor far
# above the old 65535 cut-off and makes ``/proc/self/fd`` unlistable before it calls the launcher code.
HIGH_FD = 70000
DRIVER_FD_LIMIT = 100000
# The driver raises RLIMIT_NOFILE to DRIVER_FD_LIMIT so it can open HIGH_FD; an unprivileged process cannot
# go above its hard limit (65536 on GitHub-hosted runners unless the job raises it).
needs_descriptor_room = pytest.mark.skipif(
    resource.getrlimit(resource.RLIMIT_NOFILE)[1] < DRIVER_FD_LIMIT and os.geteuid() != 0,
    reason=f"the RLIMIT_NOFILE hard limit is below {DRIVER_FD_LIMIT}; descriptor {HIGH_FD} cannot be opened",
)
DRIVER = """
import ctypes, os, resource, sys
mode, target = sys.argv[1:3]
soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
limit = int(sys.argv[3]) if len(sys.argv) > 3 else hard
resource.setrlimit(resource.RLIMIT_NOFILE, (limit, limit))
fd = os.open(target, os.O_RDWR)
high = int(sys.argv[5])
os.dup2(fd, high)
os.close(fd)
os.set_inheritable(high, True)
if mode == "lowered":  # the hard limit drops below a descriptor that is already open
    resource.setrlimit(resource.RLIMIT_NOFILE, (1024, 1024))
real_listdir = os.listdir
def listdir(path="."):
    if str(path) == "/proc/self/fd":
        raise OSError(2, "no /proc")
    return real_listdir(path)
if mode != "proc":
    os.listdir = listdir
from skm.adapters.sandbox import landlock_exec
real_libc = landlock_exec._libc
class NoCloseRange:
    def __init__(self):
        self.libc = real_libc()
        self.prctl = self.libc.prctl
    def syscall(self, number, *args):
        if number == 436:  # close_range(2) filtered as by a seccomp policy
            raise OSError("ENOSYS")
        return self.libc.syscall(number, *args)
if mode in ("no_close_range", "lowered"):
    landlock_exec._libc = NoCloseRange
command = [sys.executable, "-c", f"import os; os.write({high}, b'LEAK')"]
sys.exit(landlock_exec.main(["--no-default-rw", "--rw", sys.argv[4], "--", *command]))
"""


def run_driver(
    mode: str, target: Path, allowed: Path, limit: int = DRIVER_FD_LIMIT
) -> subprocess.CompletedProcess[str]:
    env = {"PATH": os.environ["PATH"], "PYTHONPATH": SRC}
    return subprocess.run(
        [sys.executable, "-P", "-c", DRIVER, mode, str(target), str(limit), str(allowed), str(HIGH_FD)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=60,
    )


@needs_landlock
@needs_descriptor_room
@pytest.mark.parametrize("mode", ["proc", "no_proc"])
def test_high_descriptor_is_closed_with_or_without_proc(tmp_path: Path, mode: str) -> None:
    """A writable descriptor above 65535 must not reach the command, whether the launcher lists
    ``/proc/self/fd`` or falls back to ``close_range(2)``."""
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    target = tmp_path / "outside"
    target.write_text("kept")
    result = run_driver(mode, target, allowed)
    assert result.returncode != 0, "the command wrote through the inherited descriptor"
    assert "OSError" in result.stderr or "Bad file descriptor" in result.stderr, result.stderr
    assert target.read_text() == "kept"


@needs_landlock
@needs_descriptor_room
@pytest.mark.parametrize("mode", ["no_close_range", "lowered"])
def test_descriptor_cleanup_without_proc_or_close_range_refuses_before_exec(
    tmp_path: Path, mode: str
) -> None:
    """Neither mechanism can close the range, so the command must not start; ``lowered`` keeps a descriptor
    open above a hard limit lowered afterwards, which a loop bounded by that limit would miss."""
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    target = tmp_path / "outside"
    target.write_text("kept")
    result = run_driver(mode, target, allowed)
    assert result.returncode == 1
    assert result.stderr.startswith("LANDLOCK_FAILED: cannot close inherited descriptors")
    assert "OSError" not in result.stderr  # the command never ran, so it never tried the descriptor
    assert target.read_text() == "kept"


@pytest.mark.parametrize("hard", [200000, 1024, resource.RLIM_INFINITY])
def test_descriptor_cleanup_never_falls_back_to_a_limit_bounded_loop(
    monkeypatch: pytest.MonkeyPatch, hard: int
) -> None:
    def no_listing(_path: str) -> list[str]:
        raise OSError(2, "no /proc")

    class NoSyscall:
        def syscall(self, *_args: object) -> int:
            raise OSError("ENOSYS")

    closed: list[tuple[int, int]] = []
    monkeypatch.setattr("os.listdir", no_listing)
    monkeypatch.setattr(landlock_exec, "_libc", NoSyscall)
    monkeypatch.setattr("os.closerange", lambda low, high: closed.append((low, high)))
    monkeypatch.setattr("resource.getrlimit", lambda _which: (1024, hard))
    with pytest.raises(WrapperError) as caught:
        landlock_exec._close_inherited_descriptors()
    assert caught.value.code == "LANDLOCK_FAILED"
    assert closed == []


@pytest.mark.parametrize("failing", ["mkdtemp", "mkdir", "write"])
def test_probe_setup_failure_is_a_reason_not_an_exception(
    monkeypatch: pytest.MonkeyPatch, failing: str
) -> None:
    full = OSError(errno.ENOSPC, "No space left on device")
    created: list[str] = []
    real_mkdtemp = tempfile.mkdtemp

    def mkdtemp(*args: object, **kwargs: object) -> str:
        if failing == "mkdtemp":
            raise full
        path = real_mkdtemp(*args, **kwargs)  # type: ignore[arg-type]
        created.append(path)
        return path

    def mkdir(path: str, *args: object, **kwargs: object) -> None:
        raise full

    monkeypatch.setattr(tempfile, "mkdtemp", mkdtemp)
    if failing == "mkdir":
        monkeypatch.setattr(os, "mkdir", mkdir)
    if failing == "write":
        monkeypatch.setattr("builtins.open", lambda *_args, **_kwargs: (_ for _ in ()).throw(full))
    reason = probe_enforcement(sys.executable, 3)
    assert reason is not None
    assert "could not be set up" in reason
    assert "OSError" in reason
    assert not any(Path(path).exists() for path in created), "the probe directory leaked"


@pytest.mark.skipif(sys.platform != "linux", reason="the adapter checks Linux")
def test_available_is_unavailable_when_the_probe_hits_enospc(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def no_space(*_args: object, **_kwargs: object) -> str:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(tempfile, "mkdtemp", no_space)
    real = landlock_isolation(abi_probe=lambda: 8, home=tmp_path, python=sys.executable)
    report = real.available(None)  # type: ignore[attr-defined]
    assert report["available"] is False
    assert "proves" not in report
    assert "could not be set up" in str(report["reason"])
    raising = landlock_isolation(
        abi_probe=lambda: 8,
        home=tmp_path,
        python=sys.executable,
        enforcement_probe=no_space,
    )
    report = raising.available(None)  # type: ignore[attr-defined]
    assert report["available"] is False
    assert "proves" not in report
    assert "enforcement probe failed" in str(report["reason"])


@needs_landlock
@pytest.mark.parametrize("via", ["sh", "setsid-python"])
def test_other_programs_and_detached_descendants_stay_confined(tmp_path: Path, via: str) -> None:
    allowed, denied = tmp_path / "allowed", tmp_path / "denied"
    allowed.mkdir()
    denied.mkdir()
    target = denied / "f"
    if via == "sh":
        command = [
            "sh",
            "-c",
            ': > "$1"',
            "sh",
            str(target),
        ]  # a non-Python writer: the kernel, not the runtime
    else:
        inner = f"open({str(target)!r}, 'w').write('x')"
        outer = (
            "import subprocess, sys; "
            f"p = subprocess.Popen([sys.executable, '-c', {inner!r}], start_new_session=True); "
            "sys.exit(p.wait())"
        )
        command = [sys.executable, "-c", outer]
    result = run_wrapper("--no-default-rw", "--rw", str(allowed), "--", *command)
    assert result.returncode != 0
    assert not target.exists()


@needs_landlock
def test_confinement_is_not_a_property_of_the_user_only_of_the_wrapped_tree(tmp_path: Path) -> None:
    """The negative control: an unconfined process of the same UID writes where the wrapped one cannot."""
    allowed, denied = tmp_path / "allowed", tmp_path / "denied"
    allowed.mkdir()
    denied.mkdir()
    assert subprocess.run(write_script(denied / "free"), check=False).returncode == 0
    confined = run_wrapper("--no-default-rw", "--rw", str(allowed), "--", *write_script(denied / "bound"))
    assert confined.returncode != 0
    assert (denied / "free").exists()
    assert not (denied / "bound").exists()


@needs_landlock
def test_canary_unconfined_same_uid_service_can_act_for_the_confined_command(tmp_path: Path) -> None:
    """Documents the limit of the whole mechanism: a confined command that can reach an unconfined same-UID
    service (here a local socket) gets that service to write for it. Nothing in Landlock ABI <= 8 handled by
    this launcher stops it, so the adapter claims content writes of the wrapped tree and no more."""
    allowed, denied = tmp_path / "allowed", tmp_path / "denied"
    allowed.mkdir()
    denied.mkdir()
    sock_dir = Path(tempfile.mkdtemp(prefix="skm-sock-"))  # short path: AF_UNIX allows ~100 bytes
    try:
        path = sock_dir / "s"
        server = socket.socket(socket.AF_UNIX)
        server.bind(str(path))
        server.listen(1)
        server.settimeout(30)

        def serve() -> None:
            conn, _ = server.accept()
            with conn:
                target = conn.recv(4096).decode()
                Path(target).write_text("by proxy")
                conn.sendall(b"done")

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        client = (
            "import socket, sys; s = socket.socket(socket.AF_UNIX); s.connect(sys.argv[1]); "
            "s.sendall(sys.argv[2].encode()); sys.exit(0 if s.recv(16) == b'done' else 1)"
        )
        proxied = denied / "proxied"
        direct = run_wrapper("--no-default-rw", "--rw", str(allowed), "--", *write_script(denied / "direct"))
        via_service = run_wrapper(
            "--no-default-rw",
            "--rw",
            str(allowed),
            "--",
            sys.executable,
            "-c",
            client,
            str(path),
            str(proxied),
        )
        thread.join(timeout=30)
        server.close()
    finally:
        shutil.rmtree(sock_dir, ignore_errors=True)
    assert direct.returncode != 0
    assert via_service.returncode == 0, via_service.stderr
    assert proxied.read_text() == "by proxy"


MOUNT_ATTEMPT = """
import ctypes, os, sys
try:
    os.unshare(os.CLONE_NEWUSER | os.CLONE_NEWNS)
except OSError:
    sys.exit(77)
libc = ctypes.CDLL(None, use_errno=True)
if libc.mount(sys.argv[1].encode(), sys.argv[2].encode(), None, 4096, None) != 0:
    sys.exit(77 if ctypes.get_errno() == 13 else 1)
sys.exit(0)
"""


@needs_landlock
def test_confined_command_cannot_rearrange_mounts_in_a_new_namespace(tmp_path: Path) -> None:
    allowed, denied = tmp_path / "allowed", tmp_path / "denied"
    allowed.mkdir()
    denied.mkdir()
    control = subprocess.run(
        [sys.executable, "-c", MOUNT_ATTEMPT, str(allowed), str(denied)], check=False, capture_output=True
    )
    assert control.returncode in {0, 77}
    result = run_wrapper(
        "--no-default-rw",
        "--rw",
        str(allowed),
        "--",
        sys.executable,
        "-c",
        MOUNT_ATTEMPT,
        str(allowed),
        str(denied),
    )
    assert result.returncode != 0


@needs_landlock
def test_no_new_privs_is_set_on_the_command() -> None:
    script = (
        "print([line for line in open('/proc/self/status') if line.startswith('NoNewPrivs')][0].split()[1])"
    )
    result = run_wrapper("--no-default-rw", "--", sys.executable, "-c", script)
    assert result.stdout.strip() == "1"


# -- the adapter end to end, on the real kernel -------------------------------------------------------


@needs_landlock
def test_adapter_argv_confines_the_command_it_wraps_on_this_host(tmp_path: Path) -> None:
    """The argv the adapter builds, run as built (launcher stand-in, ``-P -m`` prefix, ``--min-abi``): a write
    inside the exact grant succeeds, a write beside it does not, and ``available`` reports enforcement."""
    work, other = tmp_path / "work", tmp_path / "other"
    work.mkdir()
    other.mkdir()
    isolation = landlock_isolation(
        companions=(composite(tmp_path),), home=tmp_path / "home", python=sys.executable
    )
    report = isolation.available(None)  # type: ignore[attr-defined]
    assert report["available"] is True, report
    assert report["abi"] == ABI
    assert "does_not_cover" in report
    env = {"PATH": os.environ["PATH"], "PYTHONPATH": SRC}
    results = []
    for target in (work / "ok", other / "no"):
        spec = Spec(work, network="none", env=env)
        wrapped = isolation.wrap(write_script(target), spec)  # type: ignore[attr-defined]
        done = subprocess.run(
            wrapped.argv, env=dict(wrapped.env), cwd=wrapped.cwd, capture_output=True, text=True, check=False
        )
        results.append(done.returncode)
    assert results[0] == 0
    assert results[1] != 0
    assert (work / "ok").exists()
    assert not (other / "no").exists()


@pytest.mark.skipif(sys.platform != "linux", reason="the adapter checks Linux")
def test_available_reports_a_probe_failure_and_never_claims_enforcement_without_it(tmp_path: Path) -> None:
    failing = landlock_isolation(
        abi_probe=lambda: 8, home=tmp_path, python="python3", enforcement_probe=lambda: "restrict self: EPERM"
    )
    report = failing.available(None)  # type: ignore[attr-defined]
    assert report["available"] is False
    assert "restrict self: EPERM" in str(report["reason"])
    assert "proves" not in report
    working = landlock_isolation(
        abi_probe=lambda: 8, home=tmp_path, python="python3", enforcement_probe=lambda: None
    )
    report = working.available(None)  # type: ignore[attr-defined]
    assert report["available"] is True
    assert report["proves"] == ["fs_write"]
    uncovered = report["does_not_cover"]
    assert isinstance(uncovered, list)
    assert {"network", "unix_sockets"} <= set(uncovered)
    for abi in (0, 1, 2):  # an old or missing ABI is reported without consulting the probe
        never = landlock_isolation(
            abi_probe=lambda abi=abi: abi, home=tmp_path, enforcement_probe=lambda: "x"
        )
        assert "x" not in str(never.available(None)["reason"])  # type: ignore[attr-defined]


@pytest.mark.skipif(sys.platform != "linux", reason="the adapter checks Linux")
def test_grant_that_is_missing_or_a_file_is_refused_before_the_spawn(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    plain = tmp_path / "plain"
    plain.write_text("x")
    for grant in (tmp_path / "missing", plain):
        error = refusal(tmp_path, Spec(work, writable=(work, grant)))
        assert error.details["reason"] == "grant_not_directory"
        assert error.details["path"] == str(grant)


def test_wrapper_error_carries_code_message_and_status() -> None:
    with pytest.raises(WrapperError) as caught:
        parse(["--bogus", "--", "true"])
    assert (caught.value.code, caught.value.status) == ("USAGE", 2)
