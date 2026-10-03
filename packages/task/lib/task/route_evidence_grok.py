"""Grok Build adapter for current-session route provenance.

Primary path: inspect the nearest ``grok`` / Grok ``agent`` ancestor argv for
``--model`` / ``-m``, ``--cwd`` and the slash ``/task:`` prompt.  When that
launch has no ``--model``, ``~/.grok/config.toml`` ``[models].default`` and
``default_reasoning_effort`` resolve through ``command-routing.json``.

``agent`` on PATH is the same Grok binary as ``grok``. Cursor's CLI is
``cursor-agent``; this adapter never treats Cursor argv as Grok.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from task.route_evidence import (
    RouteEvidenceError, capture_actual, exactly_one, invocation_extends, launch_option_values,
    mapped_effort, mapped_model_class, proc_parent_argv)


CLI_SOURCE_VERSION = "grok-ancestor-argv-v1"
_CONFIG_SOURCE_VERSION = "grok-config-toml-v1"
_ATTEST_SOURCE_VERSION = "grok-explicit-attestation-v1"
_ROUTING_PATH = Path(__file__).resolve().parents[2] / "configs" / "command-routing.json"
_GROK_ARGV0 = frozenset({"grok", "agent"})


def _proc_entry(pid: int) -> tuple[int, tuple[str, ...]]:
    return proc_parent_argv(pid, label="Grok")


def _is_grok_launch(argv: tuple[str, ...]) -> bool:
    """``agent`` is Grok's PATH alias; Cursor historically used the same name.

    Cursor launches carry ``--workspace`` or ``cursor-agent``. Grok launches are
    ``grok``, or ``agent`` with ``--cwd`` / ``--always-approve`` / a grok path /
    ``GROK_SESSION_ID`` / ``GROK_AGENT=1``.
    """
    path = argv[0] if argv else ""
    name = Path(path).name
    tokens = set(argv[1:])
    if "cursor-agent" in path or name == "cursor-agent" or "--workspace" in tokens:
        return False
    if name == "grok":
        return True
    if name != "agent":
        return False
    if "grok" in path.lower():
        return True
    if "--always-approve" in tokens or "--cwd" in tokens or any(
            token.startswith("--cwd=") for token in tokens):
        return True
    session = os.environ.get("GROK_SESSION_ID")
    if isinstance(session, str) and session.strip() and not any(char.isspace() for char in session.strip()):
        return True
    return os.environ.get("GROK_AGENT") == "1"


def _grok_ancestor(start_pid: int, process_table=None) -> tuple[str, ...]:
    pid = start_pid
    seen = set()
    for _ in range(64):
        if pid <= 1 or pid in seen:
            break
        seen.add(pid)
        try:
            parent, argv = process_table[pid] if process_table is not None else _proc_entry(pid)
        except KeyError as error:
            raise RouteEvidenceError(
                "ROUTE_LAUNCH_UNAVAILABLE",
                f"process {pid} is absent from the ancestry snapshot") from error
        if _is_grok_launch(argv):
            return tuple(argv)
        pid = parent
    raise RouteEvidenceError(
        "ROUTE_LAUNCH_UNAVAILABLE", "current process is not a descendant of a Grok launch")


def _option_values(argv: tuple[str, ...], short: str, long: str) -> tuple[str, ...]:
    return launch_option_values(argv, short, long)


def _one(values: tuple[str, ...], label: str) -> str:
    return exactly_one(values, label)


def _selector_class(model: str, routing_path: Path) -> str:
    return mapped_model_class("grok", model, routing_path)


def _selector_effort(selector: str, routing_path: Path) -> str:
    return mapped_effort("grok", selector, routing_path, label="Grok")


def _normalize_invocation(value: str) -> str:
    semantic = value.strip()
    if semantic.startswith("/task:"):
        return semantic
    if semantic.startswith("task:"):
        return "/" + semantic
    raise RouteEvidenceError("ROUTE_LAUNCH_MISMATCH", "expected slash /task:<command> form")


def _invocation_extends(actual: str, expected: str) -> bool:
    return invocation_extends(actual, expected)


def _thread_id() -> str | None:
    value = os.environ.get("GROK_SESSION_ID")
    if not isinstance(value, str):
        return None
    session_id = value.strip()
    if session_id and not any(char.isspace() for char in session_id):
        return session_id
    return None


def _prompt_tokens(argv: tuple[str, ...]) -> tuple[str, ...]:
    skip = {"--always-approve", "--force", "--yolo", "--continue", "-c",
            "--debug", "--oauth", "--minimal", "--fullscreen", "--no-plan",
            "--no-subagents", "--no-alt-screen", "--fork-session"}
    valued = {"-m", "--model", "--cwd", "--agent", "--agents", "--allow", "--deny",
              "--max-turns", "--output-format", "--session-id", "--resume",
              "--debug-file", "--json-schema", "--leader-socket"}
    index = 1
    prompts = []
    while index < len(argv):
        token = argv[index]
        if token in skip:
            index += 1
            continue
        if token in valued or any(token.startswith(flag + "=") for flag in valued if flag.startswith("--")):
            if token in valued and "=" not in token:
                index += 2
            else:
                index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        if token in {"agent", "login", "mcp", "models", "sessions", "doctor", "help"}:
            index += 1
            continue
        prompts.append(token)
        index += 1
    return tuple(prompts)


def _capture_argv(*, expected_invocation: str, expected_cwd: str | Path,
                  start_pid: int | None, process_table, routing_path: Path) -> dict:
    argv = _grok_ancestor(start_pid or os.getpid(), process_table)
    models = _option_values(argv, "-m", "--model")
    cwds = _option_values(argv, "", "--cwd")
    prompts = tuple(_normalize_invocation(value) for value in _prompt_tokens(argv)
                    if "task:" in value)
    if not prompts:
        raise RouteEvidenceError("ROUTE_LAUNCH_UNAVAILABLE", "Grok argv has no Task prompt")
    invocation = _one(prompts, "Task prompt")
    expected = _normalize_invocation(expected_invocation)
    if not _invocation_extends(invocation, expected):
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_MISMATCH",
            f"Grok Task prompt {invocation!r} != expected {expected!r}")
    cwd = Path(cwds[0]).resolve() if len(cwds) == 1 else Path.cwd().resolve()
    if cwd != Path(expected_cwd).resolve():
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_MISMATCH",
            f"Grok cwd {str(cwd)!r} != expected {str(expected_cwd)!r}")
    if not models:
        raise RouteEvidenceError("ROUTE_LAUNCH_UNAVAILABLE", "Grok launch has no --model")
    model = _one(models, "Grok model selector")
    evidence = capture_actual(
        _selector_class(model, routing_path),
        _default_effort(routing_path),
        source="cli-flag",
        model=model,
    )
    evidence.update({
        "thread_id": _thread_id() or f"grok-argv:{cwd}:{invocation}",
        "source_version": CLI_SOURCE_VERSION,
        "cwd": str(cwd),
        "invocation": invocation,
    })
    return evidence


def _default_effort(routing_path: Path) -> str:
    return _selector_effort("medium", routing_path)


def _parse_toml_models(text: str) -> tuple[str | None, str | None]:
    section = None
    model = effort = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            continue
        if section != "models" or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if value.startswith('"') and value.endswith('"'):
            value = json.loads(value)
        if key == "default" and isinstance(value, str):
            model = value
        if key == "default_reasoning_effort" and isinstance(value, str):
            effort = value
    return model, effort


def _capture_config(*, expected_invocation: str, expected_cwd: str | Path,
                    routing_path: Path, config_path: Path) -> dict:
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError as error:
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_UNAVAILABLE", f"Grok config.toml is unreadable: {error}") from error
    model, effort_selector = _parse_toml_models(text)
    if not isinstance(model, str) or not model:
        raise RouteEvidenceError("ROUTE_LAUNCH_UNAVAILABLE", "Grok config has no [models].default")
    if not isinstance(effort_selector, str) or not effort_selector:
        effort_selector = "medium"
    cwd = Path.cwd().resolve()
    if cwd != Path(expected_cwd).resolve():
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_MISMATCH",
            f"Grok cwd {str(cwd)!r} != expected {str(expected_cwd)!r}")
    invocation = _normalize_invocation(expected_invocation)
    evidence = capture_actual(
        _selector_class(model, routing_path),
        _selector_effort(effort_selector, routing_path),
        source="provider-config",
        model=model,
    )
    evidence.update({
        "thread_id": _thread_id() or f"grok-config:{model}",
        "source_version": _CONFIG_SOURCE_VERSION,
        "cwd": str(cwd),
        "invocation": invocation,
    })
    return evidence


def capture_current(*, expected_invocation: str, expected_cwd: str | Path,
                    routing_path: str | Path = _ROUTING_PATH,
                    start_pid: int | None = None, process_table=None,
                    config_path: str | Path | None = None,
                    attestation: dict | None = None) -> dict:
    """Capture and validate the current Grok route for this session."""
    routing_path = Path(routing_path)
    semantic = _normalize_invocation(expected_invocation)
    try:
        return _capture_argv(
            expected_invocation=semantic,
            expected_cwd=expected_cwd,
            start_pid=start_pid,
            process_table=process_table,
            routing_path=routing_path,
        )
    except RouteEvidenceError as error:
        if error.code != "ROUTE_LAUNCH_UNAVAILABLE":
            raise
    try:
        path = Path(config_path) if config_path is not None else Path.home() / ".grok" / "config.toml"
        return _capture_config(
            expected_invocation=semantic,
            expected_cwd=expected_cwd,
            routing_path=routing_path,
            config_path=path,
        )
    except RouteEvidenceError as error:
        if error.code != "ROUTE_LAUNCH_UNAVAILABLE" or attestation is None:
            raise
    if not isinstance(attestation, dict):
        raise RouteEvidenceError("ROUTE_LAUNCH_UNAVAILABLE", "grok attestation is invalid")
    model = attestation.get("model")
    model_class = attestation.get("model_class")
    effort = attestation.get("effort")
    cwd = attestation.get("cwd")
    invocation = attestation.get("invocation")
    if not all(isinstance(value, str) and value for value in (model, model_class, effort, cwd, invocation)):
        raise RouteEvidenceError("ROUTE_LAUNCH_UNAVAILABLE", "grok attestation is incomplete")
    if _normalize_invocation(invocation) != semantic:
        raise RouteEvidenceError("ROUTE_LAUNCH_MISMATCH", "grok attestation invocation mismatch")
    if Path(cwd).resolve() != Path(expected_cwd).resolve():
        raise RouteEvidenceError("ROUTE_LAUNCH_MISMATCH", "grok attestation cwd mismatch")
    if model_class != _selector_class(model, routing_path):
        raise RouteEvidenceError("ROUTE_LAUNCH_MISMATCH", "grok attestation model_class mismatch")
    evidence = capture_actual(model_class, effort, source="provider-attestation", model=model)
    evidence.update({
        "thread_id": str(attestation.get("thread_id") or f"grok-attest:{cwd}:{invocation}"),
        "source_version": _ATTEST_SOURCE_VERSION,
        "cwd": str(Path(cwd).resolve()),
        "invocation": semantic,
    })
    return evidence


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Capture current Grok session route with argv or config.toml.")
    sub = parser.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("capture")
    capture.add_argument("--expected-invocation", required=True)
    capture.add_argument("--expected-cwd", required=True)
    capture.add_argument("--attestation", default=None)
    capture.add_argument("--config", default=None)
    args = parser.parse_args(argv)
    attestation = None
    if args.attestation:
        attestation = json.loads(Path(args.attestation).read_text(encoding="utf-8"))
    evidence = capture_current(
        expected_invocation=args.expected_invocation,
        expected_cwd=args.expected_cwd,
        config_path=args.config,
        attestation=attestation,
    )
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
