"""Conformance of a plugin: the host side of the protocol, applied to a plugin you did not write.

:func:`run_conformance` starts the plugin the way the host does (a cleaned environment, one JSON object on
stdin, one JSON object expected on stdout) and answers with a list of ``check-result/v1`` documents, one per
scenario, ``check_id`` ``ext.conformance.<scenario>``:

``manifest``, ``describe``, ``protocol-unsupported``, ``invoke``, ``redelivery``, ``stdout-discipline``,
``deadline``, ``no-descendants``, ``secrets`` and ``crash``.

Every scenario is always reported: ``ok``, ``fail``, or ``skip`` when it does not apply (a command plugin has no
redelivery) or cannot run (the manifest is broken, an earlier call timed out, the platform is not Linux).

``no-descendants`` needs the process to adopt orphans (``PR_SET_CHILD_SUBREAPER``) and to reap them with
``waitpid(-1)``, which would steal the children of whoever called :func:`run_conformance`. It therefore runs in a
child process, ``python3 -m aicore.ext.conformance --supervise``, that makes the same calls and reports what the
plugin left behind (a descendant that escaped through ``setsid()`` included). stdlib and ``aicore`` only.
"""
from __future__ import annotations

import json
import os
import signal
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Mapping, NamedTuple, Optional, Sequence, Set, Tuple, Union

from ..config import ConfigError
from ..config import secrets as _secrets
from ..util import schema as _schema
from .environment import clean_environment
from .errors import ExtError
from .events import build_event
from .plugins import DEFAULT_TIMEOUT_S, HOST_PROTOCOL, REQUEST_SCHEMA, Manifest, load_manifest, safe_text
from .process import GRACE_S, ProcessResult, run_json

SCENARIOS = ("manifest", "describe", "protocol-unsupported", "invoke", "redelivery", "stdout-discipline",
             "deadline", "no-descendants", "secrets", "crash")
CHECK_PREFIX = "ext.conformance."
RESULT_SCHEMA = "urn:swissknifeman:aicore:check-result:v1"
UNSUPPORTED_PROTOCOL = "999"
SYNTHETIC_TYPE = "conformance.test.emitted"
SYNTHETIC_SOURCE = "conformance"
PR_SET_CHILD_SUBREAPER = 36

_SCHEMA_ROOT = Path(__file__).resolve().parents[3] / "schemas"
_LIB_ROOT = Path(__file__).resolve().parents[2]
_STDOUT_CODES = ("PROTOCOL_STDOUT", "PROTOCOL_STDOUT_TOO_LARGE")
_REMEDIATION = {
    "manifest": "Fix extension.json until it matches extension/v1 and the host's rules.",
    "describe": "Answer op describe with a plugin-describe/v1 document that matches the manifest.",
    "protocol-unsupported": "Refuse a protocol you do not speak: status error, error.code PROTOCOL_UNSUPPORTED.",
    "invoke": "Answer the call with a valid plugin-response/v1 that repeats the request_id.",
    "redelivery": "Make event handling idempotent by the event id: answer ok or skipped on a repeat.",
    "stdout-discipline": "Write exactly one JSON object to stdout; send logs to stderr.",
    "deadline": "Answer within timeout_seconds of the manifest (60 s without it).",
    "no-descendants": "Wait for or stop every process the plugin starts before it exits.",
    "secrets": "Never write a secret value to stdout.",
    "crash": "Answer with status error instead of exiting; the host redelivers after a crash.",
}
_contracts: Dict[str, Tuple[Any, str]] = {}

PathLike = Union[str, "os.PathLike[str]"]


def _problems(doc: object, contract: str) -> List[str]:
    if contract not in _contracts:
        _contracts[contract] = _schema.load_contract(_SCHEMA_ROOT / contract / "v1")
    registry, kind = _contracts[contract]
    return [f"{issue.path or '/'}: {issue.message}" for issue in _schema.validate(doc, kind, registry)]


def _result(scenario: str, status: str, observed: str, evidence: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    doc: Dict[str, Any] = {"$schema": RESULT_SCHEMA, "check_id": CHECK_PREFIX + scenario, "status": status,
                           "category": "integration", "observed": safe_text(observed, 300) or "no detail"}
    if evidence:
        doc["evidence"] = [safe_text(item, 200) for item in evidence]
    if status == "fail":
        doc["remediation"] = _REMEDIATION[scenario]
    return doc


# --- calling the plugin --------------------------------------------------------------------------------------


class _Call(NamedTuple):
    label: str
    request: Dict[str, Any]
    result: ProcessResult


class _Runner:
    """Starts a plugin as the host does and remembers every call. After a timeout it starts nothing more."""

    def __init__(self, manifest: Manifest, source_env: Mapping[str, str], timeout: int, *, trusted: bool = False):
        self.manifest = manifest
        self.timeout = timeout
        self.trusted = trusted
        self.calls: List[_Call] = []
        self.stopped = False
        self._env, _ignored = clean_environment(source_env, permissions=manifest.permissions,
                                                      trusted=trusted)

    def call(self, label: str, fields: Mapping[str, Any], *, protocol: str = "1",
             attempt: int = 1) -> Optional[_Call]:
        if self.stopped:
            return None
        request: Dict[str, Any] = {"$schema": REQUEST_SCHEMA, "protocol": protocol, "request_id": uuid.uuid4().hex,
                                   "deadline_ms": self.timeout * 1000}
        request.update(fields)
        request["context"] = {"project_root": None, "attempt": attempt, "trusted": self.trusted}
        # No redaction here: a secret that reaches the output must be seen, not hidden.
        result = run_json(list(self.manifest.entrypoint), request, deadline_s=self.timeout, env=self._env,
                          cwd=str(self.manifest.directory))
        made = _Call(label, request, result)
        self.calls.append(made)
        if result.timed_out:
            self.stopped = True
        return made


def _failure_text(call: _Call, timeout: int) -> Optional[str]:
    """Why the process of ``call`` did not give a usable answer, or None."""
    result = call.result
    if result.code == "PROCESS_TIMEOUT":
        return f"no answer within {timeout} s"
    if result.code in _STDOUT_CODES:
        return "stdout is not exactly one JSON object"
    if result.code == "PROCESS_SPAWN":
        return "the plugin could not be started"
    if result.code is not None:
        return f"the process failed ({result.code}, exit {result.exit})"
    if result.document is None:
        return "nothing was written to stdout"
    return None


def _answer(call: _Call, timeout: int) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """The validated ``plugin-response/v1`` of ``call`` and the problem with it, if any."""
    problem = _failure_text(call, timeout)
    if problem:
        return None, problem
    document = call.result.document
    assert document is not None
    issues = _problems(document, "plugin-response")
    if issues:
        return None, f"the answer does not match plugin-response/v1: {safe_text(issues[0])}"
    if document["request_id"] != call.request["request_id"]:
        return None, "the answer repeats another request_id"
    if document["status"] == "error" and "error" not in document:
        return None, "status error without error.code"
    return document, None


def _describe_problem(manifest: Manifest, call: _Call, timeout: int) -> Optional[str]:
    document, problem = _answer(call, timeout)
    if document is None:
        return problem
    if document["status"] != "ok" or not isinstance(document.get("output"), dict):
        code = safe_text(document.get("error", {}).get("code", "")) or document["status"]
        return f"describe answered {code} instead of its description"
    output = document["output"]
    issues = _problems(output, "plugin-describe")
    if issues:
        return f"the description does not match plugin-describe/v1: {safe_text(issues[0])}"
    expected = {"id": manifest.id, "version": manifest.version, "kind": manifest.kind,
                "capabilities_digest": manifest.capabilities_digest}
    for name, value in expected.items():
        if output[name] != value:
            return f"{name} is {safe_text(output[name])!r} in the description but {value!r} in the manifest"
    low, high = max(manifest.protocol[0], HOST_PROTOCOL[0]), min(manifest.protocol[1], HOST_PROTOCOL[1])
    if not low <= int(output["protocol"]) <= high:
        return f"protocol {output['protocol']} is outside the range shared with the host"
    return None


def _synthetic_event() -> Dict[str, Any]:
    return build_event(SYNTHETIC_TYPE, {"purpose": "conformance"}, source=SYNTHETIC_SOURCE).to_json()


def _operation(manifest: Manifest, input_doc: Optional[Mapping[str, Any]],
               event: Optional[Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
    """``(label, request fields)`` of the main call: invoke for a command plugin, event for a subscriber."""
    if manifest.kind == "subscriber":
        return "event", {"op": "event", "event": event if event is not None else _synthetic_event()}
    sample = input_doc if input_doc is not None else manifest.example_input
    return "invoke", {"op": "invoke", "point": manifest.points[0], "input": dict(sample or {})}


def _judged(call: Optional[_Call], timeout: int, stopped_text: str) -> Tuple[str, str]:
    """``(status, observed)`` of a call whose answer must be a valid ok or skipped response."""
    if call is None:
        return "skip", stopped_text
    document, problem = _answer(call, timeout)
    if document is None:
        return "fail", problem or "no answer"
    if document["status"] == "error":
        return "fail", f"the plugin answered an error: {safe_text(document['error']['code'])}"
    return "ok", f"answered {document['status']} in {call.result.duration_ms} ms"


# --- scenarios -----------------------------------------------------------------------------------------------


def _protocol_unsupported(call: Optional[_Call], timeout: int) -> Tuple[str, str]:
    if call is None:
        return "skip", "not run: an earlier call timed out"
    result = call.result
    # Any exit status is fine here; only the answer counts.
    problem = None if result.code == "PROCESS_EXIT" and result.document is not None else _failure_text(call, timeout)
    if problem:
        return "fail", f"protocol {UNSUPPORTED_PROTOCOL}: {problem}"
    document = result.document
    assert document is not None
    error = document.get("error")
    code = error.get("code") if isinstance(error, dict) else None
    if document.get("status") == "error" and code == "PROTOCOL_UNSUPPORTED":
        return "ok", f"protocol {UNSUPPORTED_PROTOCOL} refused with PROTOCOL_UNSUPPORTED"
    return "fail", (f"protocol {UNSUPPORTED_PROTOCOL} was not refused: status {safe_text(document.get('status'))}"
                    f"{', code ' + safe_text(code) if code else ''}")


def _stdout_discipline(calls: Sequence[_Call]) -> Tuple[str, str]:
    answered = [call for call in calls if not call.result.timed_out]  # a call that was cut off said nothing
    if not answered:
        return "skip", "no call finished"
    for call in answered:
        result = call.result
        if result.code in _STDOUT_CODES or (result.code is None and result.document is None):
            return "fail", f"{call.label}: stdout is not exactly one JSON object"
    return "ok", f"stdout was exactly one JSON object in all {len(answered)} call(s)"


def _deadline(calls: Sequence[_Call], timeout: int) -> Tuple[str, str]:
    if not calls:
        return "skip", "no call was made"
    for call in calls:
        if call.result.timed_out:
            return "fail", f"{call.label}: not finished within {timeout} s"
    slowest = max(call.result.duration_ms for call in calls)
    return "ok", f"all {len(calls)} call(s) finished within {timeout} s (slowest {slowest} ms)"


def _crash(calls: Sequence[_Call]) -> Tuple[str, str, List[str]]:
    """``(status, observed, evidence)``: did the plugin die while it handled the request or the event?

    The host treats a dead process as a failed attempt: the event is not delivered, the cursor of the subscription
    stays and the event comes again (``aicore.ext.delivery``). A plugin that exits instead of answering with
    ``status: error`` therefore costs the host a retry; the exit code or the signal is the evidence.
    """
    handled = [call for call in calls if call.label in ("invoke", "event", "redelivery")]
    if not handled:
        return "skip", "no request was handled", []
    for call in handled:
        result = call.result
        if result.code != "PROCESS_EXIT" or result.exit is None:
            continue
        if result.exit < 0:
            try:
                name = signal.Signals(-result.exit).name
            except ValueError:
                name = str(-result.exit)
            return "fail", f"{call.label}: the plugin was killed by signal {name}", [f"call={call.label}", f"signal={name}"]
        return "fail", f"{call.label}: the plugin exited with code {result.exit}", [f"call={call.label}",
                                                                                   f"exit_code={result.exit}"]
    return "ok", f"the plugin survived {len(handled)} request(s)", []


def _leaks(value: object, sentinel: str) -> bool:
    return any(sentinel in json.dumps(value, ensure_ascii=ascii_only) for ascii_only in (True, False))


def _secrets_check(manifest: Manifest, source_env: Mapping[str, str], timeout: int,
                   input_doc: Optional[Mapping[str, Any]]) -> Tuple[str, str]:
    refs = [ref for ref in ((manifest.permissions or {}).get("secrets") or []) if isinstance(ref, str)]
    if not refs:
        return "skip", "the manifest declares no permissions.secrets"
    sentinel = "conformance-sentinel-" + uuid.uuid4().hex
    env = dict(source_env)
    try:
        for ref in refs:
            scheme, name = _secrets.split_ref(ref)
            if scheme == "env":
                env[name] = sentinel  # the real value is never used or read
        runner = _Runner(manifest, env, timeout, trusted=True)
    except ExtError as exc:
        return "fail", f"{exc.code}: {safe_text(exc.message)}"
    except ConfigError as exc:
        return "fail", f"a declared secret reference is not usable ({exc.code})"
    label, fields = _operation(manifest, input_doc, None)
    unreadable = False
    for name, request in (("describe", {"op": "describe"}), (label, fields)):
        call = runner.call(name, request)
        if call is None or call.result.document is None:
            unreadable = True
        elif _leaks(call.result.document, sentinel):
            return "fail", f"the secret value was written to stdout by {name}"
    if unreadable:
        return "skip", "stdout could not be read, so the secret was not checked"
    return "ok", "the secret value did not reach stdout in 2 trusted call(s)"


def _supervised(manifest_path: str, source_env: Mapping[str, str], timeout: int,
                input_doc: Optional[Mapping[str, Any]]) -> Tuple[str, str]:
    if not sys.platform.startswith("linux"):
        return "skip", "needs Linux (PR_SET_CHILD_SUBREAPER)"
    payload = {"manifest": manifest_path, "timeout": timeout, "input": input_doc}
    result = run_json([sys.executable, "-m", "aicore.ext.conformance", "--supervise"], payload,
                      deadline_s=2 * (timeout + 2 * GRACE_S + 1) + 10, env=dict(source_env), cwd=str(_LIB_ROOT))
    document = result.document
    if not result.ok or not isinstance(document, dict) or document.get("status") not in ("ok", "fail", "skip") \
            or not isinstance(document.get("observed"), str):
        return "fail", f"the supervisor process failed ({result.code or 'no answer'})"
    return document["status"], document["observed"]


def run_conformance(manifest_path: PathLike, *, input_doc: Optional[Mapping[str, Any]] = None,
                    env: Optional[Mapping[str, str]] = None) -> List[Dict[str, Any]]:
    """Run every scenario against the plugin of ``manifest_path``; one ``check-result/v1`` document each.

    ``input_doc`` is the input of the invoke call (default: ``example_input`` of the manifest, else ``{}``).
    ``env`` is the environment the host would pass on (default: the process environment). Starts the plugin
    several times; never raises for what a plugin does.
    """
    source_env = dict(os.environ if env is None else env)
    path = os.path.abspath(manifest_path)
    try:
        manifest = load_manifest(path)
    except ExtError as exc:
        results = [_result("manifest", "fail", f"{exc.code}: {exc.message}")]
        return results + [_result(name, "skip", "the manifest check failed") for name in SCENARIOS[1:]]
    timeout = manifest.timeout_seconds or DEFAULT_TIMEOUT_S
    found: Dict[str, Tuple[Any, ...]] = {
        "manifest": ("ok", f"{manifest.kind} plugin {manifest.id} {manifest.version}, protocol "
                           f"{manifest.protocol[0]}-{manifest.protocol[1]}")}
    stopped = "not run: an earlier call timed out"
    runner = _Runner(manifest, source_env, timeout)

    call = runner.call("describe", {"op": "describe"})
    assert call is not None  # nothing has timed out yet
    problem = _describe_problem(manifest, call, timeout)
    found["describe"] = ("fail", problem) if problem else ("ok", f"the description matches the manifest "
                                                                 f"({call.result.duration_ms} ms)")
    found["protocol-unsupported"] = _protocol_unsupported(
        runner.call("protocol-unsupported", {"op": "describe"}, protocol=UNSUPPORTED_PROTOCOL), timeout)

    event = _synthetic_event() if manifest.kind == "subscriber" else None
    label, fields = _operation(manifest, input_doc, event)
    found["invoke"] = _judged(runner.call(label, fields), timeout, stopped)
    if manifest.kind == "subscriber":
        found["redelivery"] = _judged(runner.call("redelivery", fields, attempt=2), timeout, stopped)
    else:
        found["redelivery"] = ("skip", "applies to subscriber plugins only")
    found["stdout-discipline"] = _stdout_discipline(runner.calls)
    found["deadline"] = _deadline(runner.calls, timeout)
    found["no-descendants"] = ("skip", stopped) if runner.stopped else _supervised(path, source_env, timeout,
                                                                                    input_doc)
    found["secrets"] = _secrets_check(manifest, source_env, timeout, input_doc)
    found["crash"] = _crash(runner.calls)
    if runner.stopped and found["crash"][0] == "ok":
        found["crash"] = ("skip", stopped)
    return [_result(name, *found[name]) for name in SCENARIOS]


# --- the supervisor ------------------------------------------------------------------------------------------


def _children() -> Set[int]:
    """Pids of the live and zombie children of this process, read from ``/proc``."""
    me = os.getpid()
    found: Set[int] = set()
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat", "rb") as handle:
                stat = handle.read().decode("utf-8", "replace")
        except OSError:
            continue  # gone since the listing
        fields = stat.rpartition(")")[2].split()  # state, ppid, ... (the name may hold spaces and parentheses)
        if len(fields) > 1 and fields[1] == str(me):
            found.add(int(entry))
    return found


def _reap() -> Set[int]:
    reaped: Set[int] = set()
    while True:
        try:
            pid, _status = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return reaped
        if pid == 0:
            return reaped
        reaped.add(pid)


def _adopted() -> Set[int]:
    """Every process the plugin left to this subreaper since the last call: reaped if it was over, killed if not."""
    seen: Set[int] = set()
    give_up = time.monotonic() + 2.0
    while True:
        reaped = _reap()
        live = _children()
        seen |= reaped | live
        if not live and not reaped:
            return seen
        for pid in live:
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        if time.monotonic() > give_up:
            return seen
        time.sleep(0.02)


def supervise(payload: Mapping[str, Any], env: Mapping[str, str]) -> Dict[str, str]:
    """The ``no-descendants`` scenario, to be run in a process of its own: ``{"status", "observed"}``."""
    import ctypes
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        adopting = libc.prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) == 0
    except (OSError, AttributeError):
        adopting = False
    if not adopting or not os.path.isdir("/proc"):
        return {"status": "skip", "observed": "this system cannot adopt orphaned processes"}
    manifest = load_manifest(payload["manifest"])
    timeout = int(payload["timeout"])
    runner = _Runner(manifest, env, timeout)
    label, fields = _operation(manifest, payload.get("input"), None)
    left: Set[int] = set()
    for name, request in (("describe", {"op": "describe"}), (label, fields)):
        if runner.call(name, request) is None:
            break
        left |= _adopted()
    if left:
        return {"status": "fail", "observed": f"{len(left)} process(es) outlived the plugin; they were killed"}
    return {"status": "ok", "observed": f"no process outlived the plugin in {len(runner.calls)} call(s)"}


def _supervisor_main(argv: Sequence[str]) -> int:
    if list(argv) != ["--supervise"]:
        print("usage: python3 -m aicore.ext.conformance --supervise  (internal: reads a request on stdin)",
              file=sys.stderr)
        return 2
    try:
        payload = json.load(sys.stdin)
        document = supervise(payload, os.environ)
    except (ValueError, KeyError, TypeError, ExtError) as exc:
        print(f"conformance supervisor: {exc.__class__.__name__}", file=sys.stderr)
        return 1
    sys.stdout.write(json.dumps(document))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_supervisor_main(sys.argv[1:]))
