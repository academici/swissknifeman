"""AGY translation must not turn mismatched or interrupted runs into success."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

spec = spec_from_file_location("agy_transport", Path(__file__).resolve().parents[1] / "scripts/agy-transport.py")
module = module_from_spec(spec)
spec.loader.exec_module(module)


def test_success_keeps_observed_model_session_and_usage():
    state = {}
    init = {"event": "init", "conversation_id": "s", "init": {"model": "claude-sonnet-5-5"}}
    end = {"event": "result", "result": {"conversation_id": "s", "status": "SUCCESS", "response": "ok",
           "usage": {"input_tokens": 100, "cache_read_tokens": 80, "output_tokens": 3}}}
    assert module.event(init, "claude-sonnet-5-5", state)["model"] == "claude-sonnet-5-5"
    result = module.event(end, "claude-sonnet-5-5", state)
    assert result["session_id"] == "s" and result["is_error"] is False
    assert result["usage"]["cached_input_tokens"] == 80


def test_mismatched_model_or_session_cannot_emit_success():
    state = {}
    assert module.event({"event": "init", "conversation_id": "s", "init": {"model": "other"}},
                        "claude-sonnet-5-5", state) is None
    assert module.event({"event": "result", "result": {"conversation_id": "s", "status": "SUCCESS",
                         "response": "ok"}}, "claude-sonnet-5-5", state) is None
    assert state["invalid"]


def test_error_and_terminal_without_init():
    state = {}
    result = {"event": "result", "result": {"conversation_id": "s", "status": "ERROR", "response": ""}}
    assert module.event(result, "claude-sonnet-5-5", state) is None
    state = {}
    module.event({"event": "init", "conversation_id": "s", "init": {"model": "claude-sonnet-5-5"}},
                 "claude-sonnet-5-5", state)
    assert module.event(result, "claude-sonnet-5-5", state)["is_error"] is True


def test_bridge_delivers_prompt_and_preserves_provider_events(tmp_path):
    import json
    import os
    import subprocess
    import sys

    executable = tmp_path / "agy"
    executable.write_text('''#!/usr/bin/env python3
import json, sys
msg = json.loads(sys.stdin.readline())
assert msg["message"]["content"] == "content with \\n and quotes"
print(json.dumps({"event":"init","conversation_id":"s","init":{"model":"claude-sonnet-5-5"}}))
print(json.dumps({"event":"result","result":{"conversation_id":"s","status":"SUCCESS","response":"ok"}}))
''')
    executable.chmod(0o755)
    env = dict(os.environ, PATH=str(tmp_path) + os.pathsep + os.environ["PATH"])
    command = [sys.executable, str(Path(module.__file__)), "--model", "claude-sonnet-5-5", "--effort", "high"]
    result = subprocess.run(command, input="content with \n and quotes", env=env, text=True, capture_output=True,
                            check=True)
    rows = [json.loads(row) for row in result.stdout.splitlines()]
    assert rows[0]["event"] == "init"
    assert rows[1]["type"] == "system"
    assert rows[2]["event"] == "result"
    assert rows[3]["type"] == "result"


def test_guard_requires_expected_mode_and_narrow_roots(tmp_path, monkeypatch):
    from orch.conductor.infrastructure.launch_plan import ORCH_ROOT, agy_guarded

    monkeypatch.setenv("HOME", str(tmp_path))
    root = str(tmp_path / "work")
    common = ["python3", str(ORCH_ROOT / "scripts" / "ro-run.py"), "--no-default-rw"]
    tail = ["--rw", "/dev", "--", "python3", str(ORCH_ROOT / "scripts" / "agy-transport.py")]
    assert agy_guarded(common + ["--rw", root] + tail, root, True)
    assert agy_guarded(common + ["--protect", root] + tail, root, False)
    assert not agy_guarded(common + ["--rw", root] + tail, root, False)
    assert not agy_guarded(common + ["--rw", root, "--rw", "/"] + tail, root, True)
    assert not agy_guarded(["python3", "bridge"], root, True)


def test_each_agent_uses_its_own_home(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from orch.conductor.infrastructure import launch_plan

    monkeypatch.setattr(launch_plan, "isolation_plan", lambda *args, **kwargs: {"env": {}, "home": None})
    owner = SimpleNamespace(env={"HOME": "/personal", "XDG_CONFIG_HOME": "/personal/config"},
                            directory=tmp_path, _local=SimpleNamespace(agent={"directory": tmp_path / "agent-a"}))
    one = launch_plan.role_env(owner, object(), "executor", {"provider": "antigravity"})
    owner._local.agent = {"directory": tmp_path / "agent-b"}
    two = launch_plan.role_env(owner, object(), "executor", {"provider": "antigravity"})
    assert one["HOME"] != two["HOME"]
    assert one["HOME"] == str(tmp_path / "agent-a" / "tmp")
    assert one["XDG_CONFIG_HOME"].startswith(one["HOME"] + "/")
    assert two["HOME"] == str(tmp_path / "agent-b" / "tmp")


def test_authority_refuses_network_docker_and_unmasked_host_reads():
    from orch.conductor.infrastructure.launch_plan import agy_authority_problem
    doc = {"network": {"declared": "none", "effective": "open"}, "docker": "open", "read_masks": "none"}
    assert "network" in agy_authority_problem(doc)
    doc["network"]["effective"] = "none"
    assert "Docker" in agy_authority_problem(doc)
    doc["docker"] = "blocked"
    assert "read masks" in agy_authority_problem(doc)
    doc["read_masks"] = "provider-settings"
    assert agy_authority_problem(doc) is None


def test_unknown_agy_model_class_does_not_inherit_stage_class():
    from types import SimpleNamespace
    from aicore.provider.models import load_model_catalog
    from orch.conductor.application.route_service import named_model_class
    from orch.conductor.domain.stop import Stop
    import pytest

    owner = SimpleNamespace(_catalog_get=lambda: SimpleNamespace(models=load_model_catalog()))
    chosen = {"provider": "antigravity", "model": "gemini-4-argon", "model_class": "frontier"}
    for requested in (None, "gemini-4-argon"):
        with pytest.raises(Stop, match="no verified Antigravity model class"):
            named_model_class(owner, object(), "executor", {"model": requested}, chosen)


def test_missing_agy_model_cannot_inherit_stage_class():
    from orch.conductor.application.route_service import named_model_class
    from orch.conductor.domain.stop import Stop
    import pytest

    for model in (None, ""):
        chosen = {"provider": "antigravity", "model": model, "model_class": "frontier"}
        with pytest.raises(Stop, match="model ID is missing"):
            named_model_class(object(), object(), "executor", {"model": None}, chosen)
