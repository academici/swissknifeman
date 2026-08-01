"""Тесты `harness.run.gate` (P4.4). Git-топология тестируется на ИЗОЛИРОВАННОМ временном
git-репозитории (не на репозитории проекта) — `plan-lint.py`/`git` вызываются как
РЕАЛЬНЫЕ подпроцессы (Code Guidance «запрет второго прибора»: сам гейт линт не
пересчитывает), но дерево, которое они видят, — синтетическая фикстура, создаваемая и
коммитящаяся заново в каждом тесте (`_Repo`)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "packages" / "harness" / "lib"))

from harness.run import gate  # noqa: E402


PLAN_ID = "GATE-FIXTURE"
PHASE_ID = "P1"
ITEM_ID = "P1.1"


def _plan_md(*, done, phase_status):
    return f"""# {PLAN_ID} — Фикстурный план для gate (P4.4)

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | {PLAN_ID} |
| Title | Фикстурный план для gate |
| Version | 0.1.0 |
| Status | 🟡 In progress |
| Document Type | Executable Master Plan |
| Authoring Model | opus |
| Repository | swissknifeman |
| Approval Owner | dv |

## 1. Context

Синтетический план для юнит-тестов `harness/run/gate.py` (P4.4). НЕ боевой план.

## 2. Execution Rules

- Один item за раз.

## 3. Routing

| Items | Model class/effort | Exec | Почему |
|:--|:--|:--|:--|
| {ITEM_ID} | implementation/medium | plan-exec | фикстура гейта |

## 4. Phase Index & Status Board

| Phase | Title | Items 🟢/всего | Status |
|:--|:--|:--|:--|
| {PHASE_ID} | Фаза раз | {done}/1 | {phase_status} |

## 5. Decision Log

| D# | Дата | Решение | Почему |
|:--|:--|:--|:--|
| D1 | 2026-08-01 | Фикстура закрытым набором | покрыть gate без второго парсера |

## 6. Update Log

| Дата | Кто (role/model) | Что |
|:--|:--|:--|
| 2026-08-01 | package-implementer/sonnet | Фикстура создана (P4.4) |
"""


def _phase_md(*, status, completion_notes="—", pending_work="—", known_deviations="—",
             escalation_needed="no", escalation_blockquote=False):
    blockquote = (f"> 🔴 ESCALATION {ITEM_ID}: тестовый блок | trigger: contradictory evidence "
                 f"| нужен: plan-design\n\n") if escalation_blockquote else ""
    # D88/P10.1: закрытие 🟢/🟠 требует напечатанных кодов границ Task Contract в
    # Completion Notes — иначе `plan-lint` заводит НОВУЮ ERROR на каждом закрытии.
    if status in ("🟢 Done", "🟠 Done with deviations"):
        completion_notes = f"{completion_notes}\n\nwrite-site: pre_mutation: allow · pre_final: allow"
    return f"""# {PHASE_ID} — Фаза раз

## Phase Context

Синтетическая фаза фикстуры `gate` (P4.4).

## Phase Status

| ID | Title | Status | Updated |
|:--|:--|:--|:--|
| {ITEM_ID} | Базовый item | {status} | 2026-08-01 |

### {ITEM_ID} — Базовый item

{blockquote}**Status:** {status}
**Intent:** Демонстрирует gate.
**Why:** Базовый кейс.
**Scope Included:** ничего — фикстура.
**Scope Excluded:** реальная логика.
**Inputs:** —
**Files:** —
**Required Reads:** 1) не применимо (фикстура).
**Implementation Rules:** нет — фикстура.
**Code Guidance:** нет — фикстура.
**Validation:** не применимо — фикстура читается тестами `gate`.
**Deliverables:** синтетические данные для `test_run_gate.py`.
**Completion Notes:** {completion_notes}
**Pending Work:** {pending_work}
**Known Deviations:** {known_deviations}
**Escalation Needed:** {escalation_needed}

## Phase Handoff

Фикстура: фаза не сдаётся по-настоящему, используется тестами `gate`.
"""


def _bootstrap_handoff_md():
    """Форма-заглушка (D37, `HANDOFF_TITLE_BOOTSTRAP`) — план ещё не тронут. Отличается
    от `_handoff_md()` содержательно, чтобы «закрывающая» перезапись `handoff.md`
    гарантированно давала РЕАЛЬНЫЙ git-дифф (иначе git не считает файл «тронутым»)."""
    return f"""# HANDOFF — 2026-08-01 — after P0.0

**Next:** exec-items: task:plan-exec {PLAN_ID} {ITEM_ID}

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | medium |
| Context | continue (/clear) |
| Суть | фикстура — план ещё не тронут |

```
/task:plan-exec {PLAN_ID} {ITEM_ID}
```

**Done:** —
**Remaining:** {ITEM_ID}.
**Sources of truth:** plans/{PLAN_ID}/plan.md · plans/{PLAN_ID}/phases/{PHASE_ID}.md
**Open risks:** —
**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: —
- open_questions: —
"""


def _handoff_md():
    return f"""# HANDOFF — 2026-08-01 — after {ITEM_ID}

**Next:** run-items: task:plan-run {PLAN_ID} {ITEM_ID}

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | medium |
| Context | continue (/clear) |
| Суть | фикстура — читается тестами `gate` |

```
/task:plan-run {PLAN_ID} {ITEM_ID}
```

**Done:** фикстура создана (P4.4).
**Remaining:** ничего — план не боевой.
**Sources of truth:** plans/{PLAN_ID}/plan.md · plans/{PLAN_ID}/phases/{PHASE_ID}.md
**Open risks:** —
**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: —
- open_questions: —
"""


def _ok_outcome(**overrides):
    base = {"outcome": "ok", "permission_denials": [], "result_text": "Status: 🟢 Done"}
    base.update(overrides)
    return base


class _Repo:
    """Временный git-репозиторий с фикстурным планом `plans/GATE-FIXTURE/`."""

    def __init__(self, tmp):
        self.root = Path(tmp)
        self.plan_dir = self.root / "plans" / PLAN_ID
        self._run(["init", "-q"])
        self._run(["config", "user.email", "gate-test@example.com"])
        self._run(["config", "user.name", "gate-test"])
        # Коммит ДО того, как каталог плана вообще появился — валидный git-ref (git
        # log/show по нему работают), но `plan-lint --baseline` на нём легитимно
        # деградирует («путь отсутствует в ref — новый план?»): используется тестом
        # деградации вместо синтетического несуществующего SHA (тот ломает уже git log,
        # не только линтер).
        (self.root / ".gitkeep").write_text("")
        self._run(["add", ".gitkeep"])
        self.pre_plan_sha = self.commit("до появления каталога плана")
        (self.plan_dir / "phases").mkdir(parents=True)

    def _run(self, args, check=True):
        proc = subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True)
        if check and proc.returncode != 0:
            raise RuntimeError(f"git {args} failed: {proc.stderr}")
        return proc

    def write_plan(self, *, done=0, phase_status="🟡 In progress"):
        # Маркер-счётчик гарантирует РЕАЛЬНЫЙ git-дифф даже когда `done`/`phase_status`
        # совпадают со значениями по умолчанию (git не считает файл «тронутым» коммитом
        # без фактического изменения содержимого).
        self._plan_writes = getattr(self, "_plan_writes", 0) + 1
        text = _plan_md(done=done, phase_status=phase_status)
        text += f"\n<!-- write #{self._plan_writes} -->\n"
        (self.plan_dir / "plan.md").write_text(text)

    def write_phase(self, **kwargs):
        (self.plan_dir / "phases" / f"{PHASE_ID}.md").write_text(_phase_md(**kwargs))

    def write_handoff(self):
        (self.plan_dir / "handoff.md").write_text(_handoff_md())

    def write_bootstrap_handoff(self):
        (self.plan_dir / "handoff.md").write_text(_bootstrap_handoff_md())

    def write_scope_file(self, content="x = 1\n"):
        scope = self.root / "src" / "module.py"
        scope.parent.mkdir(parents=True, exist_ok=True)
        scope.write_text(content)
        return scope

    def add(self, *paths):
        self._run(["add", *[str(p) for p in paths]])

    def commit(self, message="fixture"):
        self._run(["commit", "-q", "-m", message])
        return self._run(["rev-parse", "HEAD"]).stdout.strip()

    def commit_bookkeeping(self, message="bookkeeping"):
        self.add(self.plan_dir / "plan.md", self.plan_dir / "phases" / f"{PHASE_ID}.md",
                 self.plan_dir / "handoff.md")
        return self.commit(message)

    def initial_commit(self):
        self.write_plan()
        self.write_phase(status="🟡 In progress")
        self.write_bootstrap_handoff()
        self.add(self.plan_dir)
        return self.commit("initial")

    def snapshot(self):
        return gate.snapshot_before(self.plan_dir)


class GateVerdictTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _Repo(self._tmp.name)
        self.repo.initial_commit()
        self.before = self.repo.snapshot()

    def tearDown(self):
        self._tmp.cleanup()

    def _verdict(self, outcome=None):
        return gate.verdict(PLAN_ID, ITEM_ID, PHASE_ID, self.repo.plan_dir, self.before,
                           outcome or _ok_outcome(), monorepo_root=REPO_ROOT)

    # --- GREEN --------------------------------------------------------------

    def test_clean_close_is_green(self):
        self.repo.write_plan(done=1, phase_status="🟢 Done")
        self.repo.write_phase(status="🟢 Done", completion_notes="Сделано.")
        self.repo.write_handoff()
        self.repo.commit_bookkeeping()
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.GREEN)
        self.assertEqual(result["signals_matched"], ["all-clear"])
        self.assertEqual(result["lint_class"], "clean")

    # --- ATTENTION ------------------------------------------------------------

    def test_status_deviations_is_attention(self):
        self.repo.write_plan(done=0, phase_status="🟡 In progress")
        self.repo.write_phase(status="🟠 Done with deviations",
                              completion_notes="Сделано с оговоркой.",
                              known_deviations="Перебор effort.")
        self.repo.write_handoff()
        self.repo.commit_bookkeeping()
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.ATTENTION)
        self.assertIn("status-deviations", result["signals_matched"])

    def test_permission_denials_is_attention(self):
        self.repo.write_plan(done=1, phase_status="🟢 Done")
        self.repo.write_phase(status="🟢 Done", completion_notes="Сделано.")
        self.repo.write_handoff()
        self.repo.commit_bookkeeping()
        result = self._verdict(_ok_outcome(permission_denials=["Bash(rm)"]))
        self.assertEqual(result["verdict"], gate.ATTENTION)
        self.assertIn("permission-denials", result["signals_matched"])

    def test_pending_work_nonempty_is_attention(self):
        self.repo.write_plan(done=1, phase_status="🟢 Done")
        self.repo.write_phase(status="🟢 Done", completion_notes="Сделано.",
                              pending_work="Один WARN линтера вне Scope.")
        self.repo.write_handoff()
        self.repo.commit_bookkeeping()
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.ATTENTION)
        self.assertIn("pending-work", result["signals_matched"])

    def test_known_deviations_nonempty_is_attention(self):
        self.repo.write_plan(done=1, phase_status="🟢 Done")
        self.repo.write_phase(status="🟢 Done", completion_notes="Сделано.",
                              known_deviations="Перебор effort (implementation/high вместо medium).")
        self.repo.write_handoff()
        self.repo.commit_bookkeeping()
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.ATTENTION)
        self.assertIn("known-deviations", result["signals_matched"])

    def test_bundle_is_attention_not_red(self):
        """D103/§5: закрытие ЗАКОММИЧЕНО, но бухгалтерия внутри коммита со Scope-путями —
        process-отклонение, не блокер."""
        self.repo.write_plan(done=1, phase_status="🟢 Done")
        self.repo.write_phase(status="🟢 Done", completion_notes="Сделано.")
        self.repo.write_handoff()
        scope = self.repo.write_scope_file()
        self.repo.add(scope, self.repo.plan_dir / "plan.md",
                      self.repo.plan_dir / "phases" / f"{PHASE_ID}.md",
                      self.repo.plan_dir / "handoff.md")
        self.repo.commit("бандл: scope + bookkeeping одним коммитом")
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.ATTENTION)
        self.assertIn("bundle", result["signals_matched"])

    def test_only_new_warning_is_attention(self):
        self.repo.write_plan(done=1, phase_status="🟢 Done")
        self.repo.write_phase(status="🟢 Done", completion_notes="Сделано.")
        self.repo.write_handoff()
        # Update Log «Что» > 300 символов — НОВАЯ WARNING линтера, ERROR не задета.
        # Строка вставляется СРАЗУ после существующей строки таблицы (контактность
        # таблицы важна для парсера plan_lint — комментарий-маркер write_plan идёт
        # ПОСЛЕ, за пределами таблицы, и не должен рвать её).
        plan_text = (self.repo.plan_dir / "plan.md").read_text()
        oversized = "x" * 320
        anchor = "| 2026-08-01 | package-implementer/sonnet | Фикстура создана (P4.4) |\n"
        plan_text = plan_text.replace(
            anchor, anchor + f"| 2026-08-01 | package-implementer/sonnet | {oversized} |\n")
        (self.repo.plan_dir / "plan.md").write_text(plan_text)
        self.repo.commit_bookkeeping()
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.ATTENTION)
        self.assertIn("lint-new-warning-only", result["signals_matched"])
        self.assertEqual(result["lint_class"], "new-warning-only")

    # --- RED ------------------------------------------------------------------

    def test_worker_timeout_is_red(self):
        self.repo.write_plan(done=1, phase_status="🟢 Done")
        self.repo.write_phase(status="🟢 Done", completion_notes="Сделано.")
        self.repo.write_handoff()
        self.repo.commit_bookkeeping()
        result = self._verdict(_ok_outcome(outcome="timeout", result_text=None))
        self.assertEqual(result["verdict"], gate.RED)
        self.assertIn("outcome-not-ok", result["signals_matched"])

    def test_worker_transport_is_red(self):
        self.repo.write_plan(done=1, phase_status="🟢 Done")
        self.repo.write_phase(status="🟢 Done", completion_notes="Сделано.")
        self.repo.write_handoff()
        self.repo.commit_bookkeeping()
        result = self._verdict(_ok_outcome(outcome="transport", result_text=None))
        self.assertEqual(result["verdict"], gate.RED)
        self.assertIn("outcome-not-ok", result["signals_matched"])

    def test_worker_quota_is_red(self):
        self.repo.write_plan(done=1, phase_status="🟢 Done")
        self.repo.write_phase(status="🟢 Done", completion_notes="Сделано.")
        self.repo.write_handoff()
        self.repo.commit_bookkeeping()
        result = self._verdict(_ok_outcome(outcome="quota", result_text=None))
        self.assertEqual(result["verdict"], gate.RED)

    def test_new_error_is_red(self):
        self.repo.write_plan(done=0, phase_status="🟡 In progress")
        # Статус — мусорная строка вне канонического enum → НОВАЯ ERROR схемы.
        self.repo.write_phase(status="🟢 СЛОМАНО")
        self.repo.write_handoff()
        self.repo.commit_bookkeeping()
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.RED)
        self.assertIn("lint-new-error", result["signals_matched"])
        self.assertEqual(result["lint_class"], "new-error-suspected")

    def test_status_blocked_is_red(self):
        self.repo.write_plan(done=0, phase_status="🔴 Blocked")
        self.repo.write_phase(status="🔴 Blocked", escalation_needed="yes",
                              escalation_blockquote=True)
        self.repo.write_handoff()
        self.repo.commit_bookkeeping()
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.RED)
        self.assertIn("status-blocked", result["signals_matched"])

    def test_escalation_needed_yes_is_red(self):
        self.repo.write_plan(done=0, phase_status="🔴 Blocked")
        self.repo.write_phase(status="🔴 Blocked", escalation_needed="yes",
                              escalation_blockquote=True)
        self.repo.write_handoff()
        self.repo.commit_bookkeeping()
        result = self._verdict()
        self.assertIn("escalation-needed-yes", result["signals_matched"])

    def test_escalation_in_report_is_red(self):
        self.repo.write_plan(done=1, phase_status="🟢 Done")
        self.repo.write_phase(status="🟢 Done", completion_notes="Сделано.")
        self.repo.write_handoff()
        self.repo.commit_bookkeeping()
        result = self._verdict(_ok_outcome(result_text="... ESCALATION-REQUIRED: P1.1 — конфликт"))
        self.assertEqual(result["verdict"], gate.RED)
        self.assertIn("escalation-in-report", result["signals_matched"])

    def test_no_commits_at_all_is_red(self):
        # Воркер «прогнан», но диапазон before..HEAD пуст — ничего не закоммичено вовсе.
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.RED)
        self.assertIn("no-commits", result["signals_matched"])

    def test_closure_not_committed_at_all_is_red(self):
        """Субслучай α/β (research/13 §2): item-коммит есть (Scope), бухгалтерия плана
        написана, но НЕ закоммичена — D103, не ATTENTION."""
        scope = self.repo.write_scope_file()
        self.repo.add(scope)
        self.repo.commit("item-коммит: только Scope")
        # Бухгалтерия правится в РАБОЧЕМ дереве, но не коммитится.
        self.repo.write_plan(done=1, phase_status="🟢 Done")
        self.repo.write_phase(status="🟢 Done", completion_notes="Сделано.")
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.RED)
        self.assertIn("closure-signature-incomplete", result["signals_matched"])

    def test_closure_partial_handoff_missing_is_red(self):
        self.repo.write_plan(done=1, phase_status="🟢 Done")
        self.repo.write_phase(status="🟢 Done", completion_notes="Сделано.")
        # handoff.md НЕ тронут вовсе — не входит в диапазонный дифф.
        self.repo.add(self.repo.plan_dir / "plan.md", self.repo.plan_dir / "phases" / f"{PHASE_ID}.md")
        self.repo.commit("bookkeeping без handoff.md")
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.RED)
        self.assertIn("closure-signature-incomplete", result["signals_matched"])
        self.assertFalse(result["raw"]["closure"]["signature_complete"])

    def test_dirty_remainder_after_clean_close_is_red(self):
        """D106: незакоммиченный остаток, которого не было «до», портит следующий item —
        RED, даже когда закрытие ЭТОГО item'а само по себе безупречно."""
        self.repo.write_plan(done=1, phase_status="🟢 Done")
        self.repo.write_phase(status="🟢 Done", completion_notes="Сделано.")
        self.repo.write_handoff()
        self.repo.commit_bookkeeping()
        # Остаток: чужая правка plan.md, оставленная НЕЗАКОММИЧЕННОЙ поверх закрытия.
        plan_path = self.repo.plan_dir / "plan.md"
        plan_path.write_text(plan_path.read_text() + "\n<!-- незакоммиченный хвост -->\n")
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.RED)
        self.assertIn("dirty-remainder", result["signals_matched"])

    def test_preexisting_foreign_diff_does_not_cause_false_red(self):
        """D106: чужой дифф, БЫВШИЙ в снимке «до», не портит вердикт закрытия."""
        foreign = self.repo.plan_dir / "foreign-owner-edit.md"
        foreign.write_text("владелец правит параллельно\n")
        before = self.repo.snapshot()  # «до» снят ПОСЛЕ появления чужого файла — он учтён
        self.repo.write_plan(done=1, phase_status="🟢 Done")
        self.repo.write_phase(status="🟢 Done", completion_notes="Сделано.")
        self.repo.write_handoff()
        self.repo.commit_bookkeeping()
        result = gate.verdict(PLAN_ID, ITEM_ID, PHASE_ID, self.repo.plan_dir, before,
                              _ok_outcome(), monorepo_root=REPO_ROOT)
        self.assertEqual(result["verdict"], gate.GREEN)
        self.assertNotIn("dirty-remainder", result["signals_matched"])

    def test_no_op_status_not_terminal_is_red(self):
        self.repo.write_plan(done=0, phase_status="🟡 In progress")
        self.repo.write_phase(status="🟡 In progress")  # статус не сдвинулся
        self.repo.write_handoff()
        self.repo.commit_bookkeeping("no-op: коммит есть, статус не сдвинулся")
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.RED)
        self.assertIn("no-op", result["signals_matched"])

    def test_totality_default_is_red(self):
        """D105: не сматчилась НИ ОДНА строка таблицы → дефолт RED, а не тихий else."""
        signals = {
            "outcome_class": "ok", "permission_denials": [], "result_text": "",
            "lint_clean": True, "lint_new_error_suspected": False, "lint_new_warning_only": False,
            "commit_count": 1, "signature_complete": True, "bundle": False,
            "dirty_remainder": [], "item_fields_available": True,
            "item_status": "⛔ Skipped by decision",  # ни GREEN, ни ATTENTION, ни известный RED
            "pending_work_nonempty": False, "known_deviations_nonempty": False,
            "escalation_needed_yes": False,
        }
        klass, matched = gate._classify(signals)
        self.assertEqual(klass, gate.RED)
        self.assertEqual(matched, ["no-signal-matched-default"])

    # --- D104: число/порядок коммитов не судятся -------------------------------

    def test_commit_count_and_order_are_not_judged(self):
        self.repo.write_plan(done=1, phase_status="🟢 Done")
        self.repo.write_phase(status="🟢 Done", completion_notes="Сделано.")
        self.repo.write_handoff()
        # Три коммита: два «атомарных» Scope + закрывающий bookkeeping.
        scope1 = self.repo.write_scope_file("x = 1\n")
        self.repo.add(scope1)
        self.repo.commit("scope-коммит 1/2")
        scope1.write_text("x = 2\n")
        self.repo.add(scope1)
        self.repo.commit("scope-коммит 2/2 (item-коммит)")
        self.repo.commit_bookkeeping("bookkeeping-коммит")
        # Review-fix ПОСЛЕ закрывающего — легален (канон §6).
        scope1.write_text("x = 3\n")
        self.repo.add(scope1)
        self.repo.commit("review-fix поверх топологии")
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.GREEN)
        self.assertEqual(result["raw"]["closure"]["commit_count"], 4)

    # --- деградация baseline -----------------------------------------------

    def test_degraded_baseline_is_not_green(self):
        self.repo.write_plan(done=1, phase_status="🟢 Done")
        self.repo.write_phase(status="🟢 Done", completion_notes="Сделано.")
        self.repo.write_handoff()
        self.repo.commit_bookkeeping()
        broken_before = dict(self.before, sha=self.repo.pre_plan_sha)
        result = gate.verdict(PLAN_ID, ITEM_ID, PHASE_ID, self.repo.plan_dir, broken_before,
                              _ok_outcome(), monorepo_root=REPO_ROOT)
        self.assertNotEqual(result["verdict"], gate.GREEN)
        self.assertEqual(result["lint_class"], "degraded")


class PreLaunchVerdictTest(unittest.TestCase):
    def test_not_drivable_is_red_without_spawning_worker(self):
        queue_item = {"item_id": ITEM_ID, "drivable": False,
                     "refusal": "EXEC-NOT-PLAN-EXEC", "refusal_detail": "Exec=manual"}
        result = gate.pre_launch_verdict(queue_item)
        self.assertEqual(result["verdict"], gate.RED)
        self.assertEqual(result["raw"]["refusal"], "EXEC-NOT-PLAN-EXEC")

    def test_drivable_item_raises(self):
        with self.assertRaises(ValueError):
            gate.pre_launch_verdict({"drivable": True})


if __name__ == "__main__":
    sys.exit(unittest.main())
