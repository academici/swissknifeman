"""Item-local reviewer selectors cannot choose the reviewer of an entire batch."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from orch.conductor.application.review_plan import group_route
from orch.conductor.policies.routing import reviewer_selector

def route(model, strength="frontier", provider="claude-code"):
    return {"provider": provider, "model": model, "class": strength, "effort": "high"}

class GroupReviewRoutePriorityTests(unittest.TestCase):
    def test_appointed_group_priority_and_explicit_overrides(self):
        strong, weak, grok = route("opus"), route("sonnet", "implementation"), route("grok-4.7", provider="grok")
        cases = [("item:W2", "requested", strong, weak, "opus"),
                 ("item:W2", "requested", grok, strong, "grok-4.7"),
                 ("invocation:--options", "requested", strong, weak, "sonnet"),
                 ("config:orch.conductor", "requested", strong, weak, "sonnet"),
                 ("plan:example", "requested", strong, weak, "sonnet"),
                 ("phase:P1", "requested", strong, weak, "sonnet"),
                 ("item:W2", "none", strong, weak, "opus"),
                 ("item:W2", "self", strong, weak, "opus"),
                 ("item:W2", "requested", weak, weak, "sonnet")]
        for source, mode, first, last, expected in cases:
            with self.subTest(source=source, mode=mode, expected=expected), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                for ref, planned, review in (("W1", first, "requested"), ("W2", last, mode)):
                    (root / ref).mkdir()
                    (root / ref / "input.json").write_text(json.dumps({"review_mode": review, "review_route": planned}))
                owner = SimpleNamespace(directory=root, conductor={}, progress=SimpleNamespace(emit=lambda *a, **kw: None))
                item = SimpleNamespace(ref="W2", sources={"reviewer": source}, input_doc={"review_route": last},
                                       options={"reviewer": last["provider"] + "/" + last["model"] + "/high"})
                group_route(owner, 1, ["W1", "W2"], item)
                chosen = reviewer_selector(owner, item)
                self.assertEqual(chosen[0]["model"], expected)
                if source.startswith(("config:", "invocation:")):
                    self.assertEqual(chosen[2], source)
