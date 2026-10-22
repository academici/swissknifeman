"""Conductor projection of a run policy before the conductor binds a launch-plan.

Public ``orch prepare`` and ``source prepare`` bind every stage they are given. Only the
conductor's own preparation asks for an effective copy: stages it skips are omitted, and a
dependency on an omitted stage is rewritten to the stages that stage depended on. The loaded
pack and the caller's policy object stay as they are.
"""
from __future__ import annotations


def effective_policy(policy: dict) -> dict:
    """A policy whose stages omit exactly the ones the conductor skips, or ``policy`` itself when none are.

    Retained stages keep a valid dependency order. An explicit or implicit dependency on a skipped
    stage becomes the dependencies of that stage (unknown dependencies and cycles among the stages
    that remain are left for the ordinary policy checks).
    """
    if not isinstance(policy, dict):
        return policy
    from orch.conductor.policies.routing import unsupported_stages
    _required, optional = unsupported_stages(policy)
    if not optional:
        return policy
    skip = {stage_id for stage_id, _role in optional}
    stages = policy.get("stages") or []
    graph = {}
    previous = None
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        stage_id = stage.get("id")
        if not isinstance(stage_id, str):
            continue
        raw = stage.get("depends_on", [previous] if previous is not None else [])
        graph[stage_id] = [item for item in raw if isinstance(item, str)] if isinstance(raw, list) else []
        previous = stage_id

    def ancestors(stage_id, seen):
        """The stage itself when it is kept, otherwise the kept stages its own dependencies reach."""
        if stage_id in seen:
            return []
        if stage_id not in skip:
            return [stage_id]
        seen.add(stage_id)
        found = []
        for parent in graph.get(stage_id, ()):
            found.extend(ancestors(parent, seen))
        return found

    projected = []
    for stage in stages:
        if not isinstance(stage, dict):
            projected.append(stage)
            continue
        stage_id = stage.get("id")
        if isinstance(stage_id, str) and stage_id in skip:
            continue
        parents = graph.get(stage_id, []) if isinstance(stage_id, str) else []
        if not any(parent in skip for parent in parents):
            projected.append(stage)
            continue
        rewritten = []
        seen = set()
        for parent in parents:
            for name in ancestors(parent, set()):
                if name != stage_id and name not in seen:
                    seen.add(name)
                    rewritten.append(name)
        projected.append({**stage, "depends_on": rewritten})
    return {**policy, "stages": projected}
