"""Portability (R16): one execution-input prepares on every binding without rewriting goal or checks.

The four conditions of the engine-port conformance section: a valid launch-plan per binding x provider
(native x grok is the expected ``CAPABILITY_UNSUPPORTED``), one byte-identical task block in every primary-stage
projection, a stage-result bound to the input digest, and no lifecycle phrases in any projection.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from orch import catalog, contracts
from orch.bindings import BINDINGS
from orch.contracts import LIFECYCLE_PHRASES
from orch.port import PortError, RunState
from orch.render import render_task_block

from tests.test_prepare import ROUTING, fixture, roles

ROOT = Path(__file__).resolve().parents[1]
INPUTS = (("plan-bound", "solo"), ("adhoc", "solo"), ("review-only", "review-only"))
PROVIDERS = {"native": ("claude-code", "codex", "grok"), "cao": ("claude-code", "codex", "grok"),
             "claude-only": ("claude-code",)}
EXPECTED_REFUSALS = {("native", "grok"): "model.set"}
PROJECTION_REF = ("prompt_ref", "profile_ref")


def cases():
    for input_name, policy in INPUTS:
        for binding, providers in PROVIDERS.items():
            for provider in providers:
                yield input_name, policy, binding, provider


def synthetic_trace(name: str = "native-claude-code-ok") -> list[dict]:
    lines = (ROOT / "fixtures" / "traces" / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


class PortabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.catalog = catalog.Catalog(ROUTING)

    def prepare(self, input_doc: dict, policy: str, binding: str, provider: str) -> tuple[dict, Path]:
        out = Path(self.tmp.name) / f"{binding}-{provider}-{input_doc['input_id']}"
        engine = BINDINGS[binding](out, catalog=self.catalog)
        return engine.prepare(input_doc, fixture("run-policy", policy), roles(), provider=provider), out

    def test_matrix_covers_three_bindings_and_every_input_kind(self):
        self.assertEqual(set(PROVIDERS), set(BINDINGS))
        self.assertEqual({fixture("execution-input", name)["provenance"]["kind"] for name, _ in INPUTS},
                         {"plan", "adhoc", "review"})

    def test_launch_plan_is_valid_or_the_expected_refusal(self):
        for input_name, policy, binding, provider in cases():
            with self.subTest(input=input_name, binding=binding, provider=provider):
                input_doc = fixture("execution-input", input_name)
                expected = EXPECTED_REFUSALS.get((binding, provider))
                if expected:
                    with self.assertRaises(PortError) as raised:
                        self.prepare(input_doc, policy, binding, provider)
                    self.assertEqual(raised.exception.code, "CAPABILITY_UNSUPPORTED")
                    refusals = raised.exception.data["launch_plan"]["refusals"]
                    self.assertEqual([item["capability"] for item in refusals], [expected])
                    continue
                plan, _ = self.prepare(input_doc, policy, binding, provider)
                self.assertEqual([i for i in contracts.validate(plan, "launch-plan") if i.level == "error"], [])
                self.assertEqual((plan["binding"], plan["input_digest"]), (binding, input_doc["digest"]))
                self.assertTrue(plan["stages"])

    def test_every_projection_carries_the_same_task_block_without_lifecycle_phrases(self):
        projections = 0
        for input_name, policy, binding, provider in cases():
            if (binding, provider) in EXPECTED_REFUSALS:
                continue
            with self.subTest(input=input_name, binding=binding, provider=provider):
                input_doc = fixture("execution-input", input_name)
                block = render_task_block(input_doc)
                plan, out = self.prepare(input_doc, policy, binding, provider)
                stage = plan["stages"][0]  # the primary stage of the policy
                ref = next(stage[key] for key in PROJECTION_REF if key in stage)
                text = (out / Path(ref).name).read_text(encoding="utf-8")
                self.assertIn(block, text)  # byte-for-byte: no binding rewrites goal or checks
                for phrase in LIFECYCLE_PHRASES:
                    self.assertNotIn(phrase, text)
                projections += 1
        self.assertEqual(projections, len(INPUTS) * 6)

    def test_stage_result_from_synthetic_trace_is_bound_to_the_input_digest(self):
        state = RunState("synthetic-run")
        for event in synthetic_trace():
            state.apply(event)
        state.close()
        for input_name, _ in INPUTS:
            with self.subTest(input=input_name):
                input_doc = fixture("execution-input", input_name)
                result = state.stage_result("primary", role="executor", requested_route=input_doc["route"]["minimum"],
                                            input_digest=input_doc["digest"], instructions_digest="1" * 64)
                self.assertEqual([i for i in contracts.validate(result, "stage-result") if i.level == "error"], [])
                self.assertEqual(result["hashes"]["input"], input_doc["digest"])


if __name__ == "__main__":
    unittest.main()
