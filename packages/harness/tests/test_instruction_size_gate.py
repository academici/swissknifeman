"""P2.1 gate: every instruction projection stays inside its size class ceiling."""
from dataclasses import replace
import importlib
from pathlib import Path
import tempfile
import unittest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from harness.instructions import (
    CATALOG_VERSION, CONTRACT_VERSION, PACKAGE_CANON_LINE_LIMIT, PACKAGE_CANON_TOKEN_LIMIT,
    PROVIDERS, ROOT_CANON_LINE_LIMIT, ROOT_CANON_TOKEN_LIMIT, SCOPES, TARGETS,
    InstructionRequest, apply_instructions, canon_size_limits, check_instructions,
    estimate_tokens, plan_instructions, repository_root, validate_canon_size,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


def request(operation, root, **changes):
    base = InstructionRequest(
        CONTRACT_VERSION, CATALOG_VERSION, operation, SCOPES, PROVIDERS, str(root),
        (("source", "test-config"),), (("authority", "synthetic-temp-root"),))
    return replace(base, **changes)


def _skiller_budget():
    """Первоисточник формулы оценки токенов; standalone-раскладка без skiller —
    пропуск, а не красный тест (harness от skiller не зависит и в рантайме его
    не импортирует — импорт живёт только здесь, в сверке двух реализаций)."""
    lib = REPO_ROOT / "packages/skiller/lib"
    if not (lib / "skiller/budget.py").is_file():
        return None
    if str(lib) not in sys.path:
        sys.path.insert(0, str(lib))
    try:
        return importlib.import_module("skiller.budget")
    except ImportError:  # pragma: no cover — чужой пакет недоступен целиком
        return None


class CanonSizeLimitTests(unittest.TestCase):
    def test_limits_are_named_constants_per_artifact_class(self):
        self.assertEqual(canon_size_limits("root"),
                         (ROOT_CANON_LINE_LIMIT, ROOT_CANON_TOKEN_LIMIT))
        for scope_id in ("skiller", "harness", "maind", "analyst", "task", "artifex"):
            self.assertEqual(canon_size_limits(scope_id),
                             (PACKAGE_CANON_LINE_LIMIT, PACKAGE_CANON_TOKEN_LIMIT))

    def test_root_line_ceiling_is_the_upstream_recommendation(self):
        """200 строк — апстрим-рекомендация Claude Code, а не текущий размер файла."""
        self.assertEqual(ROOT_CANON_LINE_LIMIT, 200)
        self.assertLess(PACKAGE_CANON_LINE_LIMIT, ROOT_CANON_LINE_LIMIT)
        self.assertLess(PACKAGE_CANON_TOKEN_LIMIT, ROOT_CANON_TOKEN_LIMIT)


class CanonSizeTokenEstimateTests(unittest.TestCase):
    def test_empty_and_language_dependent_estimate(self):
        self.assertEqual(estimate_tokens(""), 0)
        self.assertGreater(estimate_tokens("hello world"), 0)
        self.assertGreater(estimate_tokens("привет мир" * 10),
                           estimate_tokens("hello worl" * 10))

    def test_token_estimate_matches_skiller_formula(self):
        """Анти-спор цифр: две реализации одной формулы обязаны совпадать на общем
        входе, иначе гейт размера и `skiller budget` начнут спорить о том же файле."""
        budget = _skiller_budget()
        if budget is None:  # pragma: no cover — standalone-раскладка вне монорепо
            self.skipTest("skiller.budget недоступен (standalone-раскладка)")
        samples = [
            "",
            "plain latin instruction text",
            "русский текст канона инструкций",
            "смешанный mixed текст with `code` и ссылками",
            (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8"),
            (REPO_ROOT / "packages/harness/CLAUDE.md").read_text(encoding="utf-8"),
        ]
        for sample in samples:
            self.assertEqual(estimate_tokens(sample), budget.estimate_tokens(sample))


class CanonSizeValidatorTests(unittest.TestCase):
    def _clean_root(self, temp):
        root = Path(temp).resolve()
        planned = plan_instructions(request("plan", root))
        targets = tuple(action.target_path for action in planned.artifact_plan.actions)
        applied = apply_instructions(request("apply", root, authorized_target_paths=targets))
        self.assertTrue(applied.green)
        return root

    def test_live_repository_projections_are_inside_their_ceilings(self):
        self.assertEqual(validate_canon_size(repository_root()), ())

    def test_freshly_rendered_projections_are_inside_their_ceilings(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(validate_canon_size(self._clean_root(temp)), ())

    def test_absent_target_is_not_a_size_finding(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(validate_canon_size(Path(temp).resolve()), ())

    def test_oversized_root_projection_yields_line_and_token_findings(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self._clean_root(temp)
            (root / TARGETS["root"]["claude-code"]).write_text(
                "\n".join(f"## section {index}" for index in range(ROOT_CANON_LINE_LIMIT + 1)),
                encoding="utf-8")
            findings = validate_canon_size(root)
        self.assertEqual(tuple(item.metric for item in findings), ("lines",))
        self.assertEqual(findings[0].target_path, "CLAUDE.md")
        self.assertEqual(findings[0].scope_id, "root")
        self.assertEqual(findings[0].limit, ROOT_CANON_LINE_LIMIT)
        self.assertGreater(findings[0].observed, ROOT_CANON_LINE_LIMIT)

    def test_oversized_tokens_alone_are_caught_under_the_line_ceiling(self):
        """Длинные строки обходят счётчик строк — токенный потолок ловит их отдельно."""
        with tempfile.TemporaryDirectory() as temp:
            root = self._clean_root(temp)
            (root / TARGETS["root"]["codex"]).write_text(
                "\n".join("x" * 4000 for _ in range(10)), encoding="utf-8")
            findings = validate_canon_size(root)
        self.assertEqual(tuple(item.metric for item in findings), ("tokens",))
        self.assertEqual(findings[0].target_path, "AGENTS.md")
        self.assertEqual(findings[0].limit, ROOT_CANON_TOKEN_LIMIT)

    def test_package_class_is_stricter_than_root_class(self):
        """Файл, легальный в корневом классе, за пакетным потолком — красный."""
        body = "\n".join(f"## rule {index}" for index in range(PACKAGE_CANON_LINE_LIMIT + 5))
        self.assertLess(len(body.splitlines()), ROOT_CANON_LINE_LIMIT)
        with tempfile.TemporaryDirectory() as temp:
            root = self._clean_root(temp)
            (root / TARGETS["harness"]["claude-code"]).write_text(body, encoding="utf-8")
            findings = validate_canon_size(root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].scope_id, "harness")
        self.assertEqual(findings[0].metric, "lines")
        self.assertEqual(findings[0].limit, PACKAGE_CANON_LINE_LIMIT)

    def test_findings_are_ordered_by_scope_provider_and_metric(self):
        oversized = "\n".join("y" * 4000 for _ in range(ROOT_CANON_LINE_LIMIT + 1))
        with tempfile.TemporaryDirectory() as temp:
            root = self._clean_root(temp)
            (root / TARGETS["root"]["claude-code"]).write_text(oversized, encoding="utf-8")
            (root / TARGETS["root"]["codex"]).write_text(oversized, encoding="utf-8")
            findings = validate_canon_size(root)
        self.assertEqual([(item.provider_id, item.metric) for item in findings],
                         [("claude-code", "lines"), ("claude-code", "tokens"),
                          ("codex", "lines"), ("codex", "tokens")])


class CanonSizeWiringTests(unittest.TestCase):
    def _clean_root(self, temp):
        root = Path(temp).resolve()
        planned = plan_instructions(request("plan", root))
        targets = tuple(action.target_path for action in planned.artifact_plan.actions)
        apply_instructions(request("apply", root, authorized_target_paths=targets))
        return root

    def test_check_is_red_and_names_the_metric_when_a_projection_is_oversized(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self._clean_root(temp)
            (root / TARGETS["root"]["claude-code"]).write_text(
                "\n".join(f"## section {index}" for index in range(ROOT_CANON_LINE_LIMIT + 1)),
                encoding="utf-8")
            checked = check_instructions(request("check", root))
        self.assertFalse(checked.green)
        self.assertEqual(len(checked.size_findings), 1)
        finding = checked.size_findings[0]
        self.assertEqual((finding.target_path, finding.metric, finding.limit),
                         ("CLAUDE.md", "lines", ROOT_CANON_LINE_LIMIT))
        self.assertEqual(set(finding.as_dict()),
                         {"scope_id", "provider_id", "target_path", "metric", "limit", "observed"})

    def test_check_is_green_on_a_projection_inside_the_ceiling(self):
        with tempfile.TemporaryDirectory() as temp:
            checked = check_instructions(request("check", self._clean_root(temp)))
        self.assertTrue(checked.green)
        self.assertEqual(checked.size_findings, ())

    def test_size_findings_are_additive_in_the_machine_report(self):
        """Аддитивность: ключи отчёта прежние плюс `size_findings`; коды диагностик
        замороженного контракта не расширяются (D86)."""
        with tempfile.TemporaryDirectory() as temp:
            report = check_instructions(request("check", self._clean_root(temp))).as_dict()
        self.assertEqual(set(report),
                         {"request", "targets", "diagnostics", "size_findings", "green"})
        self.assertEqual(report["size_findings"], [])

    def test_plan_and_apply_ignore_the_size_gate(self):
        """Гейт живёт только в `check`: иначе `apply`, которым и чинят размер,
        заклинило бы на собственном красном вердикте."""
        with tempfile.TemporaryDirectory() as temp:
            root = self._clean_root(temp)
            (root / TARGETS["root"]["claude-code"]).write_text(
                "\n".join(f"## section {index}" for index in range(ROOT_CANON_LINE_LIMIT + 1)),
                encoding="utf-8")
            planned = plan_instructions(request("plan", root))
            self.assertEqual(planned.size_findings, ())
            targets = tuple(action.target_path for action in planned.artifact_plan.actions
                            if action.target_path == TARGETS["root"]["claude-code"])
            repaired = check_instructions(request("check", root))
        self.assertTrue(targets)
        self.assertFalse(repaired.green)


if __name__ == "__main__":
    unittest.main()
