"""Verify preset projections, strict diagnostics, and Gemini startup admission."""

import json
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from integration.integrations.claude_code.test_host_apply import _LiveClaudeEnv
from integration.integrations.claude_code.test_host_apply import live_claude_env as live_claude_env
from integration.runtimes.test_gemini_cli import _KEY, HOST_1, _probe_cli, _request
from integration.runtimes.test_gemini_cli import fake_gemini as fake_gemini
from skm.adapters.runtimes.gemini_cli.runtime import GeminiCliRuntime, ProbedBinary
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable
from skm.kernel.ids import WorkspaceId
from skm.modules.integrations.domain.presets import PRESET_SUBSCRIPTIONS
from skm.modules.integrations.domain.reports import CommandResult
from skm.modules.runtimes.domain.detection import DetectProbe
from skm.modules.runtimes.domain.request import AgentRequest, ProcessOwnership
from skm.modules.settings.generated.commands import SetValueDefsScopeRef
from skm.modules.settings.public import SetValue
from skm.modules.workspace.public import GetProject, ResolveCheckout
from unit.integrations.test_presets_and_doctor_hygiene import _cli, _ReadOnlyRunner


def _prepare_checkout(
    env: _LiveClaudeEnv,
    tmp_path: Path,
    fake_gemini: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, WorkspaceId, GeminiCliRuntime, AgentRequest, Path, ProcessOwnership, ProbedBinary]:
    checkout = env.checkout_dir
    git = shutil.which("git")
    assert git is not None
    subprocess.run((git, "init", "--quiet", str(checkout)), check=True, timeout=10)
    (checkout / ".gitignore").write_text(".claude/settings.local.json\n", encoding="utf-8")
    location = cast("Any", env.client.ask(ResolveCheckout(env.project_id, "main", env.ctx.host_id)))
    project = cast("Any", env.client.ask(GetProject(project_id=env.project_id)))
    workspace_id = cast("WorkspaceId", project.workspace_id)
    marker = {
        "schema": "urn:skm:workspace:checkout-marker:v1",
        "instance_id": str(env.app.instance_id),
        "workspace_id": str(workspace_id),
        "project_id": str(env.project_id),
        "repository_id": str(location.repository_id),
        "mount_name": "main",
    }
    (checkout / ".skm").mkdir()
    (checkout / ".skm/project.json").write_text(json.dumps(marker), encoding="utf-8")

    def run(_self: object, argv: tuple[str, ...], **kwargs: object) -> CommandResult:
        assert argv[0] in {"which", "test", "find"}
        result = subprocess.run(
            argv,
            cwd=checkout,
            env={"PATH": str(Path(sys.executable).parent) + os.pathsep + os.defpath},
            input=b"",
            timeout=10,
            capture_output=True,
            check=False,
        )
        return CommandResult(result.returncode, result.stdout, result.stderr, 0, False)

    monkeypatch.setattr(_ReadOnlyRunner, "run", run)
    (checkout / "composer.json").write_text('{"name":"acme/widget"}', encoding="utf-8")
    (checkout / "pubspec.yaml").write_text("name: demo_widget\n", encoding="utf-8")
    env.client.dispatch(
        SetValue(
            scope=SetValueDefsScopeRef(level="project", scope_id=env.project_id),
            key="integrations.hooks.mode",
            value={"session_start": "off"},
            reason="disable unmeasurable SessionStart template for strict budget",
        )
    )
    request = replace(_request(tmp_path), workdir=str(checkout))
    runtime = GeminiCliRuntime(
        binary=str(fake_gemini), environ={"GEMINI_API_KEY": _KEY}, probe_runner=_probe_cli
    )
    runtime.detect(DetectProbe(HOST_1, None, (), 5))
    probed = runtime._last_probed()
    assert probed is not None
    runtime._validate_start(request)
    step = tmp_path / "gemini-step"
    step.mkdir()
    ownership = ProcessOwnership(request.process_owner, "pgroup_best_effort", "test")
    command, _ = runtime._build_launch(request, probed, step_dir=step, ownership=ownership)
    assert command.cwd == checkout
    return checkout, workspace_id, runtime, request, step, ownership, probed


@pytest.mark.parametrize("preset", ["php-project", "php-package", "dart-project", "dart-package"])
def test_preset_strict_and_gemini_admission(
    live_claude_env: _LiveClaudeEnv,
    tmp_path: Path,
    fake_gemini: Path,
    preset: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = live_claude_env
    checkout, workspace_id, runtime, request, step, ownership, probed = _prepare_checkout(
        env, tmp_path, fake_gemini, monkeypatch
    )

    code, plans = _cli(env, "integrations", "plan", "--preset", preset)
    assert code == 0
    assert plans
    code, applied = _cli(env, "integrations", "apply", "--preset", preset)
    assert code == 0
    assert applied
    assert all(item["state"] == "in_sync" for item in applied)
    code, codex_applied = _cli(env, "integrations", "apply", "--preset", preset, "--target", "codex")
    assert code == 0
    assert codex_applied
    assert all(item["state"] == "in_sync" for item in codex_applied)

    for sub in cast("tuple[dict[str, Any], ...]", PRESET_SUBSCRIPTIONS.get(preset, ())):
        trust_code, _ = _cli(env, "hooks", "trust", str(sub["id"]))
        assert trust_code == 0
    list_code, listed = _cli(env, "hooks", "list", "--workspace", str(workspace_id))
    assert list_code == 0
    trusted = {
        str(item["id"]): str(item["digest"]) for item in cast("list[dict[str, Any]]", listed.get("items", ()))
    }
    doctor_config = {"hooks.host.trusted": trusted} if trusted else None

    errors: list[str] = []
    for args in (
        ("doctor", "--strict"),
        *(("budget", "--target", target, "--strict") for target in ("claude_code", "codex")),
    ):
        try:
            code, report = _cli(env, *args, config=doctor_config if args[0] == "doctor" else None)
            if code != 0:
                findings = [
                    item for item in report.get("checks", []) if item["level"] in ("warning", "error")
                ]
                errors.append(
                    f"{' '.join(args)}: exit {code}, "
                    f"status={report.get('status', report.get('verdict'))}, "
                    f"checks={findings}"
                )
        except AssertionError as error:
            errors.append(f"{' '.join(args)}: {error}")

    code, applied = _cli(env, "integrations", "apply", "--preset", preset, "--target", "gemini_cli")
    assert code == 0
    assert applied
    assert all(item["state"] == "in_sync" for item in applied)
    assert (checkout / ".gemini/settings.json").is_file()
    with pytest.raises(CapabilityUnavailable) as exc:
        runtime._build_launch(request, probed, step_dir=step, ownership=ownership)
    assert exc.value.code is ErrorCode.SANDBOX_UNAVAILABLE
    assert exc.value.details["path"] == str(checkout / ".gemini/settings.json")

    assert not errors, "\n".join(errors)
