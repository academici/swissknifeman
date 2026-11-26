"""Engine conformance: a catalogue of scenarios and a runner for one binding or all of them.

The catalogue (``conformance/scenarios.json``, ``orch-conformance/v1``) names every scenario with a status per
binding: ``covered`` (a trace or an existing test proves it), ``declared`` (needs the engine, not proven yet) or
``n/a``; the last two always carry a reason and never fail the command. The rows of a run are checked against records/v1
``conformance-report`` (the rows under the catalogue's tag) before they are returned. A trace is folded through ``RunState``
(and ``retry.decide`` / ``effects.check`` when the expectation asks for a decision); a test is run by name.
"""
from __future__ import annotations

import copy
import io
import json
from pathlib import Path
import sys
import unittest

from orch import effects, retry
from orch.bindings import BINDINGS
from orch.conductor import records
from orch.conductor.domain.stop import Stop
from orch.port import PortError, RunState

SCHEMA_VERSION = "orch-conformance/v1"
ROOT = Path(__file__).resolve().parents[2]
CATALOGUE = ROOT / "conformance" / "scenarios.json"
STATUSES = ("covered", "declared", "n/a")
KITS = ("agent", "runtime")
HOWS = ("trace", "test")
_KEYS = {"id", "title", "kit", "how", "ref", "expect", "bindings", "reason"}
_EXPECT_KEYS = {"stages", "error", "foreign", "effect", "inputs", "decision"}
_RECEIPT_KEY = "conformance:primary:effect:target"
_NOW = "2026-10-05T17:00:00Z"


class ConformanceError(Exception):
    """The catalogue is unreadable or invalid; ``issues`` lists every problem."""

    def __init__(self, message: str, issues: list | None = None):
        super().__init__(message)
        self.issues = issues or []


def load(path: Path = CATALOGUE) -> dict:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConformanceError(f"conformance catalogue is unreadable: {exc}") from exc
    issues = check_catalogue(doc, path.parent.parent)
    if issues:
        raise ConformanceError("conformance catalogue is invalid", issues)
    return doc


def _test_exists(name: str, root: Path) -> bool:
    with _tests_importable(root):
        suite = unittest.defaultTestLoader.loadTestsFromName(name)
    return all(type(test).__name__ != "_FailedTest" for test in _flatten(suite)) and suite.countTestCases() == 1


def _flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _flatten(item)
        else:
            yield item


class _tests_importable:
    """Makes ``tests.<module>`` of the package importable for the duration of a block."""

    def __init__(self, root: Path):
        self.entry = str(root)

    def __enter__(self):
        self.added = self.entry not in sys.path
        if self.added:
            sys.path.insert(0, self.entry)

    def __exit__(self, *exc):
        if self.added and self.entry in sys.path:
            sys.path.remove(self.entry)


def check_catalogue(doc: object, root: Path = ROOT) -> list:
    """Problems of a catalogue as ``{"scenario", "message"}`` rows; the catalogue is valid when the list is empty."""
    issues: list = []

    def bad(scenario: str, message: str) -> None:
        issues.append({"scenario": scenario, "message": message})

    if not isinstance(doc, dict) or doc.get("schema_version") != SCHEMA_VERSION:
        return [{"scenario": "-", "message": f"schema_version must be {SCHEMA_VERSION!r}"}]
    scenarios = doc.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        return [{"scenario": "-", "message": "scenarios must be a non-empty list"}]
    seen: set = set()
    for item in scenarios:
        if not isinstance(item, dict):
            bad("-", "a scenario must be an object")
            continue
        sid = item.get("id") if isinstance(item.get("id"), str) else "-"
        if sid in seen:
            bad(sid, "duplicate id")
        seen.add(sid)
        if set(item) - _KEYS:
            bad(sid, f"unknown keys {sorted(set(item) - _KEYS)}")
        for key in ("id", "title", "kit", "how", "bindings"):
            if key not in item:
                bad(sid, f"missing {key}")
        if item.get("kit") not in KITS:
            bad(sid, f"kit must be one of {KITS}")
        if item.get("how") not in HOWS:
            bad(sid, f"how must be one of {HOWS}")
        bindings = item.get("bindings")
        if not isinstance(bindings, dict) or set(bindings) != set(BINDINGS):
            bad(sid, f"bindings must name exactly {sorted(BINDINGS)}")
            continue
        for name, status in bindings.items():
            if status not in STATUSES:
                bad(sid, f"binding {name}: status must be one of {STATUSES}")
        if (any(status in ("declared", "n/a") for status in bindings.values())
                and not (isinstance(item.get("reason"), str) and item["reason"].strip())):
            bad(sid, "declared and n/a need a reason")
        unknown = set(item.get("expect") or ()) - _EXPECT_KEYS
        if unknown:
            bad(sid, f"unknown expect keys {sorted(unknown)}")
        if "covered" in bindings.values():
            ref = item.get("ref")
            if not isinstance(ref, str) or not ref:
                bad(sid, "covered needs a ref")
            elif item.get("how") == "trace":
                if not (root / ref).is_file():
                    bad(sid, f"trace file {ref} does not exist")
                if not item.get("expect"):
                    bad(sid, "a trace needs expect")
            elif item.get("how") == "test" and not _test_exists(ref, root):
                bad(sid, f"test {ref} does not exist")
    return issues


def _read_trace(path: Path) -> list:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _failure_class(state: RunState, events: list, stage_id: str) -> str:
    stage = state.stages()[stage_id]
    if stage["status"] == "unknown_outcome":
        return retry.UNKNOWN_OUTCOME
    last = [doc for doc in events if doc.get("stage_id") == stage_id and doc.get("contract_version") == "exec/v1"][-1]
    if stage["errors"] and "error" in stage["errors"][-1]:
        return stage["errors"][-1]["error"]["class"]
    return retry.class_of(last["kind"])


def _unknown_receipt() -> dict:
    intent = {"input_digest": "ab" * 32, "target": "target", "expected_prior": {"head": "1" * 40}}
    return effects.record(effect_key=_RECEIPT_KEY, kind="git_commit", intent=intent, outcome="unknown",
                          reconcile_method="git_rev_parse", now=_NOW)


def run_trace(path: Path, expect: dict) -> list:
    """Differences between the fold of a trace and ``expect``; an empty list means the scenario passes."""
    events = _read_trace(path)
    state, raised = RunState(events[0]["run_id"]), None
    for doc in events:
        try:
            state.apply(doc)
        except PortError as exc:
            raised = exc.code
            break
    differences: list = []

    def differ(field: str, expected, actual) -> None:
        differences.append({"field": field, "expected": expected, "actual": actual})

    if raised != expect.get("error"):
        differ("error", expect.get("error"), raised)
    if raised is None:
        state.close()
    stages = {key: value["status"] for key, value in state.stages().items()}
    for stage_id, status in (expect.get("stages") or {}).items():
        if stages.get(stage_id) != status:
            differ(f"stages.{stage_id}", status, stages.get(stage_id))
    if "foreign" in expect and len(state.foreign()) != expect["foreign"]:
        differ("foreign", expect["foreign"], len(state.foreign()))
    inputs = dict(expect.get("inputs") or {})
    if expect.get("effect") == "unknown_receipt":
        receipt = _unknown_receipt()
        intent = receipt["intent"]
        verdict = effects.check(effect_key=_RECEIPT_KEY, kind="git_commit", intent=intent,
                                observed_prior=dict(intent["expected_prior"]), receipts=[receipt], now=_NOW)
        if (verdict.proceed, verdict.receipt) != (False, None):
            differ("effect", "reconcile", {"proceed": verdict.proceed})
        inputs["receipt_unresolved"] = True
    if "decision" in expect:
        stage_id = next(iter(expect["stages"]))
        stage = state.stages()[stage_id]
        decision = retry.decide(retry.RetryInputs(
            error_class=_failure_class(state, events, stage_id),
            stage_writes=inputs.get("stage_writes", False), worktree_dirty=inputs.get("worktree_dirty", False),
            receipt_unresolved=inputs.get("receipt_unresolved", False), attempts_used=stage["attempt"],
            stage_retries_max=2, budget_left=5), {})
        if decision.action != expect["decision"]:
            differ("decision", expect["decision"], decision.action)
    return differences


def run_test(name: str, root: Path = ROOT) -> list:
    """Run one unittest by name; a failure comes back as one difference carrying its trace."""
    with _tests_importable(root):
        suite = unittest.defaultTestLoader.loadTestsFromName(name)
        stream = io.StringIO()
        outcome = unittest.TextTestRunner(stream=stream, verbosity=0).run(suite)
    if outcome.wasSuccessful() and outcome.testsRun == 1:
        return []
    return [{"field": "test", "expected": "pass", "actual": stream.getvalue().strip().splitlines()[-12:]}]


def _execute(item: dict, root: Path) -> list:
    if item["how"] == "trace":
        return run_trace(root / item["ref"], copy.deepcopy(item["expect"]))
    return run_test(item["ref"], root)


def run(binding: str | None = None, *, path: Path = CATALOGUE) -> list:
    """Rows ``{scenario, binding, kit, status, reason, differences}`` for one binding or every binding.

    A covered scenario runs once however many bindings are reported; ``pass`` or ``fail`` replaces ``covered``.
    """
    if binding is not None and binding not in BINDINGS:
        raise ConformanceError(f"unknown binding {binding!r}; choose one of {sorted(BINDINGS)}")
    doc = load(path)
    root, outcomes, rows = path.parent.parent, {}, []
    for item in doc["scenarios"]:
        for name in ([binding] if binding else sorted(BINDINGS)):
            status = item["bindings"][name]
            row = {"scenario": item["id"], "binding": name, "kit": item["kit"], "status": status,
                   "reason": item.get("reason") if status != "covered" else None, "differences": []}
            if status == "covered":
                if item["id"] not in outcomes:
                    outcomes[item["id"]] = _execute(item, root)
                row["differences"] = outcomes[item["id"]]
                row["status"] = "fail" if row["differences"] else "pass"
            rows.append(row)
    return report_rows(rows)


def report_rows(rows: list) -> list:
    """``rows`` after the check of records/v1 ``conformance-report`` (the rows under the tag of the catalogue); the
    command prints the rows alone, as before. ``ConformanceError`` when a row does not match."""
    try:
        records.check({"schema": SCHEMA_VERSION, "rows": rows}, "conformance-report", "orch conformance",
                      hint=records.WRITER_HINT)
    except Stop as stop:
        raise ConformanceError(f"{stop.code}: {stop.message}") from None
    return rows
