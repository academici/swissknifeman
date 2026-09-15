#!/usr/bin/env python3
"""Opt-in Claude Stop adapter; Task owns every admission decision."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def mode(cwd: str) -> str:
    try:
        for line in (Path(cwd) / ".claude" / "terminal-admission.env.ini").read_text().splitlines():
            if line.startswith("MODE="):
                return line.split("=", 1)[1].strip().lower()
    except OSError:
        pass
    return "off"


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or mode(cwd) != "on":
        return 0
    cli = Path(cwd) / "packages/task/scripts/plan-terminal-admission.py"
    if cli.is_file():
        try:
            result = subprocess.run([sys.executable, str(cli), "check-open", "--project-root", cwd,
                                     "--provider-session", str(payload.get("session_id") or "")],
                                    cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10)
            verdict = json.loads(result.stdout)
            if not isinstance(verdict, dict) or result.returncode not in (0, 1):
                raise ValueError("invalid pre-final result")
        except (OSError, subprocess.TimeoutExpired, TypeError, ValueError):
            verdict = {"final_allowed": False, "reason": "TASK_FINAL_STATE_UNAVAILABLE"}
        if not verdict.get("final_allowed"):
            print(json.dumps({"decision": "block", "reason": verdict.get("reason")}))
            return 0
    request = payload.get("terminal_admission")
    if not isinstance(request, dict) or not request.get("applicable"):
        return 0
    required = ("plan", "subject", "command", "run_id", "task_session", "continuity_json")
    if any(not isinstance(request.get(key), str) or not request[key] for key in required):
        print(json.dumps({"decision": "block", "reason": "TERMINAL_ADMISSION_CONTEXT_INVALID"}))
        return 0
    message = payload.get("last_assistant_message")
    cli = Path(cwd) / "packages/task/scripts/plan-terminal-admission.py"
    if not isinstance(message, str) or not cli.is_file():
        print(json.dumps({"decision": "block", "reason": "TASK_TERMINAL_ADMISSION_UNAVAILABLE"}))
        return 0
    command = [sys.executable, str(cli), "check", "--state-dir", str(Path(cwd) / ".swissknifeman/terminal-admission"),
               "--plan", request["plan"], "--subject", request["subject"], "--command", request["command"],
               "--run-id", request["run_id"], "--task-session", request["task_session"], "--provider", "claude-code",
               "--provider-session", str(payload.get("session_id") or ""), "--turn-id", str(payload.get("turn_id") or "stop"),
               "--continuity-json", request["continuity_json"], "--message", message,
               "--plan-dir", str(Path(cwd) / "plans" / request["plan"])]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10)
    try:
        verdict = json.loads(result.stdout)
    except (TypeError, ValueError):
        verdict = {"final_allowed": False, "reason": "TERMINAL_ADMISSION_VERIFIER_FAILED"}
    if not verdict.get("final_allowed"):
        print(json.dumps({"decision": "block", "reason": str(verdict.get("reason") or "TERMINAL_ADMISSION_REFUSED")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
