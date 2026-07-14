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
       (`Compare` — `in`/`==`; аргумент-шаблон `re.compile`/`re.escape`/…; строковые методы
       `startswith`/`count`/…), обязан быть покрыт реестром `CANON_LITERALS` ∪
       `HEURISTIC_LITERALS`. Ссылки на модульные константы РАЗЫМЕНОВЫВАЮТСЯ — иначе гейт
       обходится тем же приёмом, что и породил H3 (строка уехала в константу).
  T2 — каждый элемент `CANON_LITERALS` объявлен директивой `i18n-keep` в `SKILL.ru.md`
       (`HEURISTIC_LITERALS` — детекторы намерения в прозе, EN их нести не обязан).

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
# Функции `re`, чей ПЕРВЫЙ аргумент — шаблон (сверяется с текстом плана).
RE_PATTERN_FUNCS = ("compile", "escape", "match", "search", "fullmatch", "sub", "findall")
# Строковые методы-грепы: их аргумент — строка, которую ищут в тексте плана.
STR_GREP_METHODS = ("startswith", "endswith", "count", "find", "index", "partition", "split")


def _find_skill_ru():
    for parent in PLAN_LINT_PY.parents:
        candidate = parent / SKILL_RELPATH
        if candidate.is_file():
            return candidate
    return None


def _module_constants(tree):
    """Модульные `NAME = <строка|кортеж строк|конкатенация>` — для разыменования ссылок."""
    consts = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            consts[node.targets[0].id] = node.value
    return consts


def _strings_in(node, consts, seen=None):
    """Все строковые константы поддерева, с разыменованием модульных имён (по одному разу)."""
    seen = seen if seen is not None else set()
    out = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            out.append((sub.value, getattr(sub, "lineno", None)))
        elif isinstance(sub, ast.Name) and sub.id in consts and sub.id not in seen:
            seen.add(sub.id)
            out.extend(_strings_in(consts[sub.id], consts, seen))
    return out


class _GrepSiteCollector(ast.NodeVisitor):
    """Собирает строки, участвующие в сверке с текстом плана (см. докстринг модуля)."""

    def __init__(self, consts):
        self.consts = consts
        self.found = []  # [(literal, lineno)]

    def _collect(self, node, lineno):
        for value, value_lineno in _strings_in(node, self.consts):
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
        self.generic_visit(node)


def _squeeze(text):
    return re.sub(r"\s+", " ", text).strip()


def _uncovered_phrases(literal, registry):
    """Кириллические фразы литерала, не покрытые НИ ОДНИМ элементом реестра целиком."""
    haystack = [_squeeze(entry) for entry in registry]
    plain = RE_SYNTAX_RE.sub(PHRASE_BREAK, RE_WHITESPACE_META_RE.sub(" ", literal))
    phrases = [_squeeze(p) for p in CYRILLIC_PHRASE_RE.findall(plain)]
    return [p for p in phrases if p and not any(p in entry for entry in haystack)]


class TestCanonLiteralsRegistry(unittest.TestCase):
    def test_ast_every_cyrillic_comparison_is_declared(self):
        """T1: кириллическая сверка вне обоих реестров → FAIL с адресом и подсказкой."""
        tree = ast.parse(PLAN_LINT_PY.read_text(encoding="utf-8"), filename=str(PLAN_LINT_PY))
        collector = _GrepSiteCollector(_module_constants(tree))
        collector.visit(tree)
        registry = tuple(CANON_LITERALS) + tuple(HEURISTIC_LITERALS)

        misses = []
        for literal, lineno in collector.found:
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
