"""Per-run workflows use the deterministic engine's closed grammar."""

from typing import cast

import pytest

from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.execution.domain.workflow.adhoc import parse_adhoc_workflow
from skm.modules.execution.domain.workflow.definition import StageType
from support.adhoc import workflow


def test_order_and_user_chosen_stage_ids_are_preserved() -> None:
    parsed = parse_adhoc_workflow(workflow(), "research")
    assert [(stage.id, stage.type) for stage in parsed.stages] == [
        ("setup", StageType.PREPARE_ENVIRONMENT),
        ("respond", StageType.AGENT_STEP),
        ("finish", StageType.ACCEPTANCE_GATE),
    ]


def test_stage_with_different_task_kind_cannot_run() -> None:
    document = workflow()
    cast("list[JsonObject]", document["stage"]).extend(
        [
            {"id": "unit_prepare", "type": "prepare_environment", "for_kinds": ["unit"]},
            {"id": "unit_integrate", "type": "integrate", "for_kinds": ["unit"]},
        ]
    )
    assert [stage.id for stage in parse_adhoc_workflow(document, "research").stages] == [
        "setup",
        "respond",
        "finish",
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [("type", "arbitrary_script"), ("type", "plan_acceptance"), ("role", "unknown"), ("role", "scout")],
)
def test_closed_stage_type_role_and_adhoc_applicability(field: str, value: JsonValue) -> None:
    document = workflow()
    cast("list[JsonObject]", document["stage"])[1][field] = value
    with pytest.raises(ValidationFailed, match="workflow"):
        parse_adhoc_workflow(document, "research")


def test_rejects_wrong_kind_and_invalid_order() -> None:
    document = workflow()
    with pytest.raises(ValidationFailed, match="work kind"):
        parse_adhoc_workflow(document, "code")
    cast("list[JsonObject]", document["stage"]).reverse()
    with pytest.raises(ValidationFailed) as exc:
        parse_adhoc_workflow(document, "research")
    assert "prepare_not_first" in str(exc.value.details)
