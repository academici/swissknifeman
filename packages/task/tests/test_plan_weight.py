"""unittest для task.plan_weight — вес обязательного чтения пункта (P0.3).

По классу дефекта отдельный кейс; фикстуры плана — общие `fixtures.py` (шаблоны
plan.md/phases/Pn.md/handoff.md), артефакты калибровки и лимита пишутся во временный
каталог, чтобы гейты можно было двигать по одному.
Запуск: cd packages/task && python3 -m unittest tests.test_plan_weight -v
"""
import hashlib
import io
import json
import os
import re
import tempfile
import unittest
import unittest.mock
from pathlib import Path

try:  # пакетный запуск
    from .fixtures import phase_md, write_valid_plan
except ImportError:  # прямой discovery из packages/task
    from fixtures import phase_md, write_valid_plan

import task.plan_weight as plan_weight  # noqa: E402
from task.token_estimate import CLASSIFIER  # noqa: E402
from task.plan_weight import (  # noqa: E402
    GAP_KINDS, GAP_MISSING_FILE, GAP_OVERSIZED_FILE, GAP_UNREADABLE_ROOT,
    GAP_UNRESOLVED_ENTRY, GATE_BOTH, GATE_SIZE_BYTES, GATE_TOKENS,
    MANDATORY_PATH_LITERALS, PLAN_EXEC_RELPATH, Measurer, PlanWeightError,
    dense_ascii_share, evaluate_canon_budget, expand_braces, load_canon_budget,
    load_read_limit, main, measure_document, measure_item, measure_plan, path_candidates,
    split_entries,
)

CALIBRATION = {
    "version": "2.0.0",
    "calibrated_at": "2026-08-07T00:00:00Z",
    "calibration_target": {"provider": "codex", "adapter": "codex-exec-jsonl-v1",
                           "requested_model_id": "gpt-5.6-terra",
                           "probe_protocol_version": "differential-input-total-v2",
                           "usage_semantics": "provider-reported-input-total-v1"},
    "classifier": CLASSIFIER,
    "corpus": {"files": 3, "total_bytes": 100, "sha256": "0" * 64},
    "classes": {"dense_ascii": 0.9, "ascii_word": 0.3, "ascii_other": 0.4,
                "cyrillic": 0.6, "other": 2.0},
    "per_file_overhead_tokens": 0,
    "safety_multiplier": 1.0,
    "bound": {"violations": 0, "max_true_over_estimate": 0.97},
    "tightness": {"p50": 1.05, "p95": 1.2, "max": 1.35},
}

# Оба гейта заведомо недостижимы — «зелёная» рамка, в которой ни один файл не оверсайз.
LIMITS_WIDE = {"size_bytes": 10 ** 9, "tokens": 10 ** 9}


def read_limit(size_bytes, tokens):
    """Артефакт лимита формы `research/12-…` §3 (минимум обязательных полей)."""
    return {
        "version": "1.0.0",
        "measured_at": "2026-08-07T00:00:00Z",
        "environment": {"platform": "linux", "harness": "claude-code"},
        "tool": "Read",
        "limits": {
            "size_bytes": {"value": size_bytes, "unit": "bytes", "reported_as": "x",
                           "severity": "refusal", "scope": "whole_file_read"},
            "tokens": {"value": tokens, "unit": "tokens", "counter": "harness-read-counter",
                       "severity": ["refusal", "truncation"], "scope": "rendered_read_output"},
        },
        "binding_for_plan_prose": "tokens",
    }


class MeasurerTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.calibration_path = self.root / "calibration.json"
        self.calibration_path.write_text(json.dumps(CALIBRATION), encoding="utf-8")
        self.limit_path = self.root / "read-limit.json"
        self.write_limits(**LIMITS_WIDE)

    def tearDown(self):
        self._tmp.cleanup()

    def write_limits(self, size_bytes, tokens):
        self.limit_path.write_text(json.dumps(read_limit(size_bytes, tokens)), encoding="utf-8")

    def measurer(self):
        return Measurer(calibration_path=self.calibration_path, read_limit_path=self.limit_path,
                        model_id="gpt-5.6-terra", provider_id="codex")

    def plan_with_reads(self, required_reads, plan_id="DEMO-1"):
        """Валидный план, у единственного item'а которого подменено `Required Reads`."""
        plan_dir = write_valid_plan(self.root, plan_id=plan_id)
        text = phase_md().replace("**Required Reads:** 1) lib/pkg/config.py",
                                  f"**Required Reads:** {required_reads}")
        (plan_dir / "phases" / "P1.md").write_text(text, encoding="utf-8")
        return plan_dir

    def item(self, required_reads, **kwargs):
        plan_dir = self.plan_with_reads(required_reads, **kwargs)
        plan = measure_plan(plan_dir, self.measurer())
        return plan["items"][0]

    def gaps_of(self, record, kind):
        return [g for g in record["gaps"] if g["kind"] == kind]


class TestMandatoryPath(unittest.TestCase):
    """Обязательный путь воспроизводится ИЗ текста команды, а не по памяти: правка
    `plan-exec.md` §1 обязана ломать этот тест, а не расходиться с инструментом молча."""

    def plan_exec_text(self):
        path = plan_weight._MONOREPO_ROOT / PLAN_EXEC_RELPATH
        if not path.is_file():  # standalone-раскладка пакета без монорепо-родителя
            self.skipTest(f"нет {path} — standalone-раскладка")
        return path.read_text(encoding="utf-8")

    def test_literals_present_in_order(self):
        text = self.plan_exec_text()
        positions = []
        for literal in MANDATORY_PATH_LITERALS:
            idx = text.find(literal)
            self.assertNotEqual(idx, -1, f"литерал §1 «{literal}» исчез из plan-exec.md")
            positions.append(idx)
        self.assertEqual(positions, sorted(positions),
                         "порядок обязательного пути в plan-exec.md §1 изменился")

    def test_literals_belong_to_section_1(self):
        text = self.plan_exec_text()
        start = text.find("1. **Порядок чтения")
        self.assertNotEqual(start, -1, "секция §1 «Порядок чтения» не найдена в plan-exec.md")
        end = text.find("\n2. **", start)
        section = text[start:end if end != -1 else len(text)]
        for literal in MANDATORY_PATH_LITERALS:
            self.assertIn(literal, section, f"литерал «{literal}» вне §1 — путь описан не там")


class TestArtifactsAreMandatory(MeasurerTestCase):
    """Литеральных дефолтов нет: нет артефакта — внятная ошибка и код возврата ≠ 0."""

    def test_missing_calibration_artifact_is_error(self):
        self.calibration_path.unlink()
        with self.assertRaises(PlanWeightError) as ctx:
            self.measurer()
        self.assertIn("калибровки", str(ctx.exception))

    def test_missing_read_limit_artifact_is_error(self):
        self.limit_path.unlink()
        with self.assertRaises(PlanWeightError) as ctx:
            self.measurer()
        self.assertIn("лимита чтения", str(ctx.exception))

    def test_read_limit_without_token_gate_is_invalid(self):
        data = read_limit(1, 1)
        del data["limits"]["tokens"]
        self.limit_path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(PlanWeightError) as ctx:
            load_read_limit(self.limit_path)
        self.assertIn("limits.tokens.value", str(ctx.exception))

    def test_read_limit_without_size_gate_is_invalid(self):
        data = read_limit(1, 1)
        del data["limits"]["size_bytes"]
        self.limit_path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(PlanWeightError) as ctx:
            load_read_limit(self.limit_path)
        self.assertIn("limits.size_bytes.value", str(ctx.exception))

    def test_read_limit_non_positive_value_is_invalid(self):
        self.write_limits(0, 25000)
        with self.assertRaises(PlanWeightError):
            load_read_limit(self.limit_path)

    def test_cli_returns_nonzero_without_artifact(self):
        self.calibration_path.unlink()
        stderr = io.StringIO()
        with unittest.mock.patch("sys.stderr", stderr):
            code = main(["--calibration", str(self.calibration_path),
                         "--read-limit", str(self.limit_path),
                         "plan", str(write_valid_plan(self.root))])
        self.assertEqual(code, 2)
        self.assertIn("ERROR:", stderr.getvalue())


class TestGapTaxonomy(MeasurerTestCase):
    """Каждая категория закрытой таксономии (`research/02-…` §5) — отдельным кейсом."""

    def test_gap_kinds_are_closed(self):
        self.assertEqual(GAP_KINDS, ("unreadable_root", "unresolved_entry",
                                     "missing_file", "oversized_file"))

    def test_unresolved_entry(self):
        record = self.item("1) P0.1 Completion Notes 2) root worktree rules")
        gaps = self.gaps_of(record, GAP_UNRESOLVED_ENTRY)
        self.assertEqual(len(gaps), 2, record["gaps"])
        self.assertIn("Completion Notes", gaps[0]["entry"])

    def test_missing_file(self):
        record = self.item("1) `lib/pkg/nope.py`")
        gaps = self.gaps_of(record, GAP_MISSING_FILE)
        self.assertEqual([g["path"] for g in gaps], ["lib/pkg/nope.py"])

    def test_unreadable_root(self):
        """Корень репозитория недоступен — отдельная категория, и позиции «от корня»
        честно падают в `missing_file`, а не тихо исчезают из суммы."""
        plan_dir = self.plan_with_reads("1) `packages/task/lib/task/plan_weight.py`")
        fields = {"Required Reads": "1) `packages/task/lib/task/plan_weight.py`"}
        record = measure_item(plan_dir, "P1.1", fields, self.measurer(),
                              phase_file=plan_dir / "phases" / "P1.md",
                              repo_root=self.root / "нет-такого-корня")
        self.assertEqual(len(self.gaps_of(record, GAP_UNREADABLE_ROOT)), 1)
        self.assertEqual(len(self.gaps_of(record, GAP_MISSING_FILE)), 1)

    def test_oversized_file_size_gate_only(self):
        self.write_limits(size_bytes=200, tokens=10 ** 9)
        record = self.item("1) `phases/P1.md`")
        gaps = self.gaps_of(record, GAP_OVERSIZED_FILE)
        self.assertTrue(gaps)
        self.assertEqual({g["gate"] for g in gaps}, {GATE_SIZE_BYTES})

    def test_oversized_file_token_gate_only(self):
        self.write_limits(size_bytes=10 ** 9, tokens=1)
        record = self.item("1) `phases/P1.md`")
        gaps = self.gaps_of(record, GAP_OVERSIZED_FILE)
        self.assertTrue(gaps)
        self.assertEqual({g["gate"] for g in gaps}, {GATE_TOKENS})

    def test_oversized_file_both_gates(self):
        self.write_limits(size_bytes=10, tokens=1)
        record = self.item("1) `phases/P1.md`")
        gaps = self.gaps_of(record, GAP_OVERSIZED_FILE)
        self.assertTrue(gaps)
        self.assertEqual({g["gate"] for g in gaps}, {GATE_BOTH})

    def test_gate_conjunction_passes_only_when_both_hold(self):
        """`pass(f) = bytes ≤ size_bytes И est_tokens ≤ tokens` (D108) — один зелёный
        гейт файл не спасает."""
        self.write_limits(size_bytes=10 ** 9, tokens=10 ** 9)
        record = self.item("1) `phases/P1.md`")
        self.assertTrue(all(f["passes"] for f in record["files"]))
        self.assertEqual(self.gaps_of(record, GAP_OVERSIZED_FILE), [])

    def test_gaps_are_never_silent(self):
        """Отчёт печатает перечень пробелов рядом с суммой — сумма без перечня есть
        нижняя оценка, выданная за измеренную."""
        plan_dir = self.plan_with_reads("1) P0.1 Completion Notes")
        stdout = io.StringIO()
        with unittest.mock.patch("sys.stdout", stdout):
            code = main(["--calibration", str(self.calibration_path),
                         "--read-limit", str(self.limit_path), "plan", str(plan_dir)])
        self.assertEqual(code, 0)
        out = stdout.getvalue()
        self.assertIn("вес:", out)
        self.assertIn(GAP_UNRESOLVED_ENTRY, out)


class TestRequiredReadsResolution(MeasurerTestCase):
    """Эвристика резолвинга — вход будущего контракта bundle (P3), поэтому проверяется
    поштучно, а не «в среднем»."""

    def test_split_entries_by_numbering(self):
        self.assertEqual(split_entries("1) a 2) b 3) c."), ["a", "b", "c"])

    def test_split_entries_without_numbering_is_single_entry(self):
        self.assertEqual(split_entries("просто проза"), ["просто проза"])

    def test_backticked_span_is_a_declared_path(self):
        self.assertEqual(path_candidates("1) `lib/pkg/config.py` и проза"),
                         [("lib/pkg/config.py", True)])

    def test_bare_strong_path_is_a_declaration(self):
        """Планы флота до 2026.07 пишут пути без бэктиков: `каталог/файл.ext` — такое же
        объявление, и его промах обязан называться `missing_file`."""
        self.assertEqual(path_candidates("см. lib/pkg/config.py без бэктиков"),
                         [("lib/pkg/config.py", True)])
        record = self.item("1) lib/pkg/no-such-file.py")
        self.assertEqual(len(self.gaps_of(record, GAP_MISSING_FILE)), 1)

    def test_bare_weak_token_is_a_guess_and_its_miss_mints_nothing(self):
        """«P4 finding/research» — проза, а не путь: `missing_file` из неё выдумывать
        запрещено, позиция честно остаётся `unresolved_entry`."""
        self.assertEqual(path_candidates("P4 finding/research по теме"),
                         [("finding/research", False)])
        record = self.item("1) P4 finding/research по теме")
        self.assertEqual(self.gaps_of(record, GAP_MISSING_FILE), [])
        self.assertEqual(len(self.gaps_of(record, GAP_UNRESOLVED_ENTRY)), 1)

    def test_bare_path_that_exists_is_measured(self):
        record = self.item("1) phases/P1.md (существующий файл без бэктиков)")
        self.assertEqual(record["gaps"], [])
        self.assertTrue(any(f["path"].endswith("phases/P1.md") for f in record["files"]))

    def test_em_dash_means_no_required_reads(self):
        record = self.item("—")
        self.assertEqual(record["gaps"], [])
        self.assertEqual(record["required_reads_tokens"], 0)

    def test_item_reference_is_not_a_path(self):
        """`P0.1` из прозы «P0.1 Completion Notes» не должен выглядеть файлом: расширение
        обязано начинаться с БУКВЫ, иначе позиция ушла бы в `missing_file` вместо
        `unresolved_entry` и класс пробела был бы назван неверно."""
        self.assertEqual(path_candidates("`P0.1` Completion Notes"), [])

    def test_brace_expansion(self):
        self.assertEqual(expand_braces("core/provider/{registry,artifact}.py"),
                         ["core/provider/registry.py", "core/provider/artifact.py"])
        self.assertEqual(path_candidates("1) `a/{x,y}.py`"),
                         [("a/x.py", True), ("a/y.py", True)])

    def test_resolution_prefers_plan_dir_then_repo_root(self):
        (self.root / "packages").mkdir(exist_ok=True)
        (self.root / "packages" / "AGENTS.md").write_text("корневой", encoding="utf-8")
        record = self.item("1) `phases/P1.md` 2) `packages/AGENTS.md`")
        paths = [f["path"] for f in record["files"]]
        self.assertIn("packages/AGENTS.md", paths)
        self.assertEqual(self.gaps_of(record, GAP_MISSING_FILE), [])

    def test_duplicate_read_is_not_double_counted(self):
        """Файл читается один раз: повтор в Required Reads вес не удваивает, и уже
        прочитанный файл раскладки (`phases/P1.md`) сохраняет свою роль `phase`."""
        record = self.item("1) `phases/P1.md` 2) `phases/P1.md`")
        phase_files = [f for f in record["files"] if f["path"].endswith("phases/P1.md")]
        self.assertEqual(len(phase_files), 1)
        self.assertEqual(phase_files[0]["role"], "phase")
        self.assertEqual(record["weight_tokens"], sum(f["est_tokens"] for f in record["files"]))
        self.assertEqual(record["required_reads_tokens"], 0)

    def test_weight_is_sum_of_resolved_only(self):
        record = self.item("1) `phases/P1.md` 2) `нет/такого.md`")
        self.assertEqual(record["weight_tokens"], sum(f["est_tokens"] for f in record["files"]))
        self.assertEqual(record["floor_tokens"],
                         sum(f["est_tokens"] for f in record["files"]
                             if f["role"] != "required_read"))


class TestDenseAsciiShare(unittest.TestCase):
    """D109: замер, не гейт. Известные векторы — проза около нуля, hex-простыня около 1."""

    def test_prose_is_near_zero(self):
        prose = ("Протокол планов рассчитан на планы, которые помещались в одно чтение. "
                 "Plain English prose with normal short words too.\n")
        self.assertLess(dense_ascii_share(prose), 0.05)

    def test_hex_sheet_is_near_one(self):
        sheet = "".join(hashlib.sha256(str(i).encode()).hexdigest() for i in range(50))
        self.assertGreater(dense_ascii_share(sheet), 0.99)

    def test_empty_text(self):
        self.assertEqual(dense_ascii_share(""), 0.0)

    def test_run_shorter_than_threshold_does_not_count(self):
        self.assertEqual(dense_ascii_share("a" * 31), 0.0)
        self.assertEqual(dense_ascii_share("a" * 32), 1.0)


class TestDenseAsciiIsNotAGate(MeasurerTestCase):
    """ЗАПРЕЩЕНО вводить порог по `dense_ascii_share` (D109): плотный, но помещающийся в
    лимиты файл пробелом не становится и «подозрительным» не помечается."""

    def test_dense_file_within_limits_produces_no_gap(self):
        plan_dir = self.plan_with_reads("1) `dense.txt`")
        (plan_dir / "dense.txt").write_text(
            "".join(hashlib.sha256(str(i).encode()).hexdigest() for i in range(10)),
            encoding="utf-8")
        record = measure_plan(plan_dir, self.measurer())["items"][0]
        dense = [f for f in record["files"] if f["path"].endswith("dense.txt")]
        self.assertEqual(len(dense), 1)
        self.assertGreater(dense[0]["dense_ascii_share"], 0.99)
        self.assertEqual(record["gaps"], [])


class TestJsonOutput(MeasurerTestCase):
    """`--json` стабилен по ключам — на нём стоят P0.4 и будущий гейт P3."""

    def run_json(self, *argv):
        stdout = io.StringIO()
        with unittest.mock.patch("sys.stdout", stdout):
            code = main(["--calibration", str(self.calibration_path),
                         "--read-limit", str(self.limit_path), *argv])
        self.assertEqual(code, 0, stdout.getvalue())
        return json.loads(stdout.getvalue())

    def test_plan_json_keys(self):
        plan_dir = self.plan_with_reads("1) `phases/P1.md` 2) P0.1 Completion Notes")
        data = self.run_json("plan", str(plan_dir), "--json")
        self.assertEqual(data["schema"], "plan-weight-v1")
        for key in ("calibration", "limits", "session_model_id", "dense_ascii_min_run",
                    "plan_id", "plan_dir", "repo_root", "items", "totals"):
            self.assertIn(key, data)
        self.assertEqual(set(data["limits"]) >= {"size_bytes", "tokens", "path"}, True)
        item = data["items"][0]
        for key in ("item_id", "phase_id", "title", "status", "files", "gaps",
                    "weight_tokens", "weight_bytes", "floor_tokens",
                    "required_reads_tokens", "resolved_files", "gap_counts"):
            self.assertIn(key, item)
        for key in ("path", "role", "bytes", "chars", "est_tokens", "dense_ascii_share",
                    "gates", "passes"):
            self.assertIn(key, item["files"][0])
        self.assertEqual(set(item["gap_counts"]), set(GAP_KINDS))
        self.assertTrue(all("kind" in g for g in item["gaps"]))

    def test_json_flag_accepted_before_and_after_subcommand(self):
        plan_dir = self.plan_with_reads("1) `phases/P1.md`")
        before = self.run_json("--json", "plan", str(plan_dir))
        after = self.run_json("plan", str(plan_dir), "--json")
        self.assertEqual(before["items"][0]["weight_tokens"],
                         after["items"][0]["weight_tokens"])

    def test_item_json_is_single_item(self):
        plan_dir = self.plan_with_reads("1) `phases/P1.md`")
        data = self.run_json("item", str(plan_dir), "P1.1", "--json")
        self.assertEqual([i["item_id"] for i in data["items"]], ["P1.1"])

    def test_v2_item_json_includes_stage_admission(self):
        plan_dir = write_valid_plan(self.root, plan_id="DEMO-V2", layout="v2")
        required = plan_dir / "lib" / "pkg" / "config.py"
        required.parent.mkdir(parents=True, exist_ok=True)
        required.write_text("VALUE = 1\n", encoding="utf-8")
        contract = plan_dir / "root" / "contracts" / "read-budget-v1.md"
        contract.parent.mkdir(parents=True, exist_ok=True)
        contract.write_text(
            "**Version:** `1.1.0`\n"
            "pass_item(i) = resolved(i) AND estimated_required_read_tokens(i) <= 100000\n",
            encoding="utf-8")
        data = self.run_json("item", str(plan_dir), "P1.1", "--json")
        item = data["items"][0]
        self.assertEqual(item["admission_state"], "ready")
        self.assertTrue(item["admission_pass"])
        self.assertEqual(data["totals"]["admission"]["counts"],
                         {"historical-pre-v2": 0, "pending-producer": 0, "ready": 1})

    def test_unknown_item_is_error(self):
        plan_dir = self.plan_with_reads("1) `phases/P1.md`")
        stderr = io.StringIO()
        with unittest.mock.patch("sys.stderr", stderr):
            code = main(["--calibration", str(self.calibration_path),
                         "--read-limit", str(self.limit_path),
                         "item", str(plan_dir), "P9.9"])
        self.assertEqual(code, 2)
        self.assertIn("P9.9", stderr.getvalue())

    def test_sweep_covers_every_plan_under_root(self):
        self.plan_with_reads("1) `phases/P1.md`", plan_id="DEMO-1")
        self.plan_with_reads("1) `phases/P1.md`", plan_id="DEMO-2")
        data = self.run_json("sweep", str(self.root / "plans"), "--json")
        self.assertEqual(sorted(p["plan_id"] for p in data["plans"]), ["DEMO-1", "DEMO-2"])
        self.assertEqual(data["totals"]["plans"], 2)
        self.assertEqual(data["errors"], [])

    def test_sweep_root_missing(self):
        data = self.run_json("sweep", str(self.root / "nope"), "--json")
        self.assertEqual([r["status"] for r in data["roots"]], ["missing"])
        row = data["roots"][0]
        self.assertEqual(row["root"], str(self.root / "nope"))
        self.assertEqual((row["discovered"], row["measured"], row["failed"]), (0, 0, 0))
        self.assertIsNotNone(row["detail"])
        self.assertEqual(data["totals"]["roots"],
                          {"total": 1, "resolved": 0, "unreadable": 0, "missing": 1})

    def test_sweep_root_resolved_without_plans(self):
        empty_root = self.root / "empty-root"
        empty_root.mkdir()
        data = self.run_json("sweep", str(empty_root), "--json")
        row = data["roots"][0]
        self.assertEqual(row["status"], "resolved")
        self.assertEqual(row["discovered"], 0)
        self.assertIsNone(row["detail"])
        self.assertEqual(data["totals"]["roots"]["resolved"], 1)

    def test_sweep_root_unreadable(self):
        if os.geteuid() == 0:
            self.skipTest("сессия от root — chmod 000 не даёт PermissionError")
        blocked_root = self.root / "blocked-root"
        blocked_root.mkdir()
        os.chmod(blocked_root, 0o000)
        try:
            data = self.run_json("sweep", str(blocked_root), "--json")
        finally:
            os.chmod(blocked_root, 0o755)
        row = data["roots"][0]
        self.assertEqual(row["status"], "unreadable")
        self.assertIsNotNone(row["detail"])
        self.assertEqual((row["discovered"], row["measured"], row["failed"]), (0, 0, 0))
        self.assertEqual(data["totals"]["roots"]["unreadable"], 1)

    def test_sweep_unreadable_root_does_not_block_neighbor(self):
        if os.geteuid() == 0:
            self.skipTest("сессия от root — chmod 000 не даёт PermissionError")
        blocked_root = self.root / "blocked-root"
        blocked_root.mkdir()
        os.chmod(blocked_root, 0o000)
        self.plan_with_reads("1) `phases/P1.md`", plan_id="DEMO-1")
        try:
            data = self.run_json("sweep", str(blocked_root), str(self.root / "plans"), "--json")
        finally:
            os.chmod(blocked_root, 0o755)
        self.assertEqual([r["status"] for r in data["roots"]], ["unreadable", "resolved"])
        self.assertEqual(data["totals"]["plans"], 1)
        self.assertEqual([p["plan_id"] for p in data["plans"]], ["DEMO-1"])

    def test_sweep_measured_converges_with_totals_plans(self):
        self.plan_with_reads("1) `phases/P1.md`", plan_id="DEMO-1")
        self.plan_with_reads("1) `phases/P1.md`", plan_id="DEMO-2")
        data = self.run_json("sweep", str(self.root / "plans"), "--json")
        self.assertEqual(sum(r["measured"] for r in data["roots"]), data["totals"]["plans"])


class TestExactMode(MeasurerTestCase):
    """`--exact` — дифференциальный харнесс P0.1, а не `count_tokens` (D92/D99)."""

    def probe_log(self, path, text):
        log = {"protocol_version": "differential-usage-v1", "measured": 1, "min_corpus": 1,
               "rejected": [], "probes": [{
                   "path": str(path), "bytes": len(text.encode()), "rejected": False,
                   "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                   "true_tokens": 1234.0}]}
        log_path = self.root / "probe-log.json"
        log_path.write_text(json.dumps(log), encoding="utf-8")
        return log_path

    def test_exact_compares_against_harness_truth(self):
        target = self.root / "corpus.md"
        text = "Проза плана для сверки оценки с истиной прогона.\n"
        target.write_text(text, encoding="utf-8")
        log_path = self.probe_log(target, text)
        stdout, stderr = io.StringIO(), io.StringIO()
        with unittest.mock.patch("sys.stdout", stdout), unittest.mock.patch("sys.stderr", stderr):
            code = main(["--calibration", str(self.calibration_path),
                         "--read-limit", str(self.limit_path), "--json",
                         "--exact", str(target), "--probe-log", str(log_path)])
        self.assertEqual(code, 0)
        data = json.loads(stdout.getvalue())["exact"]
        row = data["files"][0]
        self.assertEqual(row["truth"], 1234.0)
        self.assertEqual(row["match"], "sha256")
        self.assertIn("true_over_estimate", row)
        self.assertIn("вне CI", stderr.getvalue())

    def test_exact_names_files_without_truth(self):
        target = self.root / "unknown.md"
        target.write_text("нет такого файла в корпусе прогона\n", encoding="utf-8")
        log_path = self.probe_log(self.root / "другой.md", "другое содержимое")
        stdout = io.StringIO()
        with unittest.mock.patch("sys.stdout", stdout), unittest.mock.patch("sys.stderr", io.StringIO()):
            code = main(["--calibration", str(self.calibration_path),
                         "--read-limit", str(self.limit_path), "--json",
                         "--exact", str(target), "--probe-log", str(log_path)])
        self.assertEqual(code, 0)
        row = json.loads(stdout.getvalue())["exact"]["files"][0]
        self.assertIsNone(row["truth"])
        self.assertIn("истины нет", row["note"])

    def test_module_never_calls_count_tokens_or_opens_network(self):
        """`count_tokens` этим item'ом НЕ реализуется и не вызывается ни в одном режиме;
        сети инструмент не открывает и учётных данных не читает."""
        source = Path(plan_weight.__file__).read_text(encoding="utf-8")
        code = "\n".join(ln for ln in source.splitlines() if not ln.lstrip().startswith("#"))
        code = re.sub(r'""".*?"""', "", code, flags=re.S)
        # Вызов эндпоинта, а не упоминание запрета: `count_tokens(` — единственная форма,
        # которой он мог бы быть позван (упоминание в тексте предупреждения законно).
        self.assertNotIn("count_tokens(", code, "появился вызов count_tokens")
        for forbidden in ("import urllib", "import http", "import socket", "import requests",
                          "import subprocess", "ANTHROPIC_API_KEY"):
            self.assertNotIn(forbidden, code, f"в исполняемом коде появился «{forbidden}»")


class TestCanonWeightGate(MeasurerTestCase):
    def _budget(self, canon, *, baseline=100, warning=0.8, regression=10,
                justification="", exceptions=None):
        path = self.root / "canon-budget.json"
        path.write_text(json.dumps({
            "version": "1.0.0",
            "canon_path": str(canon),
            "baseline": {"git_anchor": "abc123", "est_tokens": baseline, "lines": 10},
            "warning_fraction": warning,
            "regression_percent": regression,
            "regression_justification": justification,
            "vendor_line_guidance": 500,
            "exceptions": exceptions or [],
        }), encoding="utf-8")
        return path

    def test_document_reports_tokens_and_lines(self):
        canon = self.root / "SKILL.md"
        canon.write_text("one\ntwo\n", encoding="utf-8")
        record = measure_document(canon, self.measurer())
        self.assertEqual(record["lines"], 2)
        self.assertGreater(record["est_tokens"], 0)

    def test_hard_cap_fails_without_active_exception(self):
        canon = self.root / "SKILL.md"
        canon.write_text("word " * 100, encoding="utf-8")
        self.write_limits(size_bytes=10 ** 9, tokens=5)
        result = evaluate_canon_budget(self._budget(canon, baseline=10), self.measurer())
        self.assertIn("hard_cap", result["failures"])
        self.assertFalse(result["passes"])

    def test_regression_requires_justification(self):
        canon = self.root / "SKILL.md"
        canon.write_text("word " * 100, encoding="utf-8")
        measured = measure_document(canon, self.measurer())["est_tokens"]
        result = evaluate_canon_budget(
            self._budget(canon, baseline=max(1, measured // 2), regression=0), self.measurer())
        self.assertIn("regression", result["failures"])
        justified = evaluate_canon_budget(
            self._budget(canon, baseline=max(1, measured // 2), regression=0,
                         justification="new observed failure mode"), self.measurer())
        self.assertNotIn("regression", justified["failures"])

    def test_every_exception_must_have_valid_expiry(self):
        canon = self.root / "SKILL.md"
        canon.write_text("small\n", encoding="utf-8")
        budget = self._budget(canon, exceptions=[{"reason": "temporary"}])
        with self.assertRaises(PlanWeightError):
            load_canon_budget(budget)


class TestSessionModelWarning(MeasurerTestCase):
    """WARNING (не блокирующий) при расхождении model_id калибровки с окружением."""

    def test_mismatch_warns_and_continues(self):
        stderr = io.StringIO()
        with unittest.mock.patch("sys.stderr", stderr):
            measurer = Measurer(calibration_path=self.calibration_path,
                                read_limit_path=self.limit_path, model_id="claude-opus-5")
        self.assertTrue(measurer.warned_model)
        self.assertIn("WARNING", stderr.getvalue())

    def test_match_is_silent(self):
        stderr = io.StringIO()
        with unittest.mock.patch("sys.stderr", stderr):
            measurer = self.measurer()
        self.assertFalse(measurer.warned_model)
        self.assertEqual(stderr.getvalue(), "")


class TestRealFleetPlan(unittest.TestCase):
    """Разбор обязан работать ОБЩИМ путём на реальных планах флота, а не только на
    фикстурах (Code Guidance P0.3): замер живого плана этого репозитория."""

    def test_measures_live_plan(self):
        repo_root = plan_weight._MONOREPO_ROOT
        plan_dir = repo_root / "plans" / "2026.08.07-PLAN-ECONOMY"
        if not (plan_dir / "plan.md").is_file():
            self.skipTest("живой план недоступен — standalone-раскладка")
        measurer = Measurer()
        plan = measure_plan(plan_dir, measurer, only_item="P0.3")
        record = plan["items"][0]
        self.assertEqual(record["item_id"], "P0.3")
        self.assertGreater(record["weight_tokens"], 0)
        self.assertEqual({f["role"] for f in record["files"]} >= {"plan", "handoff", "phase"},
                         True)
        self.assertTrue(all(g["kind"] in GAP_KINDS for g in record["gaps"]))
        self.assertTrue(all(g.get("gate") in (None, GATE_SIZE_BYTES, GATE_TOKENS, GATE_BOTH)
                            for g in record["gaps"]))


if __name__ == "__main__":
    unittest.main()
