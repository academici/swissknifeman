"""Research source adapters: ``command``, ``filesystem`` and ``mcp-stdio`` (knowledge ``p10-research#sources``).

Every adapter answers ``{source, text, sources, raw_ref}``: the text, the URLs or paths it rests on and the sha256 of
the raw reply. A busy or slow source is asked again by ``retry.decide`` (at most :data:`RETRIES_MAX` times, a wait
between the attempts); a source that stays busy, fails or sends a reply that cannot be read is ``SOURCE_UNAVAILABLE``.
The argv of a source comes from the configuration only (machine, invocation, flags: the schema forbids the project).
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time

from orch import retry

RETRIES_MAX = 3
RETRY_WAIT_S = 5          # the wait before the first repeat; it grows with the attempt
PROTOCOL_VERSION = "2024-11-05"
BUSY_MARK = "BROWSER_BUSY"
MAX_MATCHES = 50
MAX_FILE_BYTES = 1_000_000
SKIPPED_DIRS = frozenset({".git", "node_modules", "__pycache__", ".swissknifeman"})
_URL = re.compile(r"https?://[^\s<>\"')\]]+")
_GATES: dict = {}
_GATES_LOCK = threading.Lock()


class SourceError(Exception):
    """``SOURCE_UNKNOWN``: no such source; ``SOURCE_INVALID``: its entry cannot be used; ``QUERY_EMPTY``;
    ``SOURCE_UNAVAILABLE``: it did not answer (also after the repeats)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class _Busy(Exception):
    """The source asked to come back later (``BROWSER_BUSY``) or did not answer in time."""

    def __init__(self, error_class: str, message: str):
        super().__init__(message)
        self.error_class = error_class


@dataclass(frozen=True)
class Source:
    id: str
    kind: str
    argv: tuple = ()
    tool: str = "search"
    roots: tuple = ()
    capabilities: tuple = ()
    timeout_s: int = 600
    concurrency: int = 1
    order: int = 100

    def describe(self) -> dict:
        return {"id": self.id, "kind": self.kind, "order": self.order, "capabilities": list(self.capabilities),
                "timeout_s": self.timeout_s, "concurrency": self.concurrency,
                **({"argv": list(self.argv)} if self.argv else {}),
                **({"tool": self.tool} if self.kind == "mcp-stdio" else {}),
                **({"roots": list(self.roots)} if self.roots else {})}


def sources_from(settings) -> list:
    """The configured sources on the ladder: by ``order``, then by id."""
    found = []
    for name, entry in (settings.research.get("sources") or {}).items():
        kind = entry.get("kind")
        if kind is None:
            raise SourceError("SOURCE_INVALID", f"source {name!r} has no kind")
        found.append(Source(id=name, kind=kind, argv=tuple(entry.get("argv") or ()), tool=entry["tool"],
                            roots=tuple(entry.get("roots") or ()), capabilities=tuple(entry.get("capabilities") or ()),
                            timeout_s=entry["timeout_s"], concurrency=entry["concurrency"], order=entry["order"]))
    return sorted(found, key=lambda source: (source.order, source.id))


def _expand(argv: tuple) -> list:
    return [os.path.expanduser(part) if part.startswith("~") else part for part in argv]


def _digest(raw: str) -> str:
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _urls(text: str) -> list:
    found: list = []
    for url in _URL.findall(text):
        url = url.rstrip(".,;:")
        if url not in found:
            found.append(url)
    return found


# -- command ----------------------------------------------------------------------------------------------------

def _command(source: Source, text: str, *, cwd) -> dict:
    if not source.argv:
        raise SourceError("SOURCE_INVALID", f"source {source.id!r} (command) has no argv")
    try:
        done = subprocess.run(_expand(source.argv), input=text, capture_output=True, text=True,
                              timeout=source.timeout_s, cwd=cwd)
    except subprocess.TimeoutExpired:
        raise _Busy("timeout", f"no answer in {source.timeout_s} s") from None
    except OSError as error:
        raise SourceError("SOURCE_UNAVAILABLE", f"{source.id}: cannot start: {error}") from None
    if done.returncode != 0:
        raise SourceError("SOURCE_UNAVAILABLE", f"{source.id}: exit {done.returncode}: {done.stderr.strip()[:200]}")
    try:
        doc = json.loads(done.stdout)
    except ValueError:
        raise SourceError("SOURCE_UNAVAILABLE", f"{source.id}: stdout is not JSON") from None
    if not isinstance(doc, dict) or not isinstance(doc.get("text"), str):
        raise SourceError("SOURCE_UNAVAILABLE", f"{source.id}: the JSON has no string 'text'")
    urls = doc.get("sources", [])
    if not isinstance(urls, list) or not all(isinstance(item, str) for item in urls):
        raise SourceError("SOURCE_UNAVAILABLE", f"{source.id}: 'sources' is not a list of strings")
    return {"text": doc["text"], "sources": list(urls), "raw_ref": _digest(done.stdout)}


# -- filesystem -------------------------------------------------------------------------------------------------

def _filesystem(source: Source, text: str, *, cwd) -> dict:
    if not source.roots:
        raise SourceError("SOURCE_INVALID", f"source {source.id!r} (filesystem) has no roots")
    needle = text.strip().lower()
    base = Path(cwd) if cwd else Path.cwd()
    rows: list = []
    files: list = []
    for root in source.roots:
        top = Path(os.path.expanduser(root))
        top = top if top.is_absolute() else base / top
        for folder, dirs, names in os.walk(top):  # symlinked folders are not followed: only reading, only inside
            dirs[:] = sorted(name for name in dirs if name not in SKIPPED_DIRS)
            for name in sorted(names):
                path = Path(folder) / name
                try:
                    if path.is_symlink() or path.stat().st_size > MAX_FILE_BYTES:
                        continue
                    lines = path.read_text(encoding="utf-8").splitlines()
                except (OSError, UnicodeDecodeError):
                    continue
                try:
                    shown = str(path.relative_to(base))
                except ValueError:
                    shown = str(path)
                for number, line in enumerate(lines, 1):
                    if needle in line.lower() and len(rows) < MAX_MATCHES:
                        rows.append(f"{shown}:{number}: {line.strip()}")
                        if shown not in files:
                            files.append(shown)
    body = "\n".join(rows)
    return {"text": body, "sources": files, "raw_ref": _digest(body)}


# -- mcp-stdio --------------------------------------------------------------------------------------------------

class McpStdioClient:
    """A minimal MCP client over stdio: initialize, notifications/initialized, then calls (JSON-RPC, one message a line).

    Lines that are not JSON (a banner of the server) are skipped. Every wait ends at the deadline of the client.
    """

    def __init__(self, argv, *, timeout_s: float, cwd=None):
        self._deadline = time.monotonic() + timeout_s
        self._lines: queue.Queue = queue.Queue()
        self._next = 0
        self._proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                      text=True, bufsize=1, cwd=cwd)
        self._reader = threading.Thread(target=self._pump, daemon=True)
        self._reader.start()

    def _pump(self) -> None:
        for line in self._proc.stdout:
            self._lines.put(line)
        self._lines.put(None)

    def _send(self, message: dict) -> None:
        try:
            self._proc.stdin.write(json.dumps(message) + "\n")
            self._proc.stdin.flush()
        except OSError:
            raise SourceError("SOURCE_UNAVAILABLE", "the server closed its input") from None

    def _request(self, method: str, params: dict | None = None) -> dict:
        self._next += 1
        msg_id = self._next
        self._send({"jsonrpc": "2.0", "id": msg_id, "method": method, **({"params": params} if params else {})})
        while True:
            try:
                line = self._lines.get(timeout=max(self._deadline - time.monotonic(), 0))
            except queue.Empty:
                raise _Busy("timeout", f"no answer to {method}") from None
            if line is None:
                raise SourceError("SOURCE_UNAVAILABLE", "the server closed its output")
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if isinstance(message, dict) and message.get("id") == msg_id:
                return message

    def start(self) -> None:
        self._request("initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                                     "clientInfo": {"name": "orch-research", "version": "1"}})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def call(self, tool: str, arguments: dict) -> dict:
        return self._request("tools/call", {"name": tool, "arguments": arguments})

    def close(self) -> None:
        try:
            self._proc.stdin.close()
        except OSError:
            pass
        self._proc.terminate()
        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait()
        self._reader.join(timeout=2)
        self._proc.stdout.close()


def _mcp_stdio(source: Source, text: str, *, cwd) -> dict:
    if not source.argv:
        raise SourceError("SOURCE_INVALID", f"source {source.id!r} (mcp-stdio) has no argv")
    try:
        client = McpStdioClient(_expand(source.argv), timeout_s=source.timeout_s, cwd=cwd)
    except OSError as error:
        raise SourceError("SOURCE_UNAVAILABLE", f"{source.id}: cannot start: {error}") from None
    try:
        client.start()
        reply = client.call(source.tool, {"query": text})
    finally:
        client.close()
    raw = json.dumps(reply, ensure_ascii=False, sort_keys=True)
    if "error" in reply:
        message = str(reply["error"].get("message", reply["error"])) if isinstance(reply["error"], dict) else str(reply["error"])
        if BUSY_MARK in message:
            raise _Busy("rate_limit", message)
        raise SourceError("SOURCE_UNAVAILABLE", f"{source.id}: {message[:200]}")
    result = reply.get("result")
    if not isinstance(result, dict):
        raise SourceError("SOURCE_UNAVAILABLE", f"{source.id}: the reply has no result")
    body = "".join(part.get("text", "") for part in result.get("content") or [] if isinstance(part, dict))
    if BUSY_MARK in body:
        raise _Busy("rate_limit", body.strip()[:200])
    if result.get("isError"):
        raise SourceError("SOURCE_UNAVAILABLE", f"{source.id}: {body.strip()[:200] or 'the tool failed'}")
    return {"text": body, "sources": _urls(body), "raw_ref": _digest(raw)}


ADAPTERS = {"command": _command, "filesystem": _filesystem, "mcp-stdio": _mcp_stdio}


# -- query ------------------------------------------------------------------------------------------------------

def _gate(source: Source) -> threading.BoundedSemaphore:
    with _GATES_LOCK:
        return _GATES.setdefault((source.id, source.concurrency), threading.BoundedSemaphore(source.concurrency))


def query(source: Source, text: str, *, cwd=None, sleep=time.sleep, retry_wait_s: int = RETRY_WAIT_S) -> dict:
    """Ask one source; ``retry.decide`` says whether a busy or slow answer is asked again.

    Only ``concurrency`` queries of a source run at once in this process (the others wait). The answer is
    ``{source, text, sources, raw_ref}``; ``SourceError`` otherwise.
    """
    if not text.strip():
        raise SourceError("QUERY_EMPTY", "the query is empty")
    adapter = ADAPTERS.get(source.kind)
    if adapter is None:
        raise SourceError("SOURCE_INVALID", f"source {source.id!r}: unsupported kind {source.kind!r}")
    attempts = 0
    with _gate(source):
        while True:
            attempts += 1
            try:
                return {"source": source.id, **adapter(source, text, cwd=cwd)}
            except _Busy as busy:
                decision = retry.decide(
                    retry.RetryInputs(error_class=busy.error_class, stage_writes=False, worktree_dirty=False,
                                      receipt_unresolved=False, attempts_used=attempts, stage_retries_max=RETRIES_MAX,
                                      budget_left=RETRIES_MAX - (attempts - 1), retry_after_s=retry_wait_s * attempts),
                    {})
                if decision.action not in ("retry", "retry_after"):
                    raise SourceError("SOURCE_UNAVAILABLE",
                                      f"{source.id}: {busy} (after {attempts} attempts)") from None
                sleep(decision.wait_s or 0)
