"""Select: which of the valid skills a role keeps. The meaning is judged by ``policies.skills.check_skills`` from what each
skill declares in its ``selection.json`` against the tools of the route and the budget; no text is cut."""
from __future__ import annotations

from typing import Any, Mapping, Optional

from aicore.content import budget as token_budget

from orch.conductor.context import Selection
from orch.conductor.policies import skills as skill_policy


def candidate(skill: Mapping[str, Any], weigh: bool) -> dict:
    """The row ``check_skills`` takes for a checked skill; its tokens are estimated only when the text goes into the
    prompt (``weigh``: the role runs isolated) and the skill has a file."""
    tokens = token_budget.estimate_tokens(skill["body"]) if weigh and skill["path"] is not None else None
    return {"name": skill["name"], "id": skill["id"], "selection": skill["selection"], "tokens": tokens}


def select_skills(candidates: list, tools: Optional[set], budget: int) -> Selection:
    """The skills that survive the checks of ``candidates`` (rows of :func:`candidate`) for a route with ``tools`` (None when
    the route names no list) within ``budget`` tokens, what each excluded one was left out for, and the first declared
    conflict of two kept skills."""
    survivors, rows, conflict = skill_policy.check_skills(candidates, tools=tools, budget=budget)
    return Selection([skill["name"] for skill in survivors], rows,
                     [{"id": row["id"], "reason": row["reason"]} for row in rows], conflict)
