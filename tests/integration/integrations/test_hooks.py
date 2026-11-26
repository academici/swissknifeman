"""Real bus, PostgreSQL/memory, filesystem cache and native hook protocols."""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from fixtures.hooks.subprocess.harness import memory_daemon, native_invocation, runtime_environment
from integration.integrations.test_host_projection import env
from skm.adapters.git.runner import GitRunner
from skm.bootstrap.hook import evaluate, with_hook_state, write_output
from skm.kernel.errors import Forbidden, Unauthenticated
from skm.modules.integrations.application.queries.get_hook_policy import GetHookPolicy
from skm.modules.integrations.host.evaluate_hook import run
from skm.modules.integrations.host.hook_state import HookState
from skm.modules.settings.generated.commands import SetValue
from skm.modules.workspace.public import ResolveCheckout
from skm.platform.process.runner import ProcessResult
from support.pg import clean_test_database, pg_session, test_database

__all__ = ["clean_test_database", "env", "pg_session", "test_database"]


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        [
            shutil.which("git") or "/usr/bin/git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "-C",
            str(root),
            *args,
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    ).stdout.strip()


@pytest.fixture
def git_plumbing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run real Git facts on the fixture checkout without requiring process ownership support."""

    def execute(
        _runner: GitRunner,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        timeout_s: float,
        stdin: bytes | None = None,
    ) -> ProcessResult:
        assert cwd.is_relative_to(tmp_path)
        started = time.monotonic()
        result = subprocess.run(
            argv, cwd=cwd, env=env, timeout=timeout_s, input=stdin, capture_output=True, check=False
        )
        return ProcessResult(
            argv=tuple(argv),
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            timed_out=False,
            stdout_truncated=False,
            stderr_truncated=False,
            duration_seconds=time.monotonic() - started,
            signal=-result.returncode if result.returncode < 0 else None,
        )

    monkeypatch.setattr(GitRunner, "_execute", execute)


@pytest.fixture
def hook_env(env: Any) -> Any:
    git(env.checkout_dir, "init", "--quiet")
    (env.checkout_dir / "src").mkdir()
    (env.checkout_dir / "src/app.py").write_text("one\n")
    git(env.checkout_dir, "add", "src/app.py")
    git(env.checkout_dir, "commit", "-qm", "initial")
    location = env.client.ask(ResolveCheckout(env.project_id, "main", env.ctx.host_id))
    marker = {
        "schema": "urn:skm:workspace:checkout-marker:v1",
        "instance_id": str(env.app.instance_id),
        "workspace_id": str(env.ws_id),
        "project_id": str(env.project_id),
        "repository_id": str(location.repository_id),
        "mount_name": "main",
    }
    (env.checkout_dir / ".skm").mkdir(exist_ok=True)
    (env.checkout_dir / ".skm/project.json").write_text(json.dumps(marker))
    env.ctx = with_hook_state(env.ctx, env.state_dir)
    env.client.ask(GetHookPolicy.from_json({"project_id": str(env.project_id), "target": "claude_code"}))
    return env


def request(
    env: Any,
    surface: str = "lifecycle.git_guardrails",
    command: str = "git reset --hard",
    target: str = "claude_code",
) -> dict[str, Any]:
    payload: dict[str, Any] = {"cwd": str(env.checkout_dir), "session_id": "test-session"}
    event_name = "PreToolUse"
    if target == "cursor":
        event_name = "beforeShellExecution"
        payload["command"] = command
        payload.update(hook_event_name=event_name, conversation_id="conversation-1")
    else:
        payload.update(
            tool_name="Bash",
            tool_input={"command": command},
            hook_event_name=event_name,
            model="test",
            source="cli",
        )
        if target == "grok":
            payload = {
                "hookEventName": event_name,
                "sessionId": "test-session",
                "cwd": str(env.checkout_dir),
                "toolName": "Bash",
                "toolInput": {"command": command},
            }
    return {
        "target": target,
        "surface": surface,
        "project_id": str(env.project_id),
        "event_name": event_name,
        "payload": payload,
    }


@pytest.mark.parametrize("target", ["claude_code", "codex", "cursor", "grok"])
def test_native_denial_and_no_permission_escalation(hook_env: Any, target: str) -> None:
    result = run(hook_env.ctx, request(hook_env, target=target))
    assert result.get("reason_code") == "GIT_GUARDRAILS"
    assert result["verdict"] == "deny"
    output = result["client_output"]
    if target in {"codex", "grok"}:
        assert output["exit_code"] == 2
        assert output["stdout"] == ""
    elif target == "cursor":
        assert output["stdout"]["permission"] == "deny"
    else:
        assert output["stdout"]["hookSpecificOutput"]["permissionDecision"] == "deny"
    clean = run(hook_env.ctx, request(hook_env, command="git status", target=target))
    assert clean["verdict"] == "none"
    assert clean["client_output"]["exit_code"] == 0
    if target != "cursor":
        assert clean["client_output"]["stdout"] == ""


@pytest.mark.parametrize("env", ["memory"], indirect=True)
def test_bound_hook_uses_checkout_inside_untrusted_outer_repository(hook_env: Any) -> None:
    outer = hook_env.checkout_dir.parent
    (outer / ".git").symlink_to(hook_env.checkout_dir / ".git", target_is_directory=True)
    assert run(hook_env.ctx, request(hook_env)).get("reason_code") == "GIT_GUARDRAILS"

    subdir = hook_env.checkout_dir / "subdir"
    subdir.mkdir()
    (subdir / "HEAD").write_text("ordinary project data")
    (subdir / "objects").mkdir()
    req = request(hook_env)
    req["payload"]["cwd"] = str(subdir)
    assert run(hook_env.ctx, req).get("reason_code") == "GIT_GUARDRAILS"

    nested = hook_env.checkout_dir / "nested"
    bare = hook_env.checkout_dir / "bare"
    for path, options in ((nested, ()), (bare, ("--bare",))):
        path.mkdir()
        git(path, "init", "--quiet", *options)
        req = request(hook_env)
        req["payload"]["cwd"] = str(path)
        assert run(hook_env.ctx, req).get("reason_code") == "HOOK_BACKEND_UNAVAILABLE"


@pytest.mark.usefixtures("git_plumbing")
def test_bound_git_does_not_discover_parent_if_its_metadata_is_invalid(tmp_path: Path) -> None:
    git(tmp_path, "init", "--quiet")
    checkout = tmp_path / "checkout"
    (checkout / ".git").mkdir(parents=True)
    assert git(checkout, "rev-parse", "--show-toplevel") == str(tmp_path)
    result = GitRunner(checkout_root=checkout).run(checkout, ("rev-parse", "--show-toplevel"), check=False)
    assert result.exit_code == 128
    assert result.stdout == ""


@pytest.mark.usefixtures("git_plumbing")
def test_bound_git_uses_linked_worktree_metadata(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    git(source, "init", "--quiet")
    git(source, "commit", "--allow-empty", "-qm", "initial")
    linked = tmp_path / "linked"
    git(source, "worktree", "add", "--quiet", "--detach", str(linked))
    assert (linked / ".git").is_file()
    runner = GitRunner(checkout_root=linked)
    assert runner.run(linked, ("rev-parse", "HEAD")).stdout.strip() == git(source, "rev-parse", "HEAD")


def set_modes(env: Any, **modes: str) -> None:
    env.client.dispatch(
        SetValue.from_json(
            {
                "scope": {"level": "project", "scope_id": str(env.project_id)},
                "key": "integrations.hooks.mode",
                "value": modes,
            }
        ),
        idempotency_key=env.client.new_idempotency_key(),
    )
    state = env.ctx.gateways.get(HookState)
    path = state.folder / f"{env.project_id}-claude_code.json"
    if path.exists():
        path.unlink()


def test_generation_ttl_refresh_and_expired_cache_outage(
    hook_env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = hook_env.ctx.gateways.get(HookState)
    first = run(hook_env.ctx, request(hook_env))
    assert first["verdict"] == "deny"
    cached = state.load(str(hook_env.project_id), "claude_code")
    assert cached is not None
    original_generation = cached["generation"]
    # A live config change is observed after TTL, even by a new process/state adapter.
    hook_env.client.dispatch(
        SetValue.from_json(
            {
                "scope": {"level": "project", "scope_id": str(hook_env.project_id)},
                "key": "integrations.hooks.mode",
                "value": {"git_guardrails": "warn"},
            }
        ),
        idempotency_key=hook_env.client.new_idempotency_key(),
    )
    assert run(hook_env.ctx, request(hook_env))["verdict"] == "deny"
    original_time = time.time
    monkeypatch.setattr(time, "time", lambda: original_time() + 60)
    assert run(hook_env.ctx, request(hook_env))["verdict"] == "warn"
    assert state.load(str(hook_env.project_id), "claude_code")["generation"] > original_generation


@pytest.mark.usefixtures("git_plumbing")
def test_managed_state_symlink_and_changelog_gate(hook_env: Any) -> None:
    env = hook_env
    set_modes(env, plan_guard="strict", pack_guard="strict", changelog_gate="strict")
    (env.checkout_dir / "alias").symlink_to(env.checkout_dir / ".skm", target_is_directory=True)
    req = request(env, surface="lifecycle.plan_guard")
    req["payload"].update(
        tool_name="Edit", tool_input={"file_path": str(env.checkout_dir / "alias/project.json")}
    )
    assert run(env.ctx, req)["verdict"] == "deny"
    (env.checkout_dir / "src/app.py").write_text("two\n")
    git(env.checkout_dir, "add", "src/app.py")
    req = request(env, surface="lifecycle.changelog_gate", command="git commit -m 'feat: next'")
    assert run(env.ctx, req).get("reason_code") == "CHANGELOG_REQUIRED"
    (env.checkout_dir / "CHANGELOG.md").write_text("next\n")
    git(env.checkout_dir, "add", "CHANGELOG.md")
    assert run(env.ctx, req)["verdict"] == "none"


def test_audit_is_private_redacted_and_drains_on_next_success(
    hook_env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = hook_env
    assert run(env.ctx, request(env, command="TOKEN=very-secret git reset --hard"))["verdict"] == "deny"
    path = env.state_dir / "hooks/audit.jsonl"
    raw = path.read_text()
    assert "very-secret" not in raw
    assert "GIT_GUARDRAILS" in raw
    assert path.stat().st_mode & 0o077 == 0
    state = env.ctx.gateways.get(HookState)
    completed = threading.Event()
    flush = state.flush

    def deliver(client: Any) -> None:
        try:
            flush(client)
        finally:
            completed.set()

    monkeypatch.setattr(state, "flush", deliver)
    assert run(env.ctx, request(env, command="git status"))["verdict"] == "none"
    assert completed.wait(5), "next successful hook did not finish audit delivery"
    assert path.read_text() == ""


def test_stream_evaluator_uses_same_native_output(hook_env: Any) -> None:
    req = request(hook_env)
    args = argparse.Namespace(
        target=req["target"], surface=req["surface"], project=req["project_id"], event_name=req["event_name"]
    )
    result = evaluate(args, io.StringIO(json.dumps(req["payload"])), hook_env.ctx)
    stdout, stderr = io.StringIO(), io.StringIO()
    assert write_output(result, stdout, stderr) == 0
    assert json.loads(stdout.getvalue())["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert stderr.getvalue() == ""


@pytest.mark.parametrize("entrypoint", ["hook", "cli"])
def test_subprocess_backend_failure_is_native_and_does_not_echo_secrets(
    tmp_path: Path, entrypoint: str
) -> None:
    raw = json.dumps(
        {
            "cwd": str(tmp_path),
            "session_id": "test-session",
            "hook_event_name": "PreToolUse",
            "model": "test",
            "source": "cli",
            "tool_name": "Bash",
            "tool_input": {"command": "echo secret-value"},
        }
    )
    with runtime_environment(os.environ) as environ:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "skm.entrypoints." + entrypoint + ".main",
                *(["hook"] if entrypoint == "cli" else []),
                "PreToolUse",
                "--target",
                "codex",
                "--surface",
                "lifecycle.git_guardrails",
                "--project",
                "01900000-0000-7000-8000-000000000001",
            ],
            input=raw,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
            env=environ,
        )
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert "HOOK_BACKEND_UNAVAILABLE" in proc.stderr
    assert "secret-value" not in proc.stderr


def test_hook_policy_uses_bus_project_permission(hook_env: Any) -> None:
    # A principal with no project membership must not acquire cached policy data.
    from uuid import UUID

    from skm.kernel.actor import Actor, PrincipalKind
    from skm.kernel.ids import PrincipalId
    from skm.kernel.ports_uow import Surface

    client = hook_env.app.client(
        surface=Surface.HOOK, actor=Actor(PrincipalId(UUID(int=42)), PrincipalKind.HUMAN, "stranger")
    )
    with pytest.raises((Forbidden, Unauthenticated)):
        client.ask(GetHookPolicy.from_json({"project_id": str(hook_env.project_id), "target": "claude_code"}))


@pytest.mark.parametrize(
    ("target", "example", "command"),
    [
        ("claude_code", "claude-pre-tool-use", "git push --force origin main"),
        ("grok", "grok-pre-tool-use", "git status"),
    ],
)
def test_normative_hook_output(hook_env: Any, target: str, example: str, command: str) -> None:
    examples = (
        Path(__file__).resolve().parents[3] / "tests/fixtures/corpus/examples/integrations/hook-payloads"
    )
    expected = json.loads((examples / (example + ".decision.json")).read_text())
    result = run(hook_env.ctx, request(hook_env, target=target, command=command))
    assert result["client_output"] == expected["client_output"]


@pytest.mark.parametrize("flag", ["-F message.txt", "--file=message.txt"])
@pytest.mark.usefixtures("git_plumbing")
def test_changelog_gate_reads_commit_message_file(hook_env: Any, flag: str) -> None:
    env = hook_env
    set_modes(env, changelog_gate="strict")
    (env.checkout_dir / "src/app.py").write_text("new code\n")
    git(env.checkout_dir, "add", "src/app.py")
    (env.checkout_dir / "message.txt").write_text("feat: from file\n")
    req = request(env, surface="lifecycle.changelog_gate", command="git commit " + flag)
    assert run(env.ctx, req).get("reason_code") == "CHANGELOG_REQUIRED"
    (env.checkout_dir / "message.txt").write_text("feat: from file [changelog-skip]\n")
    assert run(env.ctx, req)["verdict"] == "none"


def test_utf8_stdin_is_measured_before_json_reserialization(hook_env: Any) -> None:
    req = request(hook_env)
    req["payload"]["description"] = "я" * 180_000
    raw = json.dumps(req["payload"], ensure_ascii=False).encode("utf-8")
    assert len(raw) < 1_048_576 < len(json.dumps(req["payload"]).encode())
    args = argparse.Namespace(
        target=req["target"], surface=req["surface"], project=req["project_id"], event_name=req["event_name"]
    )
    assert evaluate(args, io.BytesIO(raw), hook_env.ctx).get("reason_code") == "GIT_GUARDRAILS"
    exact = raw + b" " * (1_048_576 - len(raw))
    assert evaluate(args, io.BytesIO(exact), hook_env.ctx).get("reason_code") == "GIT_GUARDRAILS"
    assert evaluate(args, io.BytesIO(exact + b" "), hook_env.ctx).get("reason_code") == "HOOK_PAYLOAD_INVALID"


def test_enforcement_without_daemon_does_not_use_policy_cache(
    hook_env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = hook_env
    # This checks transport admission independently of repository trust checks.
    monkeypatch.setattr(env.ctx.gateways.get(HookState), "checkout", lambda *args: None)
    req = request(env, target="codex", command="git status")
    assert run(env.ctx, req)["verdict"] == "none"
    (env.state_dir / "host.json").write_text(json.dumps({"host_id": str(env.ctx.host_id)}))
    script = """
import builtins, sys
original = builtins.__import__
def guarded(name, *args, **kwargs):
    blocked = ("skm.bootstrap.composition", "skm.bootstrap.modules",
               "skm.adapters.runtimes", "skm.entrypoints.api")
    assert not name.startswith(blocked), name
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from skm.entrypoints.hook.main import main
code = main(sys.argv[1:])
blocked = ("skm.bootstrap.composition", "skm.adapters.runtimes", "skm.entrypoints.api")
assert not any(name.startswith(blocked) for name in sys.modules)
raise SystemExit(code)
"""
    with runtime_environment(
        {
            **os.environ,
            "SKM_STATE_DIR": str(env.state_dir),
            "SKM_DATABASE_URL": "postgresql://unused.invalid/skm",
        }
    ) as environ:
        proc = subprocess.run(
            [
                sys.executable,
                "-c",
                script,
                "PreToolUse",
                "--target",
                "codex",
                "--surface",
                req["surface"],
                "--project",
                str(env.project_id),
            ],
            input=json.dumps(req["payload"]),
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
            env=environ,
        )
    assert proc.returncode == 2, proc.stderr
    assert "HOOK_BACKEND_UNAVAILABLE" in proc.stderr


@pytest.mark.parametrize("env", ["memory"], indirect=True)
def test_enforcement_subprocess_observes_policy_changes(
    hook_env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    invocation = native_invocation(hook_env, "codex", command="git reset --hard")
    with (
        runtime_environment(invocation.environ) as environ,
        memory_daemon(environ, hook_env.ctx, monkeypatch),
    ):
        invocation.environ = environ
        denied, _ = invocation.execute()
        assert denied.returncode == 2
        assert "Unsafe Git operation" in denied.stderr
        cache = hook_env.state_dir / "hooks" / f"{hook_env.project_id}-codex.json"
        assert cache.is_file()
        set_modes(hook_env, git_guardrails="off")
        assert cache.is_file()
        allowed, _ = invocation.execute()
        assert allowed.returncode == 0
        assert allowed.stdout == allowed.stderr == ""


def test_live_evaluation_uses_current_policy_even_with_fresh_cache(
    hook_env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = hook_env.ctx.gateways.get(HookState)
    monkeypatch.setattr(state, "checkout", lambda *args: None)
    req = request(hook_env)
    assert run(hook_env.ctx, req).get("reason_code") == "GIT_GUARDRAILS"
    path = state.folder / f"{hook_env.project_id}-claude_code.json"
    cached = path.read_bytes()
    set_modes(hook_env, git_guardrails="off")
    path.touch(mode=0o600)
    path.write_bytes(cached)
    assert run(hook_env.ctx, req).get("reason_code") == "GIT_GUARDRAILS"
    assert run(hook_env.ctx, req, live=True)["verdict"] == "none"


def test_workflow_context_and_observation_records(hook_env: Any) -> None:
    from dataclasses import replace

    env = hook_env
    set_modes(env, session_start="warn", review_gate="warn", command_log="warn", run_report="warn")
    run_id, task_id, finding_id = ("01900000-0000-7000-8000-00000000000" + str(index) for index in (1, 2, 3))

    class WorkflowClient:
        def ask(self, query: Any) -> Any:
            urn = query.SCHEMA_URN
            if urn == "urn:skm:execution:query:list-runs:v1":
                return {"items": [{"run_id": run_id}]}
            if urn == "urn:skm:execution:query:list-tasks:v1":
                return {"tasks": [{"task_id": task_id, "status": "running"}]}
            if urn == "urn:skm:execution:query:get-task:v1":
                return {"findings": [{"finding_id": finding_id, "state": "open"}]}
            if urn == "urn:skm:execution:query:list-decision-requests:v1":
                return {"items": [{"request_id": "question"}]}
            return env.client.ask(query)

        def __getattr__(self, name: str) -> Any:
            return getattr(env.client, name)

    ctx = replace(env.ctx, client=WorkflowClient())
    req = request(env, surface="context.session_start")
    req["event_name"] = "SessionStart"
    req["payload"].update(hook_event_name="SessionStart", source="startup")
    start = run(ctx, req)
    assert run_id in start.get("additional_context", "")
    assert task_id in start.get("additional_context", "")
    assert "Open inbox questions: 1" in start.get("additional_context", "")
    req["surface"], req["event_name"] = "lifecycle.review_gate", "SubagentStop"
    req["payload"].update(hook_event_name="SubagentStop", stop_hook_active=False)
    assert finding_id in run(ctx, req).get("additional_context", "")
    assert (
        run(ctx, request(env, surface="lifecycle.command_log", command="echo PRIVATE_COMMAND"))["verdict"]
        == "none"
    )
    req["surface"], req["event_name"] = "lifecycle.run_report", "SessionEnd"
    req["payload"].update(hook_event_name="SessionEnd", reason="completed")
    assert run(ctx, req)["verdict"] == "none"
    path = env.state_dir / "hooks/observations.jsonl"
    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert {record["surface"] for record in records} == {"lifecycle.command_log", "lifecycle.run_report"}
    assert "PRIVATE_COMMAND" not in path.read_text()
    assert path.stat().st_mode & 0o077 == 0


@pytest.mark.usefixtures("git_plumbing")
def test_second_configured_changelog_file_satisfies_gate(hook_env: Any) -> None:
    env = hook_env
    set_modes(env, changelog_gate="strict")
    env.client.dispatch(
        SetValue.from_json(
            {
                "scope": {"level": "project", "scope_id": str(env.project_id)},
                "key": "integrations.hooks.changelog_files",
                "value": ["CHANGELOG.md", "CHANGES.md"],
            }
        ),
        idempotency_key=env.client.new_idempotency_key(),
    )
    policy = env.client.ask(
        GetHookPolicy.from_json({"project_id": str(env.project_id), "target": "claude_code"})
    )
    assert policy["changelog"]["changelog_paths"] == ["CHANGELOG.md", "CHANGES.md"]
    (env.checkout_dir / "src/app.py").write_text("new code\n")
    git(env.checkout_dir, "add", "src/app.py")
    req = request(env, surface="lifecycle.changelog_gate", command="git commit -m 'fix: x'")
    assert run(env.ctx, req).get("reason_code") == "CHANGELOG_REQUIRED"
    (env.checkout_dir / "CHANGES.md").write_text("changes\n")
    git(env.checkout_dir, "add", "CHANGES.md")
    assert run(env.ctx, req)["verdict"] == "none"
