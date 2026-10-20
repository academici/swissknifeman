"""Test work source of the conductor (protocol 1): a small plan kept in the JSON file ``$FAKE_CS_STATE``.

State: ``order`` (references in plan order), ``items`` (per reference: ``status``, ``title``, ``scenario``,
``options`` layers, ``checks``, ``write_set``, ``route``, ``holder``), ``registered`` (attempt id -> status),
``commits`` and ``calls`` (every request, in order). ``refuse`` names operations to refuse once (``commit``,
``register``, ``release``). The brief is built from the execution-input ``$FAKE_CS_INPUT`` with the item's checks and write set.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(os.environ["AICORE_ROOT"]) / "lib"))
from aicore.state import blobs  # noqa: E402
from aicore.util.digest import canonical_json_bytes, digest_json, sha256_hex, sha256_tagged  # noqa: E402

HERE = Path(__file__).resolve().parent
STATE = Path(os.environ["FAKE_CS_STATE"])


def load():
    return json.loads(STATE.read_text(encoding="utf-8"))


def save(state):
    STATE.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def reply(request_id, status="ok", **fields):
    document = {"$schema": "urn:swissknifeman:aicore:plugin-response:v1", "protocol": "1",
                "request_id": request_id, "status": status}
    document.update(fields)
    sys.stdout.write(json.dumps(document))


def claim(state, given):
    run_id = given["run_id"]
    ref = (given.get("items") or [None])[0]
    if ref is None:
        held = [name for name in state["order"] if state["items"][name].get("holder") == run_id]
        ready = [name for name in state["order"] if state["items"][name]["status"] == "todo"]
        ref = (held or ready or [None])[0]
    if ref is None:
        return {"op": "claim", "status": "none", "message": "no item is ready"}
    item = state["items"][ref]
    lane = [name for name in state["order"] if state["items"][name]["status"] == "todo"] if not given.get("items") else []
    if item.get("holder") not in (None, run_id):
        return {"op": "claim", "status": "blocked", "ref": ref, "reason_code": "ITEM_OWNED", "message": "held"}
    unmet = [dep for dep in item.get("depends_on", [])
             if state["items"][dep]["status"] != "done"
             and not (given.get("batch") and state["items"][dep]["status"] == "in_progress")]
    if unmet:
        return {"op": "claim", "status": "blocked", "ref": ref, "reason_code": "DEPENDENCY_NOT_READY",
                "message": f"{ref} waits for {', '.join(unmet)}"}
    if item["status"] == "todo":
        item["status"] = "in_progress"
    item["holder"] = run_id
    answer = {"op": "claim", "status": "claimed", "ref": ref, "title": item.get("title", ref),
              "scenario": item.get("scenario", "full"), "scenario_source": "item",
              "route": item.get("route", {"class": "implementation", "effort": "high"}),
              "attempt_id": f"att-{run_id}-{ref}", "session": run_id}
    if item.get("options"):
        answer["options"] = item["options"]
    if item.get("depends_on"):
        answer["depends_on"] = item["depends_on"]
    if len(lane) > 1 and lane[0] == ref and state.get("lanes", True):
        answer["lane"] = lane
    return answer


def brief(state, given, project):
    item = state["items"][given["ref"]]
    doc = json.loads(Path(os.environ["FAKE_CS_INPUT"]).read_text(encoding="utf-8"))
    doc["provenance"]["item"] = given["ref"]
    doc["acceptance"]["checks"] = item["checks"]
    doc["scope"]["write_set"] = item.get("write_set", ["out/**"])
    doc["goal"] = item.get("goal", f"Create the output of {given['ref']}.")
    for key in ("review_mode", "review_route", "review_rounds_max"):  # the review of the plan item, as the bridge carries it
        if key in item:
            doc[key] = item[key]
    if "research" in item:  # the research need of the plan item, as the planner bridge carries it
        doc["research"] = item["research"]
    doc.pop("digest", None)
    doc["input_id"] = f"PLAN9.{given['ref']}"
    digest = sha256_hex(canonical_json_bytes(doc))
    doc["digest"] = digest
    doc["input_id"] = f"PLAN9.{given['ref']}@{digest[:12]}"
    reused = blobs.blob_path(sha256_tagged(canonical_json_bytes(doc)), project=project).is_file()
    ref = blobs.put_json(doc, name=f"brief-{given['ref']}", project=project)
    return {"op": "brief", "input_ref": ref, "input_id": doc["input_id"], "digest": digest, "reused": reused,
            "artifact_id": f"brief-{given['ref'].replace('.', '-')}-{digest[:12]}",
            "artifacts_dir": f"plans/T/artifacts/{given['ref']}"}


def register(state, given, project):
    if "register" in state.get("refuse", []):
        state["refuse"].remove("register")
        return {"op": "register", "outcome": "refused", "gate": {"verdict": "none", "checks": {}},
                "reason_code": "REGISTER_TEST_REFUSAL", "message": "refused once by the test"}
    item = state["items"][given["ref"]]
    attempt = given["attempt_id"]
    checks = {}
    for check in item["checks"]:
        if check.get("kind") != "acceptance":
            continue
        path = given["evidence"].get(check["id"])
        if path and (Path(project) / path).is_file():
            checks[check["id"]] = json.loads((Path(project) / path).read_text(encoding="utf-8")).get("exit", 0)
        else:
            checks[check["id"]] = None
    if given["status"] == "blocked":
        verdict = "none"
    elif any(value is None for value in checks.values()):
        return {"op": "register", "outcome": "refused", "gate": {"verdict": "missing", "checks": checks},
                "reason_code": "REGISTER_EVIDENCE_MISSING", "message": "evidence missing"}
    elif any(value != 0 for value in checks.values()):
        return {"op": "register", "outcome": "refused", "gate": {"verdict": "red", "checks": checks},
                "reason_code": "REGISTER_EVIDENCE_RED", "message": "evidence red"}
    else:
        verdict = "pass"
    if state["registered"].get(attempt) == given["status"]:
        return {"op": "register", "outcome": "no-op", "gate": {"verdict": verdict, "checks": checks}}
    state["registered"][attempt] = given["status"]
    item["status"] = given["status"]
    item["report"] = given["report"]
    item["executed_by"] = given["executed_by"]
    return {"op": "register", "outcome": "recorded", "gate": {"verdict": verdict, "checks": checks}}


def commit(state, given, project):
    if "commit" in state.get("refuse", []):
        state["refuse"].remove("commit")
        return {"op": "commit", "outcome": "refused", "reason_code": "COMMIT_TEST_REFUSAL", "message": "once"}
    git = ["git", "-C", project]
    subprocess.run(git + ["add", "-A"], check=True, capture_output=True)
    if subprocess.run(git + ["diff", "--cached", "--quiet"]).returncode == 0:
        return {"op": "commit", "outcome": "no-op", "message": "nothing to commit"}
    subprocess.run(git + ["commit", "-q", "-m", f"feat: {given['ref']}"], check=True, capture_output=True)
    sha = subprocess.run(git + ["rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    state["commits"].append({"ref": given["ref"], "sha": sha, "paths": given["paths"]})
    return {"op": "commit", "outcome": "committed", "sha": sha}


def release(state, given):
    if "release" in state.get("refuse", []):
        state["refuse"].remove("release")
        return {"op": "release", "outcome": "refused", "reason_code": "RELEASE_TEST_REFUSAL", "message": "once"}
    item = state["items"][given["ref"]]
    if item.get("holder") != given["run_id"] or item["status"] != "in_progress":
        return {"op": "release", "outcome": "no-op", "message": "not held by this run"}
    item["status"], item["holder"] = "todo", None
    return {"op": "release", "outcome": "released"}


def note(state, given):
    if "note" in state.get("refuse", []):
        state["refuse"].remove("note")
        return {"op": "note", "outcome": "refused", "reason_code": "NOTE_TEST_REFUSAL", "message": "once"}
    state.setdefault("notes", []).append({"collection": given["collection"], "text": given["text"], "refs": given["refs"]})
    return {"op": "note", "outcome": "recorded"}


def research(state, given, project):
    """Keeps the result where the planner bridge does: ``plans/<plan>/research/<ref>-<n>.json``."""
    if "research" in state.get("refuse", []):
        state["refuse"].remove("research")
        return {"op": "research", "outcome": "refused", "reason_code": "RESEARCH_TEST_REFUSAL", "message": "once"}
    relative = f"plans/{given['plan']}/research/{given['ref']}-{given['number']}.json"
    target = Path(project) / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(given["result"], indent=2) + "\n", encoding="utf-8")
    state.setdefault("research", []).append({"ref": given["ref"], "number": given["number"], "path": relative})
    return {"op": "research", "outcome": "recorded", "path": relative}


manifest = json.loads((HERE / "extension.json").read_text(encoding="utf-8"))
request = json.load(sys.stdin)
request_id = request.get("request_id", "0" * 32)
if request.get("op") == "describe":
    reply(request_id, output={
        "$schema": "urn:swissknifeman:aicore:plugin-describe:v1", "protocol": "1", "id": manifest["id"],
        "kind": manifest["kind"], "version": manifest["version"],
        "capabilities_digest": digest_json(manifest["provides"]), "transport": "stdio-json"})
elif request.get("op") == "invoke":
    given = request["input"]
    project = request["context"]["project_root"]
    state = load()
    state.setdefault("calls", []).append(given)
    handlers = {"claim": lambda: claim(state, given), "brief": lambda: brief(state, given, project),
                "register": lambda: register(state, given, project), "commit": lambda: commit(state, given, project),
                "release": lambda: release(state, given), "note": lambda: note(state, given),
                "research": lambda: research(state, given, project)}
    answer = handlers[given["op"]]()
    save(state)
    reply(request_id, output=answer)
else:
    reply(request_id, "error", error={"code": "OP_UNSUPPORTED", "message": "unknown op"})
