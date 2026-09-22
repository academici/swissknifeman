import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

try:
    from .fixtures import write_valid_plan
except ImportError:
    from fixtures import write_valid_plan

from task import plan_context


class PlanContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plan = write_valid_plan(Path(self.tmp.name), "DEMO-V2", layout="v2")

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def _complete_chunks(snapshot):
        return [snapshot.chunk(member.role, offset=0,
                               limit=max(1, len(member.content)))
                for member in snapshot.members]

    def test_snapshot_has_the_exact_five_carriers_and_complete_cursor_proof(self):
        snapshot = plan_context.capture(self.plan, "P1.1")
        self.assertEqual([member.role for member in snapshot.members], [
            "plan-core", "phase-context", "item-spec", "bundle", "item-state"])
        chunks = []
        for member in snapshot.members:
            offset = 0
            while True:
                chunk = snapshot.chunk(member.role, offset=offset, limit=7)
                chunks.append(chunk)
                if chunk["complete"]:
                    self.assertEqual(chunk["terminal_marker"], plan_context.TERMINAL_MARKER)
                    break
                offset = chunk["next_offset"]
        plan_context.validate_chunks(snapshot, chunks)
        self.assertEqual(snapshot.receipt()["snapshot_sha256"], snapshot.snapshot_sha256)

    def test_gap_or_missing_terminal_marker_fails_closed(self):
        snapshot = plan_context.capture(self.plan, "P1.1")
        chunks = [snapshot.chunk(member.role, offset=0, limit=len(member.content))
                  for member in snapshot.members]
        chunks[0].pop("terminal_marker")
        with self.assertRaisesRegex(plan_context.PlanContextError, "PLAN_CONTEXT_TRUNCATED"):
            plan_context.validate_chunks(snapshot, chunks)

    def test_changed_live_member_never_replaces_snapshot_content(self):
        snapshot = plan_context.capture(self.plan, "P1.1")
        spec = self.plan / "phases" / "P1" / "P1.1.md"
        spec.write_text(spec.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
        with self.assertRaisesRegex(plan_context.PlanContextError, "PLAN_CONTEXT_DIGEST_MISMATCH"):
            snapshot.chunk("item-spec", offset=0, limit=10)

    def test_out_of_range_cursor_is_typed_truncation(self):
        snapshot = plan_context.capture(self.plan, "P1.1")
        with self.assertRaisesRegex(plan_context.PlanContextError, "PLAN_CONTEXT_TRUNCATED"):
            snapshot.chunk("bundle", offset=10**6, limit=1)

    def test_substituted_chunk_bytes_fail_even_when_metadata_is_unchanged(self):
        snapshot = plan_context.capture(self.plan, "P1.1")
        chunks = self._complete_chunks(snapshot)
        mutated = deepcopy(chunks)
        original = mutated[0]["content"]
        mutated[0]["content"] = bytes([original[0] ^ 1]) + original[1:]
        with self.assertRaisesRegex(plan_context.PlanContextError,
                                    "PLAN_CONTEXT_DIGEST_MISMATCH"):
            plan_context.validate_chunks(snapshot, mutated)

    def test_chunk_identity_offsets_and_terminal_state_are_all_snapshot_bound(self):
        snapshot = plan_context.capture(self.plan, "P1.1")
        baseline = self._complete_chunks(snapshot)

        def empty_bytes(chunks):
            chunks[0]["content"] = b""

        def wrong_end(chunks):
            chunks[0]["next_offset"] -= 1

        def wrong_path(chunks):
            chunks[0]["path"] = "phases/P9/P9.9.md"

        def wrong_digest(chunks):
            chunks[0]["member_sha256"] = "0" * 64

        def post_terminal(chunks):
            chunks.insert(1, deepcopy(chunks[0]))

        for name, mutate, code in (
            ("empty", empty_bytes, "PLAN_CONTEXT_TRUNCATED"),
            ("bad-end", wrong_end, "PLAN_CONTEXT_TRUNCATED"),
            ("wrong-path", wrong_path, "PLAN_CONTEXT_DIGEST_MISMATCH"),
            ("wrong-digest", wrong_digest, "PLAN_CONTEXT_DIGEST_MISMATCH"),
            ("post-terminal", post_terminal, "PLAN_CONTEXT_TRUNCATED"),
        ):
            with self.subTest(case=name):
                chunks = deepcopy(baseline)
                mutate(chunks)
                with self.assertRaisesRegex(plan_context.PlanContextError, code):
                    plan_context.validate_chunks(snapshot, chunks)
