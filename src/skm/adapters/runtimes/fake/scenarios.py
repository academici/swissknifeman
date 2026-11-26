"""Synthetic TOML scenarios and their closed child-process language.

Used by both the early M3 runtime and the shared CLI lifecycle replay suite.
No shell, imports, or arbitrary Python are accepted by the scenario language.
"""

from __future__ import annotations

import json
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from skm.platform.config.sources.document import decode_document

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonObject

__all__ = ["Scenario", "ScenarioError", "load_scenario", "select_scenario"]

_ACTIONS = frozenset(
    {
        "read_stdin",
        "emit",
        "raw",
        "raw_hex",
        "write_file",
        "delete_file",
        "sleep_ms",
        "fail_if_resume",
        "exit",
    }
)


class ScenarioError(ValueError):
    """An unreadable, unknown, or invalid synthetic scenario; never a silent fallback."""


def _document(path: Path) -> JsonObject:
    # TOML is decoded by the config sources, the only place allowed to parse it; values must be JSON.
    try:
        return decode_document(path.read_text(encoding="utf-8"), "toml")
    except (OSError, ValueError, TypeError, RecursionError) as error:
        raise ScenarioError(f"cannot read fake input {path}: {error}") from error


def _relative(path: object) -> str:
    if not isinstance(path, str) or not path or Path(path).is_absolute() or ".." in Path(path).parts:
        raise ScenarioError("scenario file paths must stay relative to workdir")
    return path


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    document: JsonObject


def load_scenario(path: Path) -> Scenario:
    data = _document(path)
    name = data.get("scenario")
    if not isinstance(name, str) or not name:
        raise ScenarioError(f"missing scenario id in {path}")
    steps = data.get("step", [])
    if not isinstance(steps, list):
        raise ScenarioError("scenario step must be an array")
    for step in steps:
        _validate_step(step)
    for field in ("ignore_signals", "hang"):
        if field in data and not isinstance(data[field], bool):
            raise ScenarioError(f"{field} must be boolean")
    result = data.get("result")
    if result is not None and (not isinstance(result, dict) or not isinstance(result.get("text"), str)):
        raise ScenarioError("result needs string text")
    if "exit_code" in data:
        _exit_code(data["exit_code"])
    if "usage" in data and not isinstance(data["usage"], dict):
        raise ScenarioError("usage must be an object")
    return Scenario(name, data)


def _validate_step(step: object) -> None:
    if not isinstance(step, dict):
        raise ScenarioError("unknown fake scenario action")
    data = cast("JsonObject", step)
    action = data.get("action")
    if not isinstance(action, str) or action not in _ACTIONS:
        raise ScenarioError("unknown fake scenario action")
    if action in ("write_file", "delete_file"):
        _relative(data.get("path"))
        if action == "write_file" and not isinstance(data.get("content"), str):
            raise ScenarioError("write_file needs string content")
    if action == "emit" and not isinstance(data.get("event"), dict):
        raise ScenarioError("emit needs an event object")
    if action == "raw" and not isinstance(data.get("data"), str):
        raise ScenarioError("raw needs string data")
    if action == "raw_hex":
        value = data.get("data")
        if not isinstance(value, str) or len(value) > 2 * 1024 * 1024:
            raise ScenarioError("raw_hex needs bounded hex data")
        try:
            bytes.fromhex(value)
        except ValueError as error:
            raise ScenarioError("raw_hex needs valid hex data") from error
    if data.get("stream", "stdout") not in ("stdout", "stderr"):
        raise ScenarioError("stream must be stdout or stderr")
    if action == "sleep_ms":
        milliseconds = data.get("ms")
        if isinstance(milliseconds, bool) or not isinstance(milliseconds, int) or milliseconds < 0:
            raise ScenarioError("sleep_ms needs non-negative integer ms")
    if "exit_code" in data:
        _exit_code(data["exit_code"])


def _exit_code(value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255:
        raise ScenarioError("exit_code must be an integer in 0..255")


def select_scenario(script: Path, *, role: str, task_key: str, invocation: int) -> Scenario:
    rules = _document(script).get("rule")
    if not isinstance(rules, list):
        raise ScenarioError("fake script needs [[rule]] entries")
    for rule in rules:
        if not isinstance(rule, dict) or not isinstance(rule.get("scenario"), str):
            raise ScenarioError("fake script rule needs a scenario")
        if (
            rule.get("role", "*") in ("*", role)
            and rule.get("task_key", task_key) == task_key
            and rule.get("invocation", invocation) == invocation
        ):
            target = script.parent / _relative(rule["scenario"])
            if not target.suffix:
                target = target.with_suffix(".toml")
            return load_scenario(target)
    raise ScenarioError(
        f"unknown fake scenario for role={role}, task_key={task_key}, invocation={invocation}"
    )


def _target(root: Path, path: object) -> Path:
    candidate = root / _relative(path)
    # Check both parents and the final component: writes through a symlink must not escape cwd.
    if not candidate.resolve().is_relative_to(root):
        raise ScenarioError("scenario file path escapes workdir through a symlink")
    if candidate.resolve() == root:
        raise ScenarioError("scenario file path must name a file")
    return candidate


def _emit(event: object) -> None:
    sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _step(step: JsonObject, root: Path, *, resume: bool) -> None:
    action = step["action"]
    if action == "read_stdin":
        sys.stdin.read()
    elif action == "emit":
        _emit(step["event"])
    elif action == "raw":
        stream = sys.stderr if step.get("stream") == "stderr" else sys.stdout
        stream.write(cast("str", step["data"]))
        stream.flush()
    elif action == "raw_hex":
        stream = sys.stderr if step.get("stream") == "stderr" else sys.stdout
        stream.buffer.write(bytes.fromhex(cast("str", step["data"])))
        stream.buffer.flush()
    elif action == "write_file":
        target = _target(root, step["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(cast("str", step["content"]), encoding="utf-8")
    elif action == "delete_file":
        _target(root, step["path"]).unlink()
    elif action == "sleep_ms":
        time.sleep(cast("int", step["ms"]) / 1000)
    elif action == "fail_if_resume" and resume:
        sys.stderr.write(cast("str", step.get("error", "resume unsupported")))
        raise SystemExit(cast("int", step.get("exit_code", 1)))
    elif action == "exit":
        raise SystemExit(cast("int", step.get("exit_code", 1)))


def _process() -> None:
    """Read a pinned scenario from argv and the prompt from stdin; never receive host secrets."""
    data = cast("JsonObject", json.loads(sys.argv[1]))
    root = Path.cwd().resolve()
    if data.get("ignore_signals", False):
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, signal.SIG_IGN)
    try:
        for step in cast("list[JsonObject]", data.get("step", [])):
            _step(step, root, resume=sys.argv[2] == "resume")
        if data.get("hang", False):
            while True:
                signal.pause()
        if "usage" in data:
            _emit({"type": "usage_reported", "usage": data["usage"], "cumulative": True})
        if "result" in data:
            result = cast("JsonObject", data["result"])
            _emit({"type": "fake_result", "final_text": result["text"], "stop_reason": "end_turn"})
    except (OSError, ValueError, KeyError, TypeError) as error:
        sys.stderr.write(f"fake scenario error: {error}\n")
        raise SystemExit(2) from error
    raise SystemExit(cast("int", data.get("exit_code", 0)))


if __name__ == "__main__":
    _process()
