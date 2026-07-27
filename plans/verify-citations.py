#!/usr/bin/env python3
"""Проверка ссылок-доказательств планов: `path:line`/`path::symbol` резолвится до факта.

Программный гейт, переиспользующий класс дефекта, который был найден в
`plans/2026.07.24-AGENT-RELIABILITY/artifacts/P4.1/verify_claim_verdicts.py` (проверял только
существование ФАЙЛА из `ref` до `::`, символ после `::` не валидировался — через эту дыру
прошёл mis-cite H06). Тот скрипт лежит в `artifacts/` терминального плана и не правится
(аддитивность, D90); этот скрипт — переиспользуемая замена его класса для ВСЕХ живых планов,
закрывающая заодно второй класс — протухшие линейные якоря на файлы, переписанные другим
планом (D89).

Форма и CLI повторяют `plans/cross-plan-files.py` (см. Required Reads P10.2): stdlib-only,
человекочитаемый отчёт всегда, `--strict` переключает только exit-код.

Проверяемые формы ссылок (внутри одинарных бэктиков, ЦЕЛИКОМ токеном):
    `path/to/file.ext:123`            — одна строка внутри файла
    `path/to/file.ext:123-145`        — диапазон строк
    `path/to/file.ext:123,145`        — пара несмежных строк
    `path/to/file.ext::symbol`        — имя символа встречается в файле (поиск по имени,
                                         БЕЗ AST; `a::B::c` — грепается ЛИСТ `c`, граница
                                         намеренная, см. docs/reference/plan-tooling.md)

Путь обязан содержать хотя бы один `/` (как `normalize()` у `cross-plan-files.py`) — короткие
формы без директории (напр. `phases/P1.md:80` как продолжение перечисления после полного пути
чуть раньше) сознательно НЕ резолвятся эвристикой: машина не восстанавливает подразумеваемый
контекст прозы, находка в отчёте — ожидаемый результат (Code Guidance item'а, анти-подгонка).

Известные исключения (ссылки на деливераблы БУДУЩИХ items, которых на этом дереве ещё нет по
построению) — данными, не кодом: `plans/verify-citations-known-exceptions.json`
(`{"exceptions": [{"citation": "...", "reason": "..."}]}`), формат — тот же принцип, что
`cross-plan-files-known-intersections.json` у соседнего гейта.

Использование:
    python3 plans/verify-citations.py                        # все живые планы
    python3 plans/verify-citations.py plans/<PLAN-ID> ...     # только названные (путь ИЛИ ID)
    python3 plans/verify-citations.py --strict                # exit 1 при любой находке
    python3 plans/verify-citations.py --include-archive        # + архивные планы
    python3 plans/verify-citations.py --selftest               # embedded unittest (Files
                                                                  # item'а не заводит отдельный
                                                                  # тестовый файл)
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

PLANS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.normpath(os.path.join(PLANS_DIR, ".."))
KNOWN_EXCEPTIONS_FILE = os.path.join(PLANS_DIR, "verify-citations-known-exceptions.json")

CITATION_RE = re.compile(
    r"`((?:[\w.-]+/)+[\w.-]+\.[A-Za-z0-9]+)"
    r"(:[0-9]+(?:[-,][0-9]+)?|::[A-Za-z_][\w.:]*)`"
)


class Finding:
    def __init__(self, source: str, line: int, citation: str, reason: str) -> None:
        self.source = source
        self.line = line
        self.citation = citation
        self.reason = reason

    def render(self) -> str:
        return f"{self.source}:{self.line} → `{self.citation}` — {self.reason}"


def live_plan_dirs(include_archive: bool = False) -> list[str]:
    out = []
    for path in sorted(glob.glob(os.path.join(PLANS_DIR, "*", "plan.md"))):
        plan_dir = os.path.dirname(path)
        plan_id = os.path.basename(plan_dir)
        if plan_id in ("archive", "tools"):
            continue
        out.append(plan_dir)
    if include_archive:
        for path in sorted(glob.glob(os.path.join(PLANS_DIR, "archive", "*", "plan.md"))):
            out.append(os.path.dirname(path))
    return out


def resolve_plan_dir(arg: str) -> str:
    for candidate in (arg, os.path.join(PLANS_DIR, arg)):
        if os.path.isdir(candidate) and os.path.exists(os.path.join(candidate, "plan.md")):
            return os.path.normpath(candidate)
    raise SystemExit(f"verify-citations: не план ({arg}) — plan.md не найден")


def plan_source_files(plan_dir: str) -> list[str]:
    files = [os.path.join(plan_dir, "plan.md")]
    files += sorted(glob.glob(os.path.join(plan_dir, "phases", "*.md")))
    return [f for f in files if os.path.exists(f)]


def load_known_exceptions() -> dict[str, str]:
    if not os.path.exists(KNOWN_EXCEPTIONS_FILE):
        return {}
    with open(KNOWN_EXCEPTIONS_FILE, encoding="utf-8") as fh:
        data = json.load(fh)
    return {item["citation"]: item.get("reason", "") for item in data.get("exceptions", [])}


def check_citation(path_token: str, suffix: str, repo_root: str) -> str | None:
    """Вернуть причину отказа, либо None если ссылка резолвится."""
    abs_path = os.path.join(repo_root, path_token)
    if not os.path.isfile(abs_path):
        return f"файл не существует под {repo_root}"
    with open(abs_path, encoding="utf-8", errors="replace") as fh:
        content = fh.read()
    if suffix.startswith("::"):
        # a::B::c — АСТ не строим (Implementation Rules item'а); грепаем ЛИСТ имени.
        leaf = suffix[2:].split("::")[-1]
        if not re.search(r"\b" + re.escape(leaf) + r"\b", content):
            return f"символ {leaf!r} не найден в файле"
        return None
    body = suffix[1:]
    if "-" in body:
        numbers = body.split("-", 1)
    elif "," in body:
        numbers = body.split(",")
    else:
        numbers = [body]
    total = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
    for raw in numbers:
        n = int(raw)
        if not (1 <= n <= total):
            return f"строка {n} вне диапазона 1..{total}"
    return None


def scan_plan(plan_dir: str, known: dict[str, str], repo_root: str) -> tuple[list[Finding], int]:
    findings: list[Finding] = []
    checked = 0
    for src in plan_source_files(plan_dir):
        rel_src = os.path.relpath(src, repo_root)
        with open(src, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                for m in CITATION_RE.finditer(line):
                    path_token, suffix = m.group(1), m.group(2)
                    citation = f"{path_token}{suffix}"
                    checked += 1
                    if citation in known:
                        continue
                    reason = check_citation(path_token, suffix, repo_root)
                    if reason:
                        findings.append(Finding(rel_src, lineno, citation, reason))
    return findings, checked


def _selftest() -> int:
    """Embedded unittest — единственный носитель тестов item'а (Files не заводит отдельный
    файл: скрипт stdlib-only и самодостаточен, как соседний `cross-plan-files.py`)."""
    import tempfile
    import unittest

    class VerifyCitationsTests(unittest.TestCase):
        def setUp(self) -> None:
            self._tmp = tempfile.TemporaryDirectory()
            self.addCleanup(self._tmp.cleanup)
            self.repo_root = self._tmp.name
            os.makedirs(os.path.join(self.repo_root, "pkg"))
            with open(os.path.join(self.repo_root, "pkg", "mod.py"), "w", encoding="utf-8") as fh:
                fh.write("line1\nline2\ndef target():\n    pass\n")

        def test_a_valid_line_ref_passes(self) -> None:
            self.assertIsNone(check_citation("pkg/mod.py", ":2", self.repo_root))

        def test_a2_valid_range_and_pair_pass(self) -> None:
            self.assertIsNone(check_citation("pkg/mod.py", ":1-4", self.repo_root))
            self.assertIsNone(check_citation("pkg/mod.py", ":1,4", self.repo_root))

        def test_b_line_out_of_range_is_finding(self) -> None:
            reason = check_citation("pkg/mod.py", ":99", self.repo_root)
            self.assertIsNotNone(reason)
            self.assertIn("диапазона", reason)

        def test_c_missing_symbol_is_finding(self) -> None:
            reason = check_citation("pkg/mod.py", "::nope", self.repo_root)
            self.assertIsNotNone(reason)
            self.assertIn("символ", reason)

        def test_c2_existing_symbol_passes(self) -> None:
            self.assertIsNone(check_citation("pkg/mod.py", "::target", self.repo_root))

        def test_c3_nested_symbol_greps_leaf(self) -> None:
            self.assertIsNone(check_citation("pkg/mod.py", "::Suite::target", self.repo_root))

        def test_d_missing_file_is_finding(self) -> None:
            reason = check_citation("pkg/absent.py", ":1", self.repo_root)
            self.assertIsNotNone(reason)
            self.assertIn("не существует", reason)

        def test_scan_plan_end_to_end(self) -> None:
            plan_dir = os.path.join(self.repo_root, "plans", "X")
            os.makedirs(os.path.join(plan_dir, "phases"))
            with open(os.path.join(plan_dir, "plan.md"), "w", encoding="utf-8") as fh:
                fh.write("см. `pkg/mod.py:2` и `pkg/mod.py::missing_symbol`\n")
            findings, checked = scan_plan(plan_dir, {}, self.repo_root)
            self.assertEqual(checked, 2)
            self.assertEqual(len(findings), 1)
            self.assertIn("missing_symbol", findings[0].citation)

        def test_known_exception_suppresses_finding(self) -> None:
            plan_dir = os.path.join(self.repo_root, "plans", "Y")
            os.makedirs(os.path.join(plan_dir, "phases"))
            with open(os.path.join(plan_dir, "plan.md"), "w", encoding="utf-8") as fh:
                fh.write("будущий деливерабл `pkg/not-yet.py:1`\n")
            known = {"pkg/not-yet.py:1": "деливерабл будущего item'а"}
            findings, checked = scan_plan(plan_dir, known, self.repo_root)
            self.assertEqual(checked, 1)
            self.assertEqual(findings, [])

        def test_determinism_two_runs_identical(self) -> None:
            plan_dir = os.path.join(self.repo_root, "plans", "Z")
            os.makedirs(os.path.join(plan_dir, "phases"))
            with open(os.path.join(plan_dir, "plan.md"), "w", encoding="utf-8") as fh:
                fh.write("`pkg/mod.py:2` и `pkg/absent.py:1`\n")
            first = [f.render() for f in scan_plan(plan_dir, {}, self.repo_root)[0]]
            second = [f.render() for f in scan_plan(plan_dir, {}, self.repo_root)[0]]
            self.assertEqual(first, second)

    suite = unittest.TestLoader().loadTestsFromTestCase(VerifyCitationsTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


def main() -> int:
    argv = sys.argv[1:]
    if "--selftest" in argv:
        return _selftest()
    strict = "--strict" in argv
    include_archive = "--include-archive" in argv
    args = [a for a in argv if not a.startswith("--")]
    plan_dirs = [resolve_plan_dir(a) for a in args] if args else live_plan_dirs(include_archive)
    known = load_known_exceptions()

    total_findings: list[Finding] = []
    total_checked = 0
    print(f"Проверка ссылок-доказательств по {len(plan_dirs)} план(ам)\n")
    for plan_dir in plan_dirs:
        plan_id = os.path.basename(plan_dir)
        findings, checked = scan_plan(plan_dir, known, REPO_ROOT)
        total_checked += checked
        total_findings += findings
        print(f"  {plan_id}: цитат проверено {checked} · находок {len(findings)}")

    print(f"\nВсего цитат: {total_checked}")
    print(f"Известных исключений в перечне: {len(known)}")
    print(f"Находок: {len(total_findings)}\n")
    if total_findings:
        for f in total_findings:
            print(f"  {f.render()}")
    else:
        print("  (находок нет)")

    if not strict:
        return 0
    return 1 if total_findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
