"""The CLI bypasses the control plane and persists local privacy state."""

from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import Never
from unittest.mock import Mock
from uuid import UUID

import pytest

from fakes.ids import SequentialIds
from skm.bootstrap import local_execution
from skm.entrypoints.cli.main import main
from skm.kernel.ids import RunId
from skm.modules.runtimes.public import AgentRequest


def _no_backend(*_args: object) -> Never:
    pytest.fail("local command opened a control plane")


def test_ephemeral_cli_uses_an_isolated_fresh_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = Mock(runtime_id="codex")
    runtime.events.return_value = iter(())
    runtime.result.return_value = SimpleNamespace(failure=None, final_text="answer")
    monkeypatch.setattr(local_execution, "RUNTIME_FACTORIES", {"codex": lambda **_kwargs: runtime})
    monkeypatch.chdir(tmp_path)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("local prompt", encoding="utf-8")
    stdout = StringIO()
    assert (
        main(
            ["run", "local", "--ephemeral", "--model", "local-test-model", str(prompt)],
            stdout=stdout,
            environ={"XDG_STATE_HOME": str(tmp_path)},
            backend=_no_backend,
        )
        == 0
    )
    request: AgentRequest = runtime.start.call_args.args[0]
    assert request.session_policy == "ephemeral"
    assert request.resume_session_ref is None
    assert request.rendered_prompt == "local prompt"
    assert request.prompt_digest.startswith("sha256:")
    assert not request.permissions.fs_write.allow
    assert request.client_home is not None
    assert not Path(request.client_home).exists()
    assert stdout.getvalue() == "answer\n"


@pytest.mark.parametrize("ephemeral", [True, False])
def test_local_run_records_host_private_consumption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ephemeral: bool
) -> None:
    env = {"XDG_STATE_HOME": str(tmp_path)}
    run_id = RunId(UUID("01900000-0000-7000-8000-000000000001"))
    run = local_execution.LocalRun(local_execution.local_run_root(env, tmp_path), run_id)
    episode = "private episode bytes"
    if ephemeral:
        runtime = Mock(runtime_id="codex")
        runtime.events.return_value = iter(())
        runtime.result.return_value = SimpleNamespace(failure=None, final_text="answer")
        monkeypatch.setattr(local_execution, "RUNTIME_FACTORIES", {"codex": lambda **_kwargs: runtime})
        local_execution.run_ephemeral(
            run,
            "task",
            model="local-test-model",
            workdir=tmp_path,
            environ=env,
            ids=SequentialIds(),
            host_private_episodes=(episode,),
        )
        assert episode in runtime.start.call_args.args[0].rendered_prompt
    else:
        run.mark_host_private_consumed()
    marker = run.root / str(run_id) / "host-private"
    assert marker.read_bytes() == b"HOST_PRIVATE\n"
    assert marker.stat().st_mode & 0o777 == 0o600


def test_removed_run_sync_never_opens_a_control_plane() -> None:
    stdout, stderr = StringIO(), StringIO()
    assert (
        main(
            ["sync", "push", str(UUID(int=1))],
            environ={},
            stdout=stdout,
            stderr=stderr,
            backend=_no_backend,
        )
        == 2
    )
    assert "unrecognized arguments: sync" in stderr.getvalue()
    assert not stdout.getvalue()
