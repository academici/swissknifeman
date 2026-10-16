from __future__ import annotations

import unittest

from orch import contracts
from orch.effects import Verdict, check, record
from orch.port import PortError

DIGEST = "ab" * 32
KEY = "run-1:primary:git_commit:main"
EXPECTED = {"head": "1" * 40}
INTENT = {"input_digest": DIGEST, "target": "main", "expected_prior": EXPECTED}
T0, T1 = "2026-10-10T10:00:00Z", "2026-10-10T10:00:05Z"


def valid(doc):
    return [i for i in contracts.validate(doc, "effect-receipt") if i.level == "error"] == []


def call(prior, receipts=(), **extra):
    return check(effect_key=KEY, kind="git_commit", intent=INTENT, observed_prior=prior, receipts=list(receipts),
                 attempt_id="att-1", owner_epoch=2, now=T1, **extra)


class EffectCheckTests(unittest.TestCase):
    def test_matching_precondition_lets_the_effect_run(self):
        self.assertEqual(call(dict(EXPECTED)), Verdict(True, None))

    def test_changed_precondition_blocks_the_effect_and_records_why(self):  # R27
        prior = {"head": "2" * 40}
        verdict = call(prior)
        self.assertFalse(verdict.proceed)
        receipt = verdict.receipt
        self.assertTrue(valid(receipt))
        self.assertEqual(receipt["outcome"], "failed")
        self.assertTrue(receipt["precondition_checked"])
        self.assertEqual(receipt["precondition"], {"checked_at": T1, "matched": False, "observed_prior": prior,
                                                   "reason_code": "PRECONDITION_CHANGED"})
        self.assertEqual(receipt["result"], {"reason": "PRECONDITION_CHANGED"})
        self.assertEqual((receipt["effect_key"], receipt["attempt_id"], receipt["owner_epoch"], receipt["recorded_at"]),
                         (KEY, "att-1", 2, T1))

    def test_applied_receipt_makes_a_repeat_already_applied(self):
        applied = record(effect_key=KEY, kind="git_commit", intent=INTENT, outcome="applied",
                         observed_prior=dict(EXPECTED), now=T0)
        verdict = call({"head": "3" * 40}, [applied])  # the prior state moved on after the effect
        self.assertEqual((verdict.proceed, verdict.receipt["outcome"]), (False, "already_applied"))
        self.assertTrue(valid(verdict.receipt))
        self.assertFalse(verdict.receipt["precondition_checked"])
        again = call(dict(EXPECTED), [verdict.receipt])
        self.assertEqual((again.proceed, again.receipt["outcome"]), (False, "already_applied"))

    def test_unknown_receipt_asks_for_reconciliation(self):
        unknown = record(effect_key=KEY, kind="git_commit", intent=INTENT, outcome="unknown",
                         reconcile_method="git_rev_parse", now=T0)
        self.assertEqual(call(dict(EXPECTED), [unknown]), Verdict(False, None))

    def test_applied_wins_over_an_earlier_unknown(self):
        receipts = [record(effect_key=KEY, kind="git_commit", intent=INTENT, outcome="unknown",
                           reconcile_method="git_rev_parse", now=T0),
                    record(effect_key=KEY, kind="git_commit", intent=INTENT, outcome="applied", now=T0)]
        self.assertEqual(call(dict(EXPECTED), receipts).receipt["outcome"], "already_applied")

    def test_receipts_of_other_effects_do_not_count(self):
        other = record(effect_key="run-1:primary:git_commit:other", kind="git_commit", intent=INTENT,
                       outcome="applied", now=T0)
        self.assertTrue(call(dict(EXPECTED), [other]).proceed)

    def test_an_invalid_receipt_of_the_effect_is_refused(self):
        with self.assertRaises(PortError) as caught:
            call(dict(EXPECTED), [{"effect_key": KEY, "outcome": "applied"}])
        self.assertEqual(caught.exception.code, "INPUT_INVALID")

    def test_receipts_are_not_modified(self):
        applied = record(effect_key=KEY, kind="git_commit", intent=INTENT, outcome="applied", now=T0)
        snapshot = dict(applied)
        call(dict(EXPECTED), [applied])
        self.assertEqual(applied, snapshot)


class EffectRecordTests(unittest.TestCase):
    def test_applied_after_a_matched_check_records_the_precondition(self):
        receipt = record(effect_key=KEY, kind="git_commit", intent=INTENT, outcome="applied",
                         result={"commit": "4" * 40}, observed_prior=dict(EXPECTED), attempt_id="att-1", now=T0)
        self.assertTrue(valid(receipt))
        self.assertEqual(receipt["precondition"], {"checked_at": T0, "matched": True, "observed_prior": EXPECTED})
        self.assertEqual(receipt["reconcile"], {"method": "none"})

    def test_a_mismatch_cannot_be_recorded_as_applied(self):
        with self.assertRaises(PortError) as caught:
            record(effect_key=KEY, kind="git_commit", intent=INTENT, outcome="applied",
                   observed_prior={"head": "9" * 40}, now=T0)
        self.assertEqual(caught.exception.code, "INPUT_INVALID")

    def test_unknown_outcome_requires_a_reconcile_method(self):
        with self.assertRaises(PortError):
            record(effect_key=KEY, kind="git_commit", intent=INTENT, outcome="unknown", now=T0)
        receipt = record(effect_key=KEY, kind="git_commit", intent=INTENT, outcome="unknown",
                         reconcile_method="git_rev_parse", now=T0)
        self.assertEqual(receipt["reconcile"], {"method": "git_rev_parse"})

    def test_without_observation_no_precondition_is_claimed(self):
        receipt = record(effect_key=KEY, kind="file_write", intent=INTENT, outcome="applied", now=T0)
        self.assertEqual((receipt["precondition_checked"], "precondition" in receipt), (False, False))


if __name__ == "__main__":
    unittest.main()
