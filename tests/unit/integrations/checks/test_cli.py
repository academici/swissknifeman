"""Both render modes, every doctor/budget exit condition, and consumed command flags."""

import argparse
import io
import json
from uuid import UUID

import pytest

from skm.entrypoints.cli.commands import budget, doctor
from skm.entrypoints.cli.context import CliOptions, CliSession
from skm.platform.logging.redaction import Redactor
from skm.platform.system_clock import SystemClock
from skm.platform.system_ids import Uuid7Generator


@pytest.mark.parametrize("json_mode", [False, True])
@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize("status", ["ok", "info", "warning", "error"])
def test_doctor_flags_modes_and_strict_exit(monkeypatch, json_mode, strict, status):
    parser = argparse.ArgumentParser()
    doctor.register(parser.add_subparsers())
    args = parser.parse_args(
        [
            "doctor",
            "--project",
            "selected",
            "--target",
            "codex",
            "--target",
            "cursor",
            *(["--json"] if json_mode else []),
            *(["--strict"] if strict else []),
        ]
    )
    out = io.StringIO()
    ctx = CliSession(
        CliOptions(json=json_mode), out, io.StringIO(), Redactor(), Uuid7Generator(SystemClock()), "cli-test"
    )
    report = {
        "project_id": str(UUID(int=1)),
        "host_id": str(UUID(int=2)),
        "targets": ["codex", "cursor"],
        "status": status,
        "counts": {level: int(level == status) for level in ("ok", "info", "warning", "error")},
        "checks": [
            {
                "target": "codex",
                "check_id": "codex.layers_readable",
                "level": status,
                "title": "Layers",
                "path": "config.toml",
                "detail": "facts",
                "hint": "advice",
            }
        ],
    }

    def project(_ctx, selected):
        assert selected == "selected"
        return UUID(int=1)

    def operation(_ctx, name, request):
        assert name == "integrations.host.run_doctor"
        assert request == {"project_id": str(UUID(int=1)), "targets": ["codex", "cursor"]}
        return report

    monkeypatch.setattr(doctor, "resolve_project_id", project)
    monkeypatch.setattr(doctor, "run_host_operation", operation)
    code = args.run(args, ctx)
    assert code == int(status == "error" or (strict and status == "warning"))
    if json_mode:
        assert json.loads(out.getvalue())["result"] == report
    else:
        assert "advice" in out.getvalue()
        assert "config.toml" in out.getvalue()
        assert len(out.getvalue().splitlines()) >= 4
        assert "\\n" not in out.getvalue()


@pytest.mark.parametrize("json_mode", [False, True])
@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize("verdict", ["ok", "elevated", "warn", "incomplete"])
def test_budget_flags_modes_and_strict_exit(monkeypatch, json_mode, strict, verdict):
    parser = argparse.ArgumentParser()
    budget.register(parser.add_subparsers())
    args = parser.parse_args(
        [
            "budget",
            "--project",
            "selected",
            "--target",
            "codex",
            *(["--json"] if json_mode else []),
            *(["--strict"] if strict else []),
        ]
    )
    out = io.StringIO()
    ctx = CliSession(
        CliOptions(json=json_mode), out, io.StringIO(), Redactor(), Uuid7Generator(SystemClock()), "cli-test"
    )
    report = {
        "project_id": str(UUID(int=1)),
        "target": "codex",
        "include_plugins": False,
        "verdict": verdict,
        "total": None if verdict == "incomplete" else 18000,
        "thresholds": {"target": 16000, "warn": 23000},
        "sources": [
            {
                "kind": "instructions",
                "tokens": None if verdict == "incomplete" else 18000,
                "method": "estimate_tokens(whole file)",
                "detail": {"files": ["AGENTS.md"]},
            }
        ],
    }

    def project(_ctx, selected):
        assert selected == "selected"
        return UUID(int=1)

    def operation(_ctx, name, request):
        assert name == "integrations.host.first_turn_budget"
        assert request == {"project_id": str(UUID(int=1)), "target": "codex", "include_plugins": False}
        return report

    monkeypatch.setattr(budget, "resolve_project_id", project)
    monkeypatch.setattr(budget, "run_host_operation", operation)
    assert args.run(args, ctx) == int(strict and verdict in ("warn", "incomplete"))
    if json_mode:
        assert json.loads(out.getvalue())["result"] == report
    else:
        assert "AGENTS.md" in out.getvalue()
        assert verdict in out.getvalue()
        assert len(out.getvalue().splitlines()) >= 4
        assert "\\n" not in out.getvalue()
