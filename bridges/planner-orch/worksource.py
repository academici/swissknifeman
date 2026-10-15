#!/usr/bin/env python3
"""The planner as a work source of orch: the plugin of the extension point ``orch:work-source`` (protocol 1).

orch starts this file through ``aicore.ext.plugins`` with one request on stdin (``op: describe`` or ``op: invoke``)
and reads one ``plugin-response/v1`` document from stdout. ``invoke`` carries a ``work-source/v1`` input:

- ``claim`` takes the first of ``items`` (or the next ready item of the plan; an item this run holds or already
  closed comes first), resolves its scenario and run options (``orchestration`` of the item, its phase and the plan,
  and the orchestration overlay documents that apply to them), checks the scenario against the run-policy packs of
  orch (``orch.py policy show``) and starts it with ``plan.py start --session <run_id>``; ``ITEM_OWNED`` is a refusal,
  never a take-over;
- ``brief`` builds the execution-input in process (``brief.build``, read-only), stores it as a content-addressed
  blob of the plan's repository and declares it with ``plan.py add-artifact`` (a repeat changes nothing); the answer
  names the item's artifact folder of the plan;
- ``register`` runs ``register.py`` with owner fencing (``--owner-session <run_id>``) and the evidence gate;
- ``commit`` runs ``plan.py commit <plan> <ref> --role executor --path …`` (nothing to commit is a no-op);
- ``release`` gives back an item this run holds in progress when the run stopped before any work began: the planner has
  no verb that returns an in-progress item to ``todo``, so it is finished as ``blocked`` under owner fencing
  (``--owner-session <run_id>``) and reopened, which clears the executor session (a run that does not hold the item is a no-op);
- ``note`` adds a note to the plan's journal (``plan.py log <plan> <phase|item> --type note``) for work that has no item of
  its own (support work run from a file input); it names a phase or an item in ``refs``, and a note without one is refused;
- ``research`` saves the research-result of a research stage as ``research/<item>-<n>.json`` in the folder of the plan and
  declares it with ``plan.py add-artifact … --role input`` (a repeat of the same result changes nothing); the file is a
  record of the research, not plan state.

An orchestration overlay is a knowledge document with an id starting with ``orchestration-`` and a section
``orchestration`` that holds one JSON object ``{"scenario"?: name, "options"?: run-options}``; it applies to the item,
phase or plan named by its ``applies_to`` (``global`` for the plan). It carries what a plan engine without the
``orchestration.scenario``/``orchestration.options`` fields cannot store; a field of the same level wins over it.

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
OPS = ("claim", "brief", "register", "commit", "release", "note", "research")
OVERLAY_PREFIX = "orchestration-"
OVERLAY_SECTION = "orchestration"
_FENCE = re.compile(r"^\s*`{3,}[A-Za-z0-9_-]*\s*\n(.*?)\n\s*`{3,}\s*$", re.S)
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
    """``(ref, None)`` of the item to claim, or ``(None, message)`` when nothing is ready; ``_LANE`` keeps the whole lane."""
    held = _held_by(plan, run_id, plans_root)  # a repeated claim of the same run answers for its own item
    if held:
        return held, None
    ready = plan_json(["next", plan, "--parallel", "1", "--json"], plans_root)
    for lane in ready.get("lanes", []):
        if lane.get("kind") == "run-items" and lane.get("items"):
            _LANE[:] = list(lane["items"])
            return lane["items"][0], None
    upcoming = ready.get("next") or {}
    return None, upcoming.get("reason") or upcoming.get("exact") or "no item is ready"


def _overlay(document: dict) -> dict | None:
    """``{"scenario"?, "options"?}`` of an orchestration overlay document, None for any other document."""
    if not str(document.get("id", "")).startswith(OVERLAY_PREFIX):
        return None
    section = next((item for item in document.get("sections") or []
                    if isinstance(item, dict) and item.get("id") == OVERLAY_SECTION), None)
    if section is None:
        return None
    text = section.get("text") or ""
    fenced = _FENCE.match(text)
    try:
        found = json.loads(fenced.group(1) if fenced else text)
    except ValueError as error:
        raise Blocked("OVERLAY_INVALID", f"document {document['id']}: section {OVERLAY_SECTION} is not JSON: {error}")
    if not isinstance(found, dict) or set(found) - {"scenario", "options"}:
        raise Blocked("OVERLAY_INVALID", f"document {document['id']}: section {OVERLAY_SECTION} must be an object "
                                         "with only scenario and options")
    if "scenario" in found and not (isinstance(found["scenario"], str) and re.fullmatch(r"[a-z][a-z0-9-]*",
                                                                                         found["scenario"])):
        raise Blocked("OVERLAY_INVALID", f"document {document['id']}: scenario must be a run-policy name")
    if "options" in found and not isinstance(found["options"], dict):
        raise Blocked("OVERLAY_INVALID", f"document {document['id']}: options must be an object")
    return found


def orchestration_of(context: dict, ref: str) -> tuple:
    """``(scenario, scenario_source, layers)`` of an item from its context pack.

    Levels from the most specific: the item, its phase, the plan. At each level the ``orchestration`` field of the
    document wins over the overlays that apply to it. The scenario is the first one found from the item up, else
    the one the planner resolved from its configuration. ``layers`` are the run options, general first.
    """
    item_id = ref.split("/", 1)[0]
    phase_id = item_id.split(".", 1)[0]
    levels = (("item", item_id, context.get("item") or {}), ("phase", phase_id, context.get("phase") or {}),
              ("plan", None, context.get("plan") or {}))
    overlays = {"item": [], "phase": [], "plan": []}
    for document in context.get("documents") or []:
        found = _overlay(document) if isinstance(document, dict) else None
        if found is None:
            continue
        applies = document.get("applies_to") or []
        level = "plan" if document.get("global") else "item" if item_id in applies or ref in applies \
            else "phase" if phase_id in applies else None
        if level:
            overlays[level].append((document["id"], found))
    scenario = source = None
    for level, name, doc in levels:
        field = (doc.get("orchestration") or {}).get("scenario") if isinstance(doc.get("orchestration"), dict) else None
        if field:
            scenario, source = field, level
            break
        named = [(doc_id, found["scenario"]) for doc_id, found in overlays[level] if "scenario" in found]
        if named:
            scenario, source = named[-1][1], f"document:{named[-1][0]}"
            break
    if scenario is None:
        resolved = context.get("orchestration") or {}
        scenario, source = resolved.get("scenario"), resolved.get("scenario_source")
    layers = []
    for level, name, doc in reversed(levels):
        label = f"{level}:{name}" if name else level
        layers += [{"source": f"document:{doc_id}", "options": found["options"]}
                   for doc_id, found in overlays[level] if "options" in found]
        orchestration = doc.get("orchestration") if isinstance(doc.get("orchestration"), dict) else {}
        if isinstance(orchestration.get("options"), dict):
            layers.append({"source": label, "options": orchestration["options"]})
    return scenario, source, layers


def op_claim(fields: dict) -> dict:
    plan, plans_root, run_id = fields["plan"], fields.get("plans_root"), fields["run_id"]
    items = fields.get("items") or []
    _LANE.clear()
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
        if len(_LANE) > 1 and _LANE[0] == ref:
            answer["lane"] = list(_LANE)
        if isinstance(doc.get("route"), dict):
            answer["route"] = {key: doc["route"][key] for key in ("class", "effort") if key in doc["route"]}
        context = plan_json(["context", plan, ref, "--stdout"], plans_root)
        answer["scenario"], answer["scenario_source"], layers = orchestration_of(context, ref)
        if layers:
            answer["options"] = layers
        refused = policy_exists(answer["scenario"], fields.get("orch_config")) if answer["scenario"] else \
            Blocked("SCENARIO_UNKNOWN", f"{ref} resolves no scenario")
        if refused:
            raise refused
        # An item this very attempt already closed stays claimed by the run: its claim is answered again, unchanged.
        if (doc.get("result") or {}).get("attempt_id") != attempt_id:
            # A batch starts its pieces one after another, each under its own run: a dependency that is in progress
            # (an earlier piece of the batch) counts as met.
            plan_json(["start", plan, ref, "--actor", actor_text(fields["actor"]), "--session", run_id,
                       "--no-scout", "--json", *(["--in-progress-deps"] if fields.get("batch") else [])],
                      plans_root, code="START_REFUSED")
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
    artifacts = plan.root.resolve().relative_to(Path(project).resolve()).as_posix() + "/artifacts/" + ref
    return {"op": "brief", "input_ref": stored, "input_id": doc["input_id"], "digest": doc["digest"],
            "reused": reused, "artifact_id": artifact_id(ref, doc["digest"]), "artifacts_dir": artifacts}


# ------------------------------------------------------------------------------------------------ register


def _plan_text(argv: list, plans_root=None, *, code: str = "PLAN_UNREADABLE") -> str:
    """Stdout of a ``plan.py`` verb that prints text; a refusal raises :class:`Blocked`."""
    done = plan_py(argv, plans_root)
    if done.returncode:
        raise refusal_of(done.stderr or done.stdout, code)
    return done.stdout


def _supersede_blocked_attempt(fields: dict) -> None:
    """A piece the run retries after it was blocked is registered under the same attempt id (``att-<run>-<item>``): the
    planner answers ``ATTEMPT_CONFLICT`` to a done outcome for an attempt it holds as blocked. The retry of the run is a new
    try of the same attempt, so the blocked record is reopened first (the plan keeps the history in its log)."""
    if fields["status"] == "blocked":
        return
    doc = item_doc(fields["plan"], fields["ref"], fields.get("plans_root"))
    result = doc.get("result") or {}
    if doc.get("status") == "blocked" and result.get("attempt_id") == fields["attempt_id"]:
        _plan_text(["reopen", fields["plan"], fields["ref"], "--reason",
                   f"retry of attempt {fields['attempt_id']} by its run after the block was resolved"],
                  fields.get("plans_root"), code="REOPEN_REFUSED")
        # the reopened piece is held by its run again (the owner fence of the registration), as the claim made it
        plan_json(["start", fields["plan"], fields["ref"], "--actor", actor_text(fields["executed_by"]), "--session",
                   fields["run_id"], "--no-scout", "--in-progress-deps", "--json"], fields.get("plans_root"),
                  code="START_REFUSED")


def op_register(fields: dict) -> dict:
    run_id = fields["run_id"]
    try:
        _supersede_blocked_attempt(fields)
    except Blocked as blocked:
        return {"op": "register", "gate": {"verdict": "none", "checks": {}}, "outcome": "refused",
                "reason_code": blocked.code, "message": blocked.message}
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


# ------------------------------------------------------------------------------------------------ commit


_LANE: list = []  # the lane of the last ``_candidate`` (a batch the planner names); one call per process
_FOREIGN = re.compile(r"OUTSIDE_SCOPE: foreign dirty paths: (.*?); use --leave-outside")


def _only_plan_dirt(text: str) -> bool:
    """``OUTSIDE_SCOPE`` whose foreign dirty paths are all plan files (``.../phases/P/Pn.m.json``, ``log.jsonl``)."""
    found = _FOREIGN.search(text or "")
    if not found:
        return False
    paths = re.findall(r"'([^']+)'", found.group(1))
    return bool(paths) and all(re.search(r"(^|/)plans/.+/(phases/[^/]+/[^/]+(\.json|/.*)|log\.jsonl|plan\.json)$", path)
                               for path in paths)


def op_commit(fields: dict) -> dict:
    """One scoped commit of the registered item through ``plan.py commit``; nothing left to commit is a no-op."""
    argv = ["commit", fields["plan"], fields["ref"], "--role", "executor"]
    for path in fields.get("paths") or []:
        argv += ["--path", path]
    if fields.get("actor"):
        argv += ["--actor", actor_text(fields["actor"])]
    done = plan_py([*argv, "--json"], fields.get("plans_root"))
    if done.returncode and _only_plan_dirt(done.stderr or done.stdout):
        # Pieces of one batch are in progress together: the bookkeeping of the others (their item files, started in the
        # same call) is dirty and belongs to their own commits, so it stays out of this one instead of refusing it.
        done = plan_py([*argv, "--leave-outside", "--json"], fields.get("plans_root"))
    if done.returncode:
        blocked = refusal_of(done.stderr or done.stdout, "COMMIT_REFUSED")
        if blocked.code == "NOTHING_TO_COMMIT":
            return {"op": "commit", "outcome": "no-op", "message": blocked.message}
        return {"op": "commit", "outcome": "refused", "reason_code": blocked.code, "message": blocked.message}
    try:
        result = json.loads(done.stdout)
    except ValueError:
        return {"op": "commit", "outcome": "refused", "reason_code": "COMMIT_RESULT_INVALID",
                "message": "plan.py commit printed no JSON"}
    if not result.get("sha"):
        return {"op": "commit", "outcome": "refused", "reason_code": "COMMIT_RESULT_INVALID",
                "message": "plan.py commit created no commit"}
    return {"op": "commit", "outcome": "committed", "sha": result["sha"]}


def op_release(fields: dict) -> dict:
    """Return an item this run holds in progress to ``todo``: ``finish --status blocked --owner-session`` then ``reopen``."""
    plan, ref, run_id, plans_root = fields["plan"], fields["ref"], fields["run_id"], fields.get("plans_root")
    try:
        doc = item_doc(plan, ref, plans_root)
    except Blocked as blocked:
        return {"op": "release", "outcome": "refused", "reason_code": blocked.code, "message": blocked.message}
    executor = ((doc.get("result") or {}).get("executor") or {})
    if doc.get("status") != "in_progress" or executor.get("session") != run_id:
        return {"op": "release", "outcome": "no-op", "message": f"{ref} is not in progress under run {run_id}"}
    reason = fields.get("reason") or "released by the run"
    actor = ["--actor", actor_text(fields["actor"])] if fields.get("actor") else []
    finished = plan_py(["finish", plan, ref, "--status", "blocked", "--owner-session", run_id, "--notes", reason,
                        "--escalation", f"claim released: {reason}", *actor], plans_root)
    if finished.returncode:
        blocked = refusal_of(finished.stderr or finished.stdout, "RELEASE_REFUSED")
        return {"op": "release", "outcome": "refused", "reason_code": blocked.code, "message": blocked.message}
    reopened = plan_py(["reopen", plan, ref, "--reason", f"claim released by run {run_id}: {reason}", *actor], plans_root)
    if reopened.returncode:
        blocked = refusal_of(reopened.stderr or reopened.stdout, "RELEASE_REFUSED")
        return {"op": "release", "outcome": "refused", "reason_code": blocked.code,
                "message": f"{ref} was finished as blocked but not reopened: {blocked.message}"}
    return {"op": "release", "outcome": "released"}


_RESEARCH_ITEM = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def op_research(fields: dict) -> dict:
    """The research-result of a piece of work in ``research/<item>-<n>.json`` of the plan, declared as an input of the item."""
    import brief  # the planner engine is located and imported only when a result is saved
    plan_ref, plans_root, number = fields["plan"], fields.get("plans_root"), fields["number"]
    item = fields["ref"].split("/", 1)[0]
    if number < 1 or not _RESEARCH_ITEM.match(item):
        return {"op": "research", "outcome": "refused", "reason_code": "RESEARCH_REF_INVALID",
                "message": f"research {number} of {fields['ref']!r} does not name a file of the plan"}
    try:
        plan = brief.store.load_plan(brief.store.resolve_plan_dir(plan_ref, Path(plans_root) if plans_root else None))
    except brief.PlanError as error:
        return {"op": "research", "outcome": "refused", "reason_code": error.code, "message": error.message}
    if item not in plan.items:
        return {"op": "research", "outcome": "refused", "reason_code": "ITEM_UNKNOWN",
                "message": f"plan {plan_ref} has no item {item}"}
    target = plan.root / "research" / f"{item}-{number}.json"
    relative = target.resolve().relative_to(Path(plan.repo_root).resolve()).as_posix()
    body = json.dumps(fields["result"], ensure_ascii=False, indent=2) + "\n"
    same = target.is_file() and target.read_text(encoding="utf-8") == body
    if not same:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    try:
        plan_json(["--output", "json", "add-artifact", plan_ref, item, "--path", relative, "--role", "input"],
                  plans_root, code="ARTIFACT_REFUSED")
    except Blocked as blocked:
        if not same:  # a result the plan did not accept leaves no file behind
            target.unlink(missing_ok=True)
        return {"op": "research", "outcome": "refused", "reason_code": blocked.code, "message": blocked.message}
    return {"op": "research", "outcome": "no-op" if same else "recorded", "path": relative}


def op_note(fields: dict) -> dict:
    """A note of support work in the journal of the plan: ``plan.py log <plan> <ref> --type note``."""
    refs = fields["refs"]
    if not refs:
        return {"op": "note", "outcome": "refused", "reason_code": "NOTE_NO_TARGET",
                "message": "the planner journals a note on a phase or an item: give one in refs"}
    actor = ["--actor", actor_text(fields["actor"])] if fields.get("actor") else []
    done = plan_py(["log", fields["collection"], refs[0], "--type", "note", "--summary", fields["text"], *actor],
                   fields.get("plans_root"))
    if done.returncode:
        blocked = refusal_of(done.stderr or done.stdout, "NOTE_REFUSED")
        return {"op": "note", "outcome": "refused", "reason_code": blocked.code, "message": blocked.message}
    return {"op": "note", "outcome": "recorded"}


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
    handler = {"claim": op_claim, "brief": op_brief, "register": op_register, "commit": op_commit,
               "release": op_release, "note": op_note, "research": op_research}[fields["op"]]
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
