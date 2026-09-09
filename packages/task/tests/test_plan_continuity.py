import unittest

from task.plan_continuity import ContinuityError, evaluate


class ContinuityTests(unittest.TestCase):
    def test_compatible_and_missing_telemetry_continue_in_root(self):
        for telemetry in (True, None):
            self.assertEqual(evaluate(route_attested=True, context_attested=telemetry,
                                      batch_receipt_valid=True).outcome, "continue-root")

    def test_owner_wait_and_isolated_review_are_not_cold_starts(self):
        self.assertFalse(evaluate(route_attested=True, context_attested=True,
                                  batch_receipt_valid=True, waiting_owner=True).runnable)
        self.assertEqual(evaluate(route_attested=True, context_attested=True,
                                  batch_receipt_valid=True, isolated_review=True).outcome,
                         "isolated-child-return")

    def test_cold_start_requires_named_boundary_and_checkpoint(self):
        with self.assertRaises(ContinuityError):
            evaluate(route_attested=True, context_attested=False, batch_receipt_valid=True,
                     boundary="context-insufficient")
        self.assertEqual(evaluate(route_attested=True, context_attested=False,
                                  batch_receipt_valid=True, boundary="audit-boundary",
                                  checkpoint="journal:22").outcome, "cold-start-root")

    def test_unattested_route_or_batch_is_refused(self):
        with self.assertRaises(ContinuityError):
            evaluate(route_attested=False, context_attested=True, batch_receipt_valid=True)


if __name__ == "__main__":
    unittest.main()
