"""Exercise preset CLI lifecycles, bundle path restrictions and checkout hygiene."""

import json
import subprocess
from dataclasses import replace
from io import StringIO
from typing import Any

import pytest

from integration.integrations.claude_code.test_host_apply import _LiveClaudeEnv
from integration.integrations.claude_code.test_host_apply import live_claude_env as live_claude_env
from skm.adapters.checkout_fs.user_home import LocalUserHomeReader
from skm.entrypoints.cli.main import Backend, main
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.gateways import GatewayTable
from skm.modules.integrations.domain.bundle import BundleAssetSurface, resolve_bundle_asset_path
from skm.modules.integrations.domain.ownership import Ownership, sha256_tagged
from skm.modules.integrations.domain.presets import dart_package_name
from skm.modules.integrations.domain.reports import CommandResult
from skm.modules.integrations.domain.target import TargetId
from skm.modules.integrations.ports import HostCommandRunner, UserHomeReader
from skm.modules.integrations.public import GetHookPolicy, HookPolicyView
from skm.modules.settings.generated.commands import SetValue


class _ReadOnlyRunner:
    def run(self, argv: tuple[str, ...], **kwargs: Any) -> CommandResult:
        assert argv[0] in {"which", "test", "find"}
        result = subprocess.run(
            argv,
            cwd=kwargs["cwd"],
            env=kwargs["env"],
            input=kwargs["stdin"],
            timeout=1,
            capture_output=True,
            check=False,
        )
        return CommandResult(result.returncode, result.stdout, result.stderr, 0, False)


def _cli(env: _LiveClaudeEnv, *argv: str, config: dict[str, Any] | None = None) -> tuple[int, Any]:
    stdout, stderr = StringIO(), StringIO()
    assert isinstance(env.ctx.gateways, GatewayTable)
    gateway = GatewayTable(
        {
            **env.ctx.gateways.entries,
            UserHomeReader: LocalUserHomeReader(env.checkout_dir.parent),
            HostCommandRunner: _ReadOnlyRunner(),
        },
        "host_gateway",
    )
    context = replace(env.ctx, gateways=gateway, config=config or {})
    backend = Backend(env.client, host_factory=lambda: context, instance_id=env.app.instance_id)
    code = main(
        [*argv, "--project", str(env.project_id), "--json"],
        backend=lambda _options, _env: backend,
        environ={},
        stdout=stdout,
        stderr=stderr,
    )
    assert stdout.getvalue(), stderr.getvalue()
    envelope = json.loads(stdout.getvalue())
    assert envelope["ok"], stderr.getvalue() or envelope.get("error")
    return code, envelope["result"]


@pytest.mark.parametrize(
    ("preset", "paths", "has_workflow", "has_stop", "live_claude_env"),
    [
        ("php-project", (".claude/rules/eloquent.md",), True, True, "demo"),
        (
            "php-package",
            ("resources/boost/guidelines/core.md", "resources/boost/skills/widget/SKILL.md"),
            False,
            False,
            "demo",
        ),
        ("dart-project", (".claude/rules/flutter-ui.md",), True, True, "demo"),
        ("dart-package", ("skills/demo_widget-usage/SKILL.md",), False, True, "123-demo"),
    ],
    indirect=["live_claude_env"],
)
def test_preset_plan_apply_remove(
    live_claude_env: _LiveClaudeEnv, preset: str, paths: tuple[str, ...], has_workflow: bool, has_stop: bool
) -> None:
    env = live_claude_env
    checkout = env.checkout_dir
    (checkout / "composer.json").write_text('{"name":"acme/widget"}')
    (checkout / "pubspec.yaml").write_text("name: demo_widget\n")
    code, (default_plan,) = _cli(env, "integrations", "plan")
    assert code == 0
    code, (plan,) = _cli(env, "integrations", "plan", "--preset", preset)
    assert code == 0
    assert plan["inputs_digest"] != default_plan["inputs_digest"]
    assert set(paths) <= {entry["relative_path"] for entry in plan["writes"]}
    assert not (checkout / "AGENTS.md").exists()
    assert all(not (checkout / path).exists() for path in paths)
    code, (applied,) = _cli(env, "integrations", "apply", "--preset", preset)
    assert (code, applied["state"]) == (0, "in_sync")
    agents = (checkout / "AGENTS.md").read_text()
    assert "<!-- skm:local:start -->" in agents
    assert "<!-- skm:local:end -->" in agents
    assert len(agents.splitlines()) < 40
    assert all((checkout / path).is_file() for path in paths)
    if preset.endswith("-package"):
        assert (checkout / ".claude/skills/spec-review/SKILL.md").is_file()
        assert (checkout / ".claude/skills/review-checklist/SKILL.md").is_file()
    if preset == "dart-package":
        assert "name: demo_widget-usage" in (checkout / paths[0]).read_text()
    hooks = json.loads((checkout / ".claude/settings.json").read_bytes())["hooks"]
    assert ("PostToolUse" in hooks) == has_workflow
    assert ("Stop" in hooks) == has_stop
    if has_stop:
        command = hooks["Stop"][0]["hooks"][0]
        assert "--class enforcement" in command["command"]
        assert "onFailure" not in command
    code, (implicit,) = _cli(env, "integrations", "plan")
    assert code == 0
    assert implicit["inputs_digest"] == plan["inputs_digest"]
    code, removed = _cli(env, "integrations", "remove", "--target", "claude_code", "--yes")
    assert code == 0
    assert removed
    assert all(not (checkout / path).exists() for path in paths)


@pytest.mark.parametrize("key", ["'name'", '"name"'])
def test_dart_package_name_accepts_quoted_top_level_key(key: str) -> None:
    pubspec = f"example:\n  {key}: nested\n{key}: demo_widget # package name\n"
    assert dart_package_name(pubspec) == "demo_widget"


@pytest.mark.parametrize(
    ("path", "preset", "allowed"),
    [
        ("resources/boost/guidelines/core.md", None, False),
        ("resources/boost/guidelines/core.md", "dart-package", False),
        ("resources/boost/guidelines/core.md", "php-package", True),
        ("resources/boost/../elsewhere/file.md", "php-package", False),
        ("skills/demo_widget-usage/SKILL.md", "dart-package", True),
        ("skills/demo_widget-usage/SKILL.md", None, False),
        ("skills/demo_widgets-usage/SKILL.md", "dart-package", False),
        ("skills/elsewhere-usage/SKILL.md", "dart-package", False),
        ("resources/other/file.md", "php-package", False),
    ],
)
def test_consumer_path_allowlist(path: str, preset: str | None, allowed: bool) -> None:
    def resolve() -> str:
        return resolve_bundle_asset_path(
            raw_path=path,
            target=TargetId.CLAUDE_CODE,
            surface=BundleAssetSurface.RULES,
            pack_prefix="skm",
            ownership=Ownership.MANAGED_FILE,
            preset=preset,
            package_name="demo_widget",
        )

    if allowed:
        assert resolve() == path
    else:
        with pytest.raises(ValidationFailed) as error:
            resolve()
        assert error.value.code is ErrorCode.INTEGRATION_UNSAFE_TARGET


def test_doctor_collects_hygiene_from_checkout(live_claude_env: _LiveClaudeEnv) -> None:
    env = live_claude_env
    checkout = env.checkout_dir
    (checkout / "AGENTS.md").write_text("Use pest/phpunit and npm/pnpm.\n" + "line\n" * 201)
    (checkout / "CLAUDE.md").write_text("Hidden \u202e here.\n")
    (checkout / "composer.json").write_text('{"require":{"laravel/framework":"^12"}}')
    (checkout / "pubspec.yaml").write_text("name: demo_widget\n")
    incorrect = checkout / "skills/other-usage/SKILL.md"
    incorrect.parent.mkdir(parents=True)
    incorrect.write_text("# Usage\n")
    script = checkout / "scripts/audit.sh"
    script.parent.mkdir()
    script.write_text("#!/bin/sh\ntouch should-never-exist\n")
    subscription = {
        "class": "workflow",
        "kind": "command",
        "execution_location": "host",
        "event_types": ["client:post_tool"],
        "target": {"argv": ["bash", "scripts/audit.sh"], "cwd": "checkout"},
    }
    env.client.dispatch(
        SetValue.from_json(
            {
                "scope": {"level": "project", "scope_id": str(env.project_id)},
                "key": "hooks.subscriptions",
                "value": {"audit": subscription},
                "reason": "test script diagnostics",
                "confirmed": True,
            }
        )
    )
    policy = env.client.ask(
        GetHookPolicy.from_json({"project_id": str(env.project_id), "target": "claude_code"})
    )
    assert isinstance(policy, HookPolicyView)
    digest = policy["subscriptions"][0]["digest"]
    settings = checkout / ".claude/settings.json"
    settings.parent.mkdir()
    hooks = [
        {"type": "command", "command": command}
        for command in (
            "pint --dirty",
            "dart format .",
            "prettier --write .",
            "ruff format .",
            "php -l src/Foo.php",
            "dart analyze lib/foo.dart",
            "ruff format --check .",
        )
    ]
    guard = {
        "command": (
            "skm-hook PreToolUse --target claude_code --surface security.safe_dirs "
            f"--project {env.project_id}"
        ),
        "type": "command",
    }
    document = {
        "hooks": {"PostToolUse": [{"hooks": hooks}], "PreToolUse": [{"matcher": "Edit", "hooks": [guard]}]}
    }
    settings.write_text(json.dumps(document))
    code, report = _cli(env, "doctor", "--target", "claude_code")
    assert code != 0
    findings = [item for item in report["checks"] if item["check_id"].startswith("hygiene.")]
    by_id = {item["check_id"]: item for item in findings}
    assert by_id["hygiene.agents_md_size"]["level"] == "warning"
    assert by_id["hygiene.slash_ambiguity"]["level"] == "warning"
    assert by_id["hygiene.hidden_unicode"]["level"] == "error"
    assert sum(item["check_id"] == "hygiene.post_tool_mutating_formatter" for item in findings) == 4
    assert by_id["hygiene.laravel_db_guard"]["level"] == "warning"
    assert by_id["hygiene.dart_package_skill_prefix"]["path"] == "skills/other-usage/SKILL.md"
    assert {
        (item["path"], item["detail"])
        for item in findings
        if item["check_id"] == "hygiene.hook_script_trust_and_exec"
    } == {
        ("scripts/audit.sh", "Hook script is missing execute permission"),
        ("scripts/audit.sh", "Hook subscription audit has no matching trusted command digest"),
    }
    assert not (checkout / "should-never-exist").exists()

    script.chmod(0o700)
    config = {"hooks.host.trusted": {"audit": sha256_tagged(script.read_bytes())}}
    _, report = _cli(env, "doctor", "--target", "claude_code", config=config)
    assert (
        next(item for item in report["checks"] if item["check_id"] == "hygiene.hook_script_trust_and_exec")[
            "level"
        ]
        == "error"
    )

    config = {"hooks.host.trusted": {"audit": digest}}
    document["hooks"]["PreToolUse"][0]["matcher"] = "Edit|Bash"
    settings.write_text(json.dumps(document))
    (checkout / "AGENTS.md").write_text("x" * (32 * 1024 + 1))
    _, report = _cli(env, "doctor", "--target", "claude_code", config=config)
    by_id = {item["check_id"]: item for item in report["checks"]}
    assert by_id["hygiene.agents_md_size"]["level"] == "error"
    assert by_id["hygiene.hook_script_trust_and_exec"]["level"] == "ok"
    assert by_id["hygiene.laravel_db_guard"]["level"] == "ok"
    assert not (checkout / "should-never-exist").exists()

    settings.with_name("settings.local.json").write_text('{"disableAllHooks":true}')
    _, report = _cli(env, "doctor", "--target", "claude_code", config=config)
    by_id = {item["check_id"]: item for item in report["checks"]}
    assert by_id["hygiene.laravel_db_guard"]["level"] == "warning"
