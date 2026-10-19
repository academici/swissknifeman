"""Doctor probe of the bridge: the partners a work-source call needs are found (``check-result/v1`` on stdout).

The work source of a conductor run starts ``plan.py`` and ``orch.py`` through this bridge; a partner that is not found
makes the first claim stop with ``BRIDGE_PARTNER_UNAVAILABLE``. The probe resolves them the way the bridge does, from
the environment it is started in (the umbrella exports the roots of the modules it found), and changes nothing.
"""
from __future__ import annotations

import json
import sys

from partners import find_orch_root, plan_argv, planner_root

CHECK = "planner-orch.partners"


def check() -> dict:
    missing = []
    if plan_argv() is None or planner_root() is None:
        missing.append("planner (set PLANNER_ROOT)")
    if find_orch_root() is None:
        missing.append("orch (set SKM_ORCH_ROOT)")
    doc = {"$schema": "urn:swissknifeman:aicore:check-result:v1", "check_id": CHECK, "category": "integration"}
    if not missing:
        return {**doc, "status": "ok", "observed": "the planner and orch are found by the bridge",
                "evidence": [f"planner: {planner_root()}", f"orch: {find_orch_root()}"]}
    return {**doc, "status": "fail", "observed": "not found by the bridge: " + ", ".join(missing),
            "remediation": "run through `swissknifeman` (it exports the roots of the modules of its hub) or set the "
                           "variables named above"}


def main() -> int:
    print(json.dumps([check()], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
