from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from orch import contracts, policies
from orch.bindings import load_capabilities
from orch.policies import PolicyError
from orch.retry import DEFAULT_ACTIONS
from orch.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
SHIPPED = ("frontend-bounded", "full", "review-only", "scout-solo", "solo")


def settings_with(*dirs: Path) -> Settings:
    return Settings(engine="native", engine_by_role={}, default_profile="solo", work_source="planner-orch",
                    capabilities_stale="warn", profiles_dirs=tuple(dirs), events_enabled=True)


def write(path: Path, doc: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc if isinstance(doc, str) else json.dumps(doc), encoding="utf-8")


class PackCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.warnings: list = []

    def shipped(self, name: str) -> dict:
        return json.loads((policies.SHIPPED_DIR / name / "policy.json").read_text(encoding="utf-8"))

    def pack(self, directory: str, name: str, policy: dict | None = None, cases: dict | None = None) -> Path:
        """An external pack ``<root>/<directory>/<name>`` that copies the shipped ``solo`` unless told otherwise."""
        folder = self.root / directory / name
        document = copy.deepcopy(policy or self.shipped("solo"))
        document["policy_id"] = name
        write(folder / "policy.json", document)
        for case, doc in (cases or {}).items():
            write(folder / "cases" / f"{case}.json", doc)
        return folder

    def ok_case(self, **changes) -> dict:
        case = {"description": "d", "input": "fixtures/exec/v1/valid/execution-input/plan-bound.json",
                "provider": "claude-code", "binding": "native",
                "expect": {"result": "ok", "stages": ["primary"], "refusals": [], "policy_decision": "allow"}}
        case.update(changes)
        return case


class ShippedTests(PackCase):
    def test_the_shipped_packs_are_the_five_profiles(self):
        found = policies.discover(settings_with(), warn=self.warnings.append)
        self.assertEqual(sorted(found), list(SHIPPED))
        self.assertEqual(self.warnings, [])

    def test_every_shipped_pack_is_valid_and_versioned(self):
        for name in SHIPPED:
            with self.subTest(name=name):
                doc = policies.load(name, settings_with())
                self.assertEqual(doc["policy_id"], name)
                self.assertRegex(doc["version"], r"^[0-9]+\.[0-9]+\.[0-9]+$")
                self.assertEqual([i for i in contracts.validate(doc, "run-policy") if i.level == "error"], [])

    def test_every_shipped_pack_has_a_success_case_and_a_refusal_case(self):
        for name in SHIPPED:
            with self.subTest(name=name):
                cases = [json.loads(p.read_text(encoding="utf-8"))
                         for p in sorted((policies.SHIPPED_DIR / name / "cases").glob("*.json"))]
                self.assertGreaterEqual(len(cases), 2)
                self.assertEqual({c["expect"]["result"] for c in cases}, {"ok", "refused"})

    def test_every_shipped_case_passes(self):
        for name in SHIPPED:
            with self.subTest(name=name):
                rows = policies.run_cases(name, settings_with())
                self.assertGreaterEqual(len(rows), 2)
                self.assertEqual([r for r in rows if r["status"] != "pass"], [])

    def test_the_fixtures_stay_as_contract_examples(self):
        for name in ("solo", "scout-solo", "frontend-bounded", "review-only"):
            with self.subTest(name=name):
                fixture = json.loads((ROOT / "fixtures" / "exec" / "v1" / "valid" / "run-policy" / f"{name}.json")
                                     .read_text(encoding="utf-8"))
                self.assertNotIn("version", fixture)

    def test_full_follows_the_design(self):
        doc = self.shipped("full")
        self.assertEqual([(s["id"], s["kind"], s["role"], s["required"]) for s in doc["stages"]],
                         [("context", "context", "deterministic", True), ("condense", "condense", "context-scout", False),
                          ("primary", "primary", "executor", True), ("checks", "checks", "deterministic", True),
                          ("review", "review", "reviewer", False), ("registrar", "registrar", "deterministic", True),
                          ("git", "git", "deterministic", True)])
        condense = doc["stages"][1]
        self.assertEqual((condense["model_class"], condense["on_unavailable"]), ("economy", "skip"))
        self.assertEqual(doc["review"], {"enabled": True, "independent_provider": True, "max_rounds": 2,
                                         "max_corrections": 1,
                                         "triage": {"role": "triager", "model_class": "implementation"}})
        self.assertEqual({k: v["action"] for k, v in doc["on_error"].items()}, DEFAULT_ACTIONS)
        self.assertEqual(doc["budgets"], {"brief_max_bytes": 65536, "packer_input_max_bytes": 262144,
                                          "stage_tokens_max": 0})
        self.assertEqual(doc["retries_budget"], {"total_max": 2})

    def test_frontend_bounded_names_a_role_that_has_a_manifest(self):
        roles = {path.stem for path in (ROOT / "roles").glob("*.json")}
        for name in SHIPPED:
            for stage in self.shipped(name)["stages"]:
                if stage["role"] != "deterministic":
                    self.assertIn({"scout": "context-scout"}.get(stage["role"], stage["role"]), roles)


class DiscoverTests(PackCase):
    def test_a_listed_folder_adds_its_packs(self):
        self.pack("extra", "custom")
        found = policies.discover(settings_with(self.root / "extra"), warn=self.warnings.append)
        self.assertEqual(sorted(found), sorted((*SHIPPED, "custom")))
        self.assertEqual(found["custom"], self.root / "extra" / "custom")

    def test_the_first_pack_of_an_id_wins_and_the_shadow_is_reported(self):
        shadow = self.pack("extra", "solo")
        found = policies.discover(settings_with(self.root / "extra"), warn=self.warnings.append)
        self.assertEqual(found["solo"], policies.SHIPPED_DIR / "solo")
        self.assertEqual(self.warnings, [f"POLICY_SHADOWED: solo in {shadow.parent} is shadowed by "
                                         f"{policies.SHIPPED_DIR}"])

    def test_between_listed_folders_the_earlier_one_wins(self):
        first, second = self.pack("a", "custom"), self.pack("b", "custom")
        found = policies.discover(settings_with(first.parent, second.parent), warn=self.warnings.append)
        self.assertEqual(found["custom"], first)
        self.assertEqual(len(self.warnings), 1)
        self.assertIn(f"shadowed by {first.parent}", self.warnings[0])

    def test_a_missing_folder_is_reported(self):
        policies.discover(settings_with(self.root / "nowhere"), warn=self.warnings.append)
        self.assertEqual(self.warnings, [f"POLICY_DIR_MISSING: {self.root / 'nowhere'} is not a folder"])

    def test_folders_that_are_not_packs_are_ignored(self):
        write(self.root / "extra" / "no-policy" / "notes.txt", "x")
        write(self.root / "extra" / "Bad_Name" / "policy.json", "{}")
        found = policies.discover(settings_with(self.root / "extra"), warn=self.warnings.append)
        self.assertEqual(sorted(found), list(SHIPPED))
        self.assertEqual(self.warnings, [])


class LoadTests(PackCase):
    def load(self, name: str) -> dict:
        return policies.load(name, settings_with(self.root / "extra"), warn=self.warnings.append)

    def refused(self, name: str) -> PolicyError:
        with self.assertRaises(PolicyError) as raised:
            self.load(name)
        return raised.exception

    def test_an_unknown_id(self):
        self.assertEqual(self.refused("nope").code, "POLICY_UNKNOWN")

    def test_the_folder_name_must_be_the_policy_id(self):
        folder = self.pack("extra", "custom")
        document = json.loads((folder / "policy.json").read_text(encoding="utf-8"))
        document["policy_id"] = "other"
        write(folder / "policy.json", document)
        error = self.refused("custom")
        self.assertEqual(error.code, "POLICY_INVALID")
        self.assertIn("differs from the pack folder", str(error))

    def test_a_policy_that_breaks_the_contract(self):
        folder = self.pack("extra", "custom")
        document = json.loads((folder / "policy.json").read_text(encoding="utf-8"))
        document["git_action"] = "push"
        write(folder / "policy.json", document)
        error = self.refused("custom")
        self.assertEqual(error.code, "POLICY_INVALID")
        self.assertTrue(error.issues)

    def test_a_pack_needs_a_version(self):
        document = self.shipped("solo")
        del document["version"]
        self.pack("extra", "custom", document)
        self.assertIn("semantic version", str(self.refused("custom")))

    def test_unreadable_json(self):
        write(self.root / "extra" / "custom" / "policy.json", "{not json")
        self.assertEqual(self.refused("custom").code, "POLICY_INVALID")

    def test_describe_reports_version_source_and_case_count(self):
        self.pack("extra", "custom", cases={"a": self.ok_case()})
        row = policies.describe("custom", settings_with(self.root / "extra"))
        self.assertEqual((row["version"], row["source"], row["cases"]), ("1.0.0", str(self.root / "extra"), 1))
        self.assertEqual(policies.describe("solo", settings_with())["source"], "shipped")


class RunCasesTests(PackCase):
    def run_pack(self, cases: dict) -> list:
        self.pack("extra", "custom", cases=cases)
        return policies.run_cases("custom", settings_with(self.root / "extra"), warn=self.warnings.append)

    def test_a_matching_case_passes(self):
        (row,) = self.run_pack({"good": self.ok_case()})
        self.assertEqual((row["policy_id"], row["case"], row["status"], row["differences"]), ("custom", "good", "pass", []))

    def test_a_mismatch_lists_each_difference(self):
        case = self.ok_case()
        case["expect"].update(stages=["scout", "primary"], policy_decision="refuse")
        (row,) = self.run_pack({"bad": case})
        self.assertEqual(row["status"], "fail")
        self.assertEqual({d["field"] for d in row["differences"]}, {"stages", "policy_decision"})
        self.assertEqual(row["differences"][0]["actual"], ["primary"])

    def test_a_refusal_is_compared_by_error_stage_and_capability(self):
        case = self.ok_case(provider="grok")
        case["expect"] = {"result": "refused", "error": "CAPABILITY_UNSUPPORTED", "stages": [],
                          "refusals": [{"stage_id": "primary", "capability": "model.set"}],
                          "policy_decision": "refuse"}
        caps = load_capabilities()
        caps[("native", "grok")]["model"]["set"] = "unknown"
        with mock.patch("orch.bindings.load_capabilities", return_value=caps):
            (row,) = self.run_pack({"refused": case})
        self.assertEqual(row["status"], "pass", row["differences"])

    def test_an_unexpected_refusal_fails_the_case(self):
        caps = load_capabilities()
        caps[("native", "grok")]["model"]["set"] = "unknown"
        with mock.patch("orch.bindings.load_capabilities", return_value=caps):
            (row,) = self.run_pack({"bad": self.ok_case(provider="grok")})
        self.assertEqual(row["status"], "fail")
        self.assertIn("result", {d["field"] for d in row["differences"]})

    def test_an_input_path_is_taken_from_the_pack_first(self):
        folder = self.pack("extra", "custom")
        source = ROOT / "fixtures" / "exec" / "v1" / "valid" / "execution-input" / "plan-bound.json"
        write(folder / "inputs" / "mine.json", source.read_text(encoding="utf-8"))
        write(folder / "cases" / "local.json", self.ok_case(input="inputs/mine.json"))
        (row,) = policies.run_cases("custom", settings_with(self.root / "extra"))
        self.assertEqual(row["status"], "pass", row["differences"])

    def test_a_missing_input_is_a_pack_error(self):
        self.pack("extra", "custom", cases={"bad": self.ok_case(input="inputs/missing.json")})
        with self.assertRaises(PolicyError) as raised:
            policies.run_cases("custom", settings_with(self.root / "extra"))
        self.assertEqual(raised.exception.code, "POLICY_INVALID")

    def test_a_pack_without_cases_fails(self):
        self.pack("extra", "custom")
        (row,) = policies.run_cases("custom", settings_with(self.root / "extra"))
        self.assertEqual((row["case"], row["status"]), (None, "fail"))

    def test_a_malformed_case_is_a_pack_error(self):
        for bad in ({"input": "x"}, {**self.ok_case(), "extra": 1}, self.ok_case(binding="tmux"),
                    {**self.ok_case(), "expect": {"result": "maybe"}}):
            with self.subTest(case=bad):
                self.pack("extra", "custom", cases={"bad": bad})
                with self.assertRaises(PolicyError) as raised:
                    policies.run_cases("custom", settings_with(self.root / "extra"))
                self.assertEqual(raised.exception.code, "POLICY_INVALID")

    def test_the_cases_do_not_write_outside_a_temporary_folder(self):
        before = sorted(p.name for p in Path.cwd().iterdir())
        self.run_pack({"good": self.ok_case()})
        self.assertEqual(before, sorted(p.name for p in Path.cwd().iterdir()))


if __name__ == "__main__":
    unittest.main()
