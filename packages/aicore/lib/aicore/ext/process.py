"""One-shot child processes speaking JSON: the only place of aicore.ext that spawns a process.

:func:`run_json` starts ``argv`` in a new session, writes one JSON object to its stdin and expects
exactly one JSON object on its stdout. Whatever the child does (garbage output, a flood, a hang, a
crash, grandchildren that outlive it) the outcome is a :class:`ProcessResult` with a ``code``; the
function raises only for invalid arguments of the caller.

Reading and writing share one ``selectors`` loop with one deadline: ``communicate()`` is not used
because a descendant that left the process group may keep a pipe open forever. A deadline kills the
whole process group (SIGTERM, a grace period, SIGKILL); after the direct child exits the group gets a
SIGKILL too, so descendants that stayed in the group do not survive the call. A descendant that calls
``setsid()`` leaves the group and is out of reach; enforcement of that needs cgroups. stdlib only.
"""
from __future__ import annotations

import json
import math
import os
import re
import selectors
import signal
import subprocess
import time
from typing import Dict, List, Mapping, NamedTuple, Optional, Sequence

from ..util.digest import canonical_json_bytes

MAX_STDOUT = 1048576
STDERR_TAIL = 2048
GRACE_S = 2.0
REDACTED = "***"
_CHUNK = 65536
_POLL_S = 0.05


class ProcessResult(NamedTuple):
    """Outcome of :func:`run_json`; ``ok`` means exit 0 and a valid answer, ``code`` names a failure."""

    ok: bool
    code: Optional[str]
    exit: Optional[int]
    document: Optional[dict]
    stderr_tail: str
    duration_ms: int
    timed_out: bool


def _killpg(pgid: int, sig: int) -> None:
    try:
        os.killpg(pgid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _has_exited(proc: "subprocess.Popen[bytes]") -> bool:
    """True once the direct child has exited. Prefers ``waitid(WNOWAIT)``: the child stays unreaped, so its
    pid (the group id) cannot be reused before the group is killed."""
    if hasattr(os, "waitid"):
        try:
            return os.waitid(os.P_PID, proc.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None
        except ChildProcessError:
            return True
    return proc.poll() is not None


_JSON_ESCAPE = re.compile(rb'\\(?:u([0-9a-fA-F]{4})|(["\\/bfnrt]))')
_PERCENT = re.compile(rb"%([0-9a-fA-F]{2})")
_SPELLING_FACTOR = 6  # longest spelling of one secret byte: "\\u0041" for "A"
_SIMPLE = {b'"': b'"', b"\\": b"\\", b"/": b"/", b"b": b"\b", b"f": b"\f", b"n": b"\n", b"r": b"\r",
           b"t": b"\t"}


def _secret_bytes(secrets: Sequence[str]) -> List[bytes]:
    """The secrets as bytes (a lone surrogate from a decoded environment is kept as its raw byte)."""
    found = set()
    for secret in secrets:
        if isinstance(secret, str) and secret:
            try:
                found.add(secret.encode("utf-8", "surrogateescape"))
            except UnicodeEncodeError:
                found.add(secret.encode("utf-8", "surrogatepass"))
    return sorted(found, key=lambda item: (-len(item), item))


def _json_view(data: bytes):
    """``(view, starts, ends)``: ``data`` with JSON escapes (``\\uXXXX``, ``\\/``, ``\\"``...) decoded; ``starts``
    and ``ends`` map every view byte back to its span in ``data``."""
    view, starts, ends = bytearray(), [], []
    position = 0
    tokens = []
    for match in _JSON_ESCAPE.finditer(data):
        if match.group(1) is not None:
            code = int(match.group(1), 16)
            tokens.append([match.start(), match.end(), code, True])
        else:
            tokens.append([match.start(), match.end(), _SIMPLE[match.group(2)], False])
    merged = []
    for token in tokens:  # a surrogate pair written as two escapes is one character
        previous = merged[-1] if merged else None
        if (token[3] and 0xDC00 <= token[2] <= 0xDFFF and previous is not None and previous[3]
                and previous[1] == token[0] and 0xD800 <= previous[2] <= 0xDBFF):
            previous[2] = 0x10000 + ((previous[2] - 0xD800) << 10) + (token[2] - 0xDC00)
            previous[1] = token[1]
        else:
            merged.append(token)
    for start, end, value, is_code in merged:
        for index in range(position, start):
            view.append(data[index])
            starts.append(index)
            ends.append(index + 1)
        if is_code:
            try:
                piece = chr(value).encode("utf-8")
            except UnicodeEncodeError:
                piece = chr(value).encode("utf-8", "surrogatepass")
                if 0xDC80 <= value <= 0xDCFF:
                    piece = bytes([value - 0xDC00])
        else:
            piece = value
        for byte in piece:
            view.append(byte)
            starts.append(start)
            ends.append(end)
        position = end
    for index in range(position, len(data)):
        view.append(data[index])
        starts.append(index)
        ends.append(index + 1)
    return bytes(view), starts, ends


def _percent_view(data: bytes):
    view, starts, ends = bytearray(), [], []
    position = 0
    for match in _PERCENT.finditer(data):
        for index in range(position, match.start()):
            view.append(data[index])
            starts.append(index)
            ends.append(index + 1)
        view.append(int(match.group(1), 16))
        starts.append(match.start())
        ends.append(match.end())
        position = match.end()
    for index in range(position, len(data)):
        view.append(data[index])
        starts.append(index)
        ends.append(index + 1)
    return bytes(view), starts, ends


def _redact_bytes(data: bytes, secrets: List[bytes]) -> bytes:
    """Replace every secret with ``***``, also where it is written with JSON escapes (any library, any mix of
    escaped and plain characters) or percent-encoded. Linear scans only: no backtracking on hostile output."""
    spans = []
    identity = list(range(len(data)))
    for view, starts, ends in ((data, identity, [index + 1 for index in identity]), _json_view(data),
                               _percent_view(data)):
        for secret in secrets:
            at = view.find(secret)
            while at != -1:
                spans.append((starts[at], ends[at + len(secret) - 1]))
                at = view.find(secret, at + len(secret))
    if not spans:
        return data
    spans.sort()
    out, position = bytearray(), 0
    for start, end in spans:
        if start < position:
            if end > position:
                position = end
            continue
        out += data[position:start] + REDACTED.encode("ascii")
        position = end
    out += data[position:]
    return bytes(out)


def _redact_text(text: str, secrets: Sequence[str]) -> str:
    for secret in sorted((s for s in secrets if isinstance(s, str) and s), key=len, reverse=True):
        text = text.replace(secret, REDACTED)
    return text


def _redact_document(value: object, secrets: Sequence[str]) -> object:
    """Replace secrets in strings, keys and scalars (a number or literal whose JSON text holds a secret
    becomes ``"***"``)."""
    if isinstance(value, str):
        return _redact_text(value, secrets)
    if isinstance(value, list):
        return [_redact_document(item, secrets) for item in value]
    if isinstance(value, dict):
        return {_redact_text(key, secrets): _redact_document(item, secrets) for key, item in value.items()}
    if any(secret in json.dumps(value) for secret in secrets):
        return REDACTED
    return value


def _tail_text(buffer: bytearray, truncated: bool, secrets: List[bytes], limit: int) -> str:
    data = _redact_bytes(bytes(buffer), secrets)
    if truncated and secrets:
        # The head of a truncated buffer may start inside a secret; a spelling is at most 6x its bytes (``\\u0041``).
        data = data[_SPELLING_FACTOR * max(len(secret) for secret in secrets) - 1:]
    return data[-limit:].decode("utf-8", "replace") if limit > 0 else ""


def _parse_stdout(raw: bytes):
    """``(document, code)`` of the child's stdout: one JSON object, empty meaning ``None``."""
    try:
        text = raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        return None, "PROTOCOL_STDOUT"
    if not text:
        return None, None
    try:
        value, end = json.JSONDecoder().raw_decode(text)
    except (ValueError, RecursionError):
        return None, "PROTOCOL_STDOUT"
    if text[end:].strip() or not isinstance(value, dict):
        return None, "PROTOCOL_STDOUT"
    return value, None


def run_json(argv: Sequence[str], payload: Optional[Mapping[str, object]], *, deadline_s: float,
             env: Optional[Mapping[str, str]], cwd: Optional[str], secrets_to_redact: Sequence[str] = (),
             max_stdout: int = MAX_STDOUT, stderr_tail: int = STDERR_TAIL,
             grace_s: float = GRACE_S) -> ProcessResult:
    """Run ``argv`` once, feed it ``payload`` as one JSON line and read one JSON object back.

    ``env=None`` means a copy of ``os.environ`` (callers pass :func:`clean_environment`); ``cwd=None`` the
    current directory. An empty stdout gives ``document=None`` (callers decide whether that is allowed).
    Every value of ``secrets_to_redact`` is replaced by ``***`` in the stderr tail and in the strings of the
    document. Raises ``ValueError``/``TypeError`` only for invalid arguments.
    """
    if isinstance(argv, (str, bytes)) or not argv or not all(isinstance(item, str) for item in argv):
        raise ValueError("argv must be a non-empty list of strings")
    if payload is not None and not isinstance(payload, Mapping):
        raise TypeError("payload must be a mapping or None")
    for name, value in (("deadline_s", deadline_s), ("grace_s", grace_s)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) \
                or value <= 0:
            raise ValueError(f"{name} must be a positive finite number")
    for name, value in (("max_stdout", max_stdout), ("stderr_tail", stderr_tail)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")
    data = b"" if payload is None else canonical_json_bytes(dict(payload)) + b"\n"
    secret_bytes = _secret_bytes(secrets_to_redact)
    secrets = [s for s in secrets_to_redact if isinstance(s, str) and s]

    started = time.monotonic()

    def finish(code, exit_code, document, tail, timed_out):
        ok = code is None and exit_code == 0
        return ProcessResult(ok, code, exit_code, document, tail, int((time.monotonic() - started) * 1000),
                             timed_out)

    child_env: Dict[str, str] = dict(os.environ) if env is None else dict(env)
    try:
        proc = subprocess.Popen(list(argv), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, start_new_session=True, env=child_env, cwd=cwd,
                                close_fds=True)
    except OSError:
        return finish("PROCESS_SPAWN", None, None, "", False)
    pgid = proc.pid  # start_new_session makes the child its own group leader

    sel = selectors.DefaultSelector()
    pipes = {"stdin": proc.stdin, "stdout": proc.stdout, "stderr": proc.stderr}
    for pipe in pipes.values():
        os.set_blocking(pipe.fileno(), False)

    def drop(name: str) -> None:
        pipe = pipes.pop(name, None)
        if pipe is None:
            return
        try:
            sel.unregister(pipe)
        except (KeyError, ValueError):
            pass
        try:
            pipe.close()
        except OSError:
            pass

    if data:
        sel.register(proc.stdin, selectors.EVENT_WRITE, "stdin")
    else:
        drop("stdin")
    sel.register(proc.stdout, selectors.EVENT_READ, "stdout")
    sel.register(proc.stderr, selectors.EVENT_READ, "stderr")

    out = bytearray()
    err = bytearray()
    err_cap = stderr_tail + 2 * _SPELLING_FACTOR * max([len(item) for item in secret_bytes] or [0])
    err_truncated = False
    too_large = False
    written = 0
    timed_out = False
    term_at: Optional[float] = None
    kill_at: Optional[float] = None
    drain_until: Optional[float] = None
    deadline = started + float(deadline_s)

    try:
        while True:
            now = time.monotonic()
            if drain_until is None:
                if _has_exited(proc):
                    _killpg(pgid, signal.SIGKILL)  # descendants that stayed in the group
                    drain_until = now + float(grace_s)
                    drop("stdin")
                elif too_large and kill_at is None:
                    _killpg(pgid, signal.SIGKILL)
                    kill_at = now
                elif not timed_out and now >= deadline:
                    timed_out = True
                    term_at = now
                    _killpg(pgid, signal.SIGTERM)
                elif timed_out and kill_at is None and now >= (term_at or now) + float(grace_s):
                    _killpg(pgid, signal.SIGKILL)
                    kill_at = now
                elif kill_at is not None and now >= kill_at + float(grace_s):
                    drain_until = now  # the child does not die: stop waiting, the pipes are closed below
            if drain_until is not None and (now >= drain_until or not (pipes.keys() & {"stdout", "stderr"})):
                break
            horizon = [now + _POLL_S]
            if drain_until is not None:
                horizon.append(drain_until)
            elif not timed_out:
                horizon.append(deadline)
            elif kill_at is None:
                horizon.append((term_at or now) + float(grace_s))
            else:
                horizon.append(kill_at + float(grace_s))
            timeout = max(0.0, min(horizon) - now)
            if not sel.get_map():
                time.sleep(timeout)
                continue
            for key, _events in sel.select(timeout):
                name = key.data
                if name == "stdin":
                    try:
                        written += os.write(proc.stdin.fileno(), data[written:written + 4096])
                    except BlockingIOError:
                        continue
                    except OSError:  # BrokenPipeError: the child does not read its input
                        drop("stdin")
                        continue
                    if written >= len(data):
                        drop("stdin")
                    continue
                try:
                    chunk = os.read(key.fileobj.fileno(), _CHUNK)
                except BlockingIOError:
                    continue
                except OSError:
                    chunk = b""
                if not chunk:
                    drop(name)
                elif name == "stdout":
                    if not too_large:
                        out += chunk
                        if len(out) > max_stdout:
                            too_large = True
                            del out[max_stdout + 1:]
                else:
                    err += chunk
                    if len(err) > err_cap:
                        del err[:len(err) - err_cap]
                        err_truncated = True
    finally:
        for name in list(pipes):
            drop(name)
        sel.close()
        try:
            proc.wait(timeout=float(grace_s))
        except subprocess.TimeoutExpired:
            _killpg(pgid, signal.SIGKILL)
            try:
                proc.wait(timeout=float(grace_s))
            except subprocess.TimeoutExpired:
                pass

    tail = _tail_text(err, err_truncated, secret_bytes, stderr_tail)
    exit_code = proc.returncode
    document, parse_code = (None, None) if too_large else _parse_stdout(bytes(out))
    if document is not None and secrets:
        try:
            document = _redact_document(document, secrets)
        except RecursionError:  # a document nested too deep to be handled is not a valid answer
            document, parse_code = None, "PROTOCOL_STDOUT"
    if timed_out:
        code = "PROCESS_TIMEOUT"
    elif too_large:
        code = "PROTOCOL_STDOUT_TOO_LARGE"
    elif exit_code != 0:
        code = "PROCESS_EXIT"
    else:
        code = parse_code
    return finish(code, exit_code, document, tail, timed_out)
