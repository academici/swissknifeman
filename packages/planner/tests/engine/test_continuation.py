"""Continuation of an in-progress item to correct review findings: start --continue correction and route.correction."""
import copy
import hashlib
import json
import subprocess
import unittest
from pathlib import Path

from test_evidence import EvidenceCase, OPUS, lifecycle, ops
from planner.plan import schema  # noqa: E402 — test_evidence puts lib on sys.path

HAIKU = {"provider": "claude-code", "model": "claude-haiku-4-5-20251001", "effort": "medium"}
SONNET = {"provider": "claude-code", "model": "claude-sonnet-5-5", "effort": "high"}
KEY = "fk-" + "a" * 16
OTHER_KEY = "fk-" + "b" * 16
ROUTE = {"class": "implementation", "effort": "high"}
CORRECTION = {"class": "economy", "effort": "medium"}


class ContinuationCase(EvidenceCase):
    """P1.1 started by OPUS/session-a; its route is implementation/high with an optional economy/medium correction."""

    def setUp(self):
        super().setUp()
        self.git("init", "-q")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        (self.repo / "a.py").write_text("base\n")
        self.git("add", "a.py")
        self.git("commit", "-qm", "base")
        (self.repo / "a.py").write_text("reviewed\n")
        self.owner = {**OPUS, "session": "session-a"}
        self.set_route(ROUTE | {"correction": CORRECTION})
        lifecycle.start(self.root, ["P1.1"], self.owner)
        self.receipt = json.loads((Path(__file__).resolve().parents[2] /
                                   "schemas/plan/v1/examples/valid/review-receipt.json").read_text())
        self.receipt.update(subject="PLAN1.P1.1", item="P1.1", base=self.git("rev-parse", "HEAD").strip(), round=1,
                            verdict="ATTENTION", open={"blocker": 0, "major": 1},
                            findings=[{"key": KEY, "id": "F1", "severity": "Major", "location": "a.py:1",
                                       "status": "confirmed"},
                                      {"key": OTHER_KEY, "id": "F2", "severity": "Minor", "location": "a.py:2",
                                       "status": "confirmed"}])
        self.receipt.pop("attempt_id")
        self.receipt["candidate"] = self.candidate(["a.py"])
        self.save()
        self.path = "@plan/artifacts/review-receipt.json"

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True, check=True).stdout

    def candidate(self, names):
        paths = {p: lifecycle._path_fingerprint(self.repo, p) for p in sorted(names)}
        digest = hashlib.sha256("\n".join(f"{p}\t{v}" for p, v in paths.items()).encode()).hexdigest()
        return {"head": self.git("rev-parse", "HEAD").strip(), "digest": "sha256:" + digest, "paths": paths}

    def save(self):
        target = self.root / "artifacts/review-receipt.json"
        target.parent.mkdir(exist_ok=True)
        target.write_text(json.dumps(self.receipt))

    def set_route(self, route):
        ops.patch(self.load(), "P1.1", {"route": route})

    def owner_haiku(self):
        """Haiku in the session that holds the item: ownership is not the question of these tests."""
        return {**HAIKU, "session": "session-a"}

    def start_events(self):
        return [e for e in lifecycle.store.read_log(self.root) if e["type"] == "start"]

    def route(self):
        return self.load().items["P1.1"]["route"]


class StartContinuationTests(ContinuationCase):
    def test_a_continuation_needs_an_item_in_progress(self):
        self.refused("CONTINUATION_INVALID", lifecycle.start, ["P1.2"], {**HAIKU, "session": "s"},
                     continue_kind="correction", receipt=self.path)

    def test_b_a_receipt_without_open_findings_is_refused(self):
        for changes in ({"findings": [], "open": {"blocker": 0, "major": 0}},
                        {"findings": [dict(self.receipt["findings"][0], status="corrected")],
                         "open": {"blocker": 0, "major": 0}},
                        {"findings": [dict(self.receipt["findings"][1])], "open": {"blocker": 0, "major": 0}}):
            with self.subTest(changes=changes):
                original = copy.deepcopy(self.receipt)
                self.receipt.update(changes)
                self.save()
                self.refused("CONTINUATION_INVALID", lifecycle.start, ["P1.1"], self.owner_haiku(),
                             continue_kind="correction", receipt=self.path)
                self.receipt = original
                self.save()

    def test_findings_must_come_from_the_receipt(self):
        error = self.refused("CONTINUATION_INVALID", lifecycle.start, ["P1.1"], self.owner_haiku(),
                             continue_kind="correction", receipt=self.path, findings=["fk-" + "c" * 16])
        self.assertIn("fk-" + "c" * 16, str(error))

    def test_a_missing_receipt_or_one_without_a_continuation_is_refused(self):
        self.refused("CONTINUATION_INVALID", lifecycle.start, ["P1.1"], self.owner_haiku(), continue_kind="correction")
        self.refused("CONTINUATION_INVALID", lifecycle.start, ["P1.1"], self.owner_haiku(), receipt=self.path)
        self.refused("REVIEW_RECEIPT_INVALID", lifecycle.start, ["P1.1"], self.owner_haiku(),
                     continue_kind="correction", receipt="@plan/artifacts/missing.json")
        self.receipt["subject"] = "PLAN1.P1.2"
        self.save()
        self.refused("REVIEW_RECEIPT_SUBJECT", lifecycle.start, ["P1.1"], self.owner_haiku(),
                     continue_kind="correction", receipt=self.path)

    def test_c_route_correction_admits_a_cheaper_model_and_records_the_continuation(self):
        before = self.load().items["P1.1"]["result"]
        (self.repo / "a.py").write_text("corrected\n")  # the receipt is stale by now: corrections change the tree
        result = lifecycle.start(self.root, ["P1.1"], self.owner_haiku(), continue_kind="correction",
                                 receipt=self.path)
        self.assertEqual(result.resumed, ("P1.1",))
        record = self.load().items["P1.1"]["result"]
        self.assertEqual(record["executor"], self.owner_haiku())
        self.assertEqual(record["started_at"], before["started_at"])
        self.assertEqual(record["continuation"], {
            "kind": "correction", "executor": self.owner_haiku(), "receipt": self.path,
            "findings": [KEY, OTHER_KEY], "previous_executor": self.owner})
        self.assertEqual(self.start_events()[-1]["data"]["continuation"], record["continuation"])
        self.assertEqual(schema.validate(self.load().items["P1.1"], "item"), [])

    def test_explicit_findings_narrow_the_continuation(self):
        lifecycle.start(self.root, ["P1.1"], self.owner_haiku(), continue_kind="correction", receipt=self.path,
                        findings=[OTHER_KEY])
        self.assertEqual(self.load().items["P1.1"]["result"]["continuation"]["findings"], [OTHER_KEY])

    def test_d_without_route_correction_the_route_applies(self):
        self.set_route({"correction": None})  # merge-patch: null removes the key
        self.assertNotIn("correction", self.route())
        error = self.refused("ROUTE_UNDERSHOOT", lifecycle.start, ["P1.1"], self.owner_haiku(),
                             continue_kind="correction", receipt=self.path)
        self.assertNotIn("route.correction", str(error))

    def test_e_a_new_item_is_still_checked_against_its_route(self):
        ops.patch(self.load(), "P1.2", {"route": ROUTE | {"correction": CORRECTION}})
        self.refused("ROUTE_UNDERSHOOT", lifecycle.start, ["P1.2"], HAIKU)

    def test_a_plain_resume_below_the_route_keeps_refusing_with_a_hint(self):
        error = self.refused("ROUTE_UNDERSHOOT", lifecycle.start, ["P1.1"], self.owner_haiku())
        self.assertIn("start --continue correction --receipt PATH", str(error))
        self.assertEqual(self.load().items["P1.1"]["result"]["executor"], self.owner)

    def test_f_another_session_gets_the_ownership_text_with_or_without_a_continuation(self):
        other = {**HAIKU, "session": "session-b"}
        for kwargs in ({}, {"continue_kind": "correction", "receipt": self.path}):
            with self.subTest(kwargs=kwargs):
                error = self.refused("ITEM_OWNED", lifecycle.start, ["P1.1"], other, **kwargs)
                self.assertIn("is held by session session-a (claude-code/claude-opus-5-5) since", str(error))
                self.assertIn("--take-over --actor", str(error))
                self.assertIn("ownership is per session, not per model", str(error))
        lifecycle.start(self.root, ["P1.1"], other, take_over=True, continue_kind="correction", receipt=self.path)
        record = self.load().items["P1.1"]["result"]
        self.assertEqual(record["continuation"]["previous_executor"], self.owner)
        self.assertEqual(self.start_events()[-1]["data"]["take_over"], {"previous": self.owner})

    def test_a_plain_start_ends_an_earlier_continuation(self):
        lifecycle.start(self.root, ["P1.1"], self.owner_haiku(), continue_kind="correction", receipt=self.path)
        lifecycle.start(self.root, ["P1.1"], {**OPUS, "session": "session-a"})
        self.assertNotIn("continuation", self.load().items["P1.1"]["result"])

    def test_a_continuation_names_one_item(self):
        self.refused("CONTINUATION_INVALID", lifecycle.start, ["P1.1", "P1.2"], self.owner_haiku(),
                     continue_kind="correction", receipt=self.path)


class FinishContinuationTests(ContinuationCase):
    def test_g_finish_by_the_continuing_executor_is_checked_against_route_correction(self):
        lifecycle.start(self.root, ["P1.1"], self.owner_haiku(), continue_kind="correction", receipt=self.path)
        lifecycle.finish(self.root, "P1.1", "done", checks={"V1": 0}, executed_by=self.owner_haiku())
        result = self.load().items["P1.1"]["result"]
        self.assertEqual(result["executor"], self.owner_haiku())
        self.assertEqual(result["continuation"]["kind"], "correction")

    def test_g_without_a_continuation_the_same_executor_is_undershooting(self):
        self.refused("ROUTE_UNDERSHOOT", lifecycle.finish, "P1.1", "done", checks={"V1": 0},
                     executed_by=self.owner_haiku())

    def test_another_executor_than_the_continuing_one_is_checked_against_route(self):
        lifecycle.start(self.root, ["P1.1"], self.owner_haiku(), continue_kind="correction", receipt=self.path)
        weak = {**HAIKU, "model": "claude-haiku-4-5", "effort": "low"}
        self.refused("ROUTE_UNDERSHOOT", lifecycle.finish, "P1.1", "done", checks={"V1": 0}, executed_by=weak)
        lifecycle.finish(self.root, "P1.1", "done", checks={"V1": 0}, executed_by=SONNET)

    def test_the_correction_minimum_still_binds_the_continuing_executor(self):
        self.set_route(ROUTE | {"correction": {"class": "implementation", "effort": "high"}})
        self.refused("ROUTE_UNDERSHOOT", lifecycle.start, ["P1.1"], self.owner_haiku(), continue_kind="correction",
                     receipt=self.path)
        self.set_route(ROUTE | {"correction": {"class": "economy", "effort": "medium", "model": "claude-haiku-9"}})
        self.refused("ROUTE_MISMATCH", lifecycle.start, ["P1.1"], self.owner_haiku(), continue_kind="correction",
                     receipt=self.path)

    def test_the_cli_passes_the_continuation_flags(self):
        code, out = self.run_cli("start", "P1.1", "--actor", "claude-code/claude-haiku-4-5-20251001/medium",
                                 "--session", "session-a", "--continue", "correction", "--receipt", self.path,
                                 "--findings", KEY, "--no-scout")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.load().items["P1.1"]["result"]["continuation"]["findings"], [KEY])


if __name__ == "__main__":
    unittest.main()
