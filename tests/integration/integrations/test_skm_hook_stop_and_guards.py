"""Exercise installed skm-hook and bound guards with trusted preset checks."""

import io
import json
import shlex
import socket
import sys
from collections.abc import Sequence
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from fixtures.hooks.subprocess.harness import (
    Invocation,
    child_environment,
    claude_on_path,
    memory_daemon,
    native_invocation,
    runtime_environment,
)
from integration.integrations.claude_code.test_host_apply import _LiveClaudeEnv
from integration.integrations.claude_code.test_host_apply import live_claude_env as live_claude_env
from integration.integrations.test_hooks import env as env
from integration.integrations.test_hooks import git
from integration.integrations.test_hooks import hook_env as hook_env
from skm.application_bus.host import HostContext
from skm.bootstrap import hook, hookd
from skm.bootstrap.hook import unavailable_context, with_hook_state
from skm.bootstrap.hook_subscriptions import bind_cli_subscriptions
from skm.entrypoints.cli.main import Backend
from skm.entrypoints.cli.main import main as skm_main
from skm.entrypoints.hook.main import main as hook_main
from skm.kernel.gateways import GatewayTable
from skm.modules.integrations.application.queries.get_hook_policy import GetHookPolicy
from skm.modules.integrations.application.queries.get_hook_policy import HookPolicyView as GetHookPolicyView
from skm.modules.integrations.domain.presets import preset_subscription_config
from skm.modules.integrations.domain.reports import CommandResult
from skm.modules.integrations.domain.target import TargetId
from skm.modules.integrations.generated.queries import ListHookSubscriptions
from skm.modules.integrations.generated.results import ListHookSubscriptionsResult
from skm.modules.integrations.host.apply_projection import apply_projection
from skm.modules.integrations.host.evaluate_hook import run
from skm.modules.integrations.host.hook_state import HookState
from skm.modules.integrations.host.host_subscriptions import setting
from skm.modules.integrations.host.plan_projection import plan_projection
from skm.modules.integrations.host.remove_projection import remove_projection
from skm.modules.integrations.host.test_host_subscription import run as run_test_subscription
from skm.modules.integrations.ports import HostCommandRunner
from skm.modules.settings.generated.commands import SetValue
from skm.modules.workspace.public import CheckoutLocationView, GetProject, ProjectView, ResolveCheckout


class _CheckRunner:
    def __init__(self) -> None:
        self.argv: list[tuple[str, ...]] = []

    def run(self, argv: Sequence[str], **kwargs: Any) -> CommandResult:
        self.argv.append(tuple(argv))
        assert not kwargs["stdin"]
        assert kwargs["timeout_ms"] > 0
        assert kwargs["env"]["PATH"] == "/usr/bin:/bin"
        return CommandResult(1, b"", b"", 1, False)


def test_active_stop_short_circuits_without_any_host_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    context = unavailable_context()
    result = run(
        context,
        {
            "target": "claude_code",
            "surface": "custom.subscriptions",
            "class": "enforcement",
            "project_id": "not-a-project-id",
            "event_name": "Stop",
            "payload": {"session_id": "s", "cwd": "/checkout", "stop_hook_active": True},
        },
    )
    assert result["verdict"] == "none"
    assert result.get("reason_code") is None
    assert result["client_output"] == {"exit_code": 0, "stdout": "", "stderr": ""}

    def unexpected_backend(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("active Stop opened the backend")

    monkeypatch.setattr(hook, "hook_context", unexpected_backend)
    header = ["claude_code", "custom.subscriptions", "not-a-project-id", "Stop", "enforcement"]
    payload = {"session_id": "s", "cwd": "/checkout", "stop_hook_active": True}
    reply = hookd._reply(json.dumps(header).encode() + b"\n" + json.dumps(payload).encode(), {}, None)
    assert json.loads(reply)["verdict"] == "none"


def _installed_request(
    invocation: Invocation, context: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Any:
    with runtime_environment(invocation.environ) as environ:
        invocation = replace(invocation, environ=environ)
        probe = Path(environ["XDG_RUNTIME_DIR"]) / "probe.sock"
        with socket.socket(socket.AF_UNIX) as listener:
            try:
                listener.bind(str(probe))
            except PermissionError:
                socket_available = False
            else:
                socket_available = True
                probe.unlink()
        if invocation.argv[invocation.argv.index("--target") + 1] == "claude_code":
            claude_on_path(environ)
        if socket_available:
            with memory_daemon(environ, context, monkeypatch):
                return invocation.execute()[0]

        # Restricted test hosts can run the installed client and the daemon request handler
        # with the exact wire bytes even though Unix socket bind is unavailable.
        args = invocation.argv
        header: list[str | None] = [
            args[args.index(flag) + 1] for flag in ("--target", "--surface", "--project")
        ]
        header.extend((args[1], args[args.index("--class") + 1] if "--class" in args else None))
        request = json.dumps(header).encode() + b"\n" + json.dumps(invocation.payload).encode()

        @contextmanager
        def context_factory(*_args: object, **_kwargs: object):
            yield context

        with monkeypatch.context() as patch:
            patch.setattr(hook, "hook_context", context_factory)
            reply = hookd._reply(request, environ, None)
        assert reply
        (tmp_path / "sitecustomize.py").write_text(
            "import subprocess\n"
            "from types import SimpleNamespace\n"
            "from skm.bootstrap import hookd\n"
            "def probe(argv, *, cwd, env, timeout_seconds, **limits):\n"
            "    result = subprocess.run(\n"
            "        argv, cwd=cwd, env=env, timeout=timeout_seconds, capture_output=True)\n"
            "    return SimpleNamespace(exit_code=result.returncode, stdout=result.stdout)\n"
            "def exchange(environ, payload, *, timeout):\n"
            f"    assert payload == {request!r}\n"
            f"    return {reply!r}\n"
            "hookd.run = probe\n"
            "hookd.exchange = exchange\n"
        )
        environ["PYTHONPATH"] = str(tmp_path)
        return invocation.execute()[0]


def test_installed_active_stop_needs_no_daemon_or_backend(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    environ = child_environment(tmp_path / "state", home)
    environ["PATH"] = ""
    with runtime_environment(environ) as environ:
        invocation = Invocation(
            [
                "skm-hook",
                "Stop",
                "--target",
                "claude_code",
                "--surface",
                "custom.subscriptions",
                "--project",
                "no-project",
                "--class",
                "enforcement",
                "--bootstrap",
                str(tmp_path / "missing.toml"),
            ],
            {"session_id": "s", "cwd": str(tmp_path), "stop_hook_active": True},
            environ,
            tmp_path,
        )
        result, _ = invocation.execute()
        assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
        assert not tuple(Path(environ["XDG_RUNTIME_DIR"]).iterdir())
    assert tuple(tmp_path.iterdir()) == (home,)
    assert not tuple(home.iterdir())


def _mark_checkout(env: _LiveClaudeEnv) -> ProjectView:
    root = env.checkout_dir
    git(root, "init", "--quiet")
    location = env.client.ask(ResolveCheckout(env.project_id, "main", env.ctx.host_id))
    view = env.client.ask(GetProject(project_id=env.project_id))
    assert isinstance(view, ProjectView)
    assert isinstance(location, CheckoutLocationView)
    (root / ".skm").mkdir()
    (root / ".skm/project.json").write_text(
        json.dumps(
            {
                "schema": "urn:skm:workspace:checkout-marker:v1",
                "instance_id": str(env.app.instance_id),
                "workspace_id": str(view.workspace_id),
                "project_id": str(env.project_id),
                "repository_id": str(location.repository_id),
                "mount_name": "main",
            }
        )
    )
    return view


@pytest.mark.parametrize("use_preset_command", [False, True])
def test_configured_preset_id_without_applied_preset(
    live_claude_env: _LiveClaudeEnv, use_preset_command: bool
) -> None:
    env = live_claude_env
    root = env.checkout_dir
    project = _mark_checkout(env)
    subscription_id = "preset.php.lint"
    subscription = preset_subscription_config("php-project", TargetId.CLAUDE_CODE)[subscription_id]
    assert isinstance(subscription, dict)
    expected_argv = ("php", "-l") if use_preset_command else ("my-php-lint",)
    if not use_preset_command:
        subscription["target"] = {"argv": list(expected_argv), "cwd": "checkout"}
    env.client.dispatch(
        SetValue.from_json(
            {
                "scope": {"level": "project", "scope_id": str(env.project_id)},
                "key": "hooks.subscriptions",
                "value": {subscription_id: subscription},
                "reason": "configure lint hook on a project without a preset",
                "confirmed": True,
            }
        )
    )
    listed = env.client.ask(
        ListHookSubscriptions(workspace_id=project.workspace_id, project_id=env.project_id)
    )
    assert isinstance(listed, ListHookSubscriptionsResult)
    (item,) = listed.items
    assert (item.id, item.valid, item.target_summary) == (subscription_id, True, expected_argv[0])
    project_id = str(env.project_id)
    query = GetHookPolicy.from_json({"project_id": project_id, "target": "claude_code"})
    policy = env.client.ask(query)
    assert isinstance(policy, GetHookPolicyView)
    (row,) = policy["subscriptions"]
    assert (row["id"], row["digest"], tuple(row["argv"])) == (subscription_id, item.digest, expected_argv)

    class Runner:
        called = False

        def run(self, argv: Sequence[str], **kwargs: Any) -> CommandResult:
            assert tuple(argv) == expected_argv
            assert json.loads(kwargs["stdin"])["subscription_id"] == subscription_id
            self.called = True
            output = b'{"schema":"urn:skm:integrations:host-command-output:v1","decision":"none"}'
            return CommandResult(0, output, b"", 1, False)

    runner = Runner()
    ctx = _subscription_context(env, runner)
    _trust(ctx, env, project, subscription_id)
    assert setting(ctx, "hooks.host.trusted", {}) == {subscription_id: item.digest}
    manual = run_test_subscription(
        ctx,
        {"project_id": project_id, "subscription_id": subscription_id, "event_kind": "post_tool"},
    )
    assert manual["status"] == "ok"
    assert runner.called
    runner.called = False
    request = {
        "target": "claude_code",
        "surface": "custom.subscriptions",
        "project_id": project_id,
        "class": "workflow",
        "event_name": "PostToolUse",
        "payload": {
            "session_id": "s",
            "cwd": str(root),
            "tool_name": "Write",
            "tool_input": {"file_path": "Example.php"},
            "tool_response": {"success": True},
        },
    }
    result = run(ctx, request, live=True)
    assert runner.called, result
    assert result["verdict"] == "none"

    state = ctx.gateways.get(HookState)
    cached = state.load(project_id, "claude_code")
    assert cached is not None
    env.client.dispatch(
        SetValue.from_json(
            {
                "scope": {"level": "project", "scope_id": project_id},
                "key": "integrations.hooks.changelog_files",
                "value": ["CHANGES.md"],
                "reason": "change changelog policy while the hook policy is cached",
            }
        )
    )
    current = env.client.ask(query)
    assert isinstance(current, GetHookPolicyView)
    assert current["generation"] != cached["generation"]
    assert current["changelog"]["changelog_paths"] == ["CHANGES.md"]
    assert current["subscriptions"] == cached["subscriptions"]

    runner.called = False
    result = run(ctx, request)
    assert runner.called, result
    assert result["verdict"] == "none"
    assert state.load(project_id, "claude_code") == cached


def _subscription_context(env: _LiveClaudeEnv, runner: HostCommandRunner) -> HostContext:
    state_dir = env.checkout_dir.parent / "state"
    app = bind_cli_subscriptions(
        env.app, SimpleNamespace(host_id=env.ctx.host_id, state_dir=state_dir), {"PATH": ".:bin:"}
    )
    assert app.host is not None
    ctx = with_hook_state(
        app.host.context(client=env.client, cancel=env.ctx.cancel, log=env.ctx.log), state_dir
    )
    return replace(
        ctx, gateways=GatewayTable({**ctx.gateways.entries, HostCommandRunner: runner}, "host_gateway")
    )


def _trust(ctx: HostContext, env: _LiveClaudeEnv, project: ProjectView, subscription_id: str) -> None:
    stdout, stderr = io.StringIO(), io.StringIO()
    backend = Backend(env.client, host_factory=lambda: ctx, instance_id=env.app.instance_id)
    status = skm_main(
        [
            "hooks",
            "trust",
            subscription_id,
            "--workspace",
            str(project.workspace_id),
            "--project",
            str(env.project_id),
            "--yes",
            "--json",
        ],
        backend=lambda *_args: backend,
        environ={},
        stdout=stdout,
        stderr=stderr,
    )
    assert status == 0, (stdout.getvalue(), stderr.getvalue())


@pytest.mark.parametrize("mode", ["off", "warn"])
def test_applied_preset_runs_bound_checks_with_trust(
    live_claude_env: _LiveClaudeEnv, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    env = live_claude_env
    root = env.checkout_dir
    project = _mark_checkout(env)
    env.client.dispatch(
        SetValue.from_json(
            {
                "scope": {"level": "project", "scope_id": str(env.project_id)},
                "key": "integrations.hooks.mode",
                "value": {"safe_dirs": mode},
                "reason": "test preset precedence",
            }
        )
    )
    assert (
        apply_projection(env.ctx, plan_projection(env.ctx, project_id=env.project_id, preset="php-project"))[
            0
        ].state
        == "in_sync"
    )
    policy = env.client.ask(
        GetHookPolicy.from_json({"project_id": str(env.project_id), "target": "claude_code"})
    )
    assert isinstance(policy, GetHookPolicyView)
    trust = {row["id"]: row["digest"] for row in policy["subscriptions"]}
    assert set(trust) == {"preset.php.lint", "preset.php.pint", "preset.php.phpstan"}
    runner = _CheckRunner()
    state_dir = root.parent / "state"
    ctx = _subscription_context(env, runner)
    req = {
        "target": "claude_code",
        "surface": "custom.subscriptions",
        "project_id": str(env.project_id),
        "class": "enforcement",
        "event_name": "Stop",
        "payload": {"session_id": "s", "cwd": str(root), "stop_hook_active": False},
    }
    untrusted = run(ctx, req, live=True)
    assert untrusted.get("reason_code") == "HOOK_SUBSCRIPTION_UNTRUSTED"
    assert runner.argv == []
    for subscription_id in trust:
        _trust(ctx, env, project, subscription_id)
    assert setting(ctx, "hooks.host.trusted", {}) == trust
    target = root / "Example.php"
    target.write_text("<?php echo 1;\n")
    post = run(
        ctx,
        {
            **req,
            "class": "workflow",
            "event_name": "PostToolUse",
            "payload": {
                "session_id": "s",
                "cwd": str(root),
                "tool_name": "Write",
                "tool_input": {"file_path": str(target)},
                "tool_response": {"success": True},
            },
        },
        live=True,
    )
    assert post["verdict"] == "warn"
    assert "preset.php.lint" in post["client_output"]["stdout"]["hookSpecificOutput"]["additionalContext"]
    assert runner.argv == [("php", "-l", str(target))]
    assert target.read_text() == "<?php echo 1;\n"

    hooks = json.loads((root / ".claude/settings.json").read_bytes())["hooks"]
    environ = child_environment(state_dir, root.parent / "home")
    stop = Invocation(shlex.split(hooks["Stop"][0]["hooks"][0]["command"]), req["payload"], environ, root)
    result = _installed_request(stop, ctx, monkeypatch, root.parent)
    assert (result.returncode, result.stderr) == (0, "")
    assert json.loads(result.stdout)["decision"] == "block"
    assert set(runner.argv[1:]) == {("pint", "--dirty"), ("phpstan", "analyse")}
    guard = next(
        shlex.split(entry["command"])
        for group in hooks["PreToolUse"]
        for entry in group["hooks"]
        if "security.safe_dirs" in entry["command"]
    )
    payload = {
        "session_id": "s",
        "cwd": str(root),
        "tool_name": "Bash",
        "tool_input": {"command": "php artisan db:wipe"},
    }
    result = _installed_request(Invocation(guard, payload, environ, root), ctx, monkeypatch, root.parent)
    assert result.returncode == 0
    assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"

    remove_projection(env.ctx, project_id=env.project_id, target=TargetId.CLAUDE_CODE)
    cached = ctx.gateways.get(HookState).load(str(env.project_id), "claude_code")
    assert cached is not None
    assert cached["subscriptions"]
    runner.argv.clear()
    after_remove = run(ctx, req)
    assert after_remove["verdict"] == "none"
    assert not runner.argv


@pytest.mark.parametrize("env", ["memory"], indirect=True)
def test_skm_hook_safe_dirs_fails_closed(
    hook_env: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    invocation = native_invocation(hook_env, "claude_code", surface="security.safe_dirs")

    @contextmanager
    def context_factory(*_args: object, **_kwargs: object):
        yield hook_env.ctx

    # Exercise both sides of the wire protocol without depending on Unix socket permissions.
    monkeypatch.setattr(hook, "hook_context", context_factory)
    monkeypatch.setattr(hookd, "_claude_can_block", lambda *_args: True)
    monkeypatch.setattr(
        hookd, "exchange", lambda environ, payload, **_kwargs: hookd._reply(payload, environ, None)
    )
    (hook_env.checkout_dir / "secret").symlink_to(".env")
    (hook_env.checkout_dir / "secret=value").symlink_to(".env")
    for tool, tool_input, allowed in (
        ("Write", {"file_path": ".env"}, False),
        ("Edit", {"file_path": "../outside.php"}, False),
        ("MultiEdit", {"edits": [{"file_path": "nested/.env.production"}]}, False),
        ("Write", {"file_path": ".env.example"}, True),
        ("Bash", {"command": "php artisan db:wipe"}, False),
        ("Bash", {"command": "php artisan migrate:fresh"}, False),
        ("Bash", {"command": "php artisan migrate:refresh"}, False),
        ("Bash", {"command": "cat .env"}, False),
        ("Bash", {"command": "cat secret"}, False),
        ("Bash", {"command": "cat 'secret=value'"}, False),
        ("Bash", {"command": "git 'unterminated"}, False),
        ("Write", {}, False),
    ):
        invocation.payload.update(tool_name=tool, tool_input=tool_input)
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(invocation.payload)))
        assert hook_main(invocation.argv[1:]) == 0
        output = capsys.readouterr()
        if allowed:
            assert output.out == ""
        else:
            assert json.loads(output.out)["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.parametrize("env", ["memory"], indirect=True)
def test_installed_gemini_before_tool_applies_safe_dirs(
    hook_env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = hook_env.checkout_dir
    fixture = Path(__file__).resolve().parents[2] / "fixtures/integrations/gemini-cli/0.71.1/hooks.json"
    payload = json.loads(fixture.read_bytes())["payloads"][0]
    payload["cwd"] = str(root)
    invocation = native_invocation(hook_env, "gemini_cli", surface="security.safe_dirs")
    invocation.argv[1] = "BeforeTool"
    for path, expected in ((".env", 2), (".env.example", 0)):
        payload["tool_input"]["file_path"] = str(root / path)
        result = _installed_request(
            replace(invocation, payload=payload), hook_env.ctx, monkeypatch, root.parent
        )
        assert (result.returncode, result.stdout) == (expected, "")
        if expected:
            assert ".env file is protected" in result.stderr
        else:
            assert result.stderr == ""


@pytest.mark.parametrize("env", ["memory"], indirect=True)
def test_installed_skm_hook_denies_when_daemon_is_unavailable(hook_env: Any) -> None:
    invocation = native_invocation(hook_env, "codex", surface="security.safe_dirs")
    with runtime_environment(invocation.environ) as environ:
        invocation.environ = environ
        completed, _ = invocation.execute()
    assert completed.returncode == 2
    assert "HOOK_BACKEND_UNAVAILABLE" in completed.stderr
