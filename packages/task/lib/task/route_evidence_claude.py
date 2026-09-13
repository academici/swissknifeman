"""Claude Code adapter for session-bound route provenance.

Claude's project JSONL records bind assistant responses to a session, cwd, concrete
model and effort.  The adapter selects the file by ``CLAUDE_CODE_SESSION_ID`` and
requires the exact Task invocation before accepting the latest assistant route.
Static settings and actor prose are never fallbacks.
"""
from __future__ import annotations

import argparse
import json
import hashlib
import os
import re
from pathlib import Path

from task.command_catalog import load_routing_metadata
from task.route_evidence import RouteEvidenceError, capture_actual


SOURCE_VERSION = "claude-project-jsonl-v1"
_ROUTING_PATH = Path(__file__).resolve().parents[2] / "configs" / "command-routing.json"
_COMMAND_RE = re.compile(r"<command-name>(/task:[^<]+)</command-name>\s*"
                         r"<command-args>(.*?)</command-args>", re.DOTALL)


def _state_root() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")) / "projects"


def _session_path(root: Path, session_id: str) -> Path:
    matches = tuple(root.glob(f"*/{session_id}.jsonl"))
    if len(matches) != 1:
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_UNAVAILABLE",
            f"Claude session {session_id!r} has {len(matches)} project records",
        )
    return matches[0]


def _invocation_from_event(event: dict) -> str | None:
    if event.get("type") != "user":
        return None
    message = event.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    texts = ([content] if isinstance(content, str) else
             [part.get("text") for part in content
              if isinstance(part, dict) and isinstance(part.get("text"), str)]
             if isinstance(content, list) else [])
    for value in texts:
        match = _COMMAND_RE.search(value)
        if match:
            command, arguments = match.group(1).strip(), match.group(2).strip()
            return f"{command} {arguments}".rstrip()
    return None


def _selector(model: str, mapping: dict) -> str:
    lowered = model.lower()
    matches = [
        selector
        for selectors in mapping.values()
        for selector in selectors
        if re.search(rf"(?:^|[-_/]){re.escape(selector.lower())}(?:$|[-_/0-9])", lowered)
    ]
    if len(matches) != 1:
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_MISMATCH",
            f"Claude model {model!r} has {len(matches)} selector mappings",
        )
    return matches[0]


def _class_for(model: str, metadata: dict) -> str:
    mapping = metadata["mappings"]["claude-code"]["class_selectors"]
    selector = _selector(model, mapping)
    return next(model_class for model_class, selectors in mapping.items() if selector in selectors)


def _effort_for(effort: str, metadata: dict) -> str:
    mapping = metadata["mappings"]["claude-code"]["effort_selectors"]
    matches = [axis for axis, selectors in mapping.items() if effort in selectors]
    if len(matches) != 1:
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_MISMATCH", f"Claude effort {effort!r} has {len(matches)} mappings")
    return matches[0]


def capture_current(*, expected_invocation: str, expected_cwd: str | Path,
                    session_id: str | None = None, state_root: str | Path | None = None,
                    routing_path: str | Path = _ROUTING_PATH, require_current_owner_invocation=False) -> dict:
    observed = session_id if session_id is not None else os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not isinstance(observed, str) or not observed.strip() or any(char.isspace() for char in observed):
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_UNAVAILABLE", "CLAUDE_CODE_SESSION_ID is absent or invalid")
    observed = observed.strip()
    path = _session_path(Path(state_root) if state_root is not None else _state_root(), observed)
    try:
        rows = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise RouteEvidenceError("ROUTE_LAUNCH_UNAVAILABLE", str(exc)) from exc

    invocation_index = None
    route_event = None
    for index, raw in enumerate(rows):
        try:
            event = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RouteEvidenceError(
                "ROUTE_LAUNCH_UNAVAILABLE", f"Claude state {path}:{index + 1} is invalid") from exc
        invocation = _invocation_from_event(event)
        if require_current_owner_invocation and event.get("type") == "user":
            message = event.get("message", {})
            content = message.get("content", []) if isinstance(message, dict) else []
            is_tool_result = isinstance(content, list) and content and all(isinstance(p, dict) and p.get("type") == "tool_result" for p in content)
            if not is_tool_result:
                invocation_index = None
                route_event = None
        if invocation == expected_invocation:
            invocation_index = index
            route_event = None
            continue
        if invocation_index is None or index <= invocation_index or event.get("type") != "assistant":
            continue
        message = event.get("message")
        if not isinstance(message, dict):
            continue
        model, effort = message.get("model"), event.get("effort")
        if isinstance(model, str) and model and isinstance(effort, str) and effort:
            route_event = event

    if invocation_index is None:
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_MISMATCH",
            f"Claude session does not contain exact Task invocation {expected_invocation!r}",
        )
    if route_event is None:
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_UNAVAILABLE", "Claude session has no route-bearing assistant event")
    cwd = route_event.get("cwd")
    if not isinstance(cwd, str) or Path(cwd).resolve() != Path(expected_cwd).resolve():
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_MISMATCH", f"Claude cwd {cwd!r} != expected {str(expected_cwd)!r}")
    message = route_event["message"]
    model, effort = message["model"], route_event["effort"]
    metadata = load_routing_metadata(Path(routing_path))
    evidence = capture_actual(
        _class_for(model, metadata), _effort_for(effort, metadata),
        source="provider-thread-state", model=model,
    )
    evidence.update({
        "thread_id": observed,
        "source_version": SOURCE_VERSION,
        "cwd": str(Path(cwd).resolve()),
        "invocation": expected_invocation,
    })
    if require_current_owner_invocation:
        evidence["owner_message_digest"] = hashlib.sha256(rows[invocation_index].encode()).hexdigest()
    return evidence


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Capture current Claude Code session route.")
    parser.add_argument("--expected-invocation", required=True)
    parser.add_argument("--expected-cwd", required=True)
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
    raise SystemExit(main())
