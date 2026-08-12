"""Codex adapter for current thread-bound route provenance.

Codex can change model and reasoning effort inside one CLI process and ``/clear``
starts a new chat without restarting that process.  The primary source is therefore
the latest persisted ``turn_context`` selected by ``CODEX_THREAD_ID``: it is the
thread-bound provider state used by the current chat, not a config default or a
model self-attestation.  Exact native ancestor argv remains a compatibility fallback
for non-interactive launches that do not expose persisted thread state.

The argv fallback is Linux-only by construction.  Missing or malformed state is a
typed unavailable result, never a fallback to config, doctor output or
self-attestation.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from task.command_catalog import load_routing_metadata
from task.route_evidence import RouteEvidenceError, capture_actual


CLI_SOURCE_VERSION = "codex-ancestor-argv-v1"
THREAD_SOURCE_VERSION = "codex-turn-context-v1"
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


def _thread_state_root() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    return (Path(codex_home) if codex_home else Path.home() / ".codex") / "sessions"


def _thread_rollout(thread_id: str, state_root: Path) -> Path | None:
    if not all(char.isalnum() or char in "-_" for char in thread_id):
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_UNAVAILABLE", "CODEX_THREAD_ID содержит небезопасные символы")
    candidates = tuple(
        path for path in state_root.rglob(f"*{thread_id}.jsonl")
        if path.is_file() and path.name.endswith(f"{thread_id}.jsonl")
    )
    if not candidates:
        return None
    if len(candidates) != 1:
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_UNAVAILABLE",
            f"для CODEX_THREAD_ID найдено файлов состояния: {len(candidates)}, ожидался один",
        )
    return candidates[0]


def _user_prompt(payload: dict) -> str | None:
    if payload.get("type") != "message" or payload.get("role") != "user":
        return None
    content = payload.get("content")
    if not isinstance(content, list):
        return None
    texts = [
        part.get("text") for part in content
        if isinstance(part, dict) and part.get("type") == "input_text"
        and isinstance(part.get("text"), str)
    ]
    return "\n".join(texts) if texts else None


def _completed_user_prompt(payload: dict, turn_id: str | None) -> str | None:
    if payload.get("type") != "item_completed" or payload.get("turn_id") != turn_id:
        return None
    item = payload.get("item")
    if not isinstance(item, dict) or item.get("type") != "UserMessage":
        return None
    content = item.get("content")
    if not isinstance(content, list):
        return None
    texts = [
        part.get("text") for part in content
        if isinstance(part, dict) and part.get("type") == "text"
        and isinstance(part.get("text"), str)
    ]
    return "\n".join(texts) if texts else None


def _read_thread_state(path: Path, thread_id: str) -> tuple[dict, tuple[str, ...]]:
    session_ids = []
    context = None
    prompts_after_context = []
    try:
        with path.open(encoding="utf-8") as lines:
            for line_number, raw_line in enumerate(lines, 1):
                if not raw_line.strip():
                    continue
                try:
                    event = json.loads(raw_line)
                except json.JSONDecodeError as error:
                    raise RouteEvidenceError(
                        "ROUTE_LAUNCH_UNAVAILABLE",
                        f"Codex thread state JSONL повреждён на строке {line_number}",
                    ) from error
                if not isinstance(event, dict) or not isinstance(event.get("payload"), dict):
                    continue
                payload = event["payload"]
                if event.get("type") == "session_meta" and isinstance(payload.get("id"), str):
                    session_ids.append(payload["id"])
                elif event.get("type") == "turn_context":
                    preceding_turn_id = context.get("turn_id") if isinstance(context, dict) else None
                    context = payload
                    if payload.get("turn_id") != preceding_turn_id:
                        prompts_after_context = []
                elif context is not None and event.get("type") == "response_item":
                    if (prompt := _user_prompt(payload)) is not None:
                        prompts_after_context.append(prompt)
                elif context is not None and event.get("type") == "event_msg":
                    if (prompt := _completed_user_prompt(
                            payload, context.get("turn_id"))) is not None:
                        prompts_after_context.append(prompt)
    except OSError as error:
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_UNAVAILABLE", f"Codex thread state не читается: {error}") from error

    if session_ids != [thread_id]:
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_UNAVAILABLE",
            f"Codex thread state несёт session ids {session_ids!r}, ожидался {thread_id!r}",
        )
    if not isinstance(context, dict):
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_UNAVAILABLE", "Codex thread state не содержит turn_context")
    return context, tuple(prompts_after_context)


def _capture_thread_state(*, thread_id: str, expected_invocation: str,
                          expected_cwd: str | Path, state_root: Path,
                          routing_path: Path) -> dict | None:
    path = _thread_rollout(thread_id, state_root)
    if path is None:
        return None
    context, prompts = _read_thread_state(path, thread_id)
    model = context.get("model")
    effort = context.get("effort")
    cwd = context.get("cwd")
    approval = context.get("approval_policy")
    sandbox = context.get("sandbox_policy")
    if not all(isinstance(value, str) and value for value in (model, effort, cwd)):
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_UNAVAILABLE", "Codex turn_context не содержит model/effort/cwd")
    if not any(expected_invocation in prompt.splitlines() for prompt in prompts):
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_MISMATCH",
            "текущий Codex turn не содержит exact Task invocation line",
        )
    if Path(cwd).resolve() != Path(expected_cwd).resolve():
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_MISMATCH", f"Codex cwd {cwd!r} != expected {str(expected_cwd)!r}")
    sandbox_type = sandbox.get("type") if isinstance(sandbox, dict) else sandbox
    if approval != "never" or sandbox_type != "danger-full-access":
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_MISMATCH",
            f"Codex safety state is {approval!r}/{sandbox_type!r}, expected never/danger-full-access",
        )
    evidence = capture_actual(
        _selector_class(model, routing_path),
        _selector_effort(effort, routing_path),
        source="provider-thread-state",
        model=model,
    )
    evidence.update({
        "thread_id": thread_id,
        "source_version": THREAD_SOURCE_VERSION,
        "cwd": str(Path(cwd).resolve()),
        "invocation": expected_invocation,
    })
    return evidence


def capture_current(*, expected_invocation: str, expected_cwd: str | Path,
                    thread_id: str | None = None, start_pid: int | None = None,
                    process_table=None, routing_path: str | Path = _ROUTING_PATH,
                    state_root: str | Path | None = None) -> dict:
    """Capture and validate the current ``plan-run`` route for this thread."""
    observed_thread = thread_id if thread_id is not None else os.environ.get("CODEX_THREAD_ID")
    if not isinstance(observed_thread, str) or not observed_thread.strip() \
            or any(char.isspace() for char in observed_thread):
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_UNAVAILABLE", "CODEX_THREAD_ID is absent or invalid")
    observed_thread = observed_thread.strip()
    routing_path = Path(routing_path)
    thread_evidence = _capture_thread_state(
        thread_id=observed_thread,
        expected_invocation=expected_invocation,
        expected_cwd=expected_cwd,
        state_root=Path(state_root) if state_root is not None else _thread_state_root(),
        routing_path=routing_path,
    )
    if thread_evidence is not None:
        return thread_evidence

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

    evidence = capture_actual(
        _selector_class(model, routing_path),
        _selector_effort(effort_selector, routing_path),
        source="cli-flag",
        model=model,
    )
    evidence.update({
        "thread_id": observed_thread,
        "source_version": CLI_SOURCE_VERSION,
        "cwd": str(Path(cwd).resolve()),
        "invocation": invocation,
    })
    return evidence


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Capture current Codex thread route with an exact native-launch fallback.")
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
