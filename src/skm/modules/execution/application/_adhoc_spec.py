"""Load a run's task instructions and workflow from its pinned specification."""

import json
from typing import cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.artifacts import public as artifacts
from skm.modules.execution.application._start_inputs import load_workflow
from skm.modules.execution.domain.run import Run
from skm.modules.execution.domain.task import Task
from skm.modules.execution.domain.workflow.adhoc import parse_adhoc_workflow
from skm.modules.execution.domain.workflow.definition import WorkflowDefinition

__all__ = ["INLINE_SPEC", "MAX_SPEC_BYTES", "load_run_workflow", "task_instructions"]

INLINE_SPEC = "skm.adhoc.v1"
MAX_SPEC_BYTES = 256 * 1024


def _read(uow: UnitOfWork, run: Run) -> tuple[str, JsonValue]:
    version_id = run.inline_spec_file_version_id
    if version_id is None:
        raise error_for(ErrorCode.INVALID_REFERENCE, "run has no inline specification")
    text = artifacts.read_text_content(uow, version_id, max_bytes=MAX_SPEC_BYTES)
    if text is None:
        raise error_for(ErrorCode.INVALID_REFERENCE, "inline specification must be bounded UTF-8 text")
    try:
        document = cast("JsonValue", json.loads(text))
    except ValueError:
        return text, None
    if isinstance(document, dict) and document.get("schema") == INLINE_SPEC:
        prompt = document.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise error_for(ErrorCode.INVALID_REFERENCE, "invalid pinned task instructions")
        return prompt, document.get("workflow")
    return text, None


def task_instructions(uow: UnitOfWork, run: Run) -> str | None:
    return None if run.inline_spec_file_version_id is None else _read(uow, run)[0]


def load_run_workflow(uow: UnitOfWork, run: Run, task: Task) -> WorkflowDefinition:
    if run.inline_spec_file_version_id is not None:
        _, workflow = _read(uow, run)
        if workflow is not None:
            return parse_adhoc_workflow(workflow, task.work_kind)
    return load_workflow(uow, run.workflow_resource_version_id)
