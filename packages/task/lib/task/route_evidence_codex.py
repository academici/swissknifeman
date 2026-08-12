"""Codex adapter for thread-bound native launch provenance.

The provider-neutral route layer accepts ``cli-flag`` evidence, but must not ask
the model to remember or retype the launch selectors.  This adapter follows the
current process ancestry to the owning Codex process and reads its original argv
from ``/proc``.  It therefore proves the selected launch route, exact Task prompt,
cwd and safety flags for this running process tree; it does not claim provider
telemetry about the model that ultimately served the thread.

Linux-only by construction.  Absence of ``/proc`` is a typed unavailable result,
never a fallback to config, doctor output or self-attestation.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from task.command_catalog import load_routing_metadata
from task.route_evidence import RouteEvidenceError, capture_actual


SOURCE_VERSION = "codex-ancestor-argv-v1"
_ROUTING_PATH = Path(__file__).resolve().parents[2] / "configs" / "command-routing.json"


def _proc_entry(pid: int) -> tuple[int, tuple[str, ...]]:
    root = Path("/proc") / str(pid)
    try:
        status = (root / "status").read_text(encoding="utf-8")
        raw_argv = (root / "cmdline").read_bytes()
    except OSError as error:
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_UNAVAILABLE", f"Codex process ancestry is unreadable: {error}") from error

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


def _codex_ancestor(start_pid: int, process_table=None) -> tuple[str, ...]:
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
                "ROUTE_LAUNCH_UNAVAILABLE", f"process {pid} is absent from the ancestry snapshot") from error
        if Path(argv[0]).name == "codex":
            return tuple(argv)
        pid = parent
    raise RouteEvidenceError(
        "ROUTE_LAUNCH_UNAVAILABLE", "current process is not a descendant of a Codex launch")


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
    mapping = metadata.get("mappings", {}).get("codex", {})
    matches = [
        model_class
        for model_class, selectors in mapping.get("class_selectors", {}).items()
        if model in selectors
    ]
    return _one(tuple(matches), f"Codex model-class mapping for {model!r}")


def _selector_effort(selector: str, routing_path: Path) -> str:
    metadata = load_routing_metadata(routing_path)
    mapping = metadata.get("mappings", {}).get("codex", {})
    matches = [
        effort
        for effort, selectors in mapping.get("effort_selectors", {}).items()
        if selector in selectors
    ]
    return _one(tuple(matches), f"Codex effort mapping for {selector!r}")


def capture_current(*, expected_invocation: str, expected_cwd: str | Path,
                    thread_id: str | None = None, start_pid: int | None = None,
                    process_table=None, routing_path: str | Path = _ROUTING_PATH) -> dict:
    """Capture and validate the exact native ``plan-run`` launch for this thread."""
    argv = _codex_ancestor(start_pid or os.getpid(), process_table)
    model = _one(_option_values(argv, "-m", "--model"), "Codex model selector")
    cwd = _one(_option_values(argv, "-C", "--cd"), "Codex cwd")
    approval = _one(
        _option_values(argv, "-a", "--ask-for-approval"), "Codex approval policy")
    sandbox = _one(_option_values(argv, "-s", "--sandbox"), "Codex sandbox policy")
    configs = _option_values(argv, "-c", "--config")
    effort_values = tuple(
        value.split("=", 1)[1].strip('"\'')
        for value in configs if value.split("=", 1)[0] == "model_reasoning_effort"
    )
    effort_selector = _one(effort_values, "model_reasoning_effort selector")
    invocations = tuple(value for value in argv if value.startswith("$ task:"))
    invocation = _one(invocations, "Task prompt")

    if invocation != expected_invocation:
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_MISMATCH",
            f"Codex Task prompt {invocation!r} != expected {expected_invocation!r}")
    if Path(cwd).resolve() != Path(expected_cwd).resolve():
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_MISMATCH", f"Codex cwd {cwd!r} != expected {str(expected_cwd)!r}")
    if approval != "never" or sandbox != "danger-full-access":
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_MISMATCH",
            f"Codex safety flags are {approval!r}/{sandbox!r}, expected never/danger-full-access")

    observed_thread = thread_id if thread_id is not None else os.environ.get("CODEX_THREAD_ID")
    if not isinstance(observed_thread, str) or not observed_thread.strip() \
            or any(char.isspace() for char in observed_thread):
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_UNAVAILABLE", "CODEX_THREAD_ID is absent or invalid")

    routing_path = Path(routing_path)
    evidence = capture_actual(
        _selector_class(model, routing_path),
        _selector_effort(effort_selector, routing_path),
        source="cli-flag",
        model=model,
    )
    evidence.update({
        "thread_id": observed_thread.strip(),
        "source_version": SOURCE_VERSION,
        "cwd": str(Path(cwd).resolve()),
        "invocation": invocation,
    })
    return evidence


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Capture current Codex native launch provenance from process ancestry.")
    sub = parser.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("capture")
    capture.add_argument("--expected-invocation", required=True)
    capture.add_argument("--expected-cwd", required=True)
    args = parser.parse_args(argv)
    try:
        evidence = capture_current(
            expected_invocation=args.expected_invocation,
            expected_cwd=args.expected_cwd,
        )
    except RouteEvidenceError as error:
        parser.error(str(error))
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
