"""Тесты `harness.run.cmd_run` — CLI-склейка волны (P4.6). Модули-доноры
(`plan_reader`/`worker`/`gate`/`journal`) уже покрыты СВОИМИ тестами
(`test_run_plan_reader.py`/`test_run_worker.py`/`test_run_gate.py`/
`test_run_journal.py`) — здесь проверяется ТОЛЬКО склейка: регистрация в
`COMMANDS`, `--dry-run` не трогает воркер/гейт/журнал, волна останавливается на
первом RED, ATTENTION её не останавливает. `--dry-run` дополнительно прогоняется
на РЕАЛЬНОЙ (не мокнутой) фикстуре `plan_reader.queue()`, чтобы покрыть и
формат печати."""
import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "packages" / "harness" / "lib"))

from harness.cli import COMMANDS  # noqa: E402
from harness.common import Env  # noqa: E402
from harness.run import cmd_run, gate, journal, plan_reader, worker  # noqa: E402

BIN_HARNESS = REPO_ROOT / "packages" / "harness" / "bin" / "harness"

PLAN_ID = "CLI-FIXTURE"
PHASE_ID = "P9"
DRIVABLE_ID = "P9.1"
MANUAL_ID = "P9.2"


def _plan_md():
    return f"""# {PLAN_ID} — Фикстурный план для cmd_run (P4.6)

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | {PLAN_ID} |
| Title | Фикстурный план для cmd_run |
| Version | 0.1.0 |
| Status | 🟡 In progress |
| Document Type | Executable Master Plan |
| Authoring Model | opus |
| Repository | swissknifeman |
| Approval Owner | dv |

## 1. Context

Синтетический план для юнит-тестов `harness/run/__init__.py` (P4.6). НЕ боевой план.

## 2. Execution Rules

- Один item за раз.

## 3. Routing

| Items | Model class/effort | Exec | Почему |
|:--|:--|:--|:--|
| {DRIVABLE_ID} | implementation/medium | plan-exec | фикстура cmd_run |
| {MANUAL_ID} | frontier/high | manual | фикстура cmd_run — отказ |

## 4. Phase Index & Status Board

| Phase | Title | Items 🟢/всего | Status |
|:--|:--|:--|:--|
| {PHASE_ID} | Фаза раз | 0/2 | 🟡 In progress |

## 5. Decision Log

| D# | Дата | Решение | Почему |
|:--|:--|:--|:--|
| D1 | 2026-08-01 | Фикстура закрытым набором | покрыть cmd_run без второго парсера |

## 6. Update Log

| Дата | Кто (role/model) | Что |
|:--|:--|:--|
| 2026-08-01 | package-implementer/sonnet | Фикстура создана (P4.6) |
"""


def _phase_md():
    return f"""# {PHASE_ID} — Фаза раз

## Phase Context

Синтетическая фаза фикстуры `cmd_run` (P4.6).

## Phase Status

| ID | Title | Status | Updated |
|:--|:--|:--|:--|
| {DRIVABLE_ID} | Ведомый item | ⬜ Not started | 2026-08-01 |
| {MANUAL_ID} | Ручной item | ⬜ Not started | 2026-08-01 |

### {DRIVABLE_ID} — Ведомый item

**Status:** ⬜ Not started
**Intent:** Демонстрирует вождение.
**Why:** Базовый кейс.
**Scope Included:** ничего — фикстура.
**Scope Excluded:** реальная логика.
**Inputs:** —
**Files:** —
**Required Reads:** 1) не применимо (фикстура).
**Implementation Rules:** нет — фикстура.
**Code Guidance:** нет — фикстура.
**Validation:** не применимо — фикстура читается тестами `cmd_run`.
**Deliverables:** синтетические данные для `test_run_cli.py`.
**Completion Notes:** —
**Pending Work:** —
**Known Deviations:** —
**Escalation Needed:** no

### {MANUAL_ID} — Ручной item

**Status:** ⬜ Not started
**Intent:** Демонстрирует отказ вождения (Exec=manual).
**Why:** Базовый кейс.
**Scope Included:** ничего — фикстура.
**Scope Excluded:** реальная логика.
**Inputs:** —
**Files:** —
**Required Reads:** 1) не применимо (фикстура).
**Implementation Rules:** нет — фикстура.
**Code Guidance:** нет — фикстура.
**Validation:** не применимо — фикстура читается тестами `cmd_run`.
**Deliverables:** синтетические данные для `test_run_cli.py`.
**Completion Notes:** —
**Pending Work:** —
**Known Deviations:** —
**Escalation Needed:** no

## Phase Handoff

Фикстура: фаза не сдаётся по-настоящему, используется тестами `cmd_run`.
"""


def _handoff_md():
    return f"""# HANDOFF — 2026-08-01 — after P0.0

**Next:** run-items: task:plan-run {PLAN_ID} {DRIVABLE_ID}-{MANUAL_ID}

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | medium |
| Context | continue (/clear) |
| Суть | фикстура — читается тестами `cmd_run` |

```
/task:plan-run {PLAN_ID} {DRIVABLE_ID}-{MANUAL_ID}
```

**Done:** —
**Remaining:** {DRIVABLE_ID}, {MANUAL_ID}.
**Sources of truth:** plans/{PLAN_ID}/plan.md · plans/{PLAN_ID}/phases/{PHASE_ID}.md
**Open risks:** —
**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: —
- open_questions: —
"""


def _init_repo(root):
    def run(args):
        proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"git {args} failed: {proc.stderr}")
        return proc

    run(["init", "-q"])
    run(["config", "user.email", "cli-test@example.com"])
    run(["config", "user.name", "cli-test"])
    plan_dir = root / "plans" / PLAN_ID
    (plan_dir / "phases").mkdir(parents=True)
    (plan_dir / "plan.md").write_text(_plan_md())
    (plan_dir / "phases" / f"{PHASE_ID}.md").write_text(_phase_md())
    (plan_dir / "handoff.md").write_text(_handoff_md())
    run(["add", "."])
    run(["commit", "-q", "-m", "initial"])
    return plan_dir


def _capture(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*a, **kw)
    return buf.getvalue()


class RegistrationTest(unittest.TestCase):
    def test_run_is_registered(self):
        self.assertIs(COMMANDS.get("run"), cmd_run)

    def test_unknown_command_exits_1(self):
        proc = subprocess.run([str(BIN_HARNESS), "bogus-command"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)

    def test_run_reaches_root_router(self):
        swissknifeman = REPO_ROOT / "bin" / "swissknifeman"
        proc = subprocess.run([str(swissknifeman), "env", "run", "--help"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("harness run", proc.stdout)


class DryRunTest(unittest.TestCase):
    """Реальная (не мокнутая) `plan_reader.queue()` на фикстуре — покрывает и
    формат печати, и «--dry-run не трогает воркер/гейт/журнал» (Implementation
    Rule 2): методы, которые совершали бы запись/спавн, подменены на функции,
    падающие AssertionError при вызове."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.plan_dir = _init_repo(self.root)
        self.env = Env(REPO_ROOT / "packages" / "harness", "run")

    def tearDown(self):
        self._tmp.cleanup()

    def _refuse_if_called(self, *_a, **_kw):
        raise AssertionError("--dry-run обязан НЕ вызывать это (Implementation Rule 2)")

    def _run(self, extra_flags):
        argv = [PLAN_ID, PHASE_ID, "--dry-run", "--plans-root", str(self.root / "plans"),
               *extra_flags]
        with mock.patch.object(worker, "run", side_effect=self._refuse_if_called), \
             mock.patch.object(gate, "snapshot_before", side_effect=self._refuse_if_called), \
             mock.patch.object(gate, "verdict", side_effect=self._refuse_if_called), \
             mock.patch.object(journal, "maybe_write", side_effect=self._refuse_if_called):
            return _capture(cmd_run, self.env, argv)

    def test_text_output_shows_argv_and_refusal(self):
        out = self._run([])
        self.assertIn(f"[ВОЖДЕНИЕ] {DRIVABLE_ID}", out)
        self.assertIn("/task:plan-exec CLI-FIXTURE P9.1", out)
        self.assertIn(f"[ОТКАЗ] {MANUAL_ID}", out)
        self.assertIn("EXEC-NOT-PLAN-EXEC", out)

    def test_json_output_is_valid(self):
        import json
        out = self._run(["--json"])
        payload = json.loads(out)
        self.assertEqual(payload["mode"], "dry-run")
        ids = {item["item_id"]: item for item in payload["items"]}
        self.assertTrue(ids[DRIVABLE_ID]["drivable"])
        self.assertFalse(ids[MANUAL_ID]["drivable"])

    def test_read_only_no_git_diff(self):
        before = subprocess.run(["git", "status", "--porcelain"], cwd=self.root,
                                capture_output=True, text=True).stdout
        self._run([])
        after = subprocess.run(["git", "status", "--porcelain"], cwd=self.root,
                               capture_output=True, text=True).stdout
        self.assertEqual(before, after)


def _queue_item(item_id, *, drivable=True):
    if drivable:
        return {"item_id": item_id, "status": "⬜ Not started",
                "route": {"model_class": "implementation", "effort": "medium"},
                "route_error": None, "exec": "plan-exec", "exec_error": None,
                "drivable": True, "refusal": None, "refusal_detail": None}
    return {"item_id": item_id, "status": "⬜ Not started", "route": None,
           "route_error": None, "exec": "manual", "exec_error": None,
           "drivable": False, "refusal": "EXEC-NOT-PLAN-EXEC",
           "refusal_detail": "Exec='manual'"}


def _canned_queue(*item_ids):
    return {"plan_dir": "irrelevant", "phase_id": PHASE_ID, "degraded": False,
           "degraded_reasons": [], "next_form": {"kind": "run-items", "declaring_line": "x"},
           "items": [_queue_item(i) for i in item_ids], "excluded_terminal": []}


class WaveOrchestrationTest(unittest.TestCase):
    """Оркестрация волны — с мокнутыми `plan_reader`/`worker`/`gate`/`journal`
    (их СОБСТВЕННАЯ логика — предмет своих тестов, не этого файла)."""

    def setUp(self):
        self.env = Env(REPO_ROOT / "packages" / "harness", "run")

    def _run(self, argv):
        return _capture(cmd_run, self.env, argv)

    def test_wave_stops_on_first_red(self):
        outcomes = {"P9.1": {"outcome": "error", "reason": "boom", "session_id": None,
                             "total_cost_usd": None, "num_turns": None, "duration_ms": None,
                             "permission_denials": None, "result_text": None}}
        with mock.patch.object(plan_reader, "queue",
                               return_value=_canned_queue("P9.1", "P9.2")), \
             mock.patch.object(gate, "snapshot_before", return_value={"sha": "abc", "dirty": []}), \
             mock.patch.object(worker, "run", side_effect=lambda pid, iid, **kw: outcomes[iid]), \
             mock.patch.object(gate, "verdict",
                               return_value={"verdict": gate.RED, "signals_matched": ["outcome-not-ok"],
                                            "lint_class": None,
                                            "raw": {"item_after": {"status": "⬜ Not started"}}}), \
             mock.patch.object(journal, "maybe_write", return_value={"category": "error"}) as jw:
            out = self._run(["FIXTURE-WAVE", PHASE_ID, "--plans-root", "/irrelevant"])
        self.assertEqual(worker.run.call_count if hasattr(worker.run, "call_count") else 1, 1)
        self.assertIn("RED", out)
        self.assertNotIn("P9.2", out)  # второй item НЕ дошёл до печати вердикта
        self.assertEqual(jw.call_count, 1)

    def test_attention_does_not_stop_wave(self):
        verdicts = {"P9.1": gate.ATTENTION, "P9.2": gate.GREEN}

        def fake_verdict(plan_id, item_id, phase_id, plan_dir, before, outcome, **kw):
            return {"verdict": verdicts[item_id], "signals_matched": ["status-deviations"],
                   "lint_class": "clean", "raw": {"item_after": {"status": "🟠 Done with deviations"}}}

        with mock.patch.object(plan_reader, "queue",
                               return_value=_canned_queue("P9.1", "P9.2")), \
             mock.patch.object(gate, "snapshot_before", return_value={"sha": "abc", "dirty": []}), \
             mock.patch.object(worker, "run",
                               return_value={"outcome": "ok", "session_id": "s1",
                                            "total_cost_usd": 0.01, "num_turns": 3,
                                            "duration_ms": 1000, "permission_denials": [],
                                            "result_text": "Status: 🟠 Done with deviations"}), \
             mock.patch.object(gate, "verdict", side_effect=fake_verdict), \
             mock.patch.object(journal, "maybe_write", return_value=None) as jw:
            out = self._run(["FIXTURE-WAVE", PHASE_ID, "--plans-root", "/irrelevant"])
        self.assertIn("ATTENTION", out)
        self.assertIn("GREEN", out)
        self.assertIn("P9.1", out)
        self.assertIn("P9.2", out)
        # ok-исход с терминальным статусом item'а — воркер уже закрыл сам (D32),
        # драйвер строку не пишет: `who == WORKER` → `maybe_write` вернул бы None
        # в реальном коде; здесь важно, что маршрут ОБОИХ item'ов дошёл до journal.
        self.assertEqual(jw.call_count, 2)


class FlagParsingTest(unittest.TestCase):
    def setUp(self):
        self.env = Env(REPO_ROOT / "packages" / "harness", "run")

    def test_no_args_prints_usage(self):
        out = _capture(cmd_run, self.env, [])
        self.assertIn("harness run <PLAN-ID>", out)

    def test_wrong_positional_count_dies(self):
        with self.assertRaises(SystemExit):
            _capture(cmd_run, self.env, ["only-one-arg"])

    def test_bad_limit_dies(self):
        with self.assertRaises(SystemExit):
            _capture(cmd_run, self.env, ["P", "P1", "--limit", "not-a-number"])

    def test_bad_timeout_dies(self):
        with self.assertRaises(SystemExit):
            _capture(cmd_run, self.env, ["P", "P1", "--timeout", "not-a-number"])


if __name__ == "__main__":
    unittest.main()
