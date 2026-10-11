"""Test plugin of orch:work-source (protocol 1): canned answers, the request echoed in the register receipt.

``FAKE_WS_MODE``: ``ok`` (default), ``blocked`` (a claim refused with ITEM_OWNED), ``invalid`` (answers outside the
contract), ``refuse`` (a register refused by the evidence gate), ``crash`` (exit 3). ``FAKE_WS_INPUT`` names the
execution-input stored by ``brief``; every invoke input is appended to ``$FAKE_WS_MARKS`` (JSON lines) when set.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(os.environ["AICORE_ROOT"]) / "lib"))
from aicore.state import blobs  # noqa: E402
from aicore.util.digest import canonical_json_bytes, digest_json, sha256_tagged  # noqa: E402

HERE = Path(__file__).resolve().parent
MODE = os.environ.get("FAKE_WS_MODE", "ok")


def reply(request_id, status="ok", **fields):
    document = {"$schema": "urn:swissknifeman:aicore:plugin-response:v1", "protocol": "1",
                "request_id": request_id, "status": status}
    document.update(fields)
    sys.stdout.write(json.dumps(document))


def claim(given):
    if MODE == "invalid":
        return {"op": "claim", "status": "taken"}
    if MODE == "blocked":
        return {"op": "claim", "status": "blocked", "ref": "W1", "reason_code": "ITEM_OWNED", "message": "held"}
    ref = (given.get("items") or ["W1"])[0]
    return {"op": "claim", "status": "claimed", "ref": ref, "title": "Work", "scenario": "solo",
            "scenario_source": "item", "route": {"class": "implementation", "effort": "high"},
            "attempt_id": "att-" + given["run_id"] + "-" + ref, "session": given["run_id"]}


def brief(given, project):
    doc = json.loads(Path(os.environ["FAKE_WS_INPUT"]).read_text(encoding="utf-8"))
    reused = blobs.blob_path(sha256_tagged(canonical_json_bytes(doc)), project=project).is_file()
    ref = blobs.put_json(doc, name="brief-W1", project=project)
    return {"op": "brief", "input_ref": ref, "input_id": doc["input_id"], "digest": doc["digest"],
            "reused": reused, "artifact_id": "brief-W1-" + doc["digest"][:12]}


def register(given):
    if MODE == "refuse":
        return {"op": "register", "outcome": "refused", "gate": {"verdict": "missing", "checks": {"V1": None}},
                "reason_code": "REGISTER_EVIDENCE_MISSING", "message": "no evidence"}
    checks = {check_id: 0 for check_id in given["evidence"]}
    return {"op": "register", "outcome": "recorded", "gate": {"verdict": "pass", "checks": checks},
            "receipt": {"input": given}}


manifest = json.loads((HERE / "extension.json").read_text(encoding="utf-8"))
request = json.load(sys.stdin)
request_id = request.get("request_id", "0" * 32)
if request.get("op") == "describe":
    reply(request_id, output={
        "$schema": "urn:swissknifeman:aicore:plugin-describe:v1", "protocol": "1", "id": manifest["id"],
        "kind": manifest["kind"], "version": manifest["version"],
        "capabilities_digest": digest_json(manifest["provides"]), "transport": "stdio-json"})
elif request.get("op") == "invoke":
    if MODE == "crash":
        sys.stderr.write("the fake source stops\n")
        sys.exit(3)
    given = request["input"]
    if os.environ.get("FAKE_WS_MARKS"):
        with open(os.environ["FAKE_WS_MARKS"], "a", encoding="utf-8") as handle:
            handle.write(json.dumps(given, sort_keys=True) + "\n")
    project = request["context"]["project_root"]
    answer = {"claim": claim, "register": register}.get(given["op"])
    reply(request_id, output=answer(given) if answer else brief(given, project))
else:
    reply(request_id, "error", error={"code": "OP_UNSUPPORTED", "message": "unknown op"})
