#!/usr/bin/env python3
"""The planner as a work source of orch: the plugin of the extension point ``orch:work-source`` (protocol 1).

orch starts this file through ``aicore.ext.plugins`` with one request on stdin (``op: describe`` or ``op: invoke``)
and reads one ``plugin-response/v1`` document from stdout. ``invoke`` carries a ``work-source/v1`` input:

- ``claim`` takes the first of ``items`` (or the next ready item of the plan; an item this run holds or already
  closed comes first), checks its scenario against the run-policy packs of orch (``orch.py policy show``) and starts it with
  ``plan.py start --session <run_id>``; ``ITEM_OWNED`` is a refusal, never a take-over;
- ``brief`` builds the execution-input in process (``brief.build``, read-only), stores it as a content-addressed
  blob of the plan's repository and declares it with ``plan.py add-artifact`` (a repeat changes nothing);
- ``register`` runs ``register.py`` with owner fencing (``--owner-session <run_id>``) and the evidence gate.

Refusals are answers (``status: ok`` with a ``reason_code``); only a broken request or a missing partner is a
protocol error. The plan is written only through ``plan.py``. stdlib and aicore only.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import partners

POINT = "orch:work-source"
RESPONSE = "urn:swissknifeman:aicore:plugin-response:v1"
DESCRIBE = "urn:swissknifeman:aicore:plugin-describe:v1"
OPS = ("claim", "brief", "register")
_CODE = re.compile(r"^([A-Z][A-Z0-9_]{1,63}): ?(.*)$")
_PLANNER_ATTEMPT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$", re.ASCII)  # planner defs.attemptId


class Blocked(Exception):
    """A refusal of the source or of a partner: ``code`` goes into ``reason_code`` of the answer."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def actor_text(actor: dict) -> str:
    return "/".join(part for part in (actor["provider"], actor["model"], actor.get("effort")) if part)


def refusal_of(text: str, fallback: str) -> Blocked:
    """The ``CODE: message`` line of a refusal (the last one of the text), else ``fallback``."""
    for line in reversed((text or "").strip().splitlines()):
        found = _CODE.match(line.strip())
        if found:
            return Blocked(found.group(1), found.group(2).strip() or found.group(1))
    return Blocked(fallback, (text or "").strip() or fallback)


# ------------------------------------------------------------------------------------------------ partners


def plan_py(argv: list, plans_root=None) -> subprocess.CompletedProcess:
    tail = ["--plans-root", str(plans_root)] if plans_root else []
    return subprocess.run([*partners.require_plan_argv(), *argv, *tail], capture_output=True, text=True,
                          encoding="utf-8", check=False)


def plan_json(argv: list, plans_root=None, *, code: str = "PLAN_UNREADABLE"):
    """JSON stdout of a ``plan.py`` verb; a refusal raises :class:`Blocked` with the planner's code."""
    done = plan_py(argv, plans_root)
    if done.returncode:
        raise refusal_of(done.stderr or done.stdout, code)
    try:
        return json.loads(done.stdout)
    except ValueError:
        raise Blocked(code, f"plan.py {argv[0]} printed no JSON") from None


def item_doc(plan: str, ref: str, plans_root=None) -> dict:
    return plan_json(["--output", "json", "get", plan, ref], plans_root)["data"]["doc"]


def policy_exists(scenario: str, config: str | None = None) -> Blocked | None:
    """``orch.py [--config FILE] policy show <scenario>``: None when the pack exists, else ``SCENARIO_UNKNOWN``.
    ``config`` is the invocation configuration of the orch command that asked (its ``profiles.dirs`` count)."""
    root = partners.require_orch()
    head = ["--config", config] if config else []
    done = subprocess.run([sys.executable, str(root / "scripts" / "orch.py"), *head, "policy", "show", scenario],
                          capture_output=True, text=True, encoding="utf-8", check=False)
    if done.returncode == 0:
        return None
    reason = refusal_of(done.stderr, "POLICY_UNKNOWN")
    return Blocked("SCENARIO_UNKNOWN", f"scenario {scenario!r} has no run-policy pack in orch ({reason.code}: "
                                       f"{reason.message})")


# ------------------------------------------------------------------------------------------------ claim


def _held_by(plan: str, run_id: str, plans_root) -> str | None:
    """The item this run holds or already closed: executor session ``run_id`` while in progress, or the recorded
    attempt ``att-<run_id>-<item>`` after its registration (the session is gone from a finished item)."""
    store = partners.planner_engine("plan.store")
    loaded = store.load_plan(store.resolve_plan_dir(plan, Path(plans_root) if plans_root else None))
    for item_id, doc in loaded.items.items():
        result = doc.get("result") if isinstance(doc.get("result"), dict) else {}
        executor = result.get("executor") if isinstance(result.get("executor"), dict) else {}
        if (doc.get("status") == "in_progress" and executor.get("session") == run_id) \
                or result.get("attempt_id") == f"att-{run_id}-{item_id}":
            return item_id
    return None


def _candidate(plan: str, run_id: str, plans_root) -> tuple:
    """``(ref, None)`` of the item to claim, or ``(None, message)`` when nothing is ready."""
    held = _held_by(plan, run_id, plans_root)  # a repeated claim of the same run answers for its own item
    if held:
        return held, None
    ready = plan_json(["next", plan, "--parallel", "1", "--json"], plans_root)
    for lane in ready.get("lanes", []):
        if lane.get("kind") == "run-items" and lane.get("items"):
            return lane["items"][0], None
    upcoming = ready.get("next") or {}
    return None, upcoming.get("reason") or upcoming.get("exact") or "no item is ready"


def op_claim(fields: dict) -> dict:
    plan, plans_root, run_id = fields["plan"], fields.get("plans_root"), fields["run_id"]
    items = fields.get("items") or []
    ref, message = (items[0], None) if items else _candidate(plan, run_id, plans_root)
    if ref is None:
        return {"op": "claim", "status": "none", "message": message}
    answer = {"op": "claim", "ref": ref}
    attempt_id = f"att-{run_id}-{ref}"
    try:
        if not _PLANNER_ATTEMPT.fullmatch(attempt_id):  # checked before start: a claim the planner cannot close
            raise Blocked("ATTEMPT_ID_INVALID", f"attempt id {attempt_id!r} does not fit the planner "
                                                f"({_PLANNER_ATTEMPT.pattern}); use a shorter run id")
        doc = item_doc(plan, ref, plans_root)
        answer["title"] = doc["title"]
        if isinstance(doc.get("route"), dict):
            answer["route"] = {key: doc["route"][key] for key in ("class", "effort") if key in doc["route"]}
        orchestration = plan_json(["context", plan, ref, "--stdout"], plans_root).get("orchestration") or {}
        answer["scenario"] = orchestration.get("scenario")
        answer["scenario_source"] = orchestration.get("scenario_source")
        refused = policy_exists(answer["scenario"], fields.get("orch_config")) if answer["scenario"] else \
            Blocked("SCENARIO_UNKNOWN", f"{ref} resolves no scenario")
        if refused:
            raise refused
        # An item this very attempt already closed stays claimed by the run: its claim is answered again, unchanged.
        if (doc.get("result") or {}).get("attempt_id") != attempt_id:
            plan_json(["start", plan, ref, "--actor", actor_text(fields["actor"]), "--session", run_id,
                       "--no-scout", "--json"], plans_root, code="START_REFUSED")
    except Blocked as blocked:
        answer.update(status="blocked", reason_code=blocked.code, message=blocked.message)
        return {key: value for key, value in answer.items() if value is not None}
    answer.update(status="claimed", attempt_id=attempt_id, session=run_id)
    return {key: value for key, value in answer.items() if value is not None}


# ------------------------------------------------------------------------------------------------ brief


def artifact_id(ref: str, digest: str) -> str:
    return "brief-" + ref.replace(".", "-").replace("/", "-") + "-" + digest[:12]


def _worker_view(doc: dict) -> dict:
    """What the worker reads: the brief without its digests. ``provenance.source_digest`` hashes the whole context
    pack, which changes when the brief itself is declared as an input of the item, so it does not decide a repeat."""
    view = {key: value for key, value in doc.items() if key != "digest"}
    view["input_id"] = str(view.get("input_id", "")).rsplit("@", 1)[0]
    view["provenance"] = {key: value for key, value in (doc.get("provenance") or {}).items() if key != "source_digest"}
    return view


def _previous_brief(plan, item_id: str, unit: str | None, project: Path, blobs):
    """The newest brief of the item (or of its unit) already declared as an input of the item, or None."""
    item = plan.items.get(item_id) or {}
    store = blobs.blob_path("sha256:" + "0" * 64, project=project).parent.resolve()
    for entry in reversed(item.get("artifacts") or []):
        if not isinstance(entry, dict) or entry.get("role") != "input" or not isinstance(entry.get("path"), str):
            continue
        path = (Path(project) / entry["path"]).resolve()
        if path.parent != store:
            continue
        try:
            doc = json.loads(blobs.read_bytes("sha256:" + path.name, project=project))
        except (OSError, ValueError):
            continue
        provenance = doc.get("provenance") if isinstance(doc, dict) else None
        if isinstance(provenance, dict) and doc.get("$schema") == "urn:swissknifeman:orch:exec:execution-input:v1" \
                and provenance.get("item") == item_id and provenance.get("unit") == unit:
            return doc
    return None


def op_brief(fields: dict) -> dict:
    import brief  # the planner engine is located and imported only when a brief is built
    from aicore.state import blobs
    from aicore.util.digest import canonical_json_bytes, sha256_tagged

    plan_ref, plans_root, ref = fields["plan"], fields.get("plans_root"), fields["ref"]
    if fields.get("unit"):
        ref = f"{ref.split('/', 1)[0]}/{fields['unit']}"
    item, _, unit = ref.partition("/")
    try:
        plan = brief.store.load_plan(brief.store.resolve_plan_dir(plan_ref, Path(plans_root) if plans_root else None))
        doc = brief.build(plan, item, unit_id=unit or None)
    except brief.PlanError as error:
        raise Blocked(error.code, error.message) from None
    project = plan.repo_root
    previous = _previous_brief(plan, item, unit or None, project, blobs)
    if previous is not None and _worker_view(previous) == _worker_view(doc):
        doc = previous  # unchanged inputs: the stored brief and its digest stay the brief of this item
    reused = blobs.blob_path(sha256_tagged(canonical_json_bytes(doc)), project=project).is_file()
    stored = blobs.put_json(doc, sensitivity="normal", name=f"brief-{ref}", project=project)
    path = blobs.blob_path(stored, project=project)
    relative = path.resolve().relative_to(Path(project).resolve()).as_posix()
    # The brief is an input of the item; a planner artifact id names an output, so the input is declared by path
    # (content-addressed, unique per digest) and the id is returned to orch only.
    plan_json(["--output", "json", "add-artifact", plan_ref, item, "--path", relative, "--role", "input"], plans_root,
              code="ARTIFACT_REFUSED")
    return {"op": "brief", "input_ref": stored, "input_id": doc["input_id"], "digest": doc["digest"],
            "reused": reused, "artifact_id": artifact_id(ref, doc["digest"])}


# ------------------------------------------------------------------------------------------------ register


def op_register(fields: dict) -> dict:
    run_id = fields["run_id"]
    with tempfile.TemporaryDirectory(prefix="planner-orch-register-") as tmp:
        report = Path(tmp) / "report.json"
        report.write_text(json.dumps(fields["report"], ensure_ascii=False), encoding="utf-8")
        argv = [sys.executable, str(partners.BRIDGE / "register.py"), fields["plan"], fields["ref"],
                "--report", str(report), "--status", fields["status"], "--actor", actor_text(fields["registrar"]),
                "--executed-by", actor_text(fields["executed_by"]), "--attempt-id", fields["attempt_id"],
                "--owner-session", run_id, "--gate", "evidence"]
        for check_id, path in sorted(fields.get("evidence", {}).items()):
            argv += ["--evidence", f"{check_id}={path}"]
        if fields.get("plans_root"):
            argv += ["--plans-root", str(fields["plans_root"])]
        done = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", check=False)
    if done.returncode not in (0, 1):
        raise refusal_of(done.stderr, "REGISTER_FAILED")
    try:
        receipt = json.loads(done.stdout) if done.stdout.strip() else None
    except ValueError:
        receipt = None
    gate = (receipt or {}).get("gate") or {"verdict": "none", "checks": {}}
    answer = {"op": "register", "gate": gate}
    if receipt is not None:
        answer["receipt"] = receipt
    if done.returncode == 0:
        calls = (receipt or {}).get("calls", [])
        answer["outcome"] = "recorded" if any(call.get("result") == "recorded" for call in calls) else "no-op"
        return answer
    refused = [call for call in (receipt or {}).get("calls", []) if call.get("result") == "refused"]
    if gate.get("verdict") == "stale":  # fenced by the guard, or by finish under the plan lock
        blocked = refusal_of(done.stderr, "REGISTER_STALE_OWNER")
    else:
        blocked = refusal_of(refused[-1].get("error", "") if refused else done.stderr, "REGISTER_REFUSED")
    answer.update(outcome="refused", reason_code=blocked.code, message=blocked.message)
    return answer


# ------------------------------------------------------------------------------------------------ protocol


def reply(request_id: str, status: str = "ok", **fields) -> None:
    document = {"$schema": RESPONSE, "protocol": "1", "request_id": request_id, "status": status}
    document.update(fields)
    sys.stdout.write(json.dumps(document, ensure_ascii=False))


def describe(request_id: str) -> None:
    from aicore.util.digest import digest_json
    manifest = json.loads((partners.BRIDGE / "extension.json").read_text(encoding="utf-8"))
    reply(request_id, output={"$schema": DESCRIBE, "protocol": "1", "id": manifest["id"], "kind": manifest["kind"],
                              "version": manifest["version"], "capabilities_digest": digest_json(manifest["provides"]),
                              "transport": "stdio-json"})


def invoke(request_id: str, request: dict) -> None:
    fields = request.get("input")
    if request.get("point") != POINT or not isinstance(fields, dict) or fields.get("op") not in OPS:
        reply(request_id, "error", error={"code": "INPUT_INVALID",
                                          "message": f"expected point {POINT} with op {' | '.join(OPS)}"})
        return
    handler = {"claim": op_claim, "brief": op_brief, "register": op_register}[fields["op"]]
    try:
        output = handler(fields)
    except Blocked as blocked:
        if fields["op"] == "brief":  # a brief has no refusal shape: the source cannot brief this item
            reply(request_id, "error", error={"code": blocked.code, "message": blocked.message})
            return
        raise
    reply(request_id, output=output)


def main() -> int:
    try:
        request = json.load(sys.stdin)
    except ValueError:
        reply("0" * 32, "error", error={"code": "REQUEST_INVALID", "message": "the request is not JSON"})
        return 0
    request_id = request.get("request_id") if isinstance(request, dict) else None
    request_id = request_id if isinstance(request_id, str) and request_id else "0" * 32
    if request.get("protocol") != "1":
        reply(request_id, "error", error={"code": "PROTOCOL_UNSUPPORTED", "message": "this plugin speaks protocol 1"})
        return 0
    try:
        partners.use_aicore()
        if request.get("op") == "describe":
            describe(request_id)
        elif request.get("op") == "invoke":
            invoke(request_id, request)
        else:
            reply(request_id, "error", error={"code": "OP_UNSUPPORTED", "message": "op is describe or invoke"})
    except SystemExit as stop:  # a partner was not found: partners printed CODE: message on stderr
        code = {2: "AICORE_NOT_FOUND", 3: "BRIDGE_PARTNER_UNAVAILABLE"}.get(stop.code, "PLUGIN_FAILED")
        reply(request_id, "error", error={"code": code, "message": f"{code}: see the plugin's stderr"})
    except Blocked as blocked:
        reply(request_id, "error", error={"code": blocked.code, "message": blocked.message})
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main())
