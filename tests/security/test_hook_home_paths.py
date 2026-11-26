"""The interactive hook resolves ``~`` to the agent's home, never to a directory inside the worktree."""

from collections.abc import Callable
from pathlib import Path

import pytest

from skm.adapters.git.hook_state import LocalHookState
from skm.modules.policy.domain.calls import FileWrite, RunCommand, ToolCall
from skm.modules.policy.domain.paths import ScopeRoots
from skm.modules.policy.domain.tool_call import Allow, EnforcementMode, check_tool_call
from unit.policy.domain.conftest import perms_of
from unit.policy.domain.layout import EMPTY


@pytest.fixture
def layout(tmp_path: Path) -> tuple[LocalHookState, Path, Path]:
    home = tmp_path / "home"
    worktree = tmp_path / "repo"
    (home / ".ssh").mkdir(parents=True)
    (worktree / "src").mkdir(parents=True)
    state = LocalHookState(tmp_path / "state", lambda _name, payload: payload, home=str(home))
    return state, home.resolve(), worktree.resolve()


def test_tilde_expands_to_the_home_directory(layout: tuple[LocalHookState, Path, Path]) -> None:
    state, home, worktree = layout
    assert state.resolve("~/.bashrc", str(worktree)) == str(home / ".bashrc")
    assert state.resolve("~", str(worktree / "src")) == str(home)
    assert state.facts(str(worktree)).resolve("~/.ssh/authorized_keys", str(worktree)) == str(
        home / ".ssh/authorized_keys"
    )
    # Only a leading ``~`` is the shell's home; elsewhere it is an ordinary path segment.
    assert state.resolve("src/~/x", str(worktree)) == str(worktree / "src/~/x")
    assert state.resolve("~user/x", str(worktree)) == str(worktree / "~user/x")


def test_default_home_comes_from_the_hook_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    state = LocalHookState(tmp_path / "state", lambda _name, payload: payload)
    assert state.home == str(tmp_path.resolve())


@pytest.mark.parametrize(
    "call",
    [
        lambda wt: RunCommand("echo x >> ~/.bashrc", wt),
        lambda wt: RunCommand("cp key ~/.ssh/authorized_keys", wt),
        lambda wt: FileWrite("~/.bashrc"),
    ],
    ids=["append-bashrc", "copy-authorized-keys", "write-bashrc"],
)
def test_home_writes_are_not_allowed_by_the_safe_dirs_check(
    layout: tuple[LocalHookState, Path, Path], call: Callable[[str], ToolCall]
) -> None:
    state, home, worktree = layout
    decision = check_tool_call(
        perms_of("workspace-contained"),
        call(str(worktree)),
        roots=ScopeRoots({"main": str(worktree)}, None, None, state.home, (), (), frozenset()),
        facts=state.facts(str(worktree)),
        authority=EMPTY,
        mode=EnforcementMode.INTERACTIVE,
    )
    assert not isinstance(decision, Allow), decision
    assert str(home) in repr(decision)
