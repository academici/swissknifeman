import sys
from pathlib import Path

import pytest

from skm.adapters.sandbox import SeatbeltSandbox, seatbelt
from skm.adapters.sandbox.registry import build_isolation_registry
from skm.kernel.errors import CapabilityUnavailable
from skm.modules.execution.host.isolation import IsolationSpec


@pytest.fixture
def layout(tmp_path: Path) -> tuple[Path, Path]:
    work = tmp_path / "checkout"
    work.mkdir()
    temp = tmp_path / "step"
    temp.mkdir(mode=0o700)
    return work.resolve(), temp.resolve()


@pytest.fixture
def launcher(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    binary = tmp_path / "sandbox-exec"
    binary.touch(mode=0o700)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(seatbelt, "_BINARY", binary)
    return binary


def test_profile_defaults_to_deny_with_read_only_system_paths_and_task_writes(layout, launcher):
    work, temp = layout
    command = SeatbeltSandbox().filesystem_argv(["/bin/echo", "-p"], worktree=work, step_tmp=temp)
    binary, option, profile, *args = command

    assert (binary, option) == (str(launcher), "-p")
    assert profile.splitlines()[:2] == ["(version 1)", "(deny default)"]
    system_read = next(line for line in profile.splitlines() if '(subpath "/usr/bin")' in line)
    assert system_read.startswith("(allow file-read* file-map-executable ")
    assert '(subpath "/System")' not in profile
    assert '(allow file-write* (subpath (param "PATH_0")) (subpath (param "PATH_1")))' in profile
    assert "(deny network*)" in profile
    assert "(allow network" not in profile
    assert args[:2] == [f"-DPATH_0={work}", f"-DPATH_1={temp}"]
    assert args[-3:] == ["--", "/bin/echo", "-p"]


def test_profile_can_use_a_read_only_worktree_and_explicit_ip_network(layout, launcher):
    work, temp = layout
    profile = SeatbeltSandbox().filesystem_argv(
        ["true"], worktree=work, step_tmp=temp, writable_worktree=False, allow_network=True
    )[2]

    assert '(allow file-write* (subpath (param "PATH_1")))' in profile
    assert '(allow file-write* (subpath (param "PATH_0"))' not in profile
    assert '(allow network-outbound (remote ip "*:*"))' in profile
    assert '(allow network-inbound network-bind (local ip "*:*"))' in profile
    assert "(deny network*)" not in profile


def test_hookd_runtime_is_excluded_even_with_ip_network(layout, launcher, monkeypatch):
    work, tmp = layout
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp / "runtime"))
    with pytest.raises(CapabilityUnavailable, match="overlaps hookd runtime"):
        SeatbeltSandbox().filesystem_argv(["true"], worktree=work, step_tmp=tmp, allow_network=True)


def test_path_aliases_are_canonicalized_and_special_characters_stay_out_of_sbpl(layout, launcher):
    work, temp = layout
    unusual = work.with_name('w") (allow default) \\ = café')
    work.rename(unusual)
    alias = work.with_name("worktree-alias")
    alias.symlink_to(unusual, target_is_directory=True)
    command = SeatbeltSandbox().filesystem_argv(["true"], worktree=alias, step_tmp=temp)

    assert "allow default" not in command[2]
    assert f"-DPATH_0={unusual}" in command
    assert not any(str(alias) in item for item in command)
    with pytest.raises(CapabilityUnavailable, match="absolute path"):
        SeatbeltSandbox().filesystem_argv(["true"], worktree=Path("relative"), step_tmp=temp)


def test_protected_git_state_and_ancestor_rules(layout, launcher):
    work, temp = layout
    git_dir = work / "linked-metadata"
    git_dir.mkdir()
    (work / ".git").write_text(f"gitdir: {git_dir}\n")
    (git_dir / "commondir").write_text("../common-metadata\n")
    protected = work / "internal" / "private"
    protected.mkdir(parents=True)
    alias = temp / "link"
    alias.symlink_to(protected, target_is_directory=True)
    command = SeatbeltSandbox().filesystem_argv(["true"], worktree=work, step_tmp=temp, protected=(alias,))
    profile = command[2].splitlines()
    keys = {value: key.removeprefix("-D") for key, value in (arg.split("=", 1) for arg in command[3:-2])}

    write_grant = next(i for i, line in enumerate(profile) if line.startswith("(allow file-write* "))
    for path in (work / ".git", git_dir, work / "common-metadata"):
        assert profile.index(f'(deny file-write* (subpath (param "{keys[str(path)]}")))') > write_grant
    for path in (protected, alias):
        assert (
            f'(deny file-read* file-write* file-map-executable (subpath (param "{keys[str(path)]}")))'
            in profile
        )
    assert f'(deny file-write-unlink (literal (param "{keys[str(protected.parent)]}")))' in profile
    state_rule = next(line for line in profile if line.startswith("(deny file-write* (regex "))
    assert "[Gg][Ii][Tt]" in state_rule
    assert "[Ss][Kk][Mm]" in state_rule
    assert "[Ss][Ww][Ii][Ss][Ss][Kk][Nn][Ii][Ff][Ee][Mm][Aa][Nn]" in state_rule


def test_step_tmp_must_be_private_and_disjoint(layout, launcher):
    work, temp = layout
    sandbox = SeatbeltSandbox()
    with pytest.raises(CapabilityUnavailable, match="disjoint"):
        sandbox.filesystem_argv(["true"], worktree=work, step_tmp=work)
    temp.chmod(0o755)
    with pytest.raises(CapabilityUnavailable, match="private"):
        sandbox.filesystem_argv(["true"], worktree=work, step_tmp=temp)


@pytest.mark.parametrize(("platform", "reason"), [("linux", "macOS is required"), ("darwin", "is missing")])
def test_unavailable_launcher_fails_closed(layout, tmp_path, monkeypatch, platform, reason):
    work, temp = layout
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(seatbelt, "_BINARY", tmp_path / "missing-sandbox-exec")

    registered = build_isolation_registry().get("skm:seatbelt")
    assert isinstance(registered, SeatbeltSandbox)
    sandbox = SeatbeltSandbox()
    response = sandbox.available()
    assert response["available"] is False
    assert response["verification_status"] == "unverified"
    assert reason in str(response["reason"])
    with pytest.raises(CapabilityUnavailable) as refused:
        sandbox.filesystem_argv(["true"], worktree=work, step_tmp=temp)
    assert refused.value.code.value == "SANDBOX_UNAVAILABLE"


def test_available_launcher_does_not_prove_enforcement(layout, launcher):
    from security.test_sandbox_profiles import make_owner

    work, temp = layout
    spec = IsolationSpec(work, (), (work, temp), (), True, "none", (), {}, None, (), make_owner())
    sandbox = SeatbeltSandbox()
    assert sandbox.available() == {"available": True, "verification_status": "unverified"}
    assert sandbox.proven(spec) == {}
    with pytest.raises(CapabilityUnavailable, match="no enforcing backend"):
        sandbox.wrap(["true"], spec)
