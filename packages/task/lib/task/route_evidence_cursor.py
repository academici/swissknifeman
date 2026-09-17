"""Cursor adapter for current-session route provenance.

Primary path: inspect the nearest ``agent`` ancestor argv for ``--workspace``,
``--model`` and the semantic ``task:`` prompt.  When process ancestry is
unavailable, callers may supply an explicit attestation record that still
fails closed on selector mismatch.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from task.command_catalog import load_routing_metadata
from task.route_evidence import RouteEvidenceError, capture_actual


CLI_SOURCE_VERSION = "cursor-ancestor-argv-v1"
_ATTEST_SOURCE_VERSION = "cursor-explicit-attestation-v1"
_ROUTING_PATH = Path(__file__).resolve().parents[2] / "configs" / "command-routing.json"


def _proc_entry(pid: int) -> tuple[int, tuple[str, ...]]:
    root = Path("/proc") / str(pid)
    try:
        status = (root / "status").read_text(encoding="utf-8")
        raw_argv = (root / "cmdline").read_bytes()
    except OSError as error:
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_UNAVAILABLE", f"Cursor process ancestry is unreadable: {error}") from error
    parent = None
    for line in status.splitlines():
        if line.startswith("PPid:"):
            _, value = line.split(":", 1)
            parent = int(value.strip())
            break
    argv = tuple(
        value.decode("utf-8", errors="surrogateescape")
        for value in raw_argv.split(b"\0") if value
    )
    if parent is None or not argv:
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_UNAVAILABLE", f"process {pid} has no readable parent/argv")
    return parent, argv


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
        if Path(argv[0]).name == "agent":
            return tuple(argv)
        pid = parent
    raise RouteEvidenceError(
        "ROUTE_LAUNCH_UNAVAILABLE", "current process is not a descendant of a Cursor agent launch")


def _option_values(argv: tuple[str, ...], short: str, long: str) -> tuple[str, ...]:
    values = []
    index = 1
    while index < len(argv):
        token = argv[index]
        if token in (short, long):
            if index + 1 >= len(argv):
                raise RouteEvidenceError(
                    "ROUTE_LAUNCH_MISMATCH", f"launch option {token} has no value")
            values.append(argv[index + 1])
            index += 2
            continue
        if token.startswith(long + "="):
            values.append(token.split("=", 1)[1])
        index += 1
    return tuple(values)


def _one(values: tuple[str, ...], label: str) -> str:
    if len(values) != 1:
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_MISMATCH", f"expected exactly one {label}, observed {len(values)}")
    return values[0]


def _selector_class(model: str, routing_path: Path) -> str:
    metadata = load_routing_metadata(routing_path)
    mapping = metadata.get("mappings", {}).get("cursor", {})
    matches = [
        model_class
        for model_class, selectors in mapping.get("class_selectors", {}).items()
        if model in selectors
    ]
    return _one(tuple(matches), f"Cursor model-class mapping for {model!r}")


def _selector_effort(selector: str, routing_path: Path) -> str:
    metadata = load_routing_metadata(routing_path)
    mapping = metadata.get("mappings", {}).get("cursor", {})
    matches = [
        effort
        for effort, selectors in mapping.get("effort_selectors", {}).items()
        if selector in selectors
    ]
    return _one(tuple(matches), f"Cursor effort mapping for {selector!r}")


def _normalize_invocation(value: str) -> str:
    semantic = value.strip()
    if semantic.startswith("task:"):
        return semantic
    if semantic.startswith("/task:"):
        return semantic[1:]
    raise RouteEvidenceError("ROUTE_LAUNCH_MISMATCH", "expected semantic task:<command> form")


def _capture_argv(*, expected_invocation: str, expected_cwd: str | Path,
                  start_pid: int | None, process_table, routing_path: Path) -> dict:
    argv = _agent_ancestor(start_pid or os.getpid(), process_table)
    model = _one(_option_values(argv, "-m", "--model"), "Cursor model selector")
    workspace = _one(_option_values(argv, "", "--workspace"), "Cursor workspace")
    invocations = tuple(_normalize_invocation(value) for value in argv if "task:" in value)
    invocation = _one(invocations, "Task prompt")
    if invocation != _normalize_invocation(expected_invocation):
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_MISMATCH",
            f"Cursor Task prompt {invocation!r} != expected {expected_invocation!r}")
    if Path(workspace).resolve() != Path(expected_cwd).resolve():
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_MISMATCH",
            f"Cursor workspace {workspace!r} != expected {str(expected_cwd)!r}")
    if "--force" not in argv and "--yolo" not in argv:
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_MISMATCH", "Cursor launch is missing --force/--yolo")
    effort_selector = "medium"
    evidence = capture_actual(
        _selector_class(model, routing_path),
        _selector_effort(effort_selector, routing_path),
        source="cli-flag",
        model=model,
    )
    evidence.update({
        "thread_id": os.environ.get("CURSOR_AGENT_CHAT_ID") or os.environ.get("CURSOR_SESSION_ID"),
        "source_version": CLI_SOURCE_VERSION,
        "cwd": str(Path(workspace).resolve()),
        "invocation": invocation,
    })
    if not isinstance(evidence.get("thread_id"), str) or not evidence["thread_id"].strip():
        evidence["thread_id"] = f"cursor-argv:{evidence['cwd']}:{invocation}"
    return evidence


def capture_current(*, expected_invocation: str, expected_cwd: str | Path,
                    attestation: dict | None = None, start_pid: int | None = None,
                    process_table=None, routing_path: str | Path = _ROUTING_PATH) -> dict:
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
    except RouteEvidenceError:
        if attestation is None:
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
    args = parser.parse_args(argv)
    attestation = None
    if args.attestation:
        attestation = json.loads(Path(args.attestation).read_text(encoding="utf-8"))
    try:
        evidence = capture_current(
            expected_invocation=args.expected_invocation,
            expected_cwd=args.expected_cwd,
            attestation=attestation,
        )
    except RouteEvidenceError as error:
        parser.error(str(error))
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
