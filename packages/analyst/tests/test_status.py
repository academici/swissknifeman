"""Tests status/compact: store summary (counters, curated-ready, promote_failed, dates)
and deterministic reduction events.ndjson (unit - which means confidence — is saved)."""
import tempfile
import unittest

from analyst import lessons, recompute, status


_seq = [0]


def _mk(proj, state, **extra):
    _seq[0] += 1
    n = _seq[0]
    L = lessons.new_lesson(trigger=f"trigger number {n}", action=f"action variant {n}",
                           scope="project:test", session_id="s1")
    L.update(extra)
    lessons.save_lesson(proj, L, state)
    return L["id"]


class TestStatus(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.proj = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_counts_by_state(self):
        _mk(self.proj, "ephemeral")
        _mk(self.proj, "candidate")
        _mk(self.proj, "candidate")
        _mk(self.proj, "curated")
        st = status.build_status(self.proj)
        self.assertEqual(st["counts"],
                         {"ephemeral": 1, "candidate": 2, "curated": 1, "deprecated": 0})
        self.assertEqual(st["total"], 4)

    def test_promote_failed_counted(self):
        _mk(self.proj, "curated", promote_failed=True)
        _mk(self.proj, "curated")
        self.assertEqual(status.build_status(self.proj)["promote_failed"], 1)

    def test_curated_ready_uses_recompute_thresholds(self):
        # candidate with numbers above the threshold curated → ready (but the transition is still human)
        _mk(self.proj, "candidate", confidence=recompute.CURATED_MIN_CONF,
            sessions_total=recompute.CURATED_MIN_N, tests_total=100, tests_passed=100)
        # candidate below volume threshold → not ready
        _mk(self.proj, "candidate", confidence=0.99, sessions_total=1,
            tests_total=1, tests_passed=1)
        self.assertEqual(status.build_status(self.proj)["curated_ready"], 1)

    def test_last_digest_and_recompute_from_audit(self):
        lessons.audit_append(self.proj, {"action": "digest", "id": "x", "ts": "2026-06-01T00:00:00Z"})
        lessons.audit_append(self.proj, {"action": "digest", "id": "y", "ts": "2026-06-03T00:00:00Z"})
        lessons.audit_append(self.proj, {"action": "recompute-promote", "id": "x",
                                         "ts": "2026-06-02T00:00:00Z"})
        st = status.build_status(self.proj)
        self.assertEqual(st["last_digest"], "2026-06-03T00:00:00Z")
        self.assertEqual(st["last_recompute"], "2026-06-02T00:00:00Z")

    def test_empty_store(self):
        st = status.build_status(self.proj)
        self.assertEqual(st["total"], 0)
        self.assertIsNone(st["last_digest"])
        self.assertIsNone(st["last_recompute"])


class TestCompact(unittest.TestCase):
    def _events(self):
        return [
            {"id": "L1", "source": "digest", "ts": "2026-06-01T00:00:00Z",
             "sessions_total": 3, "sessions_success": 2, "tests_total": 2, "tests_passed": 2},
            {"id": "L1", "source": "digest", "ts": "2026-06-05T00:00:00Z",
             "sessions_total": 4, "sessions_success": 4, "tests_total": 1, "tests_passed": 1},
            {"id": "L2", "source": "promote", "ts": "2026-06-10T00:00:00Z",
             "sessions_total": 1, "sessions_success": 1, "tests_total": 0, "tests_passed": 0},
        ]

    def _assert_same_aggregate(self, before, after, now):
        for lid in ("L1", "L2"):
            a = recompute.aggregate_events([e for e in before if e.get("id") == lid], now)
            b = recompute.aggregate_events([e for e in after if e.get("id") == lid], now)
            self.assertEqual((a["S"], a["N"], a["tests_total"], a["tests_passed"], a["days_since"]),
                             (b["S"], b["N"], b["tests_total"], b["tests_passed"], b["days_since"]),
                             f"unit {lid} sold out → confidence will change")

    def test_compact_all_preserves_aggregate(self):
        ev = self._events()
        new, stats = status.compact_events(ev, None)
        self.assertEqual(stats, {"compacted": 3, "snapshots": 2, "kept": 0})
        self._assert_same_aggregate(ev, new, "2026-07-01T00:00:00Z")
        # L1 collapsed into one snapshot with amounts and MAX ts groups
        s1 = [e for e in new if e["id"] == "L1"][0]
        self.assertEqual((s1["sessions_total"], s1["sessions_success"]), (7, 6))
        self.assertEqual(s1["ts"], "2026-06-05T00:00:00Z")
        self.assertTrue(s1["compacted"])

    def test_compact_before_keeps_recent(self):
        ev = self._events()
        new, stats = status.compact_events(ev, recompute.parse_iso("2026-06-06T00:00:00Z"))
        # both L1-events older than the boundary → collapsed; L2 later → saved as is
        self.assertEqual(stats, {"compacted": 2, "snapshots": 1, "kept": 1})
        self._assert_same_aggregate(ev, new, "2026-07-01T00:00:00Z")

    def test_compact_ignores_no_id_and_bad_ts(self):
        ev = [
            {"source": "x", "ts": "2026-06-01T00:00:00Z", "sessions_total": 1},  # no id
            {"id": "L1", "ts": "trash", "sessions_total": 1},                    # broken ts
            {"id": "L1", "ts": "2026-06-01T00:00:00Z", "sessions_total": 2, "sessions_success": 2},
        ]
        new, stats = status.compact_events(ev, None)
        self.assertEqual(stats, {"compacted": 1, "snapshots": 1, "kept": 2})

    def test_compact_empty(self):
        new, stats = status.compact_events([], None)
        self.assertEqual((new, stats["compacted"]), ([], 0))

    def test_compact_deterministic(self):
        ev = self._events()
        a, _ = status.compact_events(ev, None)
        b, _ = status.compact_events(ev, None)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
