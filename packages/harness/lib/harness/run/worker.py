"""Internal documentation."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from . import task_paths


OUTCOME_OK = "ok"
OUTCOME_TRANSPORT = "transport"
OUTCOME_TIMEOUT = "timeout"
OUTCOME_QUOTA = "quota"
OUTCOME_ERROR = "error"



CLAUDE_BIN_ENV = "SKM_CLAUDE_BIN"



PROVIDER_ID = "claude-code"
WORKER_COMMAND_ID = "task:plan-run"







DEFAULT_TIMEOUT = 1800




_QUOTA_TEXT_MARKERS = ("session limit", "weekly limit")


class WorkerUnavailable(RuntimeError):
    """Internal documentation."""


def resolve_claude_bin():
    """Internal documentation."""
    override = os.environ.get(CLAUDE_BIN_ENV)
    if override:
        p = Path(os.path.expanduser(override))
        return str(p) if p.exists() else None
    return shutil.which("claude")


def _load_routing_config(task):
    path = task_paths.routing_in(task)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"{path} is not readable: {exc}"
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        return None, f"{path} not JSON: {exc}"


def _first(selectors):
    return selectors[0] if isinstance(selectors, list) and selectors else None


def build_argv(plan_id, item_id, *, model_class, effort, monorepo_root=None, claude_bin):
    """Internal documentation."""
    try:
        task = task_paths.task_root(monorepo_root=monorepo_root)
    except task_paths.TaskUnavailable as exc:
        raise WorkerUnavailable(f"routing media not available: {exc}") from exc
    routing, reason = _load_routing_config(task)
    if routing is None:
        raise WorkerUnavailable(f"routing media not available: {reason}")

    mapping = ((routing.get("mappings") or {}).get(PROVIDER_ID)) or {}
    model_selector = _first((mapping.get("class_selectors") or {}).get(model_class))
    effort_selector = _first((mapping.get("effort_selectors") or {}).get(effort))
    template = (mapping.get("invocation_binding") or {}).get("template")

    if model_selector is None:
        raise WorkerUnavailable(
            f"command-routing.json: no class selector {model_class!r} for {PROVIDER_ID!r}")
    if effort_selector is None:
        raise WorkerUnavailable(
            f"command-routing.json: no selector effort {effort!r} for {PROVIDER_ID!r}")
    if not template:
        raise WorkerUnavailable(
            f"command-routing.json: no invocation_binding.template for {PROVIDER_ID!r}")

    invocation = template.format(command_id=WORKER_COMMAND_ID, arguments=f"{plan_id} {item_id}")
    return [claude_bin, "-p", invocation, "--output-format", "json",
            "--model", model_selector, "--effort", effort_selector]


def _capture_client_version(claude_bin_path, *, timeout=10):
    """Internal documentation."""
    try:
        proc = subprocess.run([claude_bin_path, "--version"], capture_output=True, text=True,
                              timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout.strip() if proc.returncode == 0 and proc.stdout else None


def _is_quota_text(text):
    lowered = text.lower()
    return any(marker in lowered for marker in _QUOTA_TEXT_MARKERS)


def _outcome(kind, *, argv, client_version, reason=None, raw_stdout=None, exit_code=None,
            envelope=None):
    envelope = envelope or {}
    return {
        "outcome": kind,
        "reason": reason,
        "argv": list(argv),
        "client_version": client_version,
        "exit_code": exit_code,
        "session_id": envelope.get("session_id"),
        "total_cost_usd": envelope.get("total_cost_usd"),
        "num_turns": envelope.get("num_turns"),
        "duration_ms": envelope.get("duration_ms"),
        "permission_denials": envelope.get("permission_denials"),
        "subtype": envelope.get("subtype"),
        "stop_reason": envelope.get("stop_reason"),
        "terminal_reason": envelope.get("terminal_reason"),
        "api_error_status": envelope.get("api_error_status"),
        "result_text": envelope.get("result"),
        "raw_stdout": raw_stdout,
    }


def _classify_envelope(proc, argv, client_version):
    """Internal documentation."""
    raw = proc.stdout or ""
    try:
        envelope = json.loads(raw) if raw.strip() else None
    except json.JSONDecodeError:
        envelope = None

    if not isinstance(envelope, dict) or envelope.get("type") != "result":
        return _outcome(OUTCOME_TRANSPORT, argv=argv, client_version=client_version,
                        reason="envelope is broken, empty or not `result`",
                        raw_stdout=raw[:2000], exit_code=proc.returncode)

    is_error = envelope.get("is_error")
    if is_error is False and proc.returncode == 0:
        return _outcome(OUTCOME_OK, argv=argv, client_version=client_version,
                        exit_code=proc.returncode, envelope=envelope)
    if is_error is True:
        kind = OUTCOME_QUOTA if _is_quota_text(str(envelope.get("result") or "")) else OUTCOME_ERROR
        return _outcome(kind, argv=argv, client_version=client_version,
                        exit_code=proc.returncode, envelope=envelope)



    return _outcome(OUTCOME_TRANSPORT, argv=argv, client_version=client_version,
                    reason=f"unknown combination is_error={is_error!r} / exit={proc.returncode}",
                    raw_stdout=raw[:2000], exit_code=proc.returncode, envelope=envelope)


def run(plan_id, item_id, *, model_class, effort, monorepo_root=None, claude_bin=None,
        timeout=DEFAULT_TIMEOUT):
    """Internal documentation."""
    try:
        task_paths.task_root(monorepo_root=monorepo_root)
    except task_paths.TaskUnavailable as exc:
        raise WorkerUnavailable(f"{exc} (command-routing.json not available)") from exc

    resolved_bin = claude_bin or resolve_claude_bin()
    if resolved_bin is None:
        raise WorkerUnavailable(f"client binary not found (env {CLAUDE_BIN_ENV} → PATH)")

    argv = build_argv(plan_id, item_id, model_class=model_class, effort=effort,
                      monorepo_root=monorepo_root, claude_bin=resolved_bin)
    client_version = _capture_client_version(resolved_bin)

    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return _outcome(OUTCOME_TIMEOUT, argv=argv, client_version=client_version,
                        reason=f"process did not complete in {timeout}s")
    except OSError as exc:
        return _outcome(OUTCOME_TRANSPORT, argv=argv, client_version=client_version,
                        reason=f"process did not start: {exc}")

    return _classify_envelope(proc, argv, client_version)
