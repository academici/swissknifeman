"""Three selected tasks, genuine checks/reviews and local Git integration, with event-only replay."""

import json
import sys
from copy import deepcopy
from typing import cast

from contracts.execution.harness import _publish_revision
from fixtures.execution.planning import ready_revision
from fixtures.execution.processes import scenario, script
from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain.history import build_history
from skm.modules.execution.generated.commands import StartRun, ValidateForExecution
from skm.modules.execution.ports import ExecutionQueries
from skm.modules.planning import public as planning
from skm.modules.planning.domain.specification import to_document

KEYS = ("P1.1", "P1.2", "P1.3")


def dag(side):
    ready_revision(side)
    with side.uow(readonly=True) as uow:
        doc = to_document(planning.get_revision_specification(uow, side.rev2))
    first_item = cast("list[JsonObject]", doc["items"])[0]
    first_check = cast("list[JsonObject]", doc["checks"])[0]
    first_criterion = cast("list[JsonObject]", doc["criteria"])[0]
    # Items carry required independent review; units are self-reviewed by the domain contract.
    items, checks, criteria = [], [], []
    for index, key in enumerate(KEYS):
        target = "src/second.py" if index == 1 else "src/target.py"
        item = deepcopy(first_item)
        item.update(
            id=item["id"] if index == 0 else str(side.new_id()),
            key=key,
            title=f"M3 task {index + 1}",
            depends_on=[KEYS[0]] if index == 2 else [],
            scope={"include": [f"repo:{target}"], "exclude": []},
            change_hints=[{"mount": "repo", "pattern": target, "change": "any"}],
            deliverables=["Integrated checked task"],
            review={"mode": "required"},
            reads=[{"kind": "material", "ref": "material/guide-doc", "why": "Pinned input", "required": True}]
            if index == 0
            else [],
            route={
                "runtime": "fake",
                "class": "frontier",
                "effort": "high",
                "correction": {"class": "implementation", "effort": "high"},
            },
        )
        items.append(item)
        check = deepcopy(first_check)
        check.update(
            id=check["id"] if index == 0 else str(side.new_id()),
            owner=key,
            kind="command",
            rerun_after_integration=True,
            definition={
                "argv": [
                    sys.executable,
                    "-c",
                    f"from pathlib import Path; assert '42' in Path('{target}').read_text(), "
                    "'M3 exact feedback: expected 42'",
                ],
                "cwd": {"mount": "repo", "path": "."},
                "timeout_seconds": 30,
            },
        )
        checks.append(check)
        criterion = deepcopy(first_criterion)
        criterion.update(
            id=criterion["id"] if index == 0 else str(side.new_id()),
            key=f"AC{index + 1}",
            owner=key,
            verification_mode="check",
            checks=[f"{key}:V1"],
        )
        criteria.append(criterion)
    doc.update(items=items, units=[], checks=checks, criteria=criteria)
    for material in cast("list[JsonObject]", doc["materials"]):
        material["applies_to"] = [KEYS[0]]
    for phase in cast("list[JsonObject]", doc["phases"]):
        phase["design_state"] = "detailed"
    return _publish_revision(side.app, side.client, side.owner, side.clock, side.plan1, doc, "current")


def start(side, revision, *, keys=KEYS):
    from unit.execution.application._support import set_setting

    # The owner explicitly allows the pinned correction floor below the initial task class.
    set_setting(side, "runtimes.admission.bounded_fix.below_task_class", True)
    selection = {"task_keys": list(keys), "phases": []}
    report = side.client.dispatch(
        ValidateForExecution.from_json(
            {"plan_id": str(side.plan1), "revision_id": str(revision), "selection": selection}
        )
    )
    assert report.status in {"ready", "ready_with_advisories"}, report
    return side.client.dispatch(
        StartRun.from_json(
            {
                "plan_id": str(side.plan1),
                "revision_id": str(revision),
                "readiness_report_id": str(report.report_id),
                "overrides": {},
                "selection": selection,
                "reason": "M3 process acceptance",
            }
        )
    )


def scripts(side, *, interrupted=False):
    root = side.root
    bad = scenario(root / "check-red.toml", "executor", content="answer = 41\n", model="fake-a")
    good = scenario(root / "fixed.toml", "executor")
    reviewed_fix = scenario(
        root / "review-fixed.toml", "executor", content="answer = 42\n# M3 confirmed boundary\n"
    )
    second = scenario(root / "second.toml", "executor", target="src/second.py", model="fake-a")
    dependent = scenario(
        root / "dependent.toml", "executor", content="answer = 42\n# dependent unit\n", model="fake-a"
    )
    green_doc = {
        "schema": "urn:skm:execution:role-result:reviewer:v1",
        "verdict": "green",
        "summary": "Checked",
        "findings": [],
        "residual_risk": "None",
    }
    red_doc = {
        **green_doc,
        "verdict": "red",
        "findings": [
            {
                "id": "F1",
                "severity": "major",
                "confidence": "high",
                "basis": "correctness",
                "category": "correctness",
                "message": "M3 confirmed finding",
                "failure_scenario": "Missing boundary",
                "location": {"mount": "repo", "path": "src/target.py", "line_start": 1},
            }
        ],
    }
    green = scenario(root / "green.toml", "reviewer", document=green_doc)
    red = scenario(root / "red.toml", "reviewer", document=red_doc)
    triage = scenario(
        root / "triage.toml",
        "triager",
        document={
            "schema": "urn:skm:execution:role-result:triager:v1",
            "confirmed": [{"finding_id": "F1", "decision": "fix_now"}],
            "rejected": [],
            "summary": "Confirm M3 finding",
        },
    )
    entries = [
        ("executor", KEYS[0], 1, bad),
        ("executor", KEYS[0], 2, good),
        ("executor", KEYS[0], 3, reviewed_fix),
        ("reviewer", KEYS[0], 1, red),
        ("reviewer", KEYS[0], 2, green),
        ("triager", KEYS[0], 1, triage),
    ]
    if interrupted:
        hanging = scenario(
            root / "interrupted.toml", "executor", content="answer = 41\n", model="fake-a", hang=True
        )
        entries = [
            ("executor", KEYS[0], 1, hanging),
            ("executor", KEYS[0], 2, bad),
            ("executor", KEYS[0], 3, good),
            ("executor", KEYS[0], 4, reviewed_fix),
            *entries[3:],
        ]
    for key, path in zip(KEYS[1:], (second, dependent), strict=True):
        entries.extend([("executor", key, 1, path), ("reviewer", key, 1, green)])
    return script(root / "m3-script.toml", entries)


def rebuild(side, run_id, *, through=None):
    with side.uow(readonly=True) as uow:
        queries = uow.repo(ExecutionQueries)
        cutoff = queries.head_run_seq(run_id) if through is None else through
        events, scanned = [], 0
        while scanned < cutoff:
            batch = queries.run_events(run_id, scanned, cutoff, 1000)
            assert batch, (scanned, cutoff)
            events.extend(batch)
            latest = batch[-1]["stream_seq"]
            assert latest > scanned
            scanned = latest
        assert len(events) == cutoff
    after, entries = 0, []
    while after < cutoff:
        page = build_history(events, cutoff, run_id=str(run_id), after_seq=after, limit=50)
        entries.extend(cast("list[JsonObject]", page["entries"]))
        scanned_through = page["scanned_through_seq"]
        assert isinstance(scanned_through, int)
        assert scanned_through > after
        after = scanned_through
    assert len(entries) == len(events)
    assert all("coverage" in entry and "reason_codes" in entry for entry in entries)
    assert all(len(entry["nodes"]) <= 32 and len(entry["edges"]) <= 200 for entry in entries)
    # Serialization also rejects non-JSON snapshots and leaks of operational data.
    return cutoff, json.loads(json.dumps(entries))


def assert_rework_trace(history):
    observed = [(entry.record.stage_id, entry.record.outcome_kind.value) for entry in history]
    expected = [
        ("execute", "runtime_error"),
        ("execute", "success"),
        ("checks", "checks_failed"),
        ("execute", "success"),
        ("checks", "success"),
        ("review", "verdict_red"),
        ("triage", "success"),
        ("execute", "success"),
        ("checks", "success"),
        ("review", "verdict_green"),
        ("integrate", "success"),
        ("recheck", "success"),
    ]
    cursor = iter(observed)
    for item in expected:
        assert any(value == item for value in cursor), (item, observed)


def assert_shared_budget(side, run_id, tasks):
    from skm.modules.execution.domain.budget import BudgetDimension
    from skm.modules.execution.ports import BudgetRepository, StageRepository
    from skm.modules.runtimes.public import fresh_tokens

    with side.uow(readonly=True) as uow:
        steps = [
            s
            for task in tasks
            for e in uow.repo(StageRepository).history(task.current_attempt_id).entries
            for s in e.steps
        ]
        usd, tokens = 0, 0
        for step in steps:
            report = step.usage or step.usage_so_far
            assert report is not None
            assert report.cost_usd_micros is not None
            fresh = fresh_tokens(report)
            assert fresh is not None
            usd += report.cost_usd_micros
            tokens += fresh
        expected = {
            BudgetDimension.USD: usd,
            BudgetDimension.TOKENS: tokens,
        }
        for dimension, amount in expected.items():
            accounts = uow.repo(BudgetRepository).accounts_for(run_id, None, dimension)
            assert len(accounts) == 1
            assert accounts[0].scope == "run"
            assert accounts[0].spent == amount > 0
            assert accounts[0].reserved == 0
