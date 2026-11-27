"""A docs item stays docs when readiness and start compile run tasks."""

from __future__ import annotations

import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from skm.kernel.ids import RevisionId
from skm.kernel.json_types import JsonValue
from skm.modules.execution.application._plain import plain
from skm.modules.execution.application._start_inputs import compile_spec_tasks
from skm.modules.execution.domain.workflow.definition import parse_workflow
from skm.modules.planning.domain.specification import from_document
from skm.modules.planning.public import compile_execution_graph

ROOT = Path(__file__).resolve().parents[4]
REV = RevisionId(UUID("00000000-0000-7000-8000-000000000099"))
NOW = datetime(2026, 11, 27, tzinfo=UTC)


def _docs_spec() -> Any:
    document = {
        "schema": "urn:skm:planning:specification:v1",
        "title": "Docs kind",
        "goal": "Keep a docs item docs.",
        "phases": [
            {
                "key": "P1",
                "title": "Probe",
                "goal": "One docs item",
                "design_state": "detailed",
                "id": "00000000-0000-7000-8000-000000000010",
            }
        ],
        "items": [
            {
                "key": "P1.1",
                "phase": "P1",
                "title": "Note",
                "summary": "A note",
                "why": "It is documentation.",
                "work_kind": "docs",
                "id": "00000000-0000-7000-8000-000000000011",
                "review": {"mode": "required"},
            }
        ],
    }
    spec, findings = from_document(document)
    assert findings == ()
    assert spec.items[0].work_kind.value == "docs"
    return spec


def _graph(spec: Any) -> Any:
    graph = plain(compile_execution_graph(spec, REV))
    for task in graph["tasks"]:
        task["phase"] = task.pop("phase_key")
        task["item"] = task.pop("item_key")
    for group in graph["batch_groups"]:
        group["phase"] = group.pop("phase_key")
        group["batch"] = group.pop("batch_key")
    return graph


def _workflow() -> Any:
    path = ROOT / "tests/fixtures/corpus/examples/execution/workflows/quick-fix.toml"
    definition, violations = parse_workflow(cast("JsonValue", tomllib.loads(path.read_text())))
    assert violations == ()
    assert definition is not None
    return definition


def test_a_docs_item_is_not_compiled_as_code() -> None:
    spec = _docs_spec()
    counter = iter(range(1, 1000))
    compiled = compile_spec_tasks(
        spec,
        _graph(spec),
        _workflow(),
        {},
        None,
        {},
        run_id=UUID(int=1),
        workspace_id=UUID(int=2),
        revision_id=REV,
        new_task_id=lambda: UUID(int=next(counter)),
        now=NOW,
    )
    kinds = {task.display_key: task.work_kind for task in compiled.tasks}
    assert kinds["P1.1"] == "docs"
    assert kinds["P1#gate"] == "review"
