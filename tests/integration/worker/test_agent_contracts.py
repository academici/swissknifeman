"""Shared result repair and pinned draft decoding before runtime admission."""

from dataclasses import replace

import pytest

from skm.bootstrap.host_services import decode_context_draft, worker_schema_issues
from skm.modules.execution.application._worker_dtos import document
from skm.modules.execution.host.stages.agent_step import role_result

from .test_worker_loop import documents


@pytest.mark.parametrize("role", list(documents()))
def test_all_roles_reject_missing_and_ambiguous_result_documents(role):
    for text in ("no result", '```json\n{"one":1}\n```\n```json\n{"two":2}\n```'):
        result, diagnostics = role_result(role, None, text, validate=worker_schema_issues)
        assert result is None
        assert diagnostics["error_code"] == "RESULT_INVALID"
        assert diagnostics["detail"]


def test_repair_that_changes_meaning_is_rejected_before_admission(monkeypatch):
    raw = {**documents()["executor"], "status": "blocked", "unknown_field": "forces validation failure"}
    monkeypatch.setattr(
        "skm.modules.execution.host.stages.agent_step.heal",
        lambda *_: {
            "kind": "healed",
            "document": documents()["executor"],
            "notes": ["bad repair"],
        },
    )
    result, diagnostics = role_result("executor", raw, "", validate=worker_schema_issues)
    assert result is None
    assert diagnostics["error_code"] == "REPAIR_SEMANTIC_DRIFT"


def test_decode_preserves_pinned_conditional_blocks_and_digest():
    from skm.modules.context.domain.draft import ConditionalBlock, build_draft

    draft = build_draft(
        {
            "manifest_id": "01900000-0000-7000-8000-000000000001",
            "blocks": [
                {
                    "ordinal": 0,
                    "block_type": "task_contract",
                    "budget_class": "core",
                    "mandatory": True,
                    "source_kind": "derived",
                    "source_ref": "task:contract",
                    "trust": "system",
                    "atomic_group": None,
                    "source_version": None,
                    "content": "frozen",
                    "content_digest": "sha256:" + "1" * 64,
                    "tokens_estimate": 2,
                    "reason": "mandatory",
                }
            ],
        }
    )
    conditional = ConditionalBlock(replace(draft.blocks[0], ordinal=1), "deps_any", frozenset({"python"}))
    pinned = replace(draft, conditional=(conditional,))
    assert decode_context_draft(document(pinned)) == pinned
