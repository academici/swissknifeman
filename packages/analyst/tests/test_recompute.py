"""Тесты recompute: агрегат событий, детерминизм/восстановимость из events.ndjson,
числовая state-machine (авто ephemeral→candidate, human-gate curated, soft-деприкейт)."""
import tempfile
import unittest
from pathlib import Path

from analyst import lessons, recompute


def _mk(proj, state, *, trigger="t", action="a", tt=0, tp=0):
    L = lessons.new_lesson(trigger=trigger, action=action, scope="project:test",
                           session_id="s1", tests_total=tt, tests_passed=tp)
    lessons.save_lesson(proj, L, state)
    return L["id"]


def _ev(proj, lid, *, ts, n=1, s=1, tt=0, tp=0):
    lessons.event_append(proj, {"id": lid, "ts": ts, "sessions_total": n,
                                "sessions_success": s, "tests_total": tt, "tests_passed": tp})


class TestRecompute(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.proj = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    # ── S2: агрегат / детерминизм / восстановимость ──────────────────────────
    def test_aggregate_sums_and_days(self):
        agg = recompute.aggregate_events(
            [{"ts": "2026-06-01T00:00:00Z", "sessions_total": 10, "sessions_success": 8,
              "tests_total": 4, "tests_passed": 4},
             {"ts": "2026-06-05T00:00:00Z", "sessions_total": 5, "sessions_success": 5,
              "tests_total": 2, "tests_passed": 1}],
            "2026-06-15T00:00:00Z")
        self.assertEqual((agg["N"], agg["S"]), (15, 13))
        self.assertEqual((agg["tests_total"], agg["tests_passed"]), (6, 5))
        # days_since считается от ПОСЛЕДНЕГО события (2026-06-05 → 10 дней)
        self.assertEqual(agg["days_since"], 10)

    def test_day_bucket_floor_and_clip(self):
        self.assertEqual(recompute.day_bucket("2026-06-01T00:00:00Z", "2026-06-01T23:59:59Z"), 0)
        self.assertEqual(recompute.day_bucket("2026-06-01T00:00:00Z", "2026-06-03T12:00:00Z"), 2)
        # событие в будущем относительно now → клип к 0 (не отрицательный возраст)
        self.assertEqual(recompute.day_bucket("2026-06-05T00:00:00Z", "2026-06-01T00:00:00Z"), 0)
        # неразбор ts → 0 (защитно)
        self.assertEqual(recompute.day_bucket("мусор", "2026-06-01T00:00:00Z"), 0)

    def test_recompute_deterministic_and_recoverable(self):
        lid = _mk(self.proj, "ephemeral")
        _ev(self.proj, lid, ts="2026-06-01T00:00:00Z", n=40, s=38, tt=10, tp=10)
        now = "2026-06-01T00:00:00Z"
        recompute.recompute_project(self.proj, now)
        snap1, _ = lessons.find_lesson(self.proj, lid)
        # повторный прогон с тем же now → идентичный снапшот (восстановимо из логов)
        recompute.recompute_project(self.proj, now)
        snap2, _ = lessons.find_lesson(self.proj, lid)
        for f in ("confidence", "S_decayed", "N_decayed", "confidence_tier"):
            self.assertEqual(snap1[f], snap2[f], f)
        # снапшот — из events, а не из стартового счётчика new_lesson (был sessions_total=1)
        self.assertEqual(snap2["sessions_total"], 40)
        self.assertEqual(snap2["sessions_success"], 38)

    def test_events_append_only(self):
        lid = _mk(self.proj, "ephemeral")
        _ev(self.proj, lid, ts="2026-06-01T00:00:00Z")
        _ev(self.proj, lid, ts="2026-06-02T00:00:00Z")
        raw = Path(lessons.events_path(self.proj)).read_text(encoding="utf-8")
        self.assertEqual(raw.count("\n"), 2)
        self.assertEqual(len(lessons.read_events(self.proj)), 2)

    def test_no_events_lesson_untouched(self):
        lid = _mk(self.proj, "ephemeral")
        res = recompute.recompute_project(self.proj, "2026-06-01T00:00:00Z")
        r = next(x for x in res if x["id"] == lid)
        self.assertEqual(r["action"], "no-events")
        _l, st = lessons.find_lesson(self.proj, lid)
        self.assertEqual(st, "ephemeral")

    def test_dry_run_writes_nothing(self):
        lid = _mk(self.proj, "ephemeral")
        _ev(self.proj, lid, ts="2026-06-01T00:00:00Z", n=40, s=38, tt=10, tp=10)
        recompute.recompute_project(self.proj, "2026-06-01T00:00:00Z", dry_run=True)
        _l, st = lessons.find_lesson(self.proj, lid)
        self.assertEqual(st, "ephemeral")           # не двинулся
        self.assertNotIn("confidence", _l)           # снапшот не записан

    # ── S3: числовая state-machine ───────────────────────────────────────────
    def test_auto_ephemeral_to_candidate(self):
        lid = _mk(self.proj, "ephemeral")
        _ev(self.proj, lid, ts="2026-06-01T00:00:00Z", n=40, s=38, tt=10, tp=10)
        recompute.recompute_project(self.proj, "2026-06-01T00:00:00Z")
        _l, st = lessons.find_lesson(self.proj, lid)
        self.assertEqual(st, "candidate")
        audit = lessons.read_audit(self.proj)
        self.assertTrue(any(r["action"] == "recompute-promote" and r["by"] == "auto"
                            for r in audit))

    def test_curated_never_auto(self):
        # числа перекрывают порог curated (N≥50, conf≥0.8, passrate≥0.95) — но авто НЕЛЬЗЯ
        lid = _mk(self.proj, "candidate")
        _ev(self.proj, lid, ts="2026-06-01T00:00:00Z", n=60, s=58, tt=20, tp=20)
        res = recompute.recompute_project(self.proj, "2026-06-01T00:00:00Z")
        _l, st = lessons.find_lesson(self.proj, lid)
        self.assertEqual(st, "candidate")            # ИНВАРИАНТ: остался кандидатом
        r = next(x for x in res if x["id"] == lid)
        self.assertEqual(r["action"], "curated-ready")
        audit = lessons.read_audit(self.proj)
        self.assertTrue(any(r["action"] == "recompute-flag" and r["flag"] == "curated-ready"
                            for r in audit))

    def test_soft_deprecate_keeps_file(self):
        # кандидат с объёмом, но устаревший (decay сильный) → conf<0.6 → soft-деприкейт
        lid = _mk(self.proj, "candidate")
        _ev(self.proj, lid, ts="2026-06-01T00:00:00Z", n=40, s=38, tt=10, tp=10)
        recompute.recompute_project(self.proj, "2026-08-01T00:00:00Z")   # ~61 день
        _l, st = lessons.find_lesson(self.proj, lid)
        self.assertEqual(st, "deprecated")
        # soft: файл существует в deprecated, НЕ удалён
        p = lessons.state_dir(self.proj, "deprecated") / f"{lid}.json"
        self.assertTrue(p.is_file())

    def test_candidate_stable_stays(self):
        # conf≥0.6 (не просадка), но passrate 0.8<0.95 → curated-ready не триггерится
        # НИ при статическом, НИ при адаптивном пороге N → остаётся кандидатом.
        lid = _mk(self.proj, "candidate")
        _ev(self.proj, lid, ts="2026-06-01T00:00:00Z", n=40, s=38, tt=10, tp=8)
        res = recompute.recompute_project(self.proj, "2026-06-01T00:00:00Z")
        _l, st = lessons.find_lesson(self.proj, lid)
        self.assertEqual(st, "candidate")
        self.assertEqual(next(x for x in res if x["id"] == lid)["action"], "unchanged")

    # ── S14: адаптивные пороги N от суммарной активности проекта ──────────────
    def test_adaptive_thresholds_scaling(self):
        R = recompute
        # активный проект (Σ≥CURATED_MIN_N) → статические пороги
        self.assertEqual(R.adaptive_thresholds(50), (R.CANDIDATE_MIN_N, R.CURATED_MIN_N))
        self.assertEqual(R.adaptive_thresholds(200), (15, 50))
        # малоактивный: candidate = max(3, s//5) (формула D2), curated — та же пропорция
        self.assertEqual(R.adaptive_thresholds(40), (8, round(8 * 50 / 15)))  # (8, 27)
        self.assertEqual(R.adaptive_thresholds(10), (3, 10))                  # floor 3 → cur 10
        self.assertEqual(R.adaptive_thresholds(0), (3, 10))
        # инварианты: не выше статического; curated ≥ candidate на всём диапазоне
        for s in range(0, 60):
            c, u = R.adaptive_thresholds(s)
            self.assertLessEqual(c, R.CANDIDATE_MIN_N)
            self.assertLessEqual(u, R.CURATED_MIN_N)
            self.assertGreaterEqual(u, c)

    def test_adaptive_curated_ready_for_low_activity(self):
        # малоактивный проект (Σ=40): кандидат с N=40 набирает curated-ready под
        # адаптивным порогом (27), хотя статический 50 не был бы достигнут.
        lid = _mk(self.proj, "candidate")
        _ev(self.proj, lid, ts="2026-06-01T00:00:00Z", n=40, s=40, tt=20, tp=20)
        res = recompute.recompute_project(self.proj, "2026-06-01T00:00:00Z")
        r = next(x for x in res if x["id"] == lid)
        self.assertEqual(r["action"], "curated-ready")   # адаптивный порог сработал
        _l, st = lessons.find_lesson(self.proj, lid)
        self.assertEqual(st, "candidate")                # инвариант: авто в curated нельзя

    def test_adaptive_deterministic(self):
        # тот же events-лог + тот же now → тот же исход (адаптивный порог детерминирован)
        lid = _mk(self.proj, "candidate")
        _ev(self.proj, lid, ts="2026-06-01T00:00:00Z", n=40, s=40, tt=20, tp=20)
        r1 = recompute.recompute_project(self.proj, "2026-06-01T00:00:00Z", dry_run=True)
        r2 = recompute.recompute_project(self.proj, "2026-06-01T00:00:00Z", dry_run=True)
        self.assertEqual(r1, r2)


if __name__ == "__main__":
    unittest.main()
