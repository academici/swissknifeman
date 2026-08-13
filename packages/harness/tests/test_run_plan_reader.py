"""Тесты `harness.run.plan_reader` (P4.2). Реальные подпроцессы (`plan-lint.py`,
`task.task_contract`) гоняются на committed-фикстуре `fixtures_data/run/sample-plan/`
и на синтетических tmp-планах (`monorepo_root=REPO_ROOT` — DI, plan-lint принимает
произвольный путь `path`, нестингом под репозиторием не ограничен). Никакого
мокания подпроцессов: чёрный ящик по границе процесса (D29)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures_data" / "run"
SAMPLE_PLAN = FIXTURES_ROOT / "sample-plan"

from harness.run import plan_reader  # noqa: E402 — после настройки REPO_ROOT/FIXTURES_ROOT


_ITEM_TEMPLATE = """### {item_id} — Тестовый item

**Status:** {status}
**Intent:** Тестовый item для `test_run_plan_reader.py`.
**Why:** Нужен для юнит-теста `plan_reader`.
**Scope Included:** ничего не реализует — фикстура.
**Scope Excluded:** реальная логика.
**Inputs:** —
**Files:** —
**Required Reads:** 1) не применимо (фикстура).
**Implementation Rules:** нет — фикстура.
**Code Guidance:** нет — фикстура.
**Validation:** не применимо.
**Deliverables:** синтетические данные теста.
**Completion Notes:** —
**Pending Work:** —
**Known Deviations:** —
**Escalation Needed:** no
"""


def _write_fixture(tmp, *, plan_id, item_ids, routing_rows, next_line, layout="v2"):
    """Минимальный синтетический план `<tmp>/<plan_id>/` — один phase `P1`, все
    item'ы `🟡 In progress` (терминальный кейс уже покрыт `sample-plan`). `routing_rows`
    — готовые строки таблицы `## 3. Routing` (без заголовка/разделителя)."""
    if layout != "v2":
        raise ValueError("Harness success fixtures must use canonical Layout v2")
    from packages.harness.tests.v2_plan_fixture import write_v2_plan
    return write_v2_plan(
        Path(tmp), plan_id=plan_id, items=list(zip(item_ids, ["🟡 In progress"] * len(item_ids))),
        routing_rows=routing_rows, next_line=next_line,
    )

    plan_dir = Path(tmp) / plan_id
    phase_dir = plan_dir / "phases" / "P1" if layout == "v2" else plan_dir / "phases"
    phase_dir.mkdir(parents=True)

    total = len(item_ids)
    status_rows = "\n".join(
        f"| {iid} | Тестовый item | 🟡 In progress | 2026-08-01 |" for iid in item_ids)
    item_blocks = "\n".join(
        _ITEM_TEMPLATE.format(item_id=iid, status="🟡 In progress") for iid in item_ids)
    routing_table = "\n".join(routing_rows)

    (plan_dir / "plan.md").write_text(f"""# {plan_id} — Синтетический план теста

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | {plan_id} |
| Title | Синтетический план теста |
| Version | 0.1.0 |
| Status | 🟡 In progress |
| Last Updated | 2026-08-01 |
| Layout | {layout} |

## 1. Context

Синтетика теста `test_run_plan_reader.py`.

## 2. Execution Rules

- Один item за раз.

## 3. Routing

| Items | Model class/effort | Exec | Почему |
|:--|:--|:--|:--|
{routing_table}

## 4. Phase Index & Status Board

| Phase | Title | Items 🟢/всего | Status |
|:--|:--|:--|:--|
| P1 | Фаза раз | 0/{total} | 🟡 In progress |

## 5. Decision Log

| D# | Дата | Решение | Почему |
|:--|:--|:--|:--|
| D1 | 2026-08-01 | тест | тест |

## 6. Update Log

| Дата | Кто (role/model) | Что |
|:--|:--|:--|
| 2026-08-01 | package-implementer/sonnet | план создан |
""", encoding="utf-8")

    (phase_dir / "P1.md").write_text(f"""# P1 — Фаза раз

## Phase Context

Синтетика теста.

## Phase Status

| ID | Title | Status | Updated |
|:--|:--|:--|:--|
{status_rows}

{item_blocks}
## Phase Handoff

Синтетика теста.
""", encoding="utf-8")
    (plan_dir / "handoff.md").write_text(f"""# HANDOFF — 2026-08-01 — after {item_ids[0]}

**Next:** {next_line}

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium |
| Context | continue-root |
| Суть | тест |

````
{next_line}
````

**Done:** —
**Remaining:** —
**Sources of truth:** plan.md
**Open risks:** —
**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: —
- open_questions: —
""", encoding="utf-8")

    return plan_dir


class QueueSamplePlanTest(unittest.TestCase):
    """Canonical v2 fixture keeps queue/routing coverage on generated carriers."""

    def setUp(self):
        from packages.harness.tests.v2_plan_fixture import write_v2_plan
        self._tmp = tempfile.TemporaryDirectory()
        self.plan = write_v2_plan(
            self._tmp.name, plan_id="RUN-FIXTURE",
            items=[("P1.3", "🟡 In progress"), ("P1.1", "🟡 In progress"),
                   ("P1.2", "🟢 Done")],
            routing_rows=[
                "| P1.1 | implementation/medium | plan-exec | одиночный item |",
                "| P1.3–P1.5 | implementation/medium | plan-exec | диапазон |",
            ],
            next_line="exec-items: task:plan-exec RUN-FIXTURE P1.1",
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_order_terminal_exclusion_range_form_drivable(self):
        result = plan_reader.queue(self.plan, "P1", monorepo_root=REPO_ROOT)
        self.assertFalse(result["degraded"], result["degraded_reasons"])
        self.assertEqual([it["item_id"] for it in result["items"]], ["P1.1", "P1.3"])
        self.assertEqual(
            [e["item_id"] for e in result["excluded_terminal"]], ["P1.2"])
        self.assertEqual(result["excluded_terminal"][0]["refusal"],
                         plan_reader.ITEM_TERMINAL)
        for item in result["items"]:
            self.assertTrue(item["drivable"], item)
            self.assertIsNone(item["refusal"])
            self.assertEqual(item["exec"], "plan-exec")
            self.assertEqual(item["route"], {"model_class": "implementation", "effort": "medium"})
        self.assertEqual(result["next_form"]["kind"], "exec-items")

    def test_committed_fixture_runs_without_degradation(self):
        """Package-owned committed fixture stays independent from root plan history."""
        result = plan_reader.queue(self.plan, "P1", monorepo_root=REPO_ROOT)
        self.assertFalse(result["degraded"], result["degraded_reasons"])
        self.assertIsInstance(result["items"], list)


class ExecCellTest(unittest.TestCase):
    def test_v2_reads_next_from_handoff_with_schema_pure_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_dir = _write_fixture(
                tmp, plan_id="V2-STATE", item_ids=["P1.1"],
                routing_rows=["| P1.1 | implementation/medium | plan-exec | тест |"],
                next_line="exec-items: task:plan-exec V2-STATE P1.1", layout="v2")
            result = plan_reader.queue(plan_dir, "P1", monorepo_root=REPO_ROOT)
            state = (plan_dir / "phases" / "P1" / "P1.1.state.md").read_text(encoding="utf-8")
        self.assertFalse(result["degraded"], result["degraded_reasons"])
        self.assertEqual(result["next_form"]["kind"], "exec-items")
        self.assertEqual(result["items"][0]["next_form"]["kind"], "exec-items")
        self.assertNotIn("**Next:**", state)

    def test_v2_invalid_handoff_next_remains_undrivable(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_dir = _write_fixture(
                tmp, plan_id="V2-BAD-HANDOFF", item_ids=["P1.1"],
                routing_rows=["| P1.1 | implementation/medium | plan-exec | тест |"],
                next_line="unsupported: V2-BAD-HANDOFF P1.1", layout="v2")
            result = plan_reader.queue(plan_dir, "P1", monorepo_root=REPO_ROOT)
        self.assertTrue(result["degraded"])
        self.assertEqual(result["items"], [])
        self.assertIn("Next не соответствует", result["degraded_reasons"][0])
    def test_exec_manual_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_dir = _write_fixture(
                tmp, plan_id="EXEC-MANUAL",
                item_ids=["P1.1"],
                routing_rows=["| P1.1 | implementation/medium | manual | тест |"],
                next_line="exec-items: task:plan-exec EXEC-MANUAL P1.1")
            result = plan_reader.queue(plan_dir, "P1", monorepo_root=REPO_ROOT)
        self.assertFalse(result["degraded"], result["degraded_reasons"])
        item = result["items"][0]
        self.assertFalse(item["drivable"])
        self.assertEqual(item["refusal"], plan_reader.EXEC_NOT_PLAN_EXEC)
        self.assertEqual(item["exec"], "manual")

    def test_comma_list_items_cell_refuses_both(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_dir = _write_fixture(
                tmp, plan_id="COMMA-LIST",
                item_ids=["P1.1", "P1.2"],
                routing_rows=["| P1.1, P1.2 | implementation/medium | plan-exec | тест |"],
                next_line="exec-items: task:plan-exec COMMA-LIST P1.1")
            result = plan_reader.queue(plan_dir, "P1", monorepo_root=REPO_ROOT)
        self.assertTrue(result["degraded"])
        self.assertIn("вне закрытой грамматики", result["degraded_reasons"][0])

    def test_routing_inconsistent_at_frontier_high(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_dir = _write_fixture(
                tmp, plan_id="ROUTE-INCONSISTENT",
                item_ids=["P1.1"],
                routing_rows=["| P1.1 | frontier/high | plan-exec | тест |"],
                next_line="exec-items: task:plan-exec ROUTE-INCONSISTENT P1.1")
            result = plan_reader.queue(plan_dir, "P1", monorepo_root=REPO_ROOT)
        self.assertFalse(result["degraded"], result["degraded_reasons"])
        item = result["items"][0]
        self.assertFalse(item["drivable"])
        self.assertEqual(item["refusal"], plan_reader.ROUTING_INCONSISTENT)
        self.assertEqual(item["route"], {"model_class": "frontier", "effort": "high"})

    def test_routing_unresolved_on_malformed_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_dir = _write_fixture(
                tmp, plan_id="ROUTE-UNRESOLVED",
                item_ids=["P1.1"],
                routing_rows=["| P1.1 | notaslasheffort | plan-exec | тест |"],
                next_line="exec-items: task:plan-exec ROUTE-UNRESOLVED P1.1")
            result = plan_reader.queue(plan_dir, "P1", monorepo_root=REPO_ROOT)
        self.assertFalse(result["degraded"], result["degraded_reasons"])
        item = result["items"][0]
        self.assertFalse(item["drivable"])
        self.assertEqual(item["refusal"], plan_reader.ROUTING_UNRESOLVED)
        self.assertIsNone(item["route"])
        self.assertIsNotNone(item["route_error"])


class NextFormTest(unittest.TestCase):
    def test_legacy_next_form_is_unsupported(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_dir = _write_fixture(
                tmp, plan_id="NEXT-LEGACY",
                item_ids=["P1.1"],
                routing_rows=["| P1.1 | implementation/medium | plan-exec | тест |"],
                next_line="/task:plan-exec NEXT-LEGACY P1.1")
            result = plan_reader.queue(plan_dir, "P1", monorepo_root=REPO_ROOT)
        self.assertFalse(result["degraded"], result["degraded_reasons"])
        self.assertIsNone(result["next_form"]["kind"])
        item = result["items"][0]
        self.assertFalse(item["drivable"])
        self.assertEqual(item["refusal"], plan_reader.NEXT_FORM_UNSUPPORTED)


class DegradedTest(unittest.TestCase):
    def test_monorepo_root_not_found_is_degraded_not_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_dir = Path(tmp) / "STANDALONE"
            (plan_dir / "phases").mkdir(parents=True)
            (plan_dir / "plan.md").write_text("# STANDALONE\n", encoding="utf-8")
            result = plan_reader.queue(plan_dir, "P1")  # без monorepo_root override
        self.assertTrue(result["degraded"])
        self.assertEqual(result["items"], [])
        self.assertTrue(result["degraded_reasons"])

    def test_plan_lint_nonzero_exit_is_degraded_not_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_dir = Path(tmp) / "BROKEN"
            plan_dir.mkdir(parents=True)
            # `plan.md` без обязательных Meta-полей (SKILL §6) — валидный источник ERROR
            # у `plan-lint.py`, не сбой запуска: ровно тот класс, который §2 контракта
            # обязывает трактовать как отказ источника, а не «нечего делать».
            (plan_dir / "plan.md").write_text("# BROKEN — план без Meta\n", encoding="utf-8")
            result = plan_reader.queue(plan_dir, "P1", monorepo_root=REPO_ROOT)
        self.assertTrue(result["degraded"])
        self.assertEqual(result["items"], [])
        self.assertTrue(result["degraded_reasons"])


class RoutingMatcherDriftTest(unittest.TestCase):
    """Validation (2) P4.2: одна фикстура §3 Routing прогоняется через собственный
    матчер `plan_reader` и через `task_contract._find_routing_row` — множества
    ПОКРЫТЫХ item'ов (route резолвится / ячейка Exec резолвится) совпадают. Импорт
    `task.*` — ТОЛЬКО здесь, в тесте (не в `lib/harness/run/`, Validation (5))."""

    @classmethod
    def setUpClass(cls):
        task_lib = str(REPO_ROOT / "packages" / "task" / "lib")
        if task_lib not in sys.path:
            sys.path.insert(0, task_lib)
        from task import plan_lint, task_contract  # noqa: PLC0415
        cls.plan_lint = plan_lint
        cls.task_contract = task_contract

    def test_matcher_mirrors_task_contract_find_routing_row(self):
        plan_lines = """## 3. Routing

| Items | Model class/effort | Exec | Почему |
|:--|:--|:--|:--|
| P9.1 | implementation/medium | plan-exec | одиночная форма |
| P9.2-P9.4 | implementation/medium | plan-exec | диапазон, покрывает P9.3 |
| P9.5, P9.6 | implementation/medium | plan-exec | список через запятую — нелегален |

## 4. Дальше секция
""".splitlines()

        candidate_items = ["P9.1", "P9.3", "P9.5", "P9.6", "P9.9"]

        covered_by_plan_reader = {
            item_id for item_id in candidate_items
            if plan_reader._resolve_exec_cell(plan_lines, item_id)[0] is not None
        }

        covered_by_task_contract = set()
        for item_id in candidate_items:
            try:
                self.task_contract._find_routing_row(
                    self.plan_lint, plan_lines, item_id, routing_metadata={})
            except self.task_contract.TaskContractBuildError:
                continue
            covered_by_task_contract.add(item_id)

        self.assertEqual(covered_by_plan_reader, covered_by_task_contract)
        self.assertEqual(covered_by_plan_reader, {"P9.1", "P9.3"})


if __name__ == "__main__":
    unittest.main()
