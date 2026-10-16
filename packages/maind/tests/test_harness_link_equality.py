"""Provider-file bytes and lock records must equal the capture taken before the harness link moved.

``fixtures/harness-link-before-v1.json`` came from the in-process link (harness imported by maind).
Now maind reaches harness through its JSON commands; the same scenarios must produce the same
bytes, whether the commands are answered by the fake or by the real harness.

The d104 and d108 records were re-captured once when the generated Codex dispatcher began to read the
committed hook-modes carrier (the recorded `codex-lifecycle-fragment.json` was re-captured with it); every other
scenario is the original capture."""
import json
import unittest
from pathlib import Path

from maind.provider_deploy import (generate_conformance_report, plan_d104_bootstrap_transfer,
                                   plan_d108_operation)
from tests import harness_equality as scenarios
from tests.harness_partner import FakeHarnessCase, RealHarnessCase

BEFORE = json.loads((Path(__file__).resolve().parent / "fixtures"
                     / "harness-link-before-v1.json").read_text(encoding="utf-8"))
_PREFIX, _TOKEN = "/".join(("packages", "harness")), "@HARNESS_PKG@"


def normalized(value):
    """Round-trip through JSON with the harness package prefix and the pinned machine prefix replaced by tokens."""
    text = json.dumps(value, sort_keys=True).replace(_PREFIX, _TOKEN)
    return json.loads(text.replace(scenarios.PINNED_PACKAGES, scenarios.PINNED_TOKEN))


class EqualityChecks:
    def check(self, key, actual):
        self.assertEqual(normalized(actual), BEFORE[key])

    def test_deploy_each_provider_set(self):
        for label in scenarios.PROVIDER_SETS:
            with self.subTest(providers=label):
                self.check("deploy/" + label, scenarios.deploy_scenario(label))

    def test_d104_bootstrap_transfer(self):
        self.check("d104", scenarios.d104_scenario(plan_d104_bootstrap_transfer))

    def test_d108_operation(self):
        self.check("d108", scenarios.d108_scenario(
            lambda root, config, project_id, servers: plan_d108_operation(
                root, config, project_id, servers, expected_root=root)))

    def test_conformance_report(self):
        self.check("conformance", scenarios.conformance_scenario(generate_conformance_report))

    def test_every_captured_scenario_is_compared(self):
        self.assertEqual(sorted(BEFORE), sorted(
            ["deploy/" + label for label in scenarios.PROVIDER_SETS] + ["d104", "d108", "conformance"]))


class FakeHarnessEquality(EqualityChecks, FakeHarnessCase):
    pass


class RealHarnessEquality(EqualityChecks, RealHarnessCase):
    pass


if __name__ == "__main__":
    unittest.main()
