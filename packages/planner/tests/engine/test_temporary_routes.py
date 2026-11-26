"""Owner-approved substitutions stay scoped to a plan and an exact route."""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from planner.plan import lifecycle
from planner.plan.model import PlanError


class TemporaryRouteTests(unittest.TestCase):
    def test_only_exact_mapping_for_the_authorized_plan_is_accepted(self):
        route = {"provider": "antigravity", "model": "claude-sonnet-5-5", "effort": "high"}
        actor = {"provider": "codex", "model": "gpt-6.1-sol", "effort": "xhigh"}
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            policy = root / "policy.json"
            policy.write_text(json.dumps({"kind": "temporary_owner_instruction", "plan_roots": [str(root)],
                "substitutions": {"antigravity/claude-sonnet-5-5/high": "codex/gpt-6.1-sol/xhigh"}}))
            with patch.dict(os.environ, {"SKM_PLANNER_TEMPORARY_ROUTES": str(policy)}):
                lifecycle.validate_route(route, actor, "P1.1", plan=SimpleNamespace(root=root))
                for other in ({**actor, "effort": "high"}, {**actor, "model": "gpt-6-astra"}):
                    with self.assertRaises(PlanError):
                        lifecycle.validate_route(route, other, "P1.1", plan=SimpleNamespace(root=root))
                with self.assertRaises(PlanError):
                    lifecycle.validate_route(route, actor, "P1.1", plan=SimpleNamespace(root=root / "other"))
                policy.unlink()
                with self.assertRaises(PlanError):
                    lifecycle.validate_route(route, actor, "P1.1", plan=SimpleNamespace(root=root))
            with patch.dict(os.environ, {}, clear=True), self.assertRaises(PlanError):
                lifecycle.validate_route(route, actor, "P1.1", plan=SimpleNamespace(root=root))
