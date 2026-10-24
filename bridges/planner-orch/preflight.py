"""Read-only execution checks at planner:check; never call the artifact-writing brief op."""
from __future__ import annotations

from pathlib import Path

import brief
import partners
import worksource

MAX_ITEMS = 100
MAX_ISSUES = 500


def run(check_input: dict) -> dict:
    partners.use_aicore()
    from aicore.util import schema

    planner = partners.require_planner_root()
    registry = schema.load_contract_set(planner / "schemas" / "check-plugin" / "v1")[0]
    problems = schema.validate(check_input, "input", registry)
    if problems:
        raise ValueError(f"Invalid planner:check input: {problems}")
    plan = brief.store.load_plan(Path(check_input["plan_dir"]))
    issues = []
    if plan.plan.get("status") != "archived":
        candidates = [(phase_id, item_id) for phase_id in plan.plan.get("phases", [])
                      if plan.phases.get(phase_id, {}).get("design") == "detailed"
                      for item_id in plan.phases[phase_id].get("items", [])
                      if plan.items.get(item_id, {}).get("status") == "todo"]
        scenarios = {}
        for phase_id, item_id in candidates[:MAX_ITEMS]:
            def issue(code, message, phase_id=phase_id, item_id=item_id):
                issues.append({"severity": "error", "code": code, "message": message,
                               "path": f"phases/{phase_id}/{item_id}.json", "ref": item_id})

            try:
                brief.build(plan, item_id)
            except brief.PlanError as exc:
                issue(exc.code, str(exc))
            pack = brief.context.collect(plan, item_id, with_scout=False)
            scenario, _source, _layers = worksource.orchestration_of(pack, item_id)
            if scenario not in scenarios:
                scenarios[scenario] = worksource.policy_exists(scenario) if scenario else worksource.Blocked(
                    "SCENARIO_UNKNOWN", f"{item_id} resolves no scenario")
            refused = scenarios[scenario]
            if refused:
                issue(refused.code, refused.message)
        if len(candidates) > MAX_ITEMS:
            issues.append({"severity": "warning", "code": "PREFLIGHT_TRUNCATED",
                           "message": f"Checked the first {MAX_ITEMS} of {len(candidates)} todo items"})
    output = {"issues": issues[:MAX_ISSUES]}
    problems = schema.validate(output, "output", registry)
    if problems:
        raise ValueError(f"Invalid planner:check output: {problems}")
    return output
