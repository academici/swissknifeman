"""check_overlap: a warning for checks that run the same tests twice (rules a-d), never an error."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_check import CheckCase, P1  # noqa: E402



def script(module, name):  # module ids are data of the lint
    return f"bash packages/{module}/scripts/{name}.sh"


VALIDATE = script("alpha", "validate")
SKIP_VALIDATE = "SKM_VALIDATE_SKIP_TESTS=1 " + VALIDATE
AFFECTED = "python3 scripts/affected-tests.py --run"
ALPHA_TEST = script("alpha", "test")


def checks(*commands):
    return [{"id": f"V{index + 10}", "cmd": cmd, "expect": "exit 0", "kind": "acceptance"}
            for index, cmd in enumerate(commands, 1)]


class OverlapCase(CheckCase):
    def item_checks(self, *commands):
        self.edit(P1 + "P1.2.json", lambda d: d.update(validation=checks(*commands)))

    def phase_checks(self, *commands):
        self.edit(P1 + "phase.json", lambda d: d.update(validation=checks(*commands)))

    def overlaps(self):
        return [i for i in self.run_check() if i.code == "check_overlap"]


class ItemRuleTests(OverlapCase):
    def test_baseline_demo_plan_has_no_overlap(self):
        self.assertEqual(self.overlaps(), [])

    def test_a_validate_with_tests_next_to_affected_tests_run(self):
        self.item_checks(VALIDATE, AFFECTED)
        hits = self.assertFound("check_overlap", "P1.2.json/validation/1", level="warning", count=1)
        self.assertEqual(len(self.overlaps()), 1)
        self.assertIn("V12 repeats the tests of V11", hits[0].message)
        self.assertIn("keep one, or run validate.sh with SKM_VALIDATE_SKIP_TESTS=1", hits[0].message)

    def test_a_validate_with_tests_next_to_the_full_test_script_in_either_order(self):
        self.item_checks(ALPHA_TEST, VALIDATE)
        self.assertFound("check_overlap", "P1.2.json/validation/1", level="warning", count=1)
        self.item_checks(VALIDATE, ALPHA_TEST)
        self.assertFound("check_overlap", "P1.2.json/validation/1", level="warning", count=1)

    def test_a_skipping_validate_does_not_repeat_the_tests(self):
        self.item_checks(SKIP_VALIDATE, AFFECTED)
        self.assertEqual(self.overlaps(), [])
        self.item_checks(AFFECTED, SKIP_VALIDATE, ALPHA_TEST)
        self.assertEqual(self.overlaps(), [])

    def test_a_affected_tests_with_a_tier_is_not_the_fast_run(self):
        self.item_checks(VALIDATE, "python3 scripts/affected-tests.py --run --tier full")
        self.assertEqual(self.overlaps(), [])

    def test_b_full_test_script_next_to_a_subset_of_the_same_module(self):
        self.item_checks(ALPHA_TEST, f"{ALPHA_TEST} -p 'test_observer_checks.py'")
        self.assertFound("check_overlap", "P1.2.json/validation/1", level="warning", count=1)
        self.assertEqual(len(self.overlaps()), 1)

    def test_b_subset_first_then_full_names_the_later_check(self):
        self.item_checks(f"{ALPHA_TEST} -p 'test_a.py'", ALPHA_TEST)
        self.assertFound("check_overlap", "P1.2.json/validation/1", level="warning", count=1)

    def test_two_subsets_do_not_overlap(self):
        self.item_checks(f"{ALPHA_TEST} -p 'test_a.py'", f"{ALPHA_TEST} -p 'test_b.py'")
        self.assertEqual(self.overlaps(), [])

    def test_different_modules_do_not_overlap(self):
        self.item_checks(VALIDATE, "bash packages/beta/scripts/test.sh")
        self.assertEqual(self.overlaps(), [])
        self.item_checks(ALPHA_TEST, "bash packages/beta/scripts/test.sh -p test_check.py")
        self.assertEqual(self.overlaps(), [])


class PhaseRuleTests(OverlapCase):
    def test_c_tier_all_next_to_test_bridges(self):
        self.phase_checks("python3 scripts/affected-tests.py --run --tier all", "bash scripts/test-bridges.sh")
        hits = self.assertFound("check_overlap", "phase.json/validation/1", level="warning", count=1)
        self.assertEqual(len(self.overlaps()), 1)
        self.assertIn("V12 repeats the tests of V11", hits[0].message)

    def test_c_test_bridges_alone_or_tier_alone_is_fine(self):
        self.phase_checks("bash scripts/test-bridges.sh", "bash scripts/test-integration.sh")
        self.assertEqual(self.overlaps(), [])
        self.phase_checks("python3 scripts/affected-tests.py --run --tier all")
        self.assertEqual(self.overlaps(), [])


class SameCommandRuleTests(OverlapCase):
    def test_d_item_check_equal_to_a_check_of_its_phase(self):
        self.phase_checks("bash scripts/test-all.sh")
        self.item_checks("python3 -m unittest tests/test_config.py", " bash scripts/test-all.sh ")
        hits = self.assertFound("check_overlap", "P1.2.json/validation/1", level="warning", count=1)
        self.assertEqual(len(self.overlaps()), 1)
        self.assertIn("V12 repeats the tests of V11", hits[0].message)

    def test_d_a_different_command_is_fine(self):
        self.phase_checks("bash scripts/test-all.sh")
        self.item_checks("bash scripts/test-all.sh --quick")
        self.assertEqual(self.overlaps(), [])

    def test_the_warning_is_not_an_error(self):
        self.item_checks(VALIDATE, AFFECTED)
        self.assertEqual([i for i in self.run_check() if i.level == "error"], [])

    def test_check_overlap_tolerates_malformed_validation(self):
        self.edit(P1 + "P1.2.json", lambda d: d.update(validation=[None, 3, {"cmd": 5}, {"id": "X"}]))
        self.edit(P1 + "phase.json", lambda d: d.update(validation="x"))
        self.run_check()


if __name__ == "__main__":
    unittest.main()
