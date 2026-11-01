#!/usr/bin/env python3
"""Bridge the conductor's one plain-text stdin prompt to AGY's stream-json protocol.

AGY runs as a distinct provider. This bridge does not assert sandboxing, infer backend
model identity, or fabricate a terminal result when the CLI disconnects.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys


def event(doc: object, expected_model: str, state: dict) -> dict | None:
    if not isinstance(doc, dict):
        state["invalid"] = True
        return None
    if state.get("terminal"):
        state["invalid"] = True
        return None
    kind = doc.get("event")
    if kind == "init":
        init = doc.get("init")
        if not isinstance(init, dict):
            state["invalid"] = True
            return None
        session, model = doc.get("conversation_id"), init.get("model")
        if not isinstance(session, str) or not session or model != expected_model or state.get("session"):
            state["invalid"] = True
            return None
        state["session"] = session
        return {"type": "system", "subtype": "init", "session_id": session, "model": model,
                "tools": init.get("tools", [])}
    if kind == "step_update":
        step = doc.get("step_update")
        if not isinstance(step, dict) or not state.get("session") or step.get("conversation_id") != state["session"]:
            state["invalid"] = True
        return None
    if kind != "result":
        state["invalid"] = True
        return None
    result = doc.get("result")
    if not isinstance(result, dict):
        state["invalid"] = True
        return None
    session, status, response = result.get("conversation_id"), result.get("status"), result.get("response")
    valid = (not state.get("invalid") and bool(state.get("session")) and session == state["session"]
             and not state.get("terminal") and isinstance(response, str) and status in ("SUCCESS", "ERROR"))
    if not valid:
        state["invalid"] = True
        return None
    state["terminal"] = True
    state["error"] = status == "ERROR"
    usage = result.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    return {"type": "result", "session_id": session, "is_error": status != "SUCCESS",
            "result": (result.get("error") or response) if status == "ERROR" else response,
            "usage": {"input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens"),
                      "cached_input_tokens": usage.get("cache_read_tokens")}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--effort", required=True, choices=("low", "medium", "high"))
    args = parser.parse_args()
    prompt = sys.stdin.read()
    argv = ["agy", "--dangerously-skip-permissions", "--model", args.model, "--effort", args.effort,
            "--input-format", "stream-json", "--output-format", "stream-json", "--print", ""]
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    except OSError as exc:
        print(f"AGY_START_FAILED: {exc}", file=sys.stderr)
        return 1
    assert proc.stdin is not None and proc.stdout is not None
    proc.stdin.write(json.dumps({"event": "user", "message": {"role": "user", "content": prompt}}) + "\n")
    proc.stdin.close()
    state: dict = {}
    terminal = None
    for line in proc.stdout:
        # Namespace raw evidence: provider fields must never enter the conductor protocol.
        print(json.dumps({"type": "agy.raw", "line": line}), flush=True)
        try:
            doc = json.loads(line)
        except ValueError:
            state["invalid"] = True
            continue
        mapped = event(doc, args.model, state)
        if mapped is not None:
            if mapped["type"] == "result":
                terminal = mapped
            else:
                print(json.dumps(mapped), flush=True)
    rc = proc.wait()
    if rc or not state.get("terminal") or state.get("invalid"):
        print("AGY_STREAM_INCOMPLETE: missing or inconsistent terminal evidence", file=sys.stderr)
        return rc or 1
    # A terminal result is authoritative only after EOF and successful CLI exit.
    # Publishing it earlier lets the conductor accept a lingering process as success.
    if terminal is not None:
        print(json.dumps(terminal), flush=True)
    return 1 if state.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
