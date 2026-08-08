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
    `path/to/file.json::a.b.c`        — путь ключей внутри JSON (P11.2), резолвится
                                         `json.load` + greedy-обход (на каждом уровне —
                                         ДЛИННЕЙШИЙ дотированный префикс, являющийся
                                         ключом; для списка — целочисленный индекс).
                                         Проверяется, что КЛЮЧ СУЩЕСТВУЕТ — не что значение
                                         совпадает. Не JSON-путь — прежний грep по листу.

Путь обязан содержать хотя бы один `/` (как `normalize()` у `cross-plan-files.py`) —
ГОЛЫЙ path-упоминание без суффикса (`:line`/`::symbol`) НЕ проверяется вовсе (класс отклонён
измерением, D128). Резолв пути — ДВУХШАГОВЫЙ: (1) корень репозитория, (2) каталог плана-источника
(`plans/<PLAN-ID>/`) — первая база, под которой файл существует, определяет резолв, суффикс
проверяется относительно НЕЁ. Порядок зафиксирован намеренно (корень репо однозначен и общ для
всех планов, каталог плана — контекстное дополнение); внутриплановая короткая ссылка вроде
`phases/P1.md:80` резолвится ВТОРОЙ базой — это не «восстановление подразумеваемого контекста
прозы», а вторая детерминированная база, известная скрипту по построению (сам обходит
`plans/<PLAN-ID>/`). Файл, не резолвящийся НИ ОТ ОДНОЙ из двух баз, — находка (Code Guidance
item'а P11.1, анти-подгонка): машина по-прежнему не угадывает.

Поверхность скана — семь шаблонов внутри `plans/<PLAN-ID>/`: `plan.md`, `handoff.md`,
`roadmap.md`, `phases/*.md`, `findings/**/*.md`, `research/**/*.md`, `brief/**/*.md`
(рекурсивно). `artifacts/`, `closure/`, `root/` сознательно вне поверхности (сырьё измерений /
генерируемые отчёты / переезжает в `docs/` проекта — не носитель плановой прозы).

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
import importlib
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


# Семь шаблонов поверхности (D128, `research/27-P11-citation-gate-target-design.md` §2.2):
# слои знаний `brief/`→`findings/`→`research/` канонизированы SKILL §16 как носители, из
# которых цепочка «сырьё → синтез → решение» обязана восстанавливаться без чата — ссылка в
# них ровно такое же доказательство, как ссылка в ТЗ. `artifacts/`/`closure/`/`root/` вне
# поверхности сознательно (сырьё измерений / генерируемые отчёты / переезжает в docs/ проекта).
_SOURCE_PATTERNS = (
    "plan.md",
    "handoff.md",
    "roadmap.md",
    os.path.join("findings", "**", "*.md"),
    os.path.join("research", "**", "*.md"),
    os.path.join("brief", "**", "*.md"),
)


def _phase_source_files(plan_dir: str) -> list[str]:
    """Ask task's resolver for phase carriers; this script owns no layout glob."""
    task_lib = os.path.join(REPO_ROOT, "packages", "task", "lib")
    if task_lib not in sys.path:
        sys.path.insert(0, task_lib)
    try:
        resolver = importlib.import_module("task.plan_layout")
        return [str(path) for path in resolver.phase_paths(plan_dir).values()]
    except (ImportError, ValueError, OSError):
        return []


def plan_source_files(plan_dir: str) -> list[str]:
    files: set[str] = set()
    for pattern in _SOURCE_PATTERNS:
        for f in glob.glob(os.path.join(plan_dir, pattern), recursive=True):
            if os.path.isfile(f):
                files.add(f)
    files.update(f for f in _phase_source_files(plan_dir) if os.path.isfile(f))
    return sorted(files)


def load_known_exceptions() -> dict[str, str]:
    if not os.path.exists(KNOWN_EXCEPTIONS_FILE):
        return {}
    with open(KNOWN_EXCEPTIONS_FILE, encoding="utf-8") as fh:
        data = json.load(fh)
    return {item["citation"]: item.get("reason", "") for item in data.get("exceptions", [])}


def resolve_bases(repo_root: str, plan_dir: str) -> list[tuple[str, str]]:
    """Две базы резолва пути, В ЭТОМ ПОРЯДКЕ (зафиксировано, D128/`research/27-…` §2.1):
    (1) корень репозитория — однозначен и общ для всех планов; (2) каталог плана-источника —
    контекстное дополнение, резолвит внутриплановые короткие ссылки (`phases/P9.md:260`).
    Порядок не переставляется: коллизия имён на живом дереве маловероятна, но при появлении
    файла в корне репо, совпадающего с внутриплановым путём, приоритет обязан остаться за
    корнем — это НЕ угадывание, а объявленное правило."""
    return [("корня репо", repo_root), ("каталога плана", plan_dir)]


def _resolve_json_path(obj: object, remaining: str) -> str | None:
    """Greedy-обход JSON-объекта: на каждом уровне — ДЛИННЕЙШИЙ дотированный префикс
    остатка, являющийся ключом (для списка — целочисленный индекс). Возвращает причину
    отказа, либо None если весь путь резолвился (P11.2, `research/27-…` §2.3 — greedy
    обязателен: ключи планового артефакта сами содержат точки, `owners.P2.2` = ключ
    `"P2.2"` внутри `owners`, наивный `split(".")` даёт ложную находку)."""
    while remaining:
        if isinstance(obj, dict):
            matched = None
            for k in sorted(obj.keys(), key=lambda k: (-len(k), k)):
                if remaining == k or remaining.startswith(k + "."):
                    matched = k
                    break
            if matched is None:
                segment = remaining.split(".", 1)[0]
                return f"ключ {segment!r} не найден"
            obj = obj[matched]
            remaining = remaining[len(matched):]
            remaining = remaining[1:] if remaining.startswith(".") else remaining
        elif isinstance(obj, list):
            m = re.match(r"(\d+)(?:\.(.*))?$", remaining)
            if not m:
                segment = remaining.split(".", 1)[0]
                return f"индекс {segment!r} не найден"
            idx = int(m.group(1))
            if not (0 <= idx < len(obj)):
                return f"индекс {idx} вне диапазона списка длиной {len(obj)}"
            obj = obj[idx]
            remaining = m.group(2) or ""
        else:
            segment = remaining.split(".", 1)[0]
            return f"ключ {segment!r} не найден (родитель не объект и не список)"
    return None


def _check_json_suffix(abs_path: str, dotted_path: str) -> str | None:
    """Класс цитаты `file.json::a.b.c` (P11.2): ключ существует — и НИЧЕГО больше
    (значение не сверяется, та же граница, что у P10.2 «символ = имя встречается»)."""
    with open(abs_path, encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError:
            return "JSON не парсится"
    return _resolve_json_path(data, dotted_path)


def _check_suffix(abs_path: str, suffix: str) -> str | None:
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


def check_citation(path_token: str, suffix: str, bases: list[tuple[str, str]]) -> str | None:
    """Вернуть причину отказа, либо None если ссылка резолвится. `bases` — список
    `(метка, каталог)`, пробуются ПО ПОРЯДКУ (`resolve_bases`); первая база, под которой файл
    существует, определяет резолв, суффикс проверяется ОТНОСИТЕЛЬНО НЕЁ (смешение баз дало бы
    ложный «номер строки вне диапазона» — суффикс и найденный файл обязаны быть с одной базы)."""
    for _label, base in bases:
        abs_path = os.path.join(base, path_token)
        if os.path.isfile(abs_path):
            if suffix.startswith("::") and path_token.lower().endswith(".json"):
                return _check_json_suffix(abs_path, suffix[2:])
            return _check_suffix(abs_path, suffix)
    if not bases:
        return "файл не найден (баз резолва не задано)"
    tried = ", ни ".join(f"от {label}" for label, _ in bases)
    return f"файл не найден ни {tried}"


def scan_plan(plan_dir: str, known: dict[str, str], repo_root: str) -> tuple[list[Finding], int]:
    bases = resolve_bases(repo_root, plan_dir)
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
                    reason = check_citation(path_token, suffix, bases)
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
            # каталог плана — вторая база резолва; несёт СВОЙ файл, отсутствующий под корнем.
            self.plan_dir = os.path.join(self.repo_root, "plans", "P11-BASES-FIXTURE")
            os.makedirs(os.path.join(self.plan_dir, "phases"))
            with open(os.path.join(self.plan_dir, "phases", "P1.md"), "w", encoding="utf-8") as fh:
                fh.write("line1\nline2\n")
            self.bases = resolve_bases(self.repo_root, self.plan_dir)

        def test_a_valid_line_ref_passes(self) -> None:
            self.assertIsNone(check_citation("pkg/mod.py", ":2", self.bases))

        def test_a2_valid_range_and_pair_pass(self) -> None:
            self.assertIsNone(check_citation("pkg/mod.py", ":1-4", self.bases))
            self.assertIsNone(check_citation("pkg/mod.py", ":1,4", self.bases))

        def test_b_line_out_of_range_is_finding(self) -> None:
            reason = check_citation("pkg/mod.py", ":99", self.bases)
            self.assertIsNotNone(reason)
            self.assertIn("диапазона", reason)

        def test_c_missing_symbol_is_finding(self) -> None:
            reason = check_citation("pkg/mod.py", "::nope", self.bases)
            self.assertIsNotNone(reason)
            self.assertIn("символ", reason)

        def test_c2_existing_symbol_passes(self) -> None:
            self.assertIsNone(check_citation("pkg/mod.py", "::target", self.bases))

        def test_c3_nested_symbol_greps_leaf(self) -> None:
            self.assertIsNone(check_citation("pkg/mod.py", "::Suite::target", self.bases))

        def test_d_missing_file_is_finding(self) -> None:
            reason = check_citation("pkg/absent.py", ":1", self.bases)
            self.assertIsNotNone(reason)
            self.assertIn("не найден", reason)

        # --- P11.1: двухшаговый резолвер + расширенная поверхность ---------------------

        def test_e_resolves_only_from_plan_dir(self) -> None:
            """(a) цитата резолвится ТОЛЬКО от каталога плана (`phases/P1.md:2`) — проходит."""
            self.assertIsNone(check_citation("phases/P1.md", ":2", self.bases))

        def test_e2_resolves_from_repo_root(self) -> None:
            """(b) цитата резолвится от корня репо — проходит (регрессия: база 1 не сломана)."""
            self.assertIsNone(check_citation("pkg/mod.py", ":1", self.bases))

        def test_e3_resolves_from_neither_base_names_both(self) -> None:
            """(c) не резолвится ни от одной базы → находка называет ОБЕ базы."""
            reason = check_citation("phases/absent.md", ":1", self.bases)
            self.assertIsNotNone(reason)
            self.assertIn("корня репо", reason)
            self.assertIn("каталога плана", reason)

        def test_e4_out_of_range_checked_against_correct_base(self) -> None:
            """(d) файл есть под каталогом плана, номер строки вне ЕГО диапазона (2 строки) —
            находка привязана к правильной базе, а не ложно проверена против корня репо."""
            reason = check_citation("phases/P1.md", ":99", self.bases)
            self.assertIsNotNone(reason)
            self.assertIn("диапазона", reason)

        def test_e5_recursive_glob_finds_nested_findings_file(self) -> None:
            """(e) `findings/sub/x.md` попадает в поверхность (рекурсивный glob)."""
            sub_dir = os.path.join(self.plan_dir, "findings", "sub")
            os.makedirs(sub_dir)
            with open(os.path.join(sub_dir, "x.md"), "w", encoding="utf-8") as fh:
                fh.write("см. `pkg/mod.py:1`\n")
            files = plan_source_files(self.plan_dir)
            self.assertIn(os.path.join(sub_dir, "x.md"), files)

        def test_e6_base_order_is_fixed_repo_root_first(self) -> None:
            """Порядок баз ЗАФИКСИРОВАН: корень репо первым (`resolve_bases`)."""
            self.assertEqual(
                [label for label, _ in resolve_bases(self.repo_root, self.plan_dir)],
                ["корня репо", "каталога плана"],
            )

        # --- P11.2: класс цитаты `file.json::a.b.c` (greedy-резолв) --------------------

        def test_f_json_path_resolves_nested_key(self) -> None:
            """(a) `pkg/data.json::a.b` при `{"a":{"b":1}}` — проходит."""
            with open(os.path.join(self.repo_root, "pkg", "data.json"), "w", encoding="utf-8") as fh:
                json.dump({"a": {"b": 1}}, fh)
            self.assertIsNone(check_citation("pkg/data.json", "::a.b", self.bases))

        def test_f2_json_path_greedy_key_with_dot(self) -> None:
            """(b) ключ с точкой в имени (`owners.P2.2` = ключ `"P2.2"` внутри `owners`) —
            регрессия наивного `split(".")`, обязана проходить (greedy)."""
            with open(os.path.join(self.repo_root, "pkg", "owners.json"), "w", encoding="utf-8") as fh:
                json.dump({"owners": {"P2.2": "carrier"}}, fh)
            self.assertIsNone(check_citation("pkg/owners.json", "::owners.P2.2", self.bases))

        def test_f3_json_path_missing_key_names_segment(self) -> None:
            """(c) несуществующий ключ → находка, названа ИМЕННО отсутствующая часть."""
            with open(os.path.join(self.repo_root, "pkg", "data2.json"), "w", encoding="utf-8") as fh:
                json.dump({"a": {"b": 1}}, fh)
            reason = check_citation("pkg/data2.json", "::a.nope", self.bases)
            self.assertIsNotNone(reason)
            self.assertIn("nope", reason)

        def test_f4_json_path_list_index(self) -> None:
            """(d) индекс списка (`::items.0.name`) проходит, выход за длину — находка."""
            with open(os.path.join(self.repo_root, "pkg", "list.json"), "w", encoding="utf-8") as fh:
                json.dump({"items": [{"name": "x"}]}, fh)
            self.assertIsNone(check_citation("pkg/list.json", "::items.0.name", self.bases))
            reason = check_citation("pkg/list.json", "::items.9.name", self.bases)
            self.assertIsNotNone(reason)
            self.assertIn("диапазона", reason)

        def test_f5_broken_json_is_finding(self) -> None:
            """(e) битый JSON → находка «JSON не парсится», не тихий пропуск."""
            with open(os.path.join(self.repo_root, "pkg", "broken.json"), "w", encoding="utf-8") as fh:
                fh.write("{not valid json")
            reason = check_citation("pkg/broken.json", "::a.b", self.bases)
            self.assertIsNotNone(reason)
            self.assertIn("не парсится", reason)

        def test_f6_non_json_symbol_branch_unchanged(self) -> None:
            """(f) НЕ-json файл с `::symbol` — прежнее поведение (грep листа) не изменилось."""
            self.assertIsNone(check_citation("pkg/mod.py", "::target", self.bases))

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
