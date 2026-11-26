"""Pure budget application over Phase-A draft blocks (context §5.9)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from skm.modules.context.domain.decide import decide
from skm.modules.context.domain.host_inputs import HostFacts

if TYPE_CHECKING:
    from collections.abc import Sequence

    from skm.kernel.json_types import JsonObject, JsonValue
    from skm.modules.context.domain.decide import Selection
    from skm.modules.context.domain.draft import BudgetPolicy, DraftBlock

__all__ = ["apply_budget"]


def apply_budget(blocks: Sequence[DraftBlock], policy: BudgetPolicy) -> Selection:
    """Apply class and total token budgets to ``blocks`` in reverse ladder order."""
    raw_blocks: list[JsonValue] = [
        {
            "block_ref": f"d:{b.ordinal}",
            "ordinal": b.ordinal,
            "block_type": b.block_type.value,
            "budget_class": b.budget_class.value,
            "mandatory": b.mandatory,
            "source_kind": b.source_kind,
            "source_ref": b.source_ref,
            "source_version": b.source_version,
            "trust": b.trust.value,
            "atomic_group": b.atomic_group,
            "tokens_estimate": b.tokens_estimate,
            "content_digest": b.content_digest,
            "reason": b.reason.value,
        }
        for b in blocks
    ]
    draft_meta: JsonObject = {
        "blocks": raw_blocks,
        "conditional": [],
        "host_inputs": [],
        "budget": {
            "total_limit": policy.total_limit,
            "class_limits": {k.value: v for k, v in policy.class_limits.items()},
            "skills_budget": policy.skills_budget,
            "skills_remaining": policy.skills_budget,
            "estimator_id": policy.estimator_id,
        },
        "repo_max_files": 8,
        "resume": None,
    }
    empty_facts = HostFacts(deps=frozenset(), work_paths=(), work_paths_truncated=False, baseline={})
    return decide(draft_meta, (), empty_facts)
