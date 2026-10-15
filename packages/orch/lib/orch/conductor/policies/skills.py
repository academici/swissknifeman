"""The checks of the skills of a role: what each skill declares in its ``selection.json`` against the tools of the
route and the budget. No text is cut and no meaning is judged."""
from __future__ import annotations

import re
from typing import Optional

INTERACTIVE_TOOL = "AskUserQuestion"  # a skill that needs it waits for a person; every conductor role runs headless
EXCLUSIVE_GROUP_MAX = 1
EXCLUSIVE_GROUP_LIMITS = {"php-architecture": 2}  # every other exclusive group allows one


def _is_role_contract(target: str) -> bool:
    """Whether a ``selection.replaced_by`` points at a role contract or a schema (a script or a hook does not replace the
    text a role reads)."""
    parts = re.split(r"[\\/]", target)
    return "roles" in parts[:-1] or "schemas" in parts[:-1] or target.endswith(".schema.json")


def _conflicts_with(skill: dict, other: dict) -> bool:
    """Whether ``skill`` lists ``other`` in its ``conflicts``: by id, by name, or, for a skill of the project that has no
    bucket in its id, by the folder of a ``<bucket>/<folder>`` entry."""
    return any(target in (other["id"], other["name"]) or ("/" not in other["id"] and target.rsplit("/", 1)[-1] == other["name"])
               for target in skill["selection"].get("conflicts") or [])


def check_skills(skills: list, *, tools: Optional[set], budget: int = 0) -> tuple:
    """``(kept, excluded, conflict)`` of the skills of a role, from what they declare and nothing in their text.

    ``skills`` are ``{name, id, selection, tokens}`` in the order of the role's list (``selection`` is the content of
    ``selection.json`` or ``{}``; ``tokens`` is the size of the text that enters the prompt, or None when none does).
    ``tools`` are the tools of the route (None when it names none, so ``requires_tools`` is not judged). A skill is
    left out as ``duplicated_by_role_contract``, ``interactive_in_headless``, ``tool_missing``, ``over_budget`` (the text
    is above its ``max_tokens`` or above ``budget`` when that is not 0; never cut), ``persona_duplicate`` (a second
    ``persona``) or ``exclusive_group`` (beyond the limit of its group). ``conflict`` is the first pair of kept skills
    one of which lists the other in ``conflicts``, else None. ``excluded`` rows are ``{id, reason, detail}``."""
    kept, excluded, groups = [], [], {}

    def drop(skill, reason, detail=""):
        excluded.append({"id": skill["id"], "reason": reason, "detail": detail})

    for skill in skills:
        meta = skill["selection"]
        required = list(meta.get("requires_tools") or [])
        missing = sorted(set(required) - tools) if tools is not None else []
        tokens = skill.get("tokens")
        group = meta.get("exclusive_group")
        if meta.get("replaced_by") and _is_role_contract(meta["replaced_by"]):
            drop(skill, "duplicated_by_role_contract", meta["replaced_by"])
        elif INTERACTIVE_TOOL in required:
            drop(skill, "interactive_in_headless", INTERACTIVE_TOOL)
        elif missing:
            drop(skill, "tool_missing", ", ".join(missing))
        elif tokens is not None and meta.get("max_tokens") and tokens > meta["max_tokens"]:
            drop(skill, "over_budget", f"{tokens} tokens, max_tokens {meta['max_tokens']}")
        elif tokens is not None and budget and tokens > budget:
            drop(skill, "over_budget", f"{tokens} tokens, limits.skill_tokens_max {budget}")
        elif meta.get("kind") == "persona" and any(row["selection"].get("kind") == "persona" for row in kept):
            drop(skill, "persona_duplicate", "persona")
        elif group and groups.get(group, 0) >= EXCLUSIVE_GROUP_LIMITS.get(group, EXCLUSIVE_GROUP_MAX):
            drop(skill, "exclusive_group", group)
        else:
            kept.append(skill)
            if group:
                groups[group] = groups.get(group, 0) + 1
    conflict = next(((first, second) for number, first in enumerate(kept) for second in kept[number + 1:]
                     if _conflicts_with(first, second) or _conflicts_with(second, first)), None)
    return kept, excluded, conflict
