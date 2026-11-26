"""Malformed inputs, outages, foreign cwd and symlink cache attacks fail closed."""

import json
import threading
from pathlib import Path
from typing import Any

import pytest

from integration.integrations.test_hooks import env, hook_env, request
from skm.adapters.git.hook_state import LocalHookState
from skm.bootstrap.hook import unavailable_context
from skm.modules.integrations.host.evaluate_hook import run
from skm.modules.integrations.host.hook_state import HookState
from support.pg import clean_test_database, pg_session, test_database

__all__ = ["clean_test_database", "env", "hook_env", "pg_session", "test_database"]


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"tool_name": "Bash", "tool_input": {}},
        {"cwd": "/repo", "tool_name": "Bash", "tool_input": {"command": "x" * 1_048_576}},
    ],
)
@pytest.mark.parametrize(
    "surface",
    [
        "lifecycle.git_guardrails",
        "security.safe_dirs",
        "lifecycle.plan_guard",
        "lifecycle.pack_guard",
        "lifecycle.changelog_gate",
    ],
)
def test_malformed_enforcement_payload_is_denied(payload: Any, surface: str) -> None:
    result = run(
        unavailable_context(),
        {
            "target": "claude_code",
            "surface": surface,
            "project_id": "01900000-0000-7000-8000-000000000001",
            "event_name": "PreToolUse",
            "payload": payload,
        },
    )
    assert result["verdict"] == "deny"
    assert result.get("reason_code") == "HOOK_PAYLOAD_INVALID"


@pytest.mark.parametrize(
    "surface", ["lifecycle.command_log", "context.session_start", "lifecycle.run_report"]
)
def test_malformed_observation_and_workflow_skip(surface: str) -> None:
    result = run(
        unavailable_context(),
        {
            "target": "codex",
            "surface": surface,
            "project_id": "01900000-0000-7000-8000-000000000001",
            "event_name": "PreToolUse",
            "payload": {},
        },
    )
    assert result["verdict"] == "none"
    assert result["client_output"]["exit_code"] == 0


def test_unavailable_backend_denies_without_payload_disclosure(hook_env: Any) -> None:
    req = request(hook_env, command="echo PRIVATE_TOKEN")
    result = run(unavailable_context(), req)
    assert result.get("reason_code") == "HOOK_BACKEND_UNAVAILABLE"
    assert result["verdict"] == "deny"
    assert "PRIVATE_TOKEN" not in json.dumps(result)


def test_foreign_checkout_fails_even_with_warm_cache(hook_env: Any, tmp_path: Path) -> None:
    req = request(hook_env, command="git status")
    assert run(hook_env.ctx, req)["verdict"] == "none"
    req["payload"]["cwd"] = str(tmp_path)
    assert run(hook_env.ctx, req)["verdict"] == "deny"


def test_timeout_is_bounded_without_executing_shell_payload(tmp_path: Path) -> None:
    state = LocalHookState(tmp_path, lambda name, data: data)
    done = threading.Event()
    try:
        with pytest.raises(TimeoutError):
            state.call(lambda: done.wait(5), 10)
    finally:
        done.set()


def test_cache_symlinks_are_not_read_or_overwritten(hook_env: Any, tmp_path: Path) -> None:
    env = hook_env
    assert run(env.ctx, request(env))["verdict"] == "deny"
    cache = env.state_dir / "hooks" / f"{env.project_id}-claude_code.json"
    victim = tmp_path / "victim"
    victim.write_text("do not overwrite")
    cache.unlink()
    cache.symlink_to(victim)
    assert run(env.ctx, request(env))["verdict"] == "deny"
    assert victim.read_text() == "do not overwrite"


def test_audit_symlink_does_not_modify_foreign_file(hook_env: Any, tmp_path: Path) -> None:
    env = hook_env
    state = env.ctx.gateways.get(HookState)
    state.folder.mkdir(mode=0o700, parents=True)
    victim = tmp_path / "victim"
    victim.write_text("untouched")
    (state.folder / "audit.jsonl").symlink_to(victim)
    assert run(env.ctx, request(env))["verdict"] == "deny"
    assert victim.read_text() == "untouched"


def test_audit_append_does_not_wait_for_backend_delivery(tmp_path: Path) -> None:
    state = LocalHookState(tmp_path, lambda name, data: data)
    project = "01900000-0000-7000-8000-000000000001"
    state.audit(project, "lifecycle.git_guardrails", "GIT_GUARDRAILS")
    entered, release, appended = threading.Event(), threading.Event(), threading.Event()

    class Client:
        def dispatch(self, *args: Any, **kwargs: Any) -> None:
            entered.set()
            release.wait(5)

    def append() -> None:
        state.audit(project, "lifecycle.plan_guard", "MANAGED_FILE")
        appended.set()

    drain = threading.Thread(target=lambda: state.flush(Client()), daemon=True)
    drain.start()
    assert entered.wait(5)
    writer = threading.Thread(target=append, daemon=True)
    writer.start()
    try:
        assert appended.wait(1), "audit append waited for a backend response"
    finally:
        release.set()
        drain.join(5)
        writer.join(5)
    remaining = (state.folder / "audit.jsonl").read_text()
    assert "MANAGED_FILE" in remaining
    assert "GIT_GUARDRAILS" not in remaining


def test_safe_dirs_blocks_deletion_outside_checkout(hook_env: Any) -> None:
    result = run(hook_env.ctx, request(hook_env, surface="security.safe_dirs", command="rm -rf ../outside"))
    assert result["verdict"] == "deny"


def test_plan_guard_resolves_shell_symlink(hook_env: Any) -> None:
    env = hook_env
    (env.checkout_dir / "alias").symlink_to(env.checkout_dir / ".skm", target_is_directory=True)
    result = run(env.ctx, request(env, surface="lifecycle.plan_guard", command="echo x > alias/project.json"))
    assert result["verdict"] == "deny"
    assert json.loads((env.checkout_dir / ".skm/project.json").read_text())["project_id"] == str(
        env.project_id
    )


def test_pack_guard_uses_managed_paths_from_cached_policy(hook_env: Any) -> None:
    env = hook_env
    assert run(env.ctx, request(env, command="git status"))["verdict"] == "none"
    state = env.ctx.gateways.get(HookState)
    policy = state.load(str(env.project_id), "claude_code")
    assert policy is not None
    policy["managed_file_paths"] = ["generated.md"]
    policy["hook_modes"]["pack_guard"] = "strict"
    state.save(str(env.project_id), "claude_code", policy)
    result = run(env.ctx, request(env, surface="lifecycle.pack_guard", command="echo x > generated.md"))
    assert result["verdict"] == "deny"
    assert not (env.checkout_dir / "generated.md").exists()


def test_a_checkout_without_its_marker_is_denied_with_a_distinct_reason(hook_env: Any) -> None:
    req = request(hook_env, command="ls")
    assert run(hook_env.ctx, req)["verdict"] == "none"
    # Scenario: `skm repo bind` without --write-marker. Before, this read as an unreachable backend.
    (hook_env.checkout_dir / ".skm/project.json").unlink()
    result = run(hook_env.ctx, req)
    assert result["verdict"] == "deny"
    assert result.get("reason_code") == "HOOK_BACKEND_UNAVAILABLE"
    assert result.get("user_message") == "skm hook: HOOK_BACKEND_UNAVAILABLE (checkout_marker_missing)"
    assert str(hook_env.checkout_dir) not in json.dumps(result)


def test_a_marker_of_another_project_is_denied_as_a_mismatch(hook_env: Any) -> None:
    req = request(hook_env, command="ls")
    marker = hook_env.checkout_dir / ".skm/project.json"
    document = json.loads(marker.read_text())
    document["project_id"] = "01900000-0000-7000-8000-000000000001"
    marker.write_text(json.dumps(document))
    result = run(hook_env.ctx, req)
    assert result["verdict"] == "deny"
    assert str(result.get("user_message")).endswith("(checkout_marker_mismatch)")
