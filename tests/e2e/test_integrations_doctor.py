"""CLI → host → bus and safe checkout/home observations for P10.07."""

from __future__ import annotations

import io
import json
from dataclasses import replace
from typing import Any, Literal, overload, override

import pytest

from e2e.test_instance_profiles import databases as databases
from skm.adapters.checkout_fs.user_home import LocalUserHomeReader
from skm.adapters.integrations.claude_code.doctor_layers import read_claude_layers
from skm.entrypoints.cli.main import main as cli_main
from skm.kernel.gateways import GatewayTable
from skm.kernel.json_types import JsonObject
from skm.modules.integrations.domain.reports import CommandResult
from skm.modules.integrations.domain.target import Surface, TargetId
from skm.modules.integrations.generated.host import (
    first_turn_budget_result_from_json,
    run_doctor_result_from_json,
)
from skm.modules.integrations.ports import HostCommandRunner, UserHomeReader

from .test_integrations_cli import (
    CliSandbox,
    _CliTestTarget,
    _make_desired,
    cli_box,  # noqa: F401 - imported pytest fixture
)

pytestmark = [pytest.mark.e2e, pytest.mark.pg]


class DoctorTarget(_CliTestTarget):
    @override
    def client_layers(self, fs, home):
        return read_claude_layers(fs, home)

    @override
    def instruction_paths(self):
        return ("CLAUDE.md",)


class LookupRunner:
    def __init__(self):
        self.calls = []

    def run(self, argv, **kwargs):
        self.calls.append(tuple(argv))
        assert argv[0] == "which", "Doctor must never execute configured hooks"
        return CommandResult(0, b"/bin/skm-hook\n", b"", 0, False)


@pytest.fixture
def doctor_box(cli_box: CliSandbox, monkeypatch):  # noqa: F811 - imported pytest fixture
    from skm.modules.integrations.domain.ownership import ManagedBoundary, Ownership

    target = TargetId.CLAUDE_CODE
    boundary = ManagedBoundary(Ownership.MANAGED_FILE)
    documents = [
        (Surface.INSTRUCTIONS, "CLAUDE.md", b"All instructions including unmanaged notes\n"),
        (
            Surface.SKILLS,
            ".claude/skills/test/SKILL.md",
            b"---\nname: test\ndescription: Useful skill\n---\n",
        ),
        (Surface.AGENTS, ".claude/agents/test.md", b"---\ndescription: Useful agent\n---\n"),
        (Surface.MCP, ".mcp.json", b'{"mcpServers":{"docs":{"tool_count":2},"skm":{}}}\n'),
    ]
    cli_box.targets[target] = DoctorTarget(
        target, tuple(_make_desired(target, surface, path, boundary, raw) for surface, path, raw in documents)
    )
    for _, path, raw in documents:
        file = cli_box.repo_dir / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(raw)
    home = cli_box.root / "home"
    reader = LocalUserHomeReader(home, managed_root=cli_box.root / "managed")
    runner = LookupRunner()
    config: dict[str, Any] = {}
    original = cli_box.backend

    def backend(options, environ, on_secret=lambda _value: None):
        be = original(options, environ, on_secret)
        host_factory = be.host_factory
        assert host_factory is not None
        ctx = host_factory()
        assert isinstance(ctx.gateways, GatewayTable)
        gateways = GatewayTable(
            {**ctx.gateways.entries, UserHomeReader: reader, HostCommandRunner: runner}, "host_gateway"
        )
        return replace(be, host_factory=lambda: replace(ctx, gateways=gateways, config=config))

    monkeypatch.setattr(cli_box, "backend", backend)
    return cli_box, home, runner, config


@overload
def invoke(box: CliSandbox, *args: str, json_mode: Literal[True] = True) -> tuple[int, JsonObject, str]: ...
@overload
def invoke(box: CliSandbox, *args: str, json_mode: Literal[False]) -> tuple[int, str, str]: ...
@overload
def invoke(box: CliSandbox, *args: str, json_mode: bool) -> tuple[int, JsonObject | str, str]: ...


def invoke(box: CliSandbox, *args: str, json_mode: bool = True) -> tuple[int, JsonObject | str, str]:
    out, err = io.StringIO(), io.StringIO()
    argv = [*args, "--json"] if json_mode else list(args)
    code = cli_main(argv, stdin=io.StringIO(), stdout=out, stderr=err, environ=box.env(), backend=box.backend)
    output = out.getvalue()
    if not json_mode:
        return code, output, err.getvalue()
    value = json.loads(output)
    assert isinstance(value, dict)
    return code, value, err.getvalue()


def write_settings(home, data):
    path = home / ".claude/settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def test_doctor_json_human_aliases_identical_facts_and_no_mutation(doctor_box):
    box, home, runner, _ = doctor_box
    missing = "missing-extra-directory"
    write_settings(
        home,
        {
            "permissions": {"additionalDirectories": [missing]},
            "hooks": {
                "PreToolUse": [
                    {"hooks": [{"type": "command", "command": "skm-hook PreToolUse --never-execute"}]}
                ]
            },
        },
    )
    before = {
        str(path): path.read_bytes()
        for root in (box.repo_dir, home)
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }
    code, envelope, _ = invoke(box, "doctor", "--target", "claude_code")
    assert code == 0
    assert envelope["ok"] is True
    report = run_doctor_result_from_json(envelope["result"])
    assert "counts" in report
    assert report["status"] == "warning"
    assert sum(report["counts"].values()) == len(report["checks"])
    for prefix in ((), ("integrations",)):
        code, human, err = invoke(box, *prefix, "doctor", "--target", "claude_code", json_mode=False)
        assert code == 0
        assert not err
        assert "\\n" not in human
        assert len(human.splitlines()) > 10
        for fact in report["checks"]:
            assert fact["check_id"] in human
            assert fact["level"] in human
        assert missing in human
    alias_code, alias, _ = invoke(box, "integrations", "doctor", "--target", "claude_code")
    assert alias_code == 0
    assert alias["result"] == report
    assert runner.calls
    assert all(call[0] == "which" for call in runner.calls)
    after = {
        str(path): path.read_bytes()
        for root in (box.repo_dir, home)
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }
    assert after == before
    assert invoke(box, "doctor", "--target", "claude_code", "--strict")[0] == 1


def test_secret_values_never_escape_and_errors_exit_without_strict(doctor_box):
    box, home, _, _ = doctor_box
    secret = "sk-" + "private0123456789" * 4
    write_settings(home, {"env": {"API_TOKEN": secret}})
    for mode in (True, False):
        code, output, err = invoke(box, "doctor", "--target", "claude_code", json_mode=mode)
        assert code == 1
        assert secret not in str(output) + err
        assert "API_TOKEN" in str(output)
        assert "settings.json" in str(output)


def test_budget_five_sources_complete_human_json_aliases(doctor_box):
    box, _, runner, _ = doctor_box
    code, envelope, _ = invoke(box, "budget", "--target", "claude_code", "--strict")
    assert code == 0
    assert envelope["ok"]
    report = first_turn_budget_result_from_json(envelope["result"])
    assert [source["kind"] for source in report["sources"]] == [
        "skills",
        "agents",
        "instructions",
        "hooks",
        "mcp",
    ]
    tokens = [source["tokens"] for source in report["sources"]]
    assert None not in tokens
    assert report["total"] == sum(count for count in tokens if count is not None)
    assert report["verdict"] == "ok"
    assert not runner.calls
    for prefix in ((), ("integrations",)):
        assert invoke(box, *prefix, "budget", "--target", "claude_code")[1]["result"] == report
        code, human, err = invoke(box, *prefix, "budget", "--target", "claude_code", json_mode=False)
        assert code == 0
        assert not err
        assert "\\n" not in human
        for source in report["sources"]:
            assert source["kind"] in human
            assert str(source["tokens"]) in human
        assert str(report["total"]) in human
        assert "estimated" in human


def test_partial_native_budget_is_incomplete_and_strict_exit_is_one(doctor_box):
    box, _, runner, _ = doctor_box
    (box.repo_dir / ".claude/agents/test.md").unlink()
    code, envelope, _ = invoke(box, "budget", "--target", "claude_code")
    assert code == 0
    report = first_turn_budget_result_from_json(envelope["result"])
    assert report["verdict"] == "incomplete"
    assert report["total"] is None
    assert next(source for source in report["sources"] if source["kind"] == "agents")["tokens"] is None
    for mode in (True, False):
        code, output, _ = invoke(box, "budget", "--target", "claude_code", "--strict", json_mode=mode)
        assert code == 1
        assert "incomplete" in str(output)
    assert not runner.calls


def test_budget_thresholds_use_whole_instruction_file_and_strict_warn(doctor_box):
    box, _, _, config = doctor_box
    config.update(
        {"integrations.budget.first_turn.target": 1000, "integrations.budget.first_turn.warn": 1200}
    )
    (box.repo_dir / "CLAUDE.md").write_text("unmanaged instructions " * 2000)
    assert invoke(box, "budget", "--target", "claude_code")[0] == 0
    for mode in (True, False):
        code, output, _ = invoke(box, "budget", "--target", "claude_code", "--strict", json_mode=mode)
        assert code == 1
        assert "warn" in str(output)


def test_unmeasurable_session_hook_is_not_executed_or_reported_as_zero(doctor_box):
    box, home, runner, _ = doctor_box
    write_settings(
        home, {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "touch forbidden"}]}]}}
    )
    _, envelope, _ = invoke(box, "budget", "--target", "claude_code")
    report = first_turn_budget_result_from_json(envelope["result"])
    hooks = next(source for source in report["sources"] if source["kind"] == "hooks")
    assert hooks["tokens"] is None
    assert "detail" in hooks
    assert hooks["detail"]["run_hooks"] is False
    assert report["verdict"] == "incomplete"
    assert not runner.calls
    assert not (box.repo_dir / "forbidden").exists()


def test_invalid_budget_write_rejected_before_generation_or_entries_change(doctor_box):
    box, _, _, _ = doctor_box
    scope = ("--scope", "project")
    key = "integrations.budget.first_turn.target"
    before_code, before = box.run_json("config", "entries", *scope)
    assert before_code == 0
    code, rejected = box.run_json("config", "set", key, "24000", *scope)
    assert code != 0
    assert rejected["error"]["code"] == "CONFIG_INVALID"
    assert "integrations.budget_order" in json.dumps(rejected)
    after_code, after = box.run_json("config", "entries", *scope)
    assert after_code == 0
    assert after["result"] == before["result"]
    code, effective = box.run_json("config", "get", key, *scope)
    assert code == 0
    assert effective["result"]["value"] == 16000
