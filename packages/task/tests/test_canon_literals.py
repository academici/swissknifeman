"""Гейт полноты канонических литералов (P2.16/D35 + D79 EN-only).

Механизм двухступенчат:
  * EN-only `SKILL.md` объявляет директиву `<!-- i18n-keep: <литерал> -->` и несёт
    сам литерал байт-в-байт;
  * но сам гейт видит ТОЛЬКО объявленное. Инлайн-строка `план закрыт` (три сверки в
    `plan_lint.py`) константы не имела, в директивах не значилась — гейт был к ней СЛЕП.

Отсюда два теста:
  T1 — AST-обход `plan_lint.py`: кириллический литерал, участвующий в СВЕРКЕ С ТЕКСТОМ ПЛАНА
       (`Compare` — `in`/`==`; аргумент-шаблон `re.compile`/`re.escape`/`re.finditer`/…;
       строковые методы `startswith`/`count`/…; аргумент функции, ОБЪЯВЛЕННОЙ в этом модуле),
       обязан быть покрыт реестром `CANON_LITERALS` ∪ `HEURISTIC_LITERALS`. Ссылки на имена —
       модульные И локальные — РАЗЫМЕНОВЫВАЮТСЯ: иначе гейт обходится тем же приёмом, что
       породил H3 (строка уехала в переменную).
  T2 — каждый элемент `CANON_LITERALS` объявлен директивой `i18n-keep` в `SKILL.md`
       (`HEURISTIC_LITERALS` — детекторы намерения в прозе, EN их нести не обязан).

ГРАНИЦА ОБЕЩАНИЯ (P3.8/D52, сужает D35 — честно, а не задним числом). T1 ловит ПЕРЕЧИСЛЕННЫЕ
ФОРМЫ сверки, а НЕ класс «любая сверка с текстом плана»: три вектора промаха (литерал в
локальной переменной · литерал в аргументе функции-хелпера · `re.finditer`) закрыты этим
item'ом и покрыты кейсами `TestT1CollectorVectors`, но полнота недостижима в разумном объёме —
динамически собранный шаблон (`"".join(parts)`, f-string), литерал, прочитанный из внешнего
файла/JSON, или свежая идиома мимо списка форм гейтом НЕ ловятся. Заводя НОВУЮ форму сверки,
добавь её сюда вместе с кейсом — «класс структурно невозможен» здесь не обещано.

Запуск: cd packages/task && python3 -m unittest discover -s tests
"""
import ast
import json
import re
import unittest
from pathlib import Path

try:
    from . import fixtures  # noqa: F401
except ImportError:
    import fixtures  # noqa: F401,E402
# Первым: fixture кладёт lib/ в sys.path; package- и discover-запуски оба поддержаны.
import task.plan_lint as plan_lint  # noqa: E402
from task.plan_lint import (  # noqa: E402
    CANON_LITERALS, HEURISTIC_LITERALS, I18N_KEEP_RE, SKILL_RELPATH, _find_skill,
)

PLAN_LINT_PY = Path(plan_lint.__file__).resolve()
# Скилл-SSOT канона: ищем от пакета вверх до корня монорепо. Standalone-раскладка (пакет
# task вне монорепо, скиллов рядом нет) — тест пропускается, а не падает.
# `_find_skill`/`I18N_KEEP_RE` — реюз `plan_lint.py` (2026.07.31-SKM-LEAN P5.9, Required
# Reads п. 4 «расширяется, не дублируется»): до этого item'а тот же обход и та же директива
# были определены здесь ВТОРЫМ носителем; теперь единственный владелец — модуль, `--conflicts`
# которого сверяет то же самое из CLI.


def _canonical_skill_or_skip():
    skill = _find_skill()
    if skill is not None:
        return skill
    if any((parent / "packages" / "task").is_dir() for parent in PLAN_LINT_PY.parents):
        raise AssertionError(f"монорепо найден, но canon SSOT отсутствует: {SKILL_RELPATH}")
    raise unittest.SkipTest(f"standalone-раскладка: нет {SKILL_RELPATH}")

CYRILLIC_RUN_RE = re.compile(r"[А-Яа-яЁё]")
# Кириллическая ФРАЗА литерала — то, что обязано найтись в реестре ЦЕЛИКОМ. Пословная сверка
# была бы дырой: `план` живёт в «Донор-план», `закрыт` — в «фаза закрыта» ⇒ незаявленный
# `план закрыт` (тот самый H3) прошёл бы гейт «по частям».
CYRILLIC_PHRASE_RE = re.compile(r"[А-Яа-яЁё][А-Яа-яЁё\s—-]*")
# Метасинтаксис regex вырезается: литерал сверки — часто ШАБЛОН (`^>\s*СКЕЛЕТ\s+—\s+не
# детализирован`), а канон объявляет строку (`> СКЕЛЕТ — не детализирован`); байт-в-байт
# они не сойдутся никогда, фраза внутри — сойдётся. Пробельный метасимвол (`\s+`) СКЛЕИВАЕТ
# фразу через пробел, остальной метасинтаксис (альтернация, якоря, кванторы) — РАЗРЫВАЕТ её:
# иначе `scriptPath|оркестрац|мультиагент` слился бы в одну несуществующую фразу.
RE_WHITESPACE_META_RE = re.compile(r"\\s[+*?]?")
RE_SYNTAX_RE = re.compile(r"\\[a-zA-Z]|\{\d+(?:,\d+)?\}|[\^$()\[\]{}*+?\\|]")
PHRASE_BREAK = "\x00"
# Функции `re`, чей ПЕРВЫЙ аргумент — шаблон (сверяется с текстом плана). `finditer`/`subn`
# были дырой (J8): идиома `re.finditer("<литерал>", text)` проходила мимо сборщика.
RE_PATTERN_FUNCS = ("compile", "escape", "match", "search", "fullmatch", "sub", "subn",
                    "split", "findall", "finditer")
# Строковые методы-грепы: их аргумент — строка, которую ищут в тексте плана.
STR_GREP_METHODS = ("startswith", "endswith", "count", "find", "index", "partition", "split")


def _is_string_expr(node):
    """Значение-выражение ИЗ СТРОКОВЫХ ЛИТЕРАЛОВ: `"…"` · конкатенация · кортеж/список строк ·
    `re.compile("…")`. Вызов рантайма (`ap.parse_args(argv)`, `row.get("Status", "")`) — НЕ он."""
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return bool(node.elts) and all(_is_string_expr(el) for el in node.elts)
    if isinstance(node, ast.BinOp):
        return _is_string_expr(node.left) and _is_string_expr(node.right)
    if isinstance(node, ast.Call):
        func = node.func
        return (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
                and func.value.id == "re" and func.attr in RE_PATTERN_FUNCS
                and bool(node.args) and _is_string_expr(node.args[0]))
    return False


def _string_bindings(tree):
    """`NAME = …` для разыменования ссылок: МОДУЛЬНЫЕ + ЛОКАЛЬНЫЕ (J8, вектор 1).

    Локальные обязательны: `marker = "…"; if marker in text` — тот же побег литерала в имя,
    что породил H3, только на шаг ниже, чем модульная константа.
    Асимметрия правил намеренная: модульная привязка берётся ЛЮБАЯ (по конвенции файла это
    константы), локальная — ТОЛЬКО строковое выражение (`_is_string_expr`). Иначе разыменование
    протаскивает строки из поддерева произвольного вызова: `ap = argparse.ArgumentParser(
    description="…")` + `args = ap.parse_args(argv)` дал бы «непокрытый литерал» на описании CLI
    (наблюдалось при первом прогоне расширенного сборщика).
    Одно имя может быть связано в разных областях видимости ⇒ храним ВСЕ привязки."""
    bindings = {}
    module_assigns = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            bindings.setdefault(node.targets[0].id, []).append(node.value)
            module_assigns.add(id(node))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and id(node) not in module_assigns \
                and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
                and _is_string_expr(node.value):
            bindings.setdefault(node.targets[0].id, []).append(node.value)
    return bindings


def _local_function_names(tree):
    """Имена функций, ОБЪЯВЛЕННЫХ в этом модуле (J8, вектор 2): их аргумент легко становится
    иглой грепа (`_grep(lines, "<литерал>")`). Builtins и чужие модули сюда не попадают —
    `print(f"нет планов…")` остаётся выводом, а не сверкой, и реестр литералов не раздувает."""
    return {node.name for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _strings_in(node, bindings, seen=None):
    """Все строковые константы поддерева, с разыменованием имён (по одному разу на имя)."""
    seen = seen if seen is not None else set()
    out = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            out.append((sub.value, getattr(sub, "lineno", None)))
        elif isinstance(sub, ast.Name) and sub.id in bindings and sub.id not in seen:
            seen.add(sub.id)
            for bound in bindings[sub.id]:
                out.extend(_strings_in(bound, bindings, seen))
    return out


class _GrepSiteCollector(ast.NodeVisitor):
    """Собирает строки, участвующие в сверке с текстом плана (см. докстринг модуля)."""

    def __init__(self, bindings, helpers=()):
        self.bindings = bindings
        self.helpers = set(helpers)
        self.found = []  # [(literal, lineno)]

    def _collect(self, node, lineno):
        for value, value_lineno in _strings_in(node, self.bindings):
            self.found.append((value, value_lineno or lineno))

    def visit_Compare(self, node):
        for operand in [node.left, *node.comparators]:
            self._collect(operand, node.lineno)
        self.generic_visit(node)

    def visit_Call(self, node):
        func = node.func
        if isinstance(func, ast.Attribute) and node.args:
            is_re = isinstance(func.value, ast.Name) and func.value.id == "re"
            if is_re and func.attr in RE_PATTERN_FUNCS:
                self._collect(node.args[0], node.lineno)
            elif func.attr in STR_GREP_METHODS:
                for arg in node.args:
                    self._collect(arg, node.lineno)
        elif isinstance(func, ast.Name) and func.id in self.helpers:
            for arg in node.args:  # аргумент функции-хелпера (J8, вектор 2)
                self._collect(arg, node.lineno)
        self.generic_visit(node)


def _collect_grep_sites(source, filename="<fragment>"):
    """AST-обход исходника → [(литерал, строка)] всех форм сверки, которые ловит T1."""
    tree = ast.parse(source, filename=filename)
    collector = _GrepSiteCollector(_string_bindings(tree), _local_function_names(tree))
    collector.visit(tree)
    return collector.found


def _squeeze(text):
    return re.sub(r"\s+", " ", text).strip()


def _uncovered_phrases(literal, registry):
    """Кириллические фразы литерала, не покрытые НИ ОДНИМ элементом реестра целиком."""
    haystack = [_squeeze(entry) for entry in registry]
    plain = RE_SYNTAX_RE.sub(PHRASE_BREAK, RE_WHITESPACE_META_RE.sub(" ", literal))
    phrases = [_squeeze(p) for p in CYRILLIC_PHRASE_RE.findall(plain)]
    return [p for p in phrases if p and not any(p in entry for entry in haystack)]


class TestT1CollectorVectors(unittest.TestCase):
    """J8/D52 — три известных вектора промаха сборщика T1. До P3.8 каждый давал 0 находок:
    литерал уезжал мимо гейта той же дорогой, что `план закрыт` (H3), и обнаруживался
    только аудитом. Кейсы — на СИНТЕТИЧЕСКИХ фрагментах: они фиксируют ФОРМУ, а не текущее
    содержимое `plan_lint.py` (иначе тест умрёт при первой же правке линтера)."""

    NEEDLE = "фаза закрыта"  # реальный литерал-детектор (HEURISTIC_LITERALS, D34)

    def _assert_caught(self, source, vector):
        found = [lit for lit, _ in _collect_grep_sites(source)]
        self.assertIn(self.NEEDLE, found,
                      f"вектор «{vector}» проходит мимо сборщика T1: {found}")

    def test_vector_local_variable(self):
        self._assert_caught(
            'def check(lines):\n'
            '    marker = "фаза закрыта"\n'
            '    return any(marker in ln for ln in lines)\n',
            "литерал в локальной переменной")

    def test_vector_helper_argument(self):
        self._assert_caught(
            'def _grep(lines, needle):\n'
            '    return any(needle in ln for ln in lines)\n'
            '\n'
            'def check(lines):\n'
            '    return _grep(lines, "фаза закрыта")\n',
            "литерал в аргументе функции-хелпера")

    def test_vector_re_finditer(self):
        self._assert_caught(
            'import re\n'
            'def check(text):\n'
            '    return list(re.finditer("фаза закрыта", text))\n',
            "литерал в re.finditer")

    def test_print_argument_is_not_a_grep_site(self):
        """Граница: вывод диагностики (builtin `print`) сверкой НЕ считается — иначе реестр
        литералов раздувается сообщениями, которые EN-канон нести не обязан."""
        found = [lit for lit, _ in _collect_grep_sites(
            'def report(root):\n'
            '    print(f"нет планов для проверки в {root}")\n')]
        self.assertEqual([f for f in found if CYRILLIC_RUN_RE.search(f)], [], found)


class TestCanonLiteralsRegistry(unittest.TestCase):
    def test_ast_every_cyrillic_comparison_is_declared(self):
        """T1: кириллическая сверка вне обоих реестров → FAIL с адресом и подсказкой."""
        sites = _collect_grep_sites(PLAN_LINT_PY.read_text(encoding="utf-8"), str(PLAN_LINT_PY))
        registry = tuple(CANON_LITERALS) + tuple(HEURISTIC_LITERALS)

        misses = []
        for literal, lineno in sites:
            if not CYRILLIC_RUN_RE.search(literal):
                continue
            uncovered = _uncovered_phrases(literal, registry)
            if uncovered:
                misses.append(
                    f"литерал «{literal}» (plan_lint.py:{lineno}) не объявлен "
                    f"(не покрыты: {', '.join(uncovered)}) — добавь его в CANON_LITERALS "
                    f"и директивой `<!-- i18n-keep: {literal} -->` в SKILL.md, ЛИБО "
                    f"внеси в HEURISTIC_LITERALS с обоснованием, ПОЧЕМУ присутствие в "
                    f"EN-каноне не требуется (детектор намерения в прозе, не канон-токен)")
        self.assertEqual(misses, [], "\n".join(["непокрытые литералы сверок:"] + misses))

    def test_canon_literals_declared_in_skill_canon(self):
        """T2: каждый элемент CANON_LITERALS объявлен директивой i18n-keep в SKILL.md."""
        skill_canon = _canonical_skill_or_skip()
        declared = set(I18N_KEEP_RE.findall(skill_canon.read_text(encoding="utf-8")))
        missing = [lit for lit in CANON_LITERALS if lit not in declared]
        self.assertEqual(
            missing, [],
            "литералы реестра CANON_LITERALS без директивы i18n-keep в EN-only SKILL.md: "
            + "; ".join(f"добавь `<!-- i18n-keep: {lit} -->`" for lit in missing))


class TestTaskContractCanonClaimIsBackedByCommands(unittest.TestCase):
    """P2.7/F1 repair — the literal test Implementation Rules (2) demands: §13's claim
    that `task:plan-exec`/`task:plan-close` CALL the Task Contract compiler is checked
    against the actual command bodies, not trusted. Before P2.7 the canon asserted
    "Commands call it at the noted pre-mutation/pre-final checkpoints" while
    `plan-exec.md:58` was conditional ("при наличии смонтированного Task Contract
    JSON") and nothing ever mounted one (audit finding F1) — this test goes RED the
    moment either half of that pairing (claim vs call) is edited without the other:
    strengthen/replace the claim without touching the calls, or remove the calls
    without softening the claim, and a run here catches it before publication."""

    SKILL_EN_RELPATH = Path("packages/skiller/skills/general/plan-protocol/SKILL.md")
    PLAN_EXEC_RELPATH = Path("packages/task/commands/plan-exec.md")
    PLAN_CLOSE_RELPATH = Path("packages/task/commands/plan-close.md")

    # F1's exact banned formulation — a synonym of it re-appearing anywhere in the
    # write-site paragraphs is the regression this test exists to catch.
    BANNED_CONDITIONAL_RU = "при наличии смонтированного"
    BANNED_CONDITIONAL_EN = "when a Task Contract JSON happens to be mounted"

    @classmethod
    def setUpClass(cls):
        repo_root = None
        for parent in PLAN_LINT_PY.parents:
            if (parent / cls.SKILL_EN_RELPATH).is_file():
                repo_root = parent
                break
        if repo_root is None:
            raise unittest.SkipTest(
                f"standalone-раскладка: не найден {cls.SKILL_EN_RELPATH} "
                f"(от {PLAN_LINT_PY} вверх) — SSOT канона недоступен")
        cls.repo_root = repo_root
        cls.skill_en = _canonical_skill_or_skip().read_text(encoding="utf-8")
        cls.plan_exec = (repo_root / cls.PLAN_EXEC_RELPATH).read_text(encoding="utf-8")
        cls.plan_close = (repo_root / cls.PLAN_CLOSE_RELPATH).read_text(encoding="utf-8")

    def test_canon_claims_the_checkpoints_call_the_compiler(self):
        """§13 must assert the CALL, not a weaker availability hedge."""
        self.assertIn("task_contract.build", self.skill_en)
        self.assertIn("task_contract.evaluate", self.skill_en)
        self.assertIn("task:plan-exec", self.skill_en)
        self.assertIn("task:plan-close", self.skill_en)

    def test_canon_does_not_repeat_f1s_banned_conditional(self):
        """F1's exact defect must not return to the EN canon."""
        self.assertNotIn(self.BANNED_CONDITIONAL_EN, self.skill_en)

    def test_plan_exec_pre_mutation_actually_calls_the_compiler(self):
        """The command body itself — not just the canon's claim about it — carries an
        unconditional call: both compiler entry points named, no F1 conditional."""
        self.assertIn("task_contract.build", self.plan_exec)
        self.assertIn("task_contract.evaluate", self.plan_exec)
        self.assertIn('result["pre_mutation"]', self.plan_exec)
        self.assertNotIn(self.BANNED_CONDITIONAL_RU, self.plan_exec)

    def test_plan_close_pre_final_actually_calls_the_compiler(self):
        self.assertIn("task_contract.build", self.plan_close)
        self.assertIn("task_contract.evaluate", self.plan_close)
        self.assertIn('result["pre_final"]', self.plan_close)
        self.assertNotIn(self.BANNED_CONDITIONAL_RU, self.plan_close)


class TestPreFinalGateIsBinaryNotGreenlitByNA(unittest.TestCase):
    """D76/D77/M1/M5/M6 repair (P2.11) — a DIFFERENTIATING predicate (D79), not a
    naming-only test: every assertion here was verified RED against the exact
    pre-P2.11 command bodies (`plan-close.md`/`plan-exec.md` at commit `5a410858`,
    byte-identical to `d11c3b74` for these files) before being added — see
    Completion Notes P2.11 for the recorded red run. `TestTaskContractCanonClaim
    IsBackedByCommands` above only asserts presence of identifiers; it went GREEN
    through the M1 defect (`in ("allow", "n/a")` greenlit a failed pre_mutation) and
    the M5 defect (`plan-exec.md` step 7 carried the string `pre_final` only in one
    prose sentence, never `result["pre_final"]`) — this class exists because that
    kind of test protects nothing (M6)."""

    PLAN_EXEC_RELPATH = Path("packages/task/commands/plan-exec.md")
    PLAN_CLOSE_RELPATH = Path("packages/task/commands/plan-close.md")
    SKILL_EN_RELPATH = Path("packages/skiller/skills/general/plan-protocol/SKILL.md")

    # M1's exact defect, byte-for-byte as it stood before P2.11: an exit predicate
    # that accepts `n/a` as green. A tolerant regex (whitespace-insensitive) so a
    # future reformat of the same defect is still caught.
    BANNED_NA_GREENLIGHT_RE = re.compile(r'in\s*\(\s*"allow"\s*,\s*"n/a"\s*\)')

    @classmethod
    def setUpClass(cls):
        repo_root = None
        for parent in PLAN_LINT_PY.parents:
            if (parent / cls.SKILL_EN_RELPATH).is_file():
                repo_root = parent
                break
        if repo_root is None:
            raise unittest.SkipTest(
                f"standalone-раскладка: не найден {cls.SKILL_EN_RELPATH} "
                f"(от {PLAN_LINT_PY} вверх) — SSOT канона недоступен")
        cls.repo_root = repo_root
        cls.plan_exec = (repo_root / cls.PLAN_EXEC_RELPATH).read_text(encoding="utf-8")
        cls.plan_close = (repo_root / cls.PLAN_CLOSE_RELPATH).read_text(encoding="utf-8")
        cls.skill_en = _canonical_skill_or_skip().read_text(encoding="utf-8")

    def test_neither_closing_command_greenlights_n_a(self):
        """M1: the exact `in ("allow", "n/a")` predicate must be gone from BOTH
        commands that evaluate pre_final — a regression here reopens M1."""
        for label, text in (("plan-close", self.plan_close), ("plan-exec", self.plan_exec)):
            with self.subTest(command=label):
                self.assertIsNone(self.BANNED_NA_GREENLIGHT_RE.search(text),
                                  f"{label}.md still greenlights n/a as a pre_final verdict")

    def test_both_closing_commands_gate_on_binary_allow_and_allow(self):
        """D76 fix: the exit predicate is a binary AND of both codes == 'allow'."""
        needle = 'result["pre_mutation"] == "allow" and result["pre_final"] == "allow"'
        for label, text in (("plan-close", self.plan_close), ("plan-exec", self.plan_exec)):
            with self.subTest(command=label):
                self.assertIn(needle, text)

    def test_plan_exec_step_7_calls_pre_final_on_the_routine_close_path(self):
        """M5: `plan-exec` closes the item itself (routine path) — before P2.11 its
        step 7 carried `pre_final` only in one prose sentence (`findings/14` M5),
        never a `result["pre_final"]` reference. Regression here reopens M5."""
        self.assertIn('result["pre_final"]', self.plan_exec)
        self.assertIn("task_contract.evaluate", self.plan_exec)

    def test_canon_states_n_a_is_not_green(self):
        """Compact D76 canon keeps the binary predicate without wording coupling."""
        self.assertIn("both codes must be `allow`", self.skill_en)

    def test_canon_names_the_pre_final_predicate_boundary(self):
        """D77: §13 names the spec-FORM boundary rather than claiming good execution."""
        self.assertIn("spec's FORM", self.skill_en)


class TestBoundedAuditRepairContract(unittest.TestCase):
    """D17: RED audit recovery is direct and has one repair round, not a design loop."""

    @classmethod
    def setUpClass(cls):
        repo_root = PLAN_LINT_PY.parents[4]
        cls.plan_audit = (repo_root / "packages/task/commands/plan-audit.md").read_text(
            encoding="utf-8")
        cls.plan_exec = (repo_root / "packages/task/commands/plan-exec.md").read_text(
            encoding="utf-8")

    def test_red_payload_routes_to_the_owning_item_not_phase_design(self):
        self.assertIn("<repair-command из Routing:", self.plan_audit)
        self.assertIn("несколько затронутых manual-items", self.plan_audit)
        self.assertNotIn(
            "\n/task:plan-design <PLAN-ID> Pn\n\nРЕЖИМ:", self.plan_audit)

    def test_second_audit_is_final_and_terminal_item_has_one_repair_exception(self):
        self.assertIn("второй аудит финальный", self.plan_audit)
        self.assertIn("кроме bounded audit repair-forward", self.plan_exec)
        self.assertIn("observed_rounds < audit_rounds_max", self.plan_exec)
        self.assertIn("третьего\n   repair/audit цикла нет", self.plan_exec)


class TestCommandReadPathProjection(unittest.TestCase):
    """P1.5: five command bodies project the sole executable layout."""

    COMMANDS = ("plan-design.md", "plan-exec.md", "plan-run.md", "plan-close.md", "plan-audit.md")
    V2_SLOTS = (
        "`plans/<PLAN-ID>/plan.md` — identity, Context, Execution Rules и §3 Routing",
        "`plans/<PLAN-ID>/phases/<Pn>/<Pn>.md` — только Phase Context",
        "`plans/<PLAN-ID>/phases/<Pn>/<Pn.m>.md` — полное ТЗ выбранного item",
        "`plans/<PLAN-ID>/bundles/<Pn.m>.json` — объявленные digest-qualified inputs",
        "`plans/<PLAN-ID>/phases/<Pn>/<Pn.m>.state.md` — byte-fresh item state",
    )

    @classmethod
    def setUpClass(cls):
        cls.repo_root = PLAN_LINT_PY.parents[4]
        cls.spec = json.loads((cls.repo_root / "packages/task/configs/read-path-v1.spec.json")
                              .read_text(encoding="utf-8"))

    def test_spec_keeps_only_v2_layout(self):
        self.assertEqual(set(self.spec["layout_versions"]), {"v2"})
        self.assertEqual(len(self.spec["paths"]["executor"]["slots"]), 5)
        self.assertEqual(
            self.spec["predicates"]["executor_handoff_exclusion"],
            "no executor slot carrier id is handoff",
        )

    def test_every_command_requires_explicit_v2_layout(self):
        for command in self.COMMANDS:
            with self.subTest(command=command):
                text = (self.repo_root / "packages/task/commands" / command).read_text(encoding="utf-8")
                self.assertIn("PLAN_LAYOUT_V1_RETIRED", text)
                self.assertIn("`handoff.md` НЕ входит в обязательный путь", text)
                for slot in self.V2_SLOTS:
                    self.assertIn(slot, text)

    def test_closing_commands_require_neutral_session_identity(self):
        for command in self.COMMANDS:
            with self.subTest(command=command):
                text = (self.repo_root / "packages/task/commands" / command).read_text(encoding="utf-8")
                self.assertIn("plan-session.py current --id", text)
                self.assertNotIn("CODEX_THREAD_ID", text)
        for command in ("plan-exec.md", "plan-run.md"):
            text = (self.repo_root / "packages/task/commands" / command).read_text(encoding="utf-8")
            self.assertIn("derive_run_id", text)
            self.assertIn("--run-id", text)

    def test_closure_production_is_explicit(self):
        for command in ("plan-exec.md", "plan-close.md"):
            with self.subTest(command=command):
                text = (self.repo_root / "packages/task/commands" / command).read_text(encoding="utf-8")
                self.assertIn("plan-downstream.py", text)
                self.assertIn("unqualifiable", text)


class TestQualifiedItemReferenceCanon(unittest.TestCase):
    """P2.2: global item references carry the plan identity."""

    @classmethod
    def setUpClass(cls):
        cls.repo_root = PLAN_LINT_PY.parents[4]
        cls.skill = (cls.repo_root / "packages/skiller/skills/general/plan-protocol/SKILL.md").read_text(
            encoding="utf-8")
        cls.template = (cls.repo_root / "packages/skiller/skills/general/plan-protocol/"
                        "snippets/plan-template.md").read_text(encoding="utf-8")
        cls.plan_design = (cls.repo_root / "packages/task/commands/plan-design.md").read_text(
            encoding="utf-8")

    def test_canonical_sources_distinguish_global_and_plan_local_references(self):
        self.assertIn("collision-free `<PLAN-ID> Pn.m` form", self.skill)
        self.assertIn("Bare `Pn.m` is allowed only inside that plan's own", self.skill)
        self.assertIn("carriers when the plan identity is already unambiguous", self.skill)
        self.assertIn("формой `<PLAN-ID> Pn.m`; голый `Pn.m` допустим", self.template)
        self.assertIn("внешняя ссылка на item использует", self.plan_design)
        self.assertIn("`<PLAN-ID> Pn.m`; голый `Pn.m` допустим", self.plan_design)


class TestLayoutV2ContextEnum(unittest.TestCase):
    """Consumer commands emit only the provider-neutral layout-v2 enum."""

    @classmethod
    def setUpClass(cls):
        cls.repo_root = PLAN_LINT_PY.parents[4]

    def test_plan_audit_and_exec_use_only_current_context_values(self):
        for command in ("plan-audit.md", "plan-exec.md"):
            with self.subTest(command=command):
                text = (self.repo_root / "packages/task/commands" / command).read_text(
                    encoding="utf-8")
                for value in ("continue-root", "isolated-child-return", "cold-start-root"):
                    self.assertIn(value, text)
                self.assertNotIn("continue (/clear) — ручной item", text)
                self.assertNotIn("NEW SESSION — Workflow-оркестрован", text)
                self.assertNotIn("NEW SESSION — шаг-не-item", text)


if __name__ == "__main__":
    unittest.main()
