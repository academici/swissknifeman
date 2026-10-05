"""One bounded, read-only Grok ACP review with native session attestation.

Accounting model names are not route IDs. The provider's session summary and
terminal ACP metadata establish the route; usage only establishes completion.
"""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import queue
import re
import signal
import shutil
import subprocess
import threading
import time
from urllib.parse import quote
import uuid
from task.review_sources import ReadLedger
from task import review_job


class TransportError(ValueError):
    pass


def argv(manifest: dict, *, max_turns: int = 0) -> list[str]:
    return ["grok", "--permission-mode", "dontAsk", "--tools", "read_file,grep,list_dir",
            "--allow", "Read", "--allow", "Grep", "--deny", "MCPTool", "--deny", "Bash",
            "--deny", "Edit", "--deny", "Write", "--no-subagents", "--disable-web-search",
            *(["--max-turns", str(max_turns)] if max_turns else []), "agent", "--no-leader",
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
    requested = manifest["route"].get("context_tokens")
    if requested is None:
        return
    if type(context) is not int:
        raise TransportError("REVIEW_CONTEXT_UNVERIFIABLE: native session has no effective context window")
    if context < requested:
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
    else:
        # The leader may exit while descendants still own its process group.
        kill(signal.SIGKILL)


def run(manifest: dict, packet: bytes, *, cwd: Path, timeout: int, max_turns: int = 0,
        heartbeat_interval: float = 30, progress=None, attempt_dir: Path | None = None,
        packet_path: Path | None = None) -> dict:
    """No retry, no product mutation, no prompt before native capacity proof."""
    command = argv(manifest, max_turns=max_turns)
    # A refused session/new still has a distinct attempt identity for archiving.
    result = {"session": str(uuid.uuid4()), "argv": command, "output": b"", "raw": b"",
              "stderr": b"", "complete": False, "detail": "", "observed_context": None,
              "provider_route": {}, "heartbeats": [], "read_ledger": {}}
    attempt_dir = Path(attempt_dir) if attempt_dir is not None else None
    ledger = ReadLedger(cwd)
    process = None
    process_identity = None
    raw, stderr, chunks = [], [], []
    last_response = ""
    inbox = queue.Queue()
    readers = []
    started = last_activity = time.monotonic()
    next_probe = started + heartbeat_interval
    activity_events = 0
    sequence = 0
    responses = 0
    session = None

    def persist(method, request_id=None):
        if attempt_dir is not None:
            review_job.write(attempt_dir / "job.json", {
                "session_id": session, "request_id": request_id if request_id is not None else sequence, "phase": method,
                "process": process_identity,
                "updated_at": time.time()})

    def probe(method):
        nonlocal next_probe
        now = time.monotonic()
        if process.poll() is not None:
            raise TransportError("REVIEW_ACP_TERMINATED: provider exited before terminal response")
        if session is not None and method == "session/prompt":
            verify_route(provider_route(cwd, session), manifest)
        snapshot = {"schema_version": "review-heartbeat/v1", "session_id": session,
                    "phase": method, "process_alive": True, "updated_at": time.time(),
                    "elapsed_seconds": round(now - started, 3),
                    "idle_seconds": round(now - last_activity, 3),
                    "activity_events": activity_events, "responses": responses}
        result["heartbeats"].append(snapshot)
        if attempt_dir is not None:
            with (attempt_dir / "heartbeats.jsonl").open("a") as stream:
                stream.write(json.dumps(snapshot) + "\n")
                stream.flush()
        if progress is not None:
            progress(snapshot)
        next_probe = now + heartbeat_interval

    def reader(stream, target, deliver=False):
        archive = ((attempt_dir / ("provider-output.jsonl" if deliver else "stderr.log")).open("ab", buffering=0)
                   if attempt_dir is not None else None)
        try:
            while line := stream.readline():
                if archive is None:
                    target.append(line)
                if archive is not None:
                    archive.write(line)
                if deliver:
                    inbox.put(line)
        finally:
            if archive is not None:
                archive.close()
            if deliver:
                inbox.put(None)

    def send(value):
        process.stdin.write((json.dumps(value, ensure_ascii=False) + "\n").encode())
        process.stdin.flush()

    def rpc(method, params):
        nonlocal sequence, last_response, responses, last_activity, activity_events
        sequence += 1
        request_id = sequence
        persist(method, request_id)
        send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        while True:
            now = time.monotonic()
            if attempt_dir is not None and (attempt_dir / "cancel.json").exists():
                if session is not None:
                    send({"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": session}})
                raise TransportError("REVIEW_CANCELLED: cancellation requested; provider group will be reaped")
            if now >= next_probe:
                probe(method)
            remaining = timeout - (now - last_activity)
            if remaining <= 0:
                raise TransportError("REVIEW_INACTIVE: timeout without reviewer activity")
            try:
                line = inbox.get(timeout=min(remaining, max(0, next_probe - now), 0.25))
            except queue.Empty:
                continue
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
                ledger.observe(update)
                if update.get("sessionUpdate") in {
                    "agent_message_chunk", "agent_thought_chunk", "tool_call",
                    "tool_call_update", "tool_call_delta_chunk", "response_completed",
                }:
                    last_activity = time.monotonic()
                    activity_events += 1
                if update.get("sessionUpdate") == "agent_message_chunk":
                    content = update.get("content", {})
                    if content.get("type") == "text":
                        chunks.append(content["text"])
                if update.get("sessionUpdate") == "response_completed":
                    last_response = "".join(chunks)
                    chunks.clear()
                    responses += 1
            if message.get("id") == request_id and "method" not in message:
                if "error" in message:
                    raise TransportError("REVIEW_ACP_ERROR: " + json.dumps(message["error"], ensure_ascii=False))
                value = message.get("result")
                if not isinstance(value, dict):
                    raise TransportError("REVIEW_ACP_INVALID: missing result object")
                last_activity = time.monotonic()
                return value

    def route():
        # Persistence may trail set_model with a complete default route as well
        # as missing fields. Wait for bounded convergence, never prompt until
        # the effective native route satisfies every requested axis.
        until = time.monotonic() + min(timeout, 3)
        while True:
            witness = provider_route(cwd, session)
            result["provider_route"] = witness
            result["observed_context"] = witness.get("context_tokens")
            if (witness.get("model") == manifest["route"]["model"] and witness.get("effort") == manifest["effort"]
                    and ("context_tokens" not in manifest["route"] or
                         type(witness.get("context_tokens")) is int
                         and witness["context_tokens"] >= manifest["route"]["context_tokens"])):
                verify_route(witness, manifest)
                return witness
            if time.monotonic() >= until:
                if not witness:
                    raise TransportError("REVIEW_CONTEXT_UNVERIFIABLE: native session summary is unavailable")
                verify_route(witness, manifest)
            time.sleep(min(0.05, max(0, until - time.monotonic())))

    try:
        prompt = [{"type": "text", "text": packet.decode()}]
        if packet_path is not None:
            immutable_packet = Path(packet_path).resolve()
            machine_manifest = immutable_packet.with_name("review-route.json")
            if (not immutable_packet.is_relative_to(cwd.resolve())
                    or immutable_packet.name != "packet.md"
                    or immutable_packet.read_bytes() != packet
                    or hashlib.sha256(packet).hexdigest() != manifest.get("packet_sha256")
                    or json.loads(machine_manifest.read_bytes()) != manifest):
                raise TransportError("REVIEW_PACKET_STALE: immutable packet/manifest locator differs from the bound input")
            locator = {"packet_path": str(immutable_packet), "machine_manifest": str(machine_manifest)}
            prompt.append({"type": "text", "text": "## Immutable review artifact locator\n"
                           + json.dumps(locator, ensure_ascii=False, sort_keys=True)
                           + "\nUse these exact paths for the immutable packet and its machine metadata; "
                           "they take precedence over relative locator descriptions in the packet."})
        executable = shutil.which(command[0])
        result["provider_runtime"] = {"executable": executable,
            "sha256": hashlib.sha256(Path(executable).read_bytes()).hexdigest() if executable else None}
        # Local provenance collection is not time spent waiting for a provider.
        started = last_activity = time.monotonic()
        next_probe = started + heartbeat_interval
        process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, start_new_session=os.name == "posix")
        process_identity = review_job.identity(process.pid) if attempt_dir is not None else None
        persist("spawned")
        for stream, target, deliver in ((process.stdout, raw, True), (process.stderr, stderr, False)):
            thread = threading.Thread(target=reader, args=(stream, target, deliver), daemon=True)
            thread.start()
            readers.append(thread)
        initialized = rpc("initialize", {"protocolVersion": 1, "clientCapabilities": {},
                                          "clientInfo": {"name": "swissknifeman-task-review", "version": "1"}})
        result["provider_runtime"]["agent_info"] = initialized.get("agentInfo", initialized.get("serverInfo"))
        created = rpc("session/new", {"cwd": str(cwd), "mcpServers": []})
        session = created.get("sessionId")
        if (not isinstance(session, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", session)
                or session == manifest["executor_session"]):
            raise TransportError("REVIEW_NOT_INDEPENDENT: require a distinct newly created provider session")
        result["session"] = session
        rpc("session/set_model", {"sessionId": session, "modelId": manifest["route"]["model"],
                                  "_meta": {"reasoningEffort": manifest["effort"],
                                            **({"contextWindow": manifest["route"]["context_tokens"]}
                                               if "context_tokens" in manifest["route"] else {})}})
        route()
        terminal = rpc("session/prompt", {"sessionId": session,
                                          "prompt": prompt})
        ledger.verify()
        result["read_ledger"] = ledger.result()
        metadata = terminal.get("_meta", {})
        usage = metadata.get("usage", {})
        result["usage"] = usage
        result["stop_reason"] = terminal.get("stopReason")
        usage_known = (isinstance(usage, dict)
                       and all(type(usage.get(key)) is int and usage[key] >= 0
                               for key in ("inputTokens", "outputTokens", "cachedReadTokens", "cacheCreationTokens"))
                       and usage["inputTokens"] + usage["outputTokens"] > 0
                       and type(usage.get("numTurns")) is int and usage["numTurns"] > 0
                       and (not max_turns or usage["numTurns"] <= max_turns)
                       and not usage.get("usage_is_incomplete", False))
        route()
        result["complete"] = (terminal.get("stopReason") == "end_turn" and metadata.get("sessionId") == session
                              and metadata.get("modelId") == manifest["route"]["model"] and usage_known
                              and not metadata.get("usage_is_incomplete", False)
                              and not terminal.get("usage_is_incomplete", False))
        result["detail"] = f"ACP stopReason={terminal.get('stopReason')}; usage_complete={usage_known}"
    except (KeyboardInterrupt, SystemExit):
        result["complete"] = False
        result["detail"] = "REVIEW_INTERRUPTED: executor interrupted transport"
        raise
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as exc:
        result["detail"] = str(exc) if isinstance(exc, TransportError) else type(exc).__name__ + ": " + str(exc)
    finally:
        if process is not None:
            _stop(process)
            for thread in readers:
                thread.join(timeout=2)
            for stream in (process.stdin, process.stdout, process.stderr):
                stream.close()
        result["output"] = ("".join(chunks) or last_response).encode()
        result["raw"] = b"".join(raw) if attempt_dir is None else (attempt_dir / "provider-output.jsonl").read_bytes() if (attempt_dir / "provider-output.jsonl").exists() else b""
        result["stderr"] = b"".join(stderr) if attempt_dir is None else (attempt_dir / "stderr.log").read_bytes() if (attempt_dir / "stderr.log").exists() else b""
        result["exit_code"] = process.poll() if process is not None else None
        result["process"] = process_identity
        result["prompt_request_id"] = sequence
        result["wall_seconds"] = round(time.monotonic() - started, 3)
        if attempt_dir is not None:
            (attempt_dir / "output.json").write_bytes(result["output"])
            result["read_ledger"] = result["read_ledger"] or ledger.result()
            review_job.write(attempt_dir / "transport-result.json",
                             {key: value for key, value in result.items() if key not in {"output", "raw", "stderr"}})
            persist("completed" if result["complete"] else "interrupted" if result["detail"].startswith(
                ("REVIEW_INTERRUPTED", "REVIEW_CANCELLED")) else "failed")
    return result
