"""Shared body of the plugin fixtures: speak protocol 1 and leave marks of what was started and asked.

Marks are lines of ``calls.jsonl`` in ``$FIXTURE_MARKS`` when it is set; the ``bad-*`` plugins (``local_marks``)
fall back to ``marks/`` next to the plugin, so that a test can prove they were never started. One
``{"op": "start"}`` line is written for each start, then one line per request. A plugin that was never started
leaves no file. Nothing is written when neither place applies (for example when a fixture runs in place).
"""
import json
import os
import sys
from pathlib import Path

# The cleaned environment of a plugin has no PYTHONPATH; AICORE_ROOT does pass. Run in place, find the package here.
_root = os.environ.get("AICORE_ROOT") or str(Path(__file__).resolve().parents[4])
sys.path.insert(0, str(Path(_root) / "lib"))
from aicore.util.digest import digest_json  # noqa: E402

SCHEMA = "urn:swissknifeman:aicore:plugin-response:v1"
DESCRIBE_SCHEMA = "urn:swissknifeman:aicore:plugin-describe:v1"


def mark(here, entry, local_marks=False):
    directory = os.environ.get("FIXTURE_MARKS") or (Path(here) / "marks" if local_marks else None)
    if not directory:
        return
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with open(directory / "calls.jsonl", "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def reply(request_id, status="ok", **fields):
    document = {"$schema": SCHEMA, "protocol": "1", "request_id": request_id, "status": status}
    document.update(fields)
    sys.stdout.write(json.dumps(document))


def serve(here, *, describe_patch=None, invoke=None, event=None, local_marks=False, strict_protocol=True):
    """Answer the one request on stdin. ``invoke(request) -> output dict``; ``event(request) -> status``.

    ``strict_protocol=False`` answers any protocol number as if it were 1 (a plugin that skips the check)."""
    here = Path(here)
    marked = lambda entry: mark(here, entry, local_marks)  # noqa: E731
    marked({"op": "start"})
    manifest = json.loads((here / "extension.json").read_text(encoding="utf-8"))
    request = json.load(sys.stdin)
    request_id = request.get("request_id", "0" * 32)
    if strict_protocol and request.get("protocol") != "1":
        reply(request_id, "error", error={"code": "PROTOCOL_UNSUPPORTED", "message": "protocol 1 only"})
        return
    op = request.get("op")
    if op == "describe":
        marked({"op": "describe"})
        output = {"$schema": DESCRIBE_SCHEMA, "protocol": "1", "id": manifest["id"], "kind": manifest["kind"],
                  "version": manifest["version"], "capabilities_digest": digest_json(manifest["provides"]),
                  "transport": "stdio-json"}
        output.update(describe_patch or {})
        reply(request_id, output=output)
    elif op == "invoke":
        marked({"op": "invoke", "point": request.get("point"), "context": request.get("context")})
        reply(request_id, output=(invoke or (lambda req: req["input"]))(request))
    elif op == "event":
        marked({"op": "event", "id": request["event"]["id"], "type": request["event"]["type"],
                "attempt": request["context"]["attempt"]})
        reply(request_id, (event or (lambda req: "ok"))(request))
    else:
        reply(request_id, "error", error={"code": "OP_UNSUPPORTED", "message": f"unknown op {op}"})
