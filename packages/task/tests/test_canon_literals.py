"""Гейт ПОЛНОТЫ гейта непереводимых литералов (P2.16/D35, дефект H3).

Механизм двухступенчат:
  * `SKILL.ru.md` объявляет директиву `<!-- i18n-keep: <литерал> -->`, а
    `packages/skiller/scripts/check-translations.sh` требует её присутствия в EN-каноне
    `SKILL.md` байт-в-байт (иначе генератор EN волен перевести строку, и линтер флота
    перестанет её опознавать — инцидент G3);
  * но сам гейт видит ТОЛЬКО объявленное. Инлайн-строка `план закрыт` (три сверки в
    `plan_lint.py`) константы не имела, в директивах не значилась — гейт был к ней СЛЕП.

Отсюда два теста:
  T1 — AST-обход `plan_lint.py`: кириллический литерал, участвующий в СВЕРКЕ С ТЕКСТОМ ПЛАНА
       (`Compare` — `in`/`==`; аргумент-шаблон `re.compile`/`re.escape`/`re.finditer`/…;
       строковые методы `startswith`/`count`/…; аргумент функции, ОБЪЯВЛЕННОЙ в этом модуле),
       обязан быть покрыт реестром `CANON_LITERALS` ∪ `HEURISTIC_LITERALS`. Ссылки на имена —
       модульные И локальные — РАЗЫМЕНОВЫВАЮТСЯ: иначе гейт обходится тем же приёмом, что
       породил H3 (строка уехала в переменную).
  T2 — каждый элемент `CANON_LITERALS` объявлен директивой `i18n-keep` в `SKILL.ru.md`
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
import re
import unittest
from pathlib import Path

import fixtures  # noqa: F401,E402  — ПЕРВЫМ: его импорт кладёт lib/ в sys.path (голый
                 # `python3 -m unittest discover -s tests`, без PYTHONPATH, иначе не найдёт task)
import task.plan_lint as plan_lint  # noqa: E402
from task.plan_lint import CANON_LITERALS, HEURISTIC_LITERALS  # noqa: E402

PLAN_LINT_PY = Path(plan_lint.__file__).resolve()
# Скилл-SSOT канона: ищем от пакета вверх до корня монорепо. Standalone-раскладка (пакет
# task вне монорепо, скиллов рядом нет) — тест пропускается, а не падает.
SKILL_RELPATH = Path("packages/skiller/skills/general/plan-protocol/SKILL.ru.md")

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
# Директива — тот же формат, что парсит check-translations.sh (SSOT формата — там).
I18N_KEEP_RE = re.compile(r"<!--\s*i18n-keep:\s*(.+?)\s*-->")
# Функции `re`, чей ПЕРВЫЙ аргумент — шаблон (сверяется с текстом плана). `finditer`/`subn`
# были дырой (J8): идиома `re.finditer("<литерал>", text)` проходила мимо сборщика.
RE_PATTERN_FUNCS = ("compile", "escape", "match", "search", "fullmatch", "sub", "subn",
                    "split", "findall", "finditer")
# Строковые методы-грепы: их аргумент — строка, которую ищут в тексте плана.
STR_GREP_METHODS = ("startswith", "endswith", "count", "find", "index", "partition", "split")


def _find_skill_ru():
    for parent in PLAN_LINT_PY.parents:
        candidate = parent / SKILL_RELPATH
        if candidate.is_file():
            return candidate
    return None


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
                    f"и директивой `<!-- i18n-keep: {literal} -->` в SKILL.ru.md, ЛИБО "
                    f"внеси в HEURISTIC_LITERALS с обоснованием, ПОЧЕМУ присутствие в "
                    f"EN-каноне не требуется (детектор намерения в прозе, не канон-токен)")
        self.assertEqual(misses, [], "\n".join(["непокрытые литералы сверок:"] + misses))

    def test_canon_literals_declared_in_skill_ru(self):
        """T2: каждый элемент CANON_LITERALS объявлен директивой i18n-keep в SKILL.ru.md."""
        skill_ru = _find_skill_ru()
        if skill_ru is None:
            self.skipTest(f"standalone-раскладка: не найден {SKILL_RELPATH} "
                          f"(от {PLAN_LINT_PY} вверх) — SSOT канона недоступен")
        declared = set(I18N_KEEP_RE.findall(skill_ru.read_text(encoding="utf-8")))
        missing = [lit for lit in CANON_LITERALS if lit not in declared]
        self.assertEqual(
            missing, [],
            "литералы реестра CANON_LITERALS без директивы i18n-keep в SKILL.ru.md "
            "(EN-канон волен их перевести, и гейт check-translations.sh промолчит): "
            + "; ".join(f"добавь `<!-- i18n-keep: {lit} -->`" for lit in missing))


if __name__ == "__main__":
    unittest.main()
