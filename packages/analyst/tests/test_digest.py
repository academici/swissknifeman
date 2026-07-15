"""Тесты digest: чистые извлекатели (сигналы A/B/C/D) + защитная деградация + запись в ephemeral."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from analyst import digest, lessons


def _run_report(**over):
    rr = {
        "schema": 1,
        "session_id": "sid-123",
        "generated_at": "2026-07-01T10:00:00Z",
        "tools": {"total": 5, "by_name": {"Bash": 5}},
        "files_changed": ["/proj/src/Service.php", "/proj/tests/ServiceTest.php"],
        "tool_failures": [],
        "bash": {"tests": [], "lints": [], "failed": []},
        "workflows": [],
        "devloop": None,
        "maind": None,
    }
    rr.update(over)
    return rr


class TestExtractors(unittest.TestCase):
    def test_resolved_failure(self):
        rr = _run_report(bash={"tests": [
            {"command": "vendor/bin/pest tests/ServiceTest.php", "ok": False},
            {"command": "vendor/bin/pest tests/ServiceTest.php", "ok": True},
        ], "lints": [], "failed": []})
        cands = digest.extract_resolved_failures(rr, scope="project:proj", project="proj")
        self.assertEqual(len(cands), 1)
        c = cands[0]
        self.assertEqual(c["kind"], "gotcha")
        self.assertEqual(c["provenance"]["detector"], "resolved-failure")
        self.assertIn("test-pass", c["evidence"])
        self.assertIn("attempts:2", c["evidence"])
        # файлы/счётчики вынесены в meta (action — чистый семантический текст, S11)
        self.assertIn("ServiceTest.php", c["meta"]["files"])
        self.assertEqual(c["meta"]["attempts"], 2)
        self.assertNotIn("Уточни", c["action"])
        self.assertIn("Уточни", c["review_hint"])

    def test_failure_without_pass_is_ignored(self):
        rr = _run_report(bash={"tests": [
            {"command": "vendor/bin/pest tests/ServiceTest.php", "ok": False},
        ], "lints": [], "failed": []})
        self.assertEqual(digest.extract_resolved_failures(rr, scope="s", project="p"), [])

    def test_dissimilar_pass_not_matched(self):
        rr = _run_report(bash={"tests": [
            {"command": "vendor/bin/pest tests/ServiceTest.php", "ok": False},
            {"command": "npm run build --production", "ok": True},
        ], "lints": [], "failed": []})
        self.assertEqual(digest.extract_resolved_failures(rr, scope="s", project="p"), [])

    def test_diagnostic_command_is_not_a_resolved_failure(self):
        """Разведку хук кладёт в bash.tests по подстроке раннера (`grep vitest`, `... ||`),
        но урок из «падала→прошла» такой пары мусорный (trigger≈action). Фильтруем."""
        # тот самый полевой кейс из vaulter: `ls .bin | grep vitest ||` (fail) + доп. проба (pass)
        rr = _run_report(bash={"tests": [
            {"command": "ls node_modules/.bin/ | grep -E 'vue-tsc|vitest|vite$' ||", "ok": False},
            {"command": "ls node_modules/.bin/ | grep -E 'vue-tsc|vitest|vite$' 2>/dev/null", "ok": True},
        ], "lints": [], "failed": []})
        self.assertEqual(digest.extract_resolved_failures(rr, scope="s", project="p"), [])

    def test_real_runner_still_extracted_alongside_diagnostic(self):
        """Настоящий прогон раннера остаётся уроком, даже если рядом diagnostic-шум."""
        rr = _run_report(bash={"tests": [
            {"command": "grep -rn vitest package.json", "ok": False},        # разведка — игнор
            {"command": "vendor/bin/pest tests/FooTest.php", "ok": False},   # реальный прогон
            {"command": "vendor/bin/pest tests/FooTest.php", "ok": True},
        ], "lints": [], "failed": []})
        cands = digest.extract_resolved_failures(rr, scope="s", project="p")
        self.assertEqual(len(cands), 1)
        self.assertIn("FooTest", cands[0]["trigger"])

    def test_is_real_check_helper(self):
        self.assertTrue(digest._is_real_check("vendor/bin/pest 2>&1 | tail -4"))
        self.assertTrue(digest._is_real_check("cd x && npm test"))
        self.assertTrue(digest._is_real_check("bash scripts/validate.sh"))
        self.assertFalse(digest._is_real_check("ls .bin | grep vitest || echo NO"))
        self.assertFalse(digest._is_real_check("grep -rn pest packages/"))
        self.assertFalse(digest._is_real_check("git status --short"))

    def test_is_real_check_laravel_runners(self):
        """N2a: `php artisan test`/`sail test` — доминирующий раннер Laravel-стека
        экосистемы; до фикса `_RUNNER_EXEC` их не резолвил, сигнал A был слеп."""
        self.assertTrue(digest._is_real_check("php artisan test"))
        self.assertTrue(digest._is_real_check("php artisan test --filter Foo"))
        self.assertTrue(digest._is_real_check("sail test"))

    def test_is_real_check_guarded_pipe_is_still_a_real_run(self):
        """N2b: `||`/`| xargs` guard-паттерны реально исполняют раннер и несут его
        exit-код — блайндный отказ по факту `||` в команде терял такие resolved-failure."""
        self.assertTrue(digest._is_real_check("pytest tests/ || exit 1"))
        self.assertTrue(digest._is_real_check("printf '%s' tests/*_test.py | xargs pytest"))

    def test_workarounds(self):
        rr = _run_report(devloop={"workarounds": [
            "захардкодил лимит 100 пока нет конфига",
            "захардкодил лимит 100 пока нет конфига",  # дубль — схлопнуть
        ]})
        cands = digest.extract_workarounds(rr, scope="project:proj", project="proj")
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0]["provenance"]["detector"], "workaround")
        self.assertIn("workaround", cands[0]["evidence"])
        self.assertIn("захардкодил", cands[0]["action"])

    def test_extract_candidates_combines_and_degrades(self):
        self.assertEqual(digest.extract_candidates(None, scope="s", project="p"), [])
        self.assertEqual(digest.extract_candidates({}, scope="s", project="p"), [])
        rr = _run_report(
            bash={"tests": [
                {"command": "pytest test_x.py -k slow", "ok": False},
                {"command": "pytest test_x.py -k slow", "ok": True}],
                "lints": [], "failed": []},
            devloop={"workarounds": ["обходка X"]})
        cands = digest.extract_candidates(rr, scope="s", project="p")
        self.assertEqual(len(cands), 2)

    def test_workflow_relaunch(self):
        rr = _run_report(workflow_relaunch=[
            {"name": "wf-dterema-site-p3-api", "count": 11,
             "statuses": {"async_launched": 11}}])
        cands = digest.extract_workflow_relaunch(rr, scope="project:proj", project="proj")
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0]["provenance"]["detector"], "workflow-relaunch")
        self.assertIn("11", cands[0]["trigger"])
        self.assertIn("wf-dterema-site-p3-api", cands[0]["trigger"])
        self.assertIn("count:11", cands[0]["evidence"])

    def test_workflow_relaunch_empty_no_lesson(self):
        rr = _run_report(workflow_relaunch=[])
        self.assertEqual(digest.extract_workflow_relaunch(rr, scope="s", project="p"), [])

    def test_workflow_relaunch_via_extract_candidates(self):
        rr = _run_report(workflow_relaunch=[
            {"name": "wf-x", "count": 3, "statuses": {"async_launched": 3}}])
        cands = digest.extract_candidates(rr, scope="s", project="p")
        detectors = {c["provenance"]["detector"] for c in cands}
        self.assertIn("workflow-relaunch", detectors)


class TestExtractPathologies(unittest.TestCase):
    """Сигнал C: core.pathology.detect + правило рецидива (≥2 из последних 5 прогонов).
    detector "protected-write" — самый детерминированный (срабатывает при непустом списке,
    без порогов/долей), удобен как контрольный код для проверки самого правила рецидива."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.proj = Path(self._tmp.name)
        self.runs = self.proj / ".claude" / "runs"
        self.runs.mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, sid, mtime, hit=False):
        """Синтетический run-report на диске .claude/runs/<sid>.json с фикс. mtime
        (os.utime) — детерминированный порядок «последних 5» без гонок по времени записи."""
        rr = {"session_id": sid, "protected_writes": (["/pack/skills/x/SKILL.md"] if hit else [])}
        p = self.runs / f"{sid}.json"
        p.write_text(json.dumps(rr), encoding="utf-8")
        os.utime(p, (mtime, mtime))
        return rr

    def test_no_findings_no_lesson(self):
        current = {"session_id": "cur", "protected_writes": []}
        self.assertEqual(digest.extract_pathologies(current, self.proj), [])

    def test_single_occurrence_out_of_five_no_lesson(self):
        base = 1_800_000_000
        for i, sid in enumerate(["h1", "h2", "h3", "h4"]):
            self._write(sid, base + i, hit=False)
        current = {"session_id": "cur", "protected_writes": ["/pack/skills/x/SKILL.md"]}
        # патология только в текущем прогоне (1 из 5) — рецидива нет, урок не создаётся
        self.assertEqual(digest.extract_pathologies(current, self.proj), [])

    def test_two_occurrences_out_of_five_creates_lesson(self):
        base = 1_800_000_000
        self._write("h1", base, hit=False)
        self._write("h2", base + 1, hit=True)   # тот же код уже встречался
        self._write("h3", base + 2, hit=False)
        self._write("h4", base + 3, hit=False)
        current = {"session_id": "cur", "protected_writes": ["/pack/skills/x/SKILL.md"]}
        cands = digest.extract_pathologies(current, self.proj)
        self.assertEqual(len(cands), 1)
        c = cands[0]
        self.assertEqual(c["kind"], "gotcha")
        self.assertEqual(c["provenance"]["detector"], "protected-write")
        self.assertIn("оверрайды", c["action"])
        self.assertIn(".claude/rules/*-overrides.md", c["action"])
        self.assertIn("recurred:2/5", c["evidence"])
        self.assertIn("session:cur", c["evidence"])

    def test_window_excludes_reports_beyond_last_five(self):
        base = 1_800_000_000
        # старейший прогон (за пределами окна из 5) — с патологией, но его не должны увидеть
        self._write("stale", base, hit=True)
        self._write("h1", base + 10, hit=False)
        self._write("h2", base + 11, hit=False)
        self._write("h3", base + 12, hit=False)
        self._write("h4", base + 13, hit=False)
        current = {"session_id": "cur", "protected_writes": ["/pack/skills/x/SKILL.md"]}
        # без учёта окна было бы 2 совпадения (stale+cur); в окне последних 5 "stale" не входит →
        # рецидива нет
        self.assertEqual(digest.extract_pathologies(current, self.proj), [])

    def test_code_without_remediation_stays_signal_even_if_recurring(self):
        # no-op-run — код БЕЗ готовой ремедиации (не входит в _PATHOLOGY_REMEDIATIONS):
        # даже устойчивый рецидив (5 из 5) не должен рождать урок — это сигнал для analyze.
        base = 1_800_000_000
        noop = {"tools": {"total": 25}, "files_changed": [],
                "bash": {"tests": [], "lints": [], "failed": []}, "retrieval": {"calls": 0}}
        for i, sid in enumerate(["h1", "h2", "h3", "h4"]):
            self.runs.joinpath(f"{sid}.json").write_text(
                json.dumps(dict(noop, session_id=sid)), encoding="utf-8")
            os.utime(self.runs / f"{sid}.json", (base + i, base + i))
        current = dict(noop, session_id="cur")
        self.assertEqual(digest.extract_pathologies(current, self.proj), [])

    def test_non_dict_input_degrades(self):
        self.assertEqual(digest.extract_pathologies(None, self.proj), [])
        self.assertEqual(digest.extract_pathologies("мусор", self.proj), [])


class TestDigestCmd(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.proj = Path(self._tmp.name)
        (self.proj / ".claude" / "runs").mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_rr(self, rr, mtime=None):
        p = self.proj / ".claude" / "runs" / f"{rr['session_id']}.json"
        p.write_text(json.dumps(rr), encoding="utf-8")
        if mtime is not None:
            os.utime(p, (mtime, mtime))
        return p

    def test_digest_writes_ephemeral_and_is_idempotent(self):
        rr = _run_report(bash={"tests": [
            {"command": "vendor/bin/pest", "ok": False},
            {"command": "vendor/bin/pest", "ok": True}], "lints": [], "failed": []})
        self._write_rr(rr)
        cwd = os.getcwd()
        try:
            os.chdir(self.proj)
            from analyst.cli import main
            main([str(self.proj), "digest"])
            eph = lessons.list_lessons(str(self.proj), "ephemeral")
            self.assertEqual(len(eph), 1)
            # аудит записан
            audit = lessons.read_audit(str(self.proj))
            self.assertTrue(any(r.get("action") == "digest" for r in audit))
            # повторный digest не создаёт дубль
            main([str(self.proj), "digest"])
            self.assertEqual(len(lessons.list_lessons(str(self.proj), "ephemeral")), 1)
        finally:
            os.chdir(cwd)

    def test_recurring_pathology_becomes_lesson_via_cli_and_dedups_on_rerun(self):
        # 5 прогонов проекта (правило рецидива читает .claude/runs целиком): 3 чистых + 1
        # старый с той же патологией + текущий (самый свежий по mtime) — тоже с патологией →
        # 2 из 5 → digest должен создать урок-gotcha с detector="protected-write".
        # files_changed=[] — иначе шаблон _run_report() (files_changed непуст, tests пуст)
        # попутно триггерит СВОЙ рецидив "no-verify" и засоряет assert по чистому сигналу.
        base = 1_800_000_000
        for i, sid in enumerate(["h1", "h2", "h3"]):
            self._write_rr(_run_report(session_id=sid, protected_writes=[], files_changed=[]),
                           mtime=base + i)
        self._write_rr(_run_report(session_id="h4", files_changed=[],
                                   protected_writes=["/pack/skills/x/SKILL.md"]), mtime=base + 10)
        self._write_rr(_run_report(session_id="cur", files_changed=[],
                                   protected_writes=["/pack/skills/x/SKILL.md"]), mtime=base + 20)
        cwd = os.getcwd()
        try:
            os.chdir(self.proj)
            from analyst.cli import main
            main([str(self.proj), "digest"])
            eph = [L for L, _st in lessons.list_lessons(str(self.proj), "ephemeral")]
            self.assertEqual(len(eph), 1)
            pw = eph[0]
            self.assertEqual(pw["provenance"]["detector"], "protected-write")
            self.assertEqual(pw["kind"], "gotcha")
            self.assertIn("оверрайды", pw["action"])
            # повторный digest на том же прогоне-истории — NOOP-дедуп (не плодит второй урок)
            main([str(self.proj), "digest"])
            self.assertEqual(len(lessons.list_lessons(str(self.proj), "ephemeral")), 1)
        finally:
            os.chdir(cwd)

    def test_single_pathology_occurrence_via_cli_creates_no_lesson(self):
        # только текущий прогон несёт патологию (1 из 5) — рецидива нет, урока быть не должно.
        # files_changed=[] — исключить попутный рецидив "no-verify" из шаблона _run_report()
        # (иначе тест перестал бы проверять именно правило рецидива для одиночного кода).
        base = 1_800_000_000
        for i, sid in enumerate(["h1", "h2", "h3", "h4"]):
            self._write_rr(_run_report(session_id=sid, protected_writes=[], files_changed=[]),
                           mtime=base + i)
        self._write_rr(_run_report(session_id="cur", files_changed=[],
                                   protected_writes=["/pack/skills/x/SKILL.md"]), mtime=base + 20)
        cwd = os.getcwd()
        try:
            os.chdir(self.proj)
            from analyst.cli import main
            main([str(self.proj), "digest"])
            eph = lessons.list_lessons(str(self.proj), "ephemeral")
            self.assertEqual(eph, [])
        finally:
            os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
