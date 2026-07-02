"""Тесты ingest: ephemeral-only (enforced кодом), die-без-записи на невалидном файле,
audit-провенанс, маркер PROMOTE-CANDIDATE, семантический дедуп (NOOP)."""
import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from analyst import lessons
from analyst.common import Env
from analyst.ingest import PROMOTE_MARK, cmd_ingest, validate_findings


@contextmanager
def chdir(path):
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def payload(findings, **top):
    return {"source": "agent", "session": "s-deep", "findings": findings, **top}


def finding(**over):
    base = {"trigger": "handoff между фазами терял контекст задачи",
            "action": "передавать бриф среза в промпте следующего агента",
            "kind": "procedure"}
    base.update(over)
    return base


class TestIngest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.proj = self._tmp.name
        self.env = Env(self.proj, "ingest")

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, data, name="findings.json"):
        p = Path(self.proj) / name
        text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
        p.write_text(text, encoding="utf-8")
        return str(p)

    def _store_files(self):
        """Все файлы под .claude/analyst — для проверки «ни одной записи»."""
        d = lessons.project_dir(self.proj)
        return sorted(str(p) for p in d.rglob("*") if p.is_file()) if d.is_dir() else []

    # ── happy path: только ephemeral + audit ─────────────────────────────────
    def test_ingest_writes_ephemeral_only_with_audit(self):
        f = self._write(payload([finding()]))
        with chdir(self.proj):
            cmd_ingest(self.env, ["--file", f])
        eph = lessons.list_lessons(self.proj, "ephemeral")
        self.assertEqual(len(eph), 1)
        L, st = eph[0]
        self.assertEqual(st, "ephemeral")
        self.assertEqual(L["state"], "ephemeral")
        self.assertEqual(L["provenance"]["detector"], "agent-finding")
        self.assertEqual(L["source"], "agent")
        self.assertEqual(L["provenance"]["session_id"], "s-deep")
        self.assertIn("session:s-deep", L["evidence"])
        # ничего в других состояниях
        for other in ("candidate", "curated", "deprecated"):
            self.assertEqual(lessons.list_lessons(self.proj, other), [])
        # audit-строка существующим механизмом провенанса
        audit = lessons.read_audit(self.proj)
        self.assertTrue(any(r["action"] == "ingest" and r["id"] == L["id"]
                            and r["detector"] == "agent-finding" for r in audit))
        # events не пишем: finding — гипотеза, не верифицированный сигнал
        self.assertEqual(lessons.read_events(self.proj), [])

    def test_promote_candidate_marker_in_evidence(self):
        f = self._write(payload([finding(promote_candidate=True)]))
        with chdir(self.proj):
            cmd_ingest(self.env, ["--file", f])
        (L, _st), = lessons.list_lessons(self.proj, "ephemeral")
        self.assertIn(PROMOTE_MARK, L["evidence"])

    # ── die БЕЗ записи: невалидный JSON / схема ──────────────────────────────
    def test_broken_json_dies_without_any_write(self):
        f = self._write("{не json")
        with chdir(self.proj):
            with self.assertRaises(SystemExit):
                cmd_ingest(self.env, ["--file", f])
        self.assertEqual(self._store_files(), [])

    def test_invalid_schema_dies_without_any_write(self):
        # первый finding валиден, второй бит — валидация ЦЕЛИКОМ до побочных эффектов
        f = self._write(payload([finding(), {"trigger": "", "action": "x"}]))
        with chdir(self.proj):
            with self.assertRaises(SystemExit):
                cmd_ingest(self.env, ["--file", f])
        self.assertEqual(self._store_files(), [])

    def test_missing_file_dies(self):
        with chdir(self.proj):
            with self.assertRaises(SystemExit):
                cmd_ingest(self.env, ["--file", os.path.join(self.proj, "nope.json")])
        self.assertEqual(self._store_files(), [])

    # ── ephemeral-only / agent-finding-only — enforced кодом ─────────────────
    def test_non_ephemeral_state_dies_without_write(self):
        f = self._write(payload([finding(state="curated")]))
        with chdir(self.proj):
            with self.assertRaises(SystemExit):
                cmd_ingest(self.env, ["--file", f])
        self.assertEqual(self._store_files(), [])

    def test_foreign_detector_dies_without_write(self):
        f = self._write(payload([finding(detector="workaround")]))
        with chdir(self.proj):
            with self.assertRaises(SystemExit):
                cmd_ingest(self.env, ["--file", f])
        self.assertEqual(self._store_files(), [])

    def test_unknown_key_dies(self):
        with self.assertRaises(ValueError):
            validate_findings(payload([finding(auto_promote=True)]))

    def test_explicit_ephemeral_state_accepted(self):
        out = validate_findings(payload([finding(state="ephemeral",
                                                 detector="agent-finding")]))
        self.assertEqual(len(out), 1)

    # ── дедуп ────────────────────────────────────────────────────────────────
    def test_noop_duplicate_skipped(self):
        f = self._write(payload([finding()]))
        with chdir(self.proj):
            cmd_ingest(self.env, ["--file", f])
            cmd_ingest(self.env, ["--file", f])   # повтор — NOOP-дубль, не плодим
        self.assertEqual(len(lessons.list_lessons(self.proj, "ephemeral")), 1)

    # ── dry-run: без записей ─────────────────────────────────────────────────
    def test_dry_run_writes_nothing(self):
        f = self._write(payload([finding()]))
        with chdir(self.proj):
            cmd_ingest(self.env, ["--file", f, "--dry-run"])
        self.assertEqual(self._store_files(), [])


if __name__ == "__main__":
    unittest.main()
