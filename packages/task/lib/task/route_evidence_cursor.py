"""Cursor adapter for current-session route provenance.

Primary path: inspect the nearest ``agent`` ancestor argv for ``--workspace``,
``--model`` and the semantic ``task:`` prompt.  When that launch has no
``--model``, the live ``~/.cursor/cli-config.json`` ``selectedModel`` and
``reasoning_effort`` (or Grok 4.6 ``effort``) resolve through
``command-routing.json`` selectors.
An explicit attestation remains only when that config is unreadable, and it
still fails closed on selector mismatch.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from task.route_evidence import (
    RouteEvidenceError, capture_actual, exactly_one, invocation_extends, launch_option_values,
    mapped_effort, mapped_model_class, proc_parent_argv)


CLI_SOURCE_VERSION = "cursor-ancestor-argv-v1"
_CLI_CONFIG_SOURCE_VERSION = "cursor-cli-config-v1"
_RESUME_SOURCE_VERSION = "cursor-chat-store-v1"
_ATTEST_SOURCE_VERSION = "cursor-explicit-attestation-v1"
_ROUTING_PATH = Path(__file__).resolve().parents[2] / "configs" / "command-routing.json"


def _proc_entry(pid: int) -> tuple[int, tuple[str, ...]]:
    return proc_parent_argv(pid, label="Cursor")


def _agent_ancestor(start_pid: int, process_table=None) -> tuple[str, ...]:
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
        if Path(argv[0]).name in {"agent", "cursor-agent"}:
            return tuple(argv)
        pid = parent
    raise RouteEvidenceError(
        "ROUTE_LAUNCH_UNAVAILABLE", "current process is not a descendant of a Cursor agent launch")


def _cursor_thread_id() -> str | None:
    """Session id already observed by ``session_context_cursor``.

    A fresh ``agent --model`` launch is not a resume, so the chat-store path
    does not run. The conversation id is still the session the runtime binds.
    """
    for key in ("CURSOR_CONVERSATION_ID", "CURSOR_AGENT_CHAT_ID", "CURSOR_SESSION_ID"):
        value = os.environ.get(key)
        if not isinstance(value, str):
            continue
        session_id = value.strip()
        if session_id and not any(char.isspace() for char in session_id):
            return session_id
    return None


def _option_values(argv: tuple[str, ...], short: str, long: str) -> tuple[str, ...]:
    return launch_option_values(argv, short, long)


def _one(values: tuple[str, ...], label: str) -> str:
    return exactly_one(values, label)


def _selector_class(model: str, routing_path: Path) -> str:
    return mapped_model_class("cursor", model, routing_path)


def _selector_effort(selector: str, routing_path: Path) -> str:
    return mapped_effort("cursor", selector, routing_path, label="Cursor")


def _normalize_invocation(value: str) -> str:
    semantic = value.strip()
    if semantic.startswith("task:"):
        return semantic
    if semantic.startswith("/task:"):
        return semantic[1:]
    raise RouteEvidenceError("ROUTE_LAUNCH_MISMATCH", "expected semantic task:<command> form")


def _invocation_extends(actual: str, expected: str) -> bool:
    """Admit the execution-sheet prompt when it continues the admitted command."""
    return invocation_extends(actual, expected)


def _model_and_effort(selector: str, routing_path: Path) -> tuple[str, str]:
    """Map a Cursor ``--model`` slug onto catalog id plus effort.

    A whole catalog id such as ``claude-opus-5-thinking-high`` stays intact and
    keeps the argv default effort. ``grok-4.7-high`` is the CLI form of catalog
    model ``grok-4.7`` with effort ``high``.
    """
    try:
        _selector_class(selector, routing_path)
    except RouteEvidenceError as whole:
        base, separator, effort = selector.rpartition("-")
        if not separator:
            raise
        try:
            _selector_effort(effort, routing_path)
            _selector_class(base, routing_path)
        except RouteEvidenceError:
            raise whole from None
        return base, effort
    return selector, "medium"


def _capture_argv(*, expected_invocation: str, expected_cwd: str | Path,
                  start_pid: int | None, process_table, routing_path: Path) -> dict:
    argv = _agent_ancestor(start_pid or os.getpid(), process_table)
    model = _one(_option_values(argv, "-m", "--model"), "Cursor model selector")
    workspace = _one(_option_values(argv, "", "--workspace"), "Cursor workspace")
    invocations = tuple(_normalize_invocation(value) for value in argv if "task:" in value)
    invocation = _one(invocations, "Task prompt")
    expected = _normalize_invocation(expected_invocation)
    if not _invocation_extends(invocation, expected):
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_MISMATCH",
            f"Cursor Task prompt {invocation!r} != expected {expected!r}")
    if Path(workspace).resolve() != Path(expected_cwd).resolve():
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_MISMATCH",
            f"Cursor workspace {workspace!r} != expected {str(expected_cwd)!r}")
    if "--force" not in argv and "--yolo" not in argv:
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_MISMATCH", "Cursor launch is missing --force/--yolo")
    catalog_model, effort_selector = _model_and_effort(model, routing_path)
    evidence = capture_actual(
        _selector_class(catalog_model, routing_path),
        _selector_effort(effort_selector, routing_path),
        source="cli-flag",
        model=model,
    )
    evidence.update({
        "thread_id": _cursor_thread_id(),
        "source_version": CLI_SOURCE_VERSION,
        "cwd": str(Path(workspace).resolve()),
        "invocation": invocation,
    })
    if evidence["thread_id"] is None:
        evidence["thread_id"] = f"cursor-argv:{evidence['cwd']}:{invocation}"
    return evidence


def _cli_config_file(explicit: str | Path | None) -> Path:
    if explicit is not None:
        return Path(explicit)
    return Path.home() / ".cursor" / "cli-config.json"


def _effort_from_cli_parameters(parameters: list) -> str:
    """Grok 4.7 uses ``reasoning_effort``; Grok 4.6 uses ``effort``."""
    by_id: dict[str, tuple[str, ...]] = {}
    for item in parameters:
        if not isinstance(item, dict):
            continue
        key = item.get("id")
        value = item.get("value")
        if key not in {"reasoning_effort", "effort"}:
            continue
        if not isinstance(value, str) or not value:
            continue
        by_id[key] = by_id.get(key, ()) + (value,)
    if "reasoning_effort" in by_id and "effort" in by_id:
        reasoning = _one(by_id["reasoning_effort"], "Cursor reasoning_effort")
        effort = _one(by_id["effort"], "Cursor effort")
        if reasoning != effort:
            raise RouteEvidenceError(
                "ROUTE_LAUNCH_MISMATCH",
                f"Cursor reasoning_effort {reasoning!r} != effort {effort!r}")
        return reasoning
    if "reasoning_effort" in by_id:
        return _one(by_id["reasoning_effort"], "Cursor reasoning_effort")
    if "effort" in by_id:
        return _one(by_id["effort"], "Cursor effort")
    return _one((), "Cursor reasoning_effort")


def _capture_cli_config(*, expected_invocation: str, expected_cwd: str | Path,
                        routing_path: Path, cli_config_path: Path) -> dict:
    try:
        payload = json.loads(cli_config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_UNAVAILABLE", f"Cursor cli-config is unreadable: {error}") from error
    selected = payload.get("selectedModel") if isinstance(payload, dict) else None
    if not isinstance(selected, dict):
        raise RouteEvidenceError("ROUTE_LAUNCH_UNAVAILABLE", "Cursor cli-config has no selectedModel")
    model = selected.get("modelId")
    if not isinstance(model, str) or not model:
        raise RouteEvidenceError("ROUTE_LAUNCH_UNAVAILABLE", "Cursor selectedModel.modelId is absent")
    parameters = selected.get("parameters")
    if not isinstance(parameters, list):
        raise RouteEvidenceError("ROUTE_LAUNCH_UNAVAILABLE", "Cursor selectedModel.parameters is absent")
    effort_selector = _effort_from_cli_parameters(parameters)
    cwd = Path.cwd().resolve()
    if cwd != Path(expected_cwd).resolve():
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_MISMATCH",
            f"Cursor cwd {str(cwd)!r} != expected {str(expected_cwd)!r}")
    evidence = capture_actual(
        _selector_class(model, routing_path),
        _selector_effort(effort_selector, routing_path),
        source="provider-config",
        model=model,
    )
    thread = os.environ.get("CURSOR_CONVERSATION_ID") or os.environ.get("CURSOR_AGENT_CHAT_ID")
    evidence.update({
        "thread_id": thread.strip() if isinstance(thread, str) and thread.strip() else f"cursor-cli-config:{model}",
        "source_version": _CLI_CONFIG_SOURCE_VERSION,
        "cwd": str(cwd),
        "invocation": _normalize_invocation(expected_invocation),
    })
    return evidence


def _resume_argv(start_pid: int | None, process_table) -> tuple[str, ...] | None:
    try:
        argv = _agent_ancestor(start_pid or os.getpid(), process_table)
    except RouteEvidenceError:
        return None
    if "resume" not in argv or "--model" in argv or "-m" in argv:
        return None
    return argv


def _chat_directory(conversation_id: str, chats_root: Path) -> Path:
    matches = [path for path in chats_root.glob(f"*/{conversation_id}") if path.is_dir()]
    if len(matches) != 1:
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_UNAVAILABLE",
            f"expected one Cursor chat directory for this session, observed {len(matches)}")
    return matches[0]


def _last_used_model(store: Path) -> str:
    import sqlite3

    try:
        connection = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    except sqlite3.Error as error:
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_UNAVAILABLE", "cursor chat store is unreadable") from error
    try:
        row = connection.execute("SELECT value FROM meta LIMIT 1").fetchone()
    except sqlite3.Error as error:
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_UNAVAILABLE", "cursor chat store is unreadable") from error
    finally:
        connection.close()
    if row is None or not isinstance(row[0], str):
        raise RouteEvidenceError("ROUTE_LAUNCH_UNAVAILABLE", "cursor chat store has no meta")
    try:
        payload = bytes.fromhex(row[0])
        data = json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_UNAVAILABLE", "cursor chat meta is unreadable") from error
    model = data.get("lastUsedModel") if isinstance(data, dict) else None
    if not isinstance(model, str) or not model:
        raise RouteEvidenceError("ROUTE_LAUNCH_UNAVAILABLE", "cursor chat has no lastUsedModel")
    return model


def _capture_resume(*, expected_invocation: str, expected_cwd: str | Path,
                    start_pid: int | None, process_table, routing_path: Path,
                    chats_root: Path, conversation_id: str | None) -> dict:
    argv = _resume_argv(start_pid, process_table)
    if argv is None:
        raise RouteEvidenceError("ROUTE_LAUNCH_UNAVAILABLE", "current process is not a Cursor resume")
    if "--force" not in argv and "--yolo" not in argv:
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_MISMATCH", "Cursor resume is missing --force/--yolo")
    if not isinstance(conversation_id, str) or not conversation_id.strip():
        raise RouteEvidenceError("ROUTE_LAUNCH_UNAVAILABLE", "Cursor conversation id is absent")
    conversation_id = conversation_id.strip()
    chat = _chat_directory(conversation_id, chats_root)
    try:
        sidecar = json.loads((chat / "meta.json").read_text(encoding="utf-8"))
        history = json.loads((chat / "prompt_history.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_UNAVAILABLE", "cursor chat sidecar is unreadable") from error
    cwd = sidecar.get("cwd") if isinstance(sidecar, dict) else None
    if not isinstance(cwd, str) or Path(cwd).resolve() != Path(expected_cwd).resolve():
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_MISMATCH",
            f"Cursor chat cwd {cwd!r} != expected {str(expected_cwd)!r}")
    if not isinstance(history, list) or not history or not isinstance(history[0], str):
        raise RouteEvidenceError("ROUTE_LAUNCH_UNAVAILABLE", "cursor prompt history is empty")
    invocation = _normalize_invocation(history[0])
    expected = _normalize_invocation(expected_invocation)
    if not _invocation_extends(invocation, expected):
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_MISMATCH",
            f"Cursor resume prompt {invocation!r} != expected {expected!r}")
    model = _last_used_model(chat / "store.db")
    catalog_model, effort_selector = _model_and_effort(model, routing_path)
    evidence = capture_actual(
        _selector_class(catalog_model, routing_path),
        _selector_effort(effort_selector, routing_path),
        source="provider-thread-state",
        model=model,
    )
    evidence.update({
        "thread_id": conversation_id,
        "source_version": _RESUME_SOURCE_VERSION,
        "cwd": str(Path(cwd).resolve()),
        "invocation": invocation,
    })
    return evidence


def capture_current(*, expected_invocation: str, expected_cwd: str | Path,
                    attestation: dict | None = None, start_pid: int | None = None,
                    process_table=None, routing_path: str | Path = _ROUTING_PATH,
                    cli_config_path: str | Path | None = None,
                    chats_root: str | Path | None = None,
                    conversation_id: str | None = None) -> dict:
    """Capture and validate the current Cursor route for this session."""
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
        # A modeled launch that disagrees with the admitted command must not
        # fall through to cli-config. A resume argv has no --model; that miss
        # is the resume path, not a second model source.
        if error.code != "ROUTE_LAUNCH_UNAVAILABLE" and _resume_argv(start_pid, process_table) is None:
            raise
    if _resume_argv(start_pid, process_table) is not None:
        try:
            return _capture_resume(
                expected_invocation=semantic,
                expected_cwd=expected_cwd,
                start_pid=start_pid,
                process_table=process_table,
                routing_path=routing_path,
                chats_root=Path(chats_root) if chats_root is not None else Path.home() / ".cursor" / "chats",
                conversation_id=conversation_id or os.environ.get("CURSOR_CONVERSATION_ID"),
            )
        except RouteEvidenceError as error:
            if error.code != "ROUTE_LAUNCH_UNAVAILABLE":
                raise
    try:
        return _capture_cli_config(
            expected_invocation=semantic,
            expected_cwd=expected_cwd,
            routing_path=routing_path,
            cli_config_path=_cli_config_file(cli_config_path),
        )
    except RouteEvidenceError as error:
        if error.code != "ROUTE_LAUNCH_UNAVAILABLE" or attestation is None:
            raise
    if not isinstance(attestation, dict):
        raise RouteEvidenceError("ROUTE_LAUNCH_UNAVAILABLE", "cursor attestation is invalid")
    model = attestation.get("model")
    model_class = attestation.get("model_class")
    effort = attestation.get("effort")
    cwd = attestation.get("cwd")
    invocation = attestation.get("invocation")
    if not all(isinstance(value, str) and value for value in (model, model_class, effort, cwd, invocation)):
        raise RouteEvidenceError("ROUTE_LAUNCH_UNAVAILABLE", "cursor attestation is incomplete")
    if _normalize_invocation(invocation) != semantic:
        raise RouteEvidenceError("ROUTE_LAUNCH_MISMATCH", "cursor attestation invocation mismatch")
    if Path(cwd).resolve() != Path(expected_cwd).resolve():
        raise RouteEvidenceError("ROUTE_LAUNCH_MISMATCH", "cursor attestation cwd mismatch")
    if model_class != _selector_class(model, routing_path):
        raise RouteEvidenceError("ROUTE_LAUNCH_MISMATCH", "cursor attestation model_class mismatch")
    evidence = capture_actual(model_class, effort, source="provider-attestation", model=model)
    evidence.update({
        "thread_id": str(attestation.get("thread_id") or f"cursor-attest:{cwd}:{invocation}"),
        "source_version": _ATTEST_SOURCE_VERSION,
        "cwd": str(Path(cwd).resolve()),
        "invocation": semantic,
    })
    return evidence


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Capture current Cursor session route with argv or explicit attestation.")
    sub = parser.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("capture")
    capture.add_argument("--expected-invocation", required=True)
    capture.add_argument("--expected-cwd", required=True)
    capture.add_argument("--attestation", default=None,
                         help="path to an explicit attestation JSON fallback")
    capture.add_argument("--cli-config", default=None,
                         help="path to Cursor cli-config.json; default is ~/.cursor/cli-config.json")
    args = parser.parse_args(argv)
    attestation = None
    if args.attestation:
        attestation = json.loads(Path(args.attestation).read_text(encoding="utf-8"))
    try:
        evidence = capture_current(
            expected_invocation=args.expected_invocation,
            expected_cwd=args.expected_cwd,
            attestation=attestation,
            cli_config_path=args.cli_config,
        )
    except RouteEvidenceError as error:
        parser.error(str(error))
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
