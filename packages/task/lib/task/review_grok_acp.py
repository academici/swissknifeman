"""One bounded, read-only Grok ACP review with native session attestation.

Accounting model names are not route IDs. The provider's session summary and
terminal ACP metadata establish the route; usage only establishes completion.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import re
import signal
import subprocess
import threading
import time
from urllib.parse import quote
import uuid


class TransportError(ValueError):
    pass


def argv(manifest: dict, *, max_turns: int) -> list[str]:
    return ["grok", "--permission-mode", "dontAsk", "--tools", "read_file,grep,list_dir",
            "--allow", "Read", "--allow", "Grep", "--deny", "MCPTool", "--deny", "Bash",
            "--deny", "Edit", "--deny", "Write", "--no-subagents", "--disable-web-search",
            "--max-turns", str(max_turns), "agent", "--no-leader",
            "--model", manifest["route"]["model"], "--reasoning-effort", manifest["effort"], "stdio"]


def provider_route(cwd: Path, session: str) -> dict:
    """Read only this newly created native session, never launch flags/config."""
    path = Path.home() / ".grok/sessions" / quote(str(cwd), safe="") / session / "summary.json"
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(value, dict):
        return {}
    info = value.get("info", {})
    if not isinstance(info, dict) or info.get("id") != session or info.get("cwd") != str(cwd):
        return {}
    return {"source": str(path), "session_id": info["id"], "cwd": info["cwd"],
            "model": value.get("current_model_id"), "effort": value.get("reasoning_effort"),
            "context_tokens": value.get("context_window")}


def verify_route(witness: dict, manifest: dict) -> None:
    if witness.get("model") != manifest["route"]["model"] or witness.get("effort") != manifest["effort"]:
        raise TransportError("REVIEW_ROUTE_MISMATCH: native model/effort does not match the selected reviewer")
    context = witness.get("context_tokens")
    if type(context) is not int:
        raise TransportError("REVIEW_CONTEXT_UNVERIFIABLE: native session has no effective context window")
    if context < manifest["route"]["context_tokens"]:
        raise TransportError("REVIEW_CONTEXT_UNDERSHOOT: native context is smaller than requested")


def _stop(process) -> None:
    """Reconcile the complete child group even after an early ACP refusal."""
    def kill(sig):
        if os.name == "posix":
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                pass
        elif process.poll() is None:
            process.terminate() if sig == signal.SIGTERM else process.kill()
    kill(signal.SIGTERM)
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        kill(signal.SIGKILL)
        process.wait(timeout=2)


def run(manifest: dict, packet: bytes, *, cwd: Path, timeout: int, max_turns: int) -> dict:
    """No retry, no product mutation, no prompt before native capacity proof."""
    command = argv(manifest, max_turns=max_turns)
    # A refused session/new still has a distinct attempt identity for archiving.
    result = {"session": str(uuid.uuid4()), "argv": command, "output": b"", "raw": b"",
              "stderr": b"", "complete": False, "detail": "", "observed_context": None,
              "provider_route": {}}
    process = None
    raw, stderr, chunks = [], [], []
    last_response = ""
    inbox = queue.Queue()
    readers = []
    deadline = time.monotonic() + timeout
    sequence = 0
    responses = 0
    session = None

    def reader(stream, target, deliver=False):
        try:
            while line := stream.readline():
                target.append(line)
                if deliver:
                    inbox.put(line)
        finally:
            if deliver:
                inbox.put(None)

    def send(value):
        process.stdin.write((json.dumps(value, ensure_ascii=False) + "\n").encode())
        process.stdin.flush()

    def rpc(method, params):
        nonlocal sequence, last_response, responses
        sequence += 1
        request_id = sequence
        send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TransportError("timeout")
            try:
                line = inbox.get(timeout=remaining)
            except queue.Empty as exc:
                raise TransportError("timeout") from exc
            if line is None:
                raise TransportError("REVIEW_ACP_TERMINATED: provider exited before terminal response")
            message = json.loads(line)
            if not isinstance(message, dict):
                raise TransportError("REVIEW_ACP_INVALID: expected an object")
            if "method" in message and "id" in message:
                if message["method"] == "session/request_permission":
                    send({"jsonrpc": "2.0", "id": message["id"],
                          "result": {"outcome": {"outcome": "cancelled"}}})
                else:
                    send({"jsonrpc": "2.0", "id": message["id"],
                          "error": {"code": -32601, "message": "Read-only reviewer client does not provide this method"}})
            if message.get("method") in {"session/update", "_x.ai/session_notification"}:
                params = message.get("params", {})
                if params.get("sessionId") != session:
                    continue
                update = params.get("update", {})
                if update.get("sessionUpdate") == "agent_message_chunk":
                    content = update.get("content", {})
                    if content.get("type") == "text":
                        chunks.append(content["text"])
                if update.get("sessionUpdate") == "response_completed":
                    last_response = "".join(chunks)
                    chunks.clear()
                    responses += 1
                    if responses > max_turns:
                        raise TransportError("REVIEW_MAX_TURNS: provider exceeded the bounded review turns")
            if message.get("id") == request_id and "method" not in message:
                if "error" in message:
                    raise TransportError("REVIEW_ACP_ERROR: " + json.dumps(message["error"], ensure_ascii=False))
                value = message.get("result")
                if not isinstance(value, dict):
                    raise TransportError("REVIEW_ACP_INVALID: missing result object")
                return value

    def route():
        # Persistence may trail set_model with a complete default route as well
        # as missing fields. Wait for bounded convergence, never prompt until
        # the effective native route satisfies every requested axis.
        until = min(deadline, time.monotonic() + 3)
        while True:
            witness = provider_route(cwd, session)
            result["provider_route"] = witness
            result["observed_context"] = witness.get("context_tokens")
            if (witness.get("model") == manifest["route"]["model"] and witness.get("effort") == manifest["effort"]
                    and type(witness.get("context_tokens")) is int
                    and witness["context_tokens"] >= manifest["route"]["context_tokens"]):
                verify_route(witness, manifest)
                return witness
            if time.monotonic() >= until:
                if not witness:
                    raise TransportError("REVIEW_CONTEXT_UNVERIFIABLE: native session summary is unavailable")
                verify_route(witness, manifest)
            time.sleep(min(0.05, max(0, until - time.monotonic())))

    try:
        process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, start_new_session=os.name == "posix")
        for stream, target, deliver in ((process.stdout, raw, True), (process.stderr, stderr, False)):
            thread = threading.Thread(target=reader, args=(stream, target, deliver), daemon=True)
            thread.start()
            readers.append(thread)
        rpc("initialize", {"protocolVersion": 1, "clientCapabilities": {},
                           "clientInfo": {"name": "swissknifeman-task-review", "version": "1"}})
        created = rpc("session/new", {"cwd": str(cwd), "mcpServers": []})
        session = created.get("sessionId")
        if (not isinstance(session, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", session)
                or session == manifest["executor_session"]):
            raise TransportError("REVIEW_NOT_INDEPENDENT: require a distinct newly created provider session")
        result["session"] = session
        rpc("session/set_model", {"sessionId": session, "modelId": manifest["route"]["model"],
                                  "_meta": {"contextWindow": manifest["route"]["context_tokens"],
                                            "reasoningEffort": manifest["effort"]}})
        route()
        terminal = rpc("session/prompt", {"sessionId": session,
                                          "prompt": [{"type": "text", "text": packet.decode()}]})
        metadata = terminal.get("_meta", {})
        usage = metadata.get("usage", {})
        usage_known = (isinstance(usage, dict)
                       and all(type(usage.get(key)) is int and usage[key] >= 0
                               for key in ("inputTokens", "outputTokens", "cachedReadTokens", "cacheCreationTokens"))
                       and usage["inputTokens"] + usage["outputTokens"] > 0
                       and type(usage.get("numTurns")) is int and 0 < usage["numTurns"] <= max_turns
                       and not usage.get("usage_is_incomplete", False))
        route()
        result["complete"] = (terminal.get("stopReason") == "end_turn" and metadata.get("sessionId") == session
                              and metadata.get("modelId") == manifest["route"]["model"] and usage_known
                              and not metadata.get("usage_is_incomplete", False)
                              and not terminal.get("usage_is_incomplete", False))
        result["detail"] = f"ACP stopReason={terminal.get('stopReason')}; usage_complete={usage_known}"
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        result["detail"] = str(exc) if isinstance(exc, TransportError) else type(exc).__name__ + ": " + str(exc)
    finally:
        if process is not None:
            _stop(process)
            for thread in readers:
                thread.join(timeout=2)
            for stream in (process.stdin, process.stdout, process.stderr):
                stream.close()
        result["output"] = ("".join(chunks) or last_response).encode()
        result["raw"] = b"".join(raw)
        result["stderr"] = b"".join(stderr)
    return result
