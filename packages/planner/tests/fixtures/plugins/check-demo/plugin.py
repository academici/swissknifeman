"""Demo plugin for the planner:check extension point (protocol 1, stdio-json).

``CHECK_DEMO_MODE`` selects the answer of ``invoke``: ``issues`` (default: one error and one warning), ``clean``,
``skipped``, ``error`` (a protocol error), ``exit`` (a non-zero exit), ``invalid`` (an output outside the
contract), ``many`` (501 issues). Every start and request is appended to ``$CHECK_DEMO_MARKS/calls.jsonl``.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(os.environ["AICORE_ROOT"]) / "lib"))
from aicore.util.digest import digest_json  # noqa: E402

HERE = Path(__file__).resolve().parent
MODE = os.environ.get("CHECK_DEMO_MODE", "issues")


def mark(entry):
    directory = os.environ.get("CHECK_DEMO_MARKS")
    if directory:
        Path(directory).mkdir(parents=True, exist_ok=True)
        with open(Path(directory) / "calls.jsonl", "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")


def reply(request_id, status="ok", **fields):
    document = {"$schema": "urn:swissknifeman:aicore:plugin-response:v1", "protocol": "1",
                "request_id": request_id, "status": status}
    document.update(fields)
    sys.stdout.write(json.dumps(document))


def issues(plan_id):
    if MODE == "clean":
        return []
    if MODE == "invalid":
        return [{"severity": "fatal", "code": "bad code", "message": ""}]
    if MODE == "many":
        return [{"severity": "warning", "code": "DEMO_MANY", "message": f"finding {n}"} for n in range(501)]
    return [{"severity": "error", "code": "DEMO_ERROR", "message": f"the demo check rejects {plan_id}",
             "ref": "P1.1"},
            {"severity": "warning", "code": "DEMO_WARNING", "message": "the demo check has a remark",
             "path": "plan.json"}]


mark({"op": "start"})
manifest = json.loads((HERE / "extension.json").read_text(encoding="utf-8"))
request = json.load(sys.stdin)
request_id = request.get("request_id", "0" * 32)
if request.get("protocol") != "1":
    reply(request_id, "error", error={"code": "PROTOCOL_UNSUPPORTED", "message": "protocol 1 only"})
elif request.get("op") == "describe":
    mark({"op": "describe"})
    reply(request_id, output={
        "$schema": "urn:swissknifeman:aicore:plugin-describe:v1", "protocol": "1", "id": manifest["id"],
        "kind": manifest["kind"], "version": manifest["version"],
        "capabilities_digest": digest_json(manifest["provides"]), "transport": "stdio-json"})
elif request.get("op") == "invoke":
    given = request["input"]
    mark({"op": "invoke", "point": request.get("point"), "plan_id": given.get("plan_id"),
          "keys": sorted(given)})
    if MODE == "exit":
        sys.stderr.write("the demo plugin stops\n")
        sys.exit(3)
    if MODE == "skipped":
        reply(request_id, "skipped")
    elif MODE == "error":
        reply(request_id, "error", error={"code": "DEMO_CRASH", "message": "the demo plugin failed"})
    else:
        reply(request_id, output={"issues": issues(given.get("plan_id"))})
else:
    reply(request_id, "error", error={"code": "OP_UNSUPPORTED", "message": "unknown op"})
