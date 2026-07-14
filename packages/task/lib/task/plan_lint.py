"""plan_lint — детерминированный валидатор протокола исполняемых мастер-планов
`plans/<PLAN-ID>/{plan.md, phases/Pn.md, handoff.md}`.

Схема (жёстко фиксирована — SSOT: скилл `packages/skiller/skills/general/
plan-protocol/SKILL.ru.md` + его `snippets/{plan,phase,handoff}-template.md`;
эти три файла и `commands/plan-{design,exec,close,audit}.md` уже вызывают
именно этот скрипт как `scripts/plan-lint.py plans/<ID>`):
  plan.md      — «## 0. Meta» (ТАБЛИЦА `Поле|Значение`; обязательные
                 Plan ID/Title/Version/Status) + «## 4. Phase Index & Status
                 Board» (таблица `Phase|Title|Items 🟢/всего|Status`).
  phases/Pn.md — «## Phase Status» (таблица `ID|Title|Status|Updated`, по
                 строке на item), item-блоки (`### Pn.m — Заголовок`, поля
                 строками `**Поле:** значение`) и «## Phase Handoff» в конце.
  handoff.md   — `# HANDOFF — … — after Pn.m` + поля Next/Done/Remaining/
                 Sources of truth (минимально обязательные; протокол несёт ещё
                 Open risks/Workarounds — их наличие лишним не считается).

stdlib-only (re/argparse/pathlib/json/sys), сообщения — на русском.
"""
import argparse
import io
import json
import re
import subprocess
import sys
import tarfile
import tempfile
from collections import Counter
from pathlib import Path

try:
    # core.warn — дословно то же самое (print "WARN: …" в stderr); переиспользуем
    # вместо дубля. Опционально: core/ на PYTHONPATH добавляет лаунчер
    # (scripts/plan-lint.py), в standalone-раскладке (нет core/) — свой фолбэк.
    from core.term import warn as _core_warn
except ImportError:  # pragma: no cover - standalone-фолбэк, см. docstring выше
    def _core_warn(msg):
        print(f"WARN: {msg}", file=sys.stderr)

# --- канон схемы -------------------------------------------------------------

# РОВНО 6 канонических статусов — никаких иных строк/синонимов не допускается.
STATUSES = (
    "⬜ Not started",
    "🟡 In progress",
    "🟢 Done",
    "🟠 Done with deviations",
    "🔴 Blocked",
    "⛔ Skipped by decision",
)
STATUS_BLOCKED = "🔴 Blocked"
STATUS_DONE = "🟢 Done"
STATUS_DEVIATIONS = "🟠 Done with deviations"
STATUS_IN_PROGRESS = "🟡 In progress"
# «терминальный» = фаза закрыта (готова/пропущена/сдана с оговорками) —
# используется для phase-first-эвристики (WARNING), не путать с 🔴 (стоит, не закрыта).
TERMINAL_STATUSES = (STATUS_DONE, STATUS_DEVIATIONS, "⛔ Skipped by decision")
EMPTY_PLACEHOLDER = "—"  # пустое поле помечается ровно этим символом (em dash)

# Meta — таблица `Поле|Значение`; обязательны только 4 identity-поля (остальные 8 из
# шаблона — Document Type/Authoring Model/…/Approval Owner — информационные, не гейтятся).
REQUIRED_META_FIELDS = ("Plan ID", "Title", "Version", "Status")
META_TABLE_COLUMNS = ("Поле", "Значение")
# Полный канон item-полей — SKILL.ru.md §4 / snippets/phase-template.md, строго в этом
# порядке (порядок здесь не гейтится, только присутствие — см. lint_plan).
REQUIRED_ITEM_FIELDS = (
    "Status", "Intent", "Why", "Scope Included", "Scope Excluded", "Inputs", "Files",
    "Required Reads", "Implementation Rules", "Code Guidance", "Validation",
    "Deliverables", "Completion Notes", "Pending Work", "Known Deviations",
    "Escalation Needed",
)
STATUS_BOARD_COLUMNS = ("Phase", "Title", "Items 🟢/всего", "Status")
STATUS_BOARD_ITEMS_COL = "Items 🟢/всего"
PHASE_STATUS_COLUMNS = ("ID", "Title", "Status", "Updated")
# handoff.md — минимально обязательные 4 поля (протокол несёт ещё Open risks и
# Workarounds/Deferred/Open questions — их отсутствие лишь предупреждение см. WARNING).
HANDOFF_REQUIRED_FIELDS = ("Next", "Done", "Remaining", "Sources of truth")

# --- regex-канон ---------------------------------------------------------
ITEM_HEADER_RE = re.compile(r"^###\s+(P\d+\.\d+)\s+—\s+(.*)$")
SECTION_HEADER_RE = re.compile(r"^##\s+\S.*$")  # уровень 2 (### уровня 3 не матчит)
META_HEADER_RE = re.compile(r"^##\s+0\.\s+Meta\s*$")
STATUS_BOARD_HEADER_RE = re.compile(r"^##\s+4\.\s+Phase Index & Status Board\s*$")
PHASE_STATUS_HEADER_RE = re.compile(r"^##\s+Phase Status\s*$")
PHASE_HANDOFF_HEADER_RE = re.compile(r"^##\s+Phase Handoff\s*$")
FIELD_RE = re.compile(r"^\*\*([^*:]+):\*\*\s*(.*)$")
ESCALATION_RE = re.compile(r"^>\s*🔴\s*ESCALATION\s+(P\d+\.\d+)\s*:")
# Две формы заголовка handoff (SKILL §8 / D30): `after Pn.m` — закрыт item; `after Pn` —
# закрыта/проаудирована/ре-дизайнена ФАЗА (шаг без «последнего закрытого item'а» как
# адресата). Группа отдаёт ссылку: с точкой — item, без точки — фаза (резолвится в
# lint_plan). Иные формы (`after phase 2`, `after P2 item 8`) остаются ERROR.
HANDOFF_TITLE_RE = re.compile(r"^#\s+HANDOFF\s+—.*—\s+after\s+(P\d+(?:\.\d+)?)\s*$")
HANDOFF_TITLE_HELP = ("заголовок не соответствует ни одной из двух форм (SKILL §8): "
                      "«# HANDOFF — … — after Pn.m» (item) · «# HANDOFF — … — after Pn» (фаза)")
PLAN_EXEC_RE = re.compile(r"/task:plan-exec\s+(\S+)\s+(P\d+\.\d+)")
# Форма m8/B1/N1/N2: `handoff.Next` допускает закрытый enum 8 форм (SKILL §8) —
# ниже регулярки на каждую (кроме plan-exec/«план закрыт», уже объявленных). Порядок
# проверки в резолвере (см. lint_plan) идёт от специфичной к общей: design-item ДО
# design-phase (иначе `(?!\.\d)`-lookahead фазовой формы просто не даст матчу проиграть
# ветке item), plan-close-archive ДО общего plan-close (иначе «archive» читался бы как
# «фаза»/PLAN-ID общей формы — хотя у общей формы обязателен `P\d+`, конфликта нет; тем
# не менее порядок фиксируем явно, а не полагаемся на побочный эффект regex).
PLAN_DESIGN_ITEM_RE = re.compile(r"/task:plan-design\s+(\S+)\s+(P\d+\.\d+)")
# Следующий шаг допустим и как «сначала детализировать фазу-скелет» (Execution Rules
# протокола прямо предписывают plan-design перед plan-exec на фазах без заполненных
# 16 полей) — ссылка на ФАЗУ (Pn), не на item (Pn.m).
PLAN_DESIGN_PHASE_RE = re.compile(r"/task:plan-design\s+(\S+)\s+(P\d+)(?!\.\d)\b")
PLAN_AUDIT_RE = re.compile(r"/task:plan-audit\s+(\S+)\s+(P\d+)(?!\.\d)\b")
PLAN_CLOSE_ARCHIVE_RE = re.compile(r"/task:plan-close\s+archive\s+(\S+)")
PLAN_CLOSE_RE = re.compile(r"/task:plan-close\s+(\S+)\s+(P\d+)(\.\d+)?\b")
MANUAL_RUN_MARKER = "ЗАПУСК ВРУЧНУЮ"  # Exec=manual (§9): форма без slash-команды, ищется подстрокой
NEXT_FORMS_HELP = (
    "Next не соответствует ни одной из допустимых форм (SKILL §8): "
    "/task:plan-exec <ID> Pn.m · /task:plan-design <ID> Pn · /task:plan-design <ID> Pn.m · "
    "/task:plan-audit <ID> Pn · /task:plan-close <ID> Pn[.m] · /task:plan-close archive <ID> · "
    "«план закрыт» · «ЗАПУСК ВРУЧНУЮ: <model/effort>»"
)
PHASE_FILENAME_RE = re.compile(r"^(P\d+)\.md$")
PHASE_TOKEN_RE = re.compile(r"^P(\d+)$")
DONE_TOTAL_RE = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*$")
ACTIVE_FIELD_RE = re.compile(r"^\*\*Active:\*\*\s*(.+)$")
ACTIVE_FILENAME = "ACTIVE.md"
README_FILENAME = "README.md"

# --- канон 2.0 (все проверки ниже — ТОЛЬКО warning, существующие планы не ломаем) --
# Маркер фазы-скелета (SKILL §5): при нём пустые поля items легальны, без него
# item с ≥50% пустых полей — warning (P0.3 рек#1).
SKELETON_MARKER_RE = re.compile(r"^>\s*СКЕЛЕТ\s+—\s+не детализирован")
# Маркер неоднозначности (SKILL §7): в фазе со статусом 🟡+ (не ⬜) = DoR-warning.
NEEDS_CLARIFICATION_RE = re.compile(r"\[NEEDS CLARIFICATION")
# RAG-маркеры несущих фактов (SKILL §7, enum из трёх значений — D29) — эвристика по
# D-логу. `RAG:—` (repo-grounded) пишется через em dash, как EMPTY_PLACEHOLDER;
# ASCII-дефис не канонизирован.
RAG_MARKER_RE = re.compile(r"RAG:✅|RAG:" + EMPTY_PLACEHOLDER + r"|\[UNVERIFIED\]")
# launch-block в handoff.Next (SKILL §8): таблица с `| Model |` + code-block.
LAUNCH_TABLE_ROW_RE = re.compile(r"^\|\s*Model\s*\|")
CODE_FENCE_RE = re.compile(r"^\s*```")
# Канонический порядок нумерованных секций plan.md (P0.3 рек#6).
PLAN_SECTION_NUM_RE = re.compile(r"^##\s+(\d+)\.\s+(.*?)\s*$")
PLAN_SECTION_TITLES = {
    0: "Meta", 1: "Context", 2: "Execution Rules", 3: "Routing",
    4: "Phase Index & Status Board", 5: "Decision Log", 6: "Update Log",
}
# --- m7/D10: `## 7. Contracts` — носитель cross-plan notification ---------------
# Секция опциональна и молода → ВСЕ находки по ней WARNING-уровня (ERROR сломал бы
# back-compat-гейт: ни один живой план флота секции не имеет).
# Опознаётся по ЗАГОЛОВКУ, не по номеру (D20): номер 7 — канон для НОВЫХ планов, но
# живые планы уже заняли его своими секциями (VLT-HSEAM «## 7. Обсуждение») — жёсткая
# привязка номера дала бы им новые WARNING «≠ канонической «## 7. Contracts»».
CONTRACTS_HEADER_RE = re.compile(r"^##\s+(?:\d+\.\s+)?Contracts\s*$")
CONTRACTS_EXPORTED_RE = re.compile(r"^\s*###\s+Exported\s*$")
CONTRACTS_CONSUMED_RE = re.compile(r"^\s*###\s+Consumed\s*$")
EXPORTED_COLUMNS = ("Контракт", "Версия", "Статус", "Потребители", "Уведомлены")
CONSUMED_COLUMNS = ("Контракт", "Донор-план", "Pinned", "Замечено", "Реакция")
SEMVER_RE = re.compile(r"v(\d+)\.(\d+)\.(\d+)")
DECISION_LOG_HEADER_RE = re.compile(r"^##\s+5\.\s+Decision Log\s*$")
UPDATE_LOG_HEADER_RE = re.compile(r"^##\s+6\.\s+Update Log\s*$")
UPDATE_LOG_MAX_CHARS = 300  # лимит «Что» Update Log (P0.3 рек#5, EDUFY 54KB-инцидент)
PHASE_CONTEXT_HEADER_RE = re.compile(r"^##\s+Phase Context\s*$")
# порог «item по сути пуст» для требования скелет-маркера
SKELETON_EMPTY_RATIO = 0.5

# --- P4.3: канон ID / места-имени workflow-скрипта / supersedes (D24/D27/D28) --
# Регулярка PLAN-ID (D16/D24) — union: датовый канон `ГГГГ.ММ.ДД-КОДОВОЕ-ИМЯ`
# и старый паттерн (back-compat: живые планы SKM-ROADMAP-005/SKM-AUDIT-004 матчат
# старый → 0 warning; несоответствие ни одному — WARNING, никогда не ERROR).
PLAN_ID_DATED_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2}-[A-Z][A-Z0-9-]*$")
PLAN_ID_LEGACY_RE = re.compile(r"^[A-Z][A-Z0-9-]+$")
# Маркер workflow-скрипта в теле .js — детект ПОДСТРОКОЙ (не eval/import JS,
# прецедент P2.1/D19 `parse_script_meta`).
WORKFLOW_META_MARKER = "export const meta"
WORKFLOW_DIR_NAME = "workflows"  # единственный дом скриптов плана (D28)

# --- P4.6: workflow-как-DoR — грепаемый признак заявленной оркестрации (D29) ---
# КОНСЕРВАТИВНЫЙ набор маркеров в теле фазы: явный `scriptPath` launch-block'а,
# «оркестрац», «мультиагент»/`multi-agent`. Правило Code Guidance «при сомнении НЕ
# срабатывать» перевешивает буквальный список: бумерный `fan-out` НАМЕРЕННО исключён —
# как одиночное слово он ловит нерелевантную прозу (напр. «искажение при fan-out» в
# Known Deviations про токен-учёт), давая ложный warning. Условность (D29): ручное
# item-by-item исполнение workflow не требует — маркер должен быть намеренным.
ORCHESTRATION_MARKER_RE = re.compile(r"scriptPath|оркестрац|мультиагент|multi-agent", re.IGNORECASE)

# --- P2.15/D34: протухший `## Phase Handoff` при реопене фазы (H2) --------------
# Реопен (SKILL §3, 4-й шаг) НЕ удаляет блок сдачи, а помечает его ПЕРВОЙ НЕПУСТОЙ строкой
# маркером `> УСТАРЕЛ — фаза реопенена <D#>` (провенанс сдачи сохраняется, ложь снимается);
# перезаписывает блок `plan-close` при следующем закрытии фазы. Жирное начертание маркера
# (`> **УСТАРЕЛ — …**`) легально — гейт смотрит на начало строки. Именно ПЕРВАЯ строка, а не
# «где-то в тексте»: иначе гейт обходится упоминанием слова.
PHASE_HANDOFF_STALE_RE = re.compile(r"^>\s*\*{0,2}\s*УСТАРЕЛ\b")
# УЗКИЙ предикат «блок УТВЕРЖДАЕТ закрытие фазы». Формы взяты из замера по флоту
# (findings/P2-third-reopen-fleet-measurements.md §1, 8 корней / 38 планов): наивное «блок
# непуст при нетерминальной фазе» бьёт 104 фазы (скелеты/заготовки — ложно-положительные),
# эти три формы — 4 фазы, все истинно-положительные. Список НЕ расширять «на всякий случай»:
# каждое лишнее слово — риск ложного WARNING на сотне фаз (пойдёт в реестр CANON_LITERALS,
# P2.16). Регистронезависимо (флот пишет и «Терминальн…», и «терминальн…»).
PHASE_HANDOFF_CLOSURE_LITERALS = ("терминальн", "фаза закрыта", "Сдано:")
PHASE_HANDOFF_CLOSURE_RE = re.compile(
    "|".join(re.escape(lit) for lit in PHASE_HANDOFF_CLOSURE_LITERALS), re.IGNORECASE)


def _plan_codename(plan_id):
    """Кодовое имя плана (D28) — для деривации имени workflow-скрипта и supersedes-сверки:
    датовый ID `ГГГГ.ММ.ДД-ИМЯ` → часть после даты; старый ID → весь ID; всегда `.lower()`.
    Примеры: `2026.07.10-FLEX` → `flex`; `SKM-ROADMAP-005` → `skm-roadmap-005`."""
    if PLAN_ID_DATED_RE.match(plan_id) and "-" in plan_id:
        return plan_id.split("-", 1)[1].lower()
    return plan_id.lower()


def _workflow_name_re(codename):
    """Каноничное имя workflow-скрипта — `wf-<кодовое-имя-lower>-<назначение>.js` (D28)."""
    return re.compile(r"^wf-" + re.escape(codename) + r"-[a-z0-9-]+\.js$")


def _plan_has_workflow_script(plan_dir):
    """Есть ли у плана хоть один `.js`-workflow-скрипт (с маркером `export const meta`)
    в `plans/<ID>/workflows/` — признак «готового workflow» для DoR-проверки P4.6 (D29).
    Детект БЕЗ исполнения JS (подстрока-маркер, прецедент P2.1/D19)."""
    workflows_dir = Path(plan_dir) / WORKFLOW_DIR_NAME
    if not workflows_dir.is_dir():
        return False
    for js in workflows_dir.glob("*.js"):
        if not js.is_file():
            continue
        try:
            if WORKFLOW_META_MARKER in js.read_text(encoding="utf-8"):
                return True
        except (OSError, UnicodeDecodeError):
            continue
    return False


class Diagnostics:
    """Копилка ERROR/WARNING с человекочитаемым выводом (русский, file:line)."""

    def __init__(self):
        self.errors = []
        self.warnings = []
        self._raw_errors = []  # (path, msg) — для normalized_keys (P1.2/B1)
        self._raw_warnings = []

    def error(self, path, line, msg):
        self.errors.append(f"{_loc(path, line)}: {msg}")
        self._raw_errors.append((Path(path), msg))

    def warning(self, path, line, msg):
        self.warnings.append(f"{_loc(path, line)}: {msg}")
        self._raw_warnings.append((Path(path), msg))

    @property
    def ok(self):
        return not self.errors

    def normalized_keys(self, base_dir):
        """Мультимножество `(kind, отн_путь, msg)` для сравнения деревьев (`--baseline`,
        P1.2/D5/D6): путь — относительно `base_dir` (если под ним, иначе как есть),
        номер строки НЕ участвует (сдвиг строк от собственного диффа не должен превращать
        старую ошибку в «новую»)."""
        base_dir = Path(base_dir).resolve()

        def rel(path):
            try:
                return str(Path(path).resolve().relative_to(base_dir))
            except ValueError:
                return str(path)

        keys = [("ERROR", rel(p), m) for p, m in self._raw_errors]
        keys += [("WARN", rel(p), m) for p, m in self._raw_warnings]
        return keys


def _loc(path, line):
    return f"{path}:{line}" if line else str(path)


def _is_empty(value):
    v = (value or "").strip()
    return v == "" or v == EMPTY_PLACEHOLDER


# --- низкоуровневый парсинг markdown -----------------------------------------

def _read_lines(path):
    """Читает файл построчно (без \\n). None — если файла нет/не читается."""
    p = Path(path)
    if not p.is_file():
        return None
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return text.replace("\r\n", "\n").split("\n")


def _section_header_indexes(lines):
    """Индексы всех строк-заголовков уровня 2 (`## …`, НЕ `### …`)."""
    return [i for i, ln in enumerate(lines) if SECTION_HEADER_RE.match(ln)]


def _section_body(lines, header_idx, header_idxs):
    """Тело секции header_idx: строки до следующего `##`-заголовка либо EOF.
    Возвращает (body_lines, first_line_no) — line_no 1-индексный, для диагностик."""
    following = [i for i in header_idxs if i > header_idx]
    end = following[0] if following else len(lines)
    return lines[header_idx + 1:end], header_idx + 2  # +2: 1-индекс + сдвиг на след. строку


def _find_section(lines, header_re):
    """Ищет ПЕРВУЮ строку, матчащую header_re, среди `##`-заголовков.
    Возвращает (header_idx, body_lines, body_start_lineno) либо (None, None, None)."""
    header_idxs = _section_header_indexes(lines)
    for idx in header_idxs:
        if header_re.match(lines[idx]):
            body, start_lineno = _section_body(lines, idx, header_idxs)
            return idx, body, start_lineno
    return None, None, None


def _parse_table(body_lines, body_start_lineno):
    """Разбирает первую markdown-таблицу в блоке строк. Возвращает
    (headers, rows, header_lineno) — rows: list[dict[col] = (value, row_lineno)].
    (None, [], None) — если таблицы в блоке нет."""
    start = None
    for i, ln in enumerate(body_lines):
        if ln.strip().startswith("|"):
            start = i
            break
    if start is None:
        return None, [], None

    def split_row(ln):
        s = ln.strip()
        if s.startswith("|"):
            s = s[1:]
        if s.endswith("|"):
            s = s[:-1]
        return [c.strip() for c in s.split("|")]

    headers = split_row(body_lines[start])
    rows = []
    i = start + 2  # строка start+1 — разделитель `---|---`, пропускаем без проверки формата
    while i < len(body_lines) and body_lines[i].strip().startswith("|"):
        cells = split_row(body_lines[i])
        row = {headers[j]: (cells[j] if j < len(cells) else "") for j in range(len(headers))}
        rows.append((row, body_start_lineno + i))
        i += 1
    return headers, rows, body_start_lineno + start


def _parse_fields(body_lines, body_start_lineno, field_re):
    """Разбирает строки-поля `**Поле:** значение` (значение может продолжаться
    на следующих строках до следующего поля/конца блока). Возвращает
    fields: dict[name] = (value, lineno)."""
    fields = {}
    cur_key = cur_lineno = None
    cur_val = []

    def flush():
        if cur_key is not None:
            fields[cur_key] = ("\n".join(cur_val).strip(), cur_lineno)

    for i, ln in enumerate(body_lines):
        m = field_re.match(ln)
        if m:
            flush()
            cur_key = m.group(1).strip()
            cur_lineno = body_start_lineno + i
            rest = m.group(2).strip()
            cur_val = [rest] if rest else []
        elif cur_key is not None:
            if ln.strip() or cur_val:
                cur_val.append(ln.rstrip())
    flush()
    return fields


def _find_items(lines):
    """Все item-блоки `### Pn.m — Заголовок` в файле. Возвращает
    list[(item_id, title, header_lineno, body_lines, body_start_lineno)]
    (список — не dict: дубли ID не должны молча схлопываться)."""
    header_idxs = [i for i, ln in enumerate(lines) if ln.startswith("###")]
    section_idxs = _section_header_indexes(lines)
    boundaries = sorted(set(header_idxs) | set(section_idxs) | {len(lines)})
    items = []
    for idx in header_idxs:
        m = ITEM_HEADER_RE.match(lines[idx])
        if not m:
            continue  # заголовок вида "### …" без соответствия item-паттерну — не item
        item_id, title = m.group(1), m.group(2).strip()
        nxt = min(b for b in boundaries if b > idx)
        items.append((item_id, title, idx + 1, lines[idx + 1:nxt], idx + 2))
    return items


def _malformed_item_headers(lines):
    """Строки `### …`, похожие на item-заголовок (есть Pn.m), но не прошедшие
    строгий regex (напр. без ` — ` разделителя) — отдельная ERROR-категория."""
    bad = []
    loose_re = re.compile(r"^###\s+(P\d+\.\d+)\b")
    for i, ln in enumerate(lines):
        if ln.startswith("###") and loose_re.match(ln) and not ITEM_HEADER_RE.match(ln):
            bad.append((ln, i + 1))
    return bad


# --- warning-проверки 2.0 для plan.md ------------------------------------------

def _lint_plan_md_20(lines, path, diag):
    """Warning-проверки схемы 2.0 поверх plan.md (существующее поведение не трогают):
    (а) порядок/заголовки нумерованных секций `## 0-6` (P0.3 рек#6);
    (б) Update Log: ячейка «Что» длиннее UPDATE_LOG_MAX_CHARS (P0.3 рек#5);
    (в) D-лог с ≥3 решениями без единого RAG-маркера — эвристика отсутствия
        маркировки несущих фактов (SKILL §7)."""
    # (а) нумерованные секции: номера по возрастанию, заголовки 0-6 — канонические
    numbered = []
    for i, ln in enumerate(lines):
        m = PLAN_SECTION_NUM_RE.match(ln)
        if m:
            numbered.append((int(m.group(1)), m.group(2), i + 1))
    nums = [n for n, _, _ in numbered]
    if nums != sorted(nums):
        diag.warning(path, numbered[0][2],
                     f"секции plan.md идут не по порядку: {nums} (канон — ## 0…6 по возрастанию)")
    for n, title, lineno in numbered:
        expected = PLAN_SECTION_TITLES.get(n)
        if expected and title != expected:
            diag.warning(path, lineno,
                         f"секция «## {n}. {title}» ≠ канонической «## {n}. {expected}»")

    # (б) Update Log — лимит «Что»
    _, ul_body, ul_start = _find_section(lines, UPDATE_LOG_HEADER_RE)
    if ul_body is not None:
        headers, rows, _ = _parse_table(ul_body, ul_start)
        if headers and "Что" in headers:
            for row, lineno in rows:
                what_val = row.get("Что", "")
                if len(what_val) > UPDATE_LOG_MAX_CHARS:
                    diag.warning(path, lineno,
                                 f"Update Log: запись «Что» {len(what_val)} символов > "
                                 f"{UPDATE_LOG_MAX_CHARS} — канон: ≤2 строк + ссылка на "
                                 f"Completion Notes, не пересказ")

    # (в) D-лог ≥3 решений без единого RAG-маркера
    _, dl_body, dl_start = _find_section(lines, DECISION_LOG_HEADER_RE)
    if dl_body is not None:
        _, rows, _ = _parse_table(dl_body, dl_start)
        if len(rows) >= 3 and not any(
                RAG_MARKER_RE.search(" ".join(str(v) for v in row.values()))
                for row, _ in rows):
            diag.warning(path, dl_start,
                         f"Decision Log: {len(rows)} решений и ни одного маркера "
                         f"«RAG:✅»/«RAG:{EMPTY_PLACEHOLDER}»/«[UNVERIFIED]» — несущие "
                         f"факты не промаркированы (SKILL §7)")


# --- m7/D10: парсер секции `## 7. Contracts` -----------------------------------

def _contract_key(value):
    """Нормализация имени контракта — последний сегмент пути: донор пишет
    `root/contracts/module-manifest.md`, потребитель — `REGHUB/root/contracts/…`."""
    return (value or "").strip().strip("`").rsplit("/", 1)[-1]


def _semver_tuple(value):
    """`v2.0.2` → (2, 0, 2); пре-релизы не поддерживаем (D10). Нет матча → None."""
    m = SEMVER_RE.search(value or "")
    return tuple(int(g) for g in m.groups()) if m else None


def parse_contracts(lines, path, diag):
    """Опциональная секция `## 7. Contracts` → {"exported": [...], "consumed": [...]}.
    Секции нет — молча пустая модель (отсутствие не дефект). Кривые колонки/подсекции —
    WARNING (механизм молод: ERROR сломал бы back-compat-гейт)."""
    model = {"exported": [], "consumed": []}
    _, body, body_start = _find_section(lines, CONTRACTS_HEADER_RE)
    if body is None:
        return model

    subs = []
    for i, ln in enumerate(body):
        if CONTRACTS_EXPORTED_RE.match(ln):
            subs.append(("exported", i))
        elif CONTRACTS_CONSUMED_RE.match(ln):
            subs.append(("consumed", i))
    if not subs:
        diag.warning(path, body_start,
                     "«## 7. Contracts»: нет подсекций «### Exported» / «### Consumed»")
        return model

    expected = {"exported": EXPORTED_COLUMNS, "consumed": CONSUMED_COLUMNS}
    for pos, (kind, start) in enumerate(subs):
        end = subs[pos + 1][1] if pos + 1 < len(subs) else len(body)
        headers, rows, header_lineno = _parse_table(body[start + 1:end],
                                                    body_start + start + 1)
        title = kind.capitalize()
        if headers is None:
            diag.warning(path, body_start + start, f"«### {title}»: таблица не найдена")
            continue
        if tuple(headers) != expected[kind]:
            diag.warning(path, header_lineno,
                         f"«### {title}»: колонки {headers} ≠ канонических "
                         f"{list(expected[kind])}")
            continue
        for row, lineno in rows:
            model[kind].append({**row, "_lineno": lineno})
    return model


def _lint_contracts_cross_plan(models, diag):
    """(m7/D10) Сверка потребителей с донорами В ПРЕДЕЛАХ одного корня `plans/`.
    Связь строится ОТ потребителя (`Consumed.Донор-план`) — единственное детерминированное
    направление. Донор вне корня (кросс-репо) не проверяется — граница §11.
    `Pinned` ≠ `Версия` донора → WARNING «уведомление не разнесено»."""
    exported = {}  # (plan_id, contract_key) -> версия-строка
    for pid, model in models.items():
        for row in (model or {}).get("contracts", {}).get("exported", []):
            key = _contract_key(row.get("Контракт"))
            if key:
                exported[(pid, key)] = (row.get("Версия") or "").strip()

    for pid, model in models.items():
        plan_md = Path((model or {}).get("path", pid)) / "plan.md"
        for row in (model or {}).get("contracts", {}).get("consumed", []):
            donor = (row.get("Донор-план") or "").strip()
            key = _contract_key(row.get("Контракт"))
            donor_ver = exported.get((donor, key))
            if donor_ver is None:
                continue  # донора нет в этом корне — линтер честно молчит (§11)
            pinned = (row.get("Pinned") or "").strip()
            dv, pv = _semver_tuple(donor_ver), _semver_tuple(pinned)
            if dv is None or pv is None or dv == pv:
                continue
            diag.warning(plan_md, row.get("_lineno"),
                         f"донор {donor}: контракт {key} = {donor_ver}, потребитель {pid} "
                         f"запинен на {pinned} — уведомление не разнесено (§11)")


# --- P4.3 warning-проверки: ID / workflow-скрипты / supersedes (D24/D27/D28) ----

def _lint_plan_identity_20(plan_dir, plan_id, meta, plan_md, diag):
    """Три WARNING-проверки идентичности плана (все — warning, back-compat D24):
    (1) имя каталога-плана против union PLAN-ID-паттернов (D24);
    (2) workflow-скрипты (`*.js` c `export const meta`) вне `plans/<ID>/workflows/`
        или с неканоничным именем (D28) — два раздельных сообщения (место / имя);
    (3) план без Meta `supersedes` при совпадении кодового имени с архивным (D27).
    `meta` — dict[name] = (value, lineno) из parse_plan_md (может быть None/пустым)."""
    plan_dir = Path(plan_dir)
    meta = meta or {}

    # (1) регулярка PLAN-ID (union старого и датового; несоответствие → warning)
    if not (PLAN_ID_LEGACY_RE.match(plan_id) or PLAN_ID_DATED_RE.match(plan_id)):
        diag.warning(plan_dir, None,
                     f"имя каталога-плана «{plan_id}» не соответствует канону PLAN-ID "
                     f"(старый `[A-Z][A-Z0-9-]+` ИЛИ датовый `ГГГГ.ММ.ДД-КОДОВОЕ-ИМЯ`, D24)")

    codename = _plan_codename(plan_id)

    # (2) место/имя workflow-скриптов (только `.js` с маркером `export const meta`)
    name_re = _workflow_name_re(codename)
    for js in sorted(plan_dir.rglob("*.js")):
        if not js.is_file():
            continue
        try:
            text = js.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if WORKFLOW_META_MARKER not in text:
            continue
        rel = js.relative_to(plan_dir)
        if not (rel.parts and rel.parts[0] == WORKFLOW_DIR_NAME):
            diag.warning(js, None,
                         f"workflow-скрипт «{rel}» вне `plans/{plan_id}/workflows/` — "
                         f"единственный дом workflow-скриптов плана (D28)")
        if not name_re.match(js.name):
            diag.warning(js, None,
                         f"workflow-скрипт «{js.name}» с неканоничным именем — "
                         f"канон `wf-{codename}-<назначение>.js` (D28)")

    # (3) supersedes: совпадение кодового имени с архивным планом без Meta supersedes
    archive_dir = plan_dir.parent / "archive"
    if archive_dir.is_dir():
        archived = {_plan_codename(p.name) for p in archive_dir.iterdir() if p.is_dir()}
        supersedes_val = (meta.get("supersedes", ("", None))[0] or "").strip()
        if codename in archived and _is_empty(supersedes_val):
            diag.warning(plan_md, None,
                         f"план «{plan_id}» повторяет кодовое имя «{codename}» архивного "
                         f"плана, но не несёт Meta `supersedes` — преемственность волны "
                         f"трека не объявлена (D27)")


# --- парсинг файлов схемы -----------------------------------------------------

def parse_plan_md(path, diag):
    """plan.md → (meta: dict[name]=(value,lineno), status_board: list[(row,lineno)])."""
    lines = _read_lines(path)
    if lines is None:
        diag.error(path, None, "plan.md отсутствует или не читается")
        return None, []

    _lint_plan_md_20(lines, path, diag)

    meta = {}
    _, meta_body, meta_start = _find_section(lines, META_HEADER_RE)
    if meta_body is None:
        diag.error(path, None, "нет секции «## 0. Meta»")
    else:
        headers, rows, header_lineno = _parse_table(meta_body, meta_start)
        if headers is None:
            diag.error(path, meta_start, "Meta: таблица `Поле|Значение` не найдена")
        elif tuple(headers) != META_TABLE_COLUMNS:
            diag.error(path, header_lineno,
                       f"Meta: колонки {headers} ≠ ожидаемых {list(META_TABLE_COLUMNS)}")
        else:
            for row, lineno in rows:
                meta[row.get("Поле", "")] = (row.get("Значение", ""), lineno)
        for field in REQUIRED_META_FIELDS:
            if field not in meta:
                diag.error(path, meta_start, f"Meta: нет обязательного поля «{field}»")

    status_board = []
    _, board_body, board_start = _find_section(lines, STATUS_BOARD_HEADER_RE)
    if board_body is None:
        diag.error(path, None, "нет секции «## 4. Phase Index & Status Board»")
    else:
        headers, rows, header_lineno = _parse_table(board_body, board_start)
        if headers is None:
            diag.error(path, board_start, "Status Board: таблица не найдена")
        elif tuple(headers) != STATUS_BOARD_COLUMNS:
            diag.error(path, header_lineno,
                       f"Status Board: колонки {headers} ≠ ожидаемых {list(STATUS_BOARD_COLUMNS)}")
        else:
            status_board = rows
            for row, lineno in rows:
                st = row.get("Status", "")
                if st not in STATUSES:
                    diag.error(path, lineno, f"Status Board: недопустимый статус «{st}»")
                if not PHASE_TOKEN_RE.match(row.get("Phase", "")):
                    diag.error(path, lineno,
                               f"Status Board: Phase «{row.get('Phase')}» не похож на Pn")

    return meta, status_board


def parse_phase_md(path, phase_id, diag):
    """phases/Pn.md → dict со status_table/items/handoff (см. lint_plan)."""
    lines = _read_lines(path)
    if lines is None:
        diag.error(path, None, "файл фазы отсутствует или не читается")
        return None

    status_table = []
    _, ps_body, ps_start = _find_section(lines, PHASE_STATUS_HEADER_RE)
    if ps_body is None:
        diag.error(path, None, "нет секции «## Phase Status»")
    else:
        headers, rows, header_lineno = _parse_table(ps_body, ps_start)
        if headers is None:
            diag.error(path, ps_start, "Phase Status: таблица не найдена")
        elif tuple(headers) != PHASE_STATUS_COLUMNS:
            diag.error(path, header_lineno,
                       f"Phase Status: колонки {headers} ≠ ожидаемых {list(PHASE_STATUS_COLUMNS)}")
        else:
            status_table = rows
            for row, lineno in rows:
                st = row.get("Status", "")
                if st not in STATUSES:
                    diag.error(path, lineno, f"Phase Status: недопустимый статус «{st}»")

    for bad_ln, lineno in _malformed_item_headers(lines):
        diag.error(path, lineno,
                    f"заголовок item не соответствует regex `^### (P\\d+\\.\\d+) — `: «{bad_ln}»")

    # --- 2.0: скелет-маркер в Phase Context (легализует пустые поля items) ------
    is_skeleton = False
    _, ctx_body, _ = _find_section(lines, PHASE_CONTEXT_HEADER_RE)
    if ctx_body is not None:
        is_skeleton = any(SKELETON_MARKER_RE.match(ln) for ln in ctx_body)

    # --- 2.0: маркеры [NEEDS CLARIFICATION] — линуются в lint_plan по статусу фазы
    needs_clarification = [i + 1 for i, ln in enumerate(lines)
                           if NEEDS_CLARIFICATION_RE.search(ln)]

    # --- P4.6: заявляет ли фаза оркестрацию (грепаемый признак, D29) — линуется
    # в lint_plan (workflow-как-DoR: фаза с оркестрацией без workflow-скрипта = warning)
    declares_orchestration = any(ORCHESTRATION_MARKER_RE.search(ln) for ln in lines)

    items = {}
    for item_id, title, header_lineno, body_lines, body_start in _find_items(lines):
        prefix_m = PHASE_TOKEN_RE.match(item_id.split(".")[0])
        if prefix_m and item_id.split(".")[0] != phase_id:
            diag.error(path, header_lineno,
                       f"item {item_id}: префикс «{item_id.split('.')[0]}» не совпадает "
                       f"с файлом фазы «{phase_id}»")
        fields = _parse_fields(body_lines, body_start, FIELD_RE)
        for f in REQUIRED_ITEM_FIELDS:
            if f not in fields:
                diag.error(path, header_lineno,
                           f"item {item_id}: нет обязательного поля «{f}» (item фазы-скелета "
                           f"обязан нести все 16 полей со значением «—»; детализация — "
                           f"/task:plan-design <ID> {phase_id})")

        # --- 2.0 WARNING: порядок 16 канонических полей (P0.3 рек#6) ------------
        canon_index = {f: i for i, f in enumerate(REQUIRED_ITEM_FIELDS)}
        present_order = [f for f in fields if f in canon_index]
        if present_order != sorted(present_order, key=canon_index.get):
            diag.warning(path, header_lineno,
                         f"item {item_id}: поля идут не в каноническом порядке "
                         f"(канон — SKILL §5 / phase-template)")

        # --- 2.0 WARNING: ≥50% пустых полей без скелет-маркера (P0.3 рек#1) -----
        empty = sum(1 for f in REQUIRED_ITEM_FIELDS if _is_empty(fields.get(f, ("",))[0]))
        if not is_skeleton and empty >= len(REQUIRED_ITEM_FIELDS) * SKELETON_EMPTY_RATIO:
            diag.warning(path, header_lineno,
                         f"item {item_id}: {empty}/{len(REQUIRED_ITEM_FIELDS)} полей пусты, "
                         f"а в Phase Context нет маркера «> СКЕЛЕТ — не детализирован…» — "
                         f"либо детализировать, либо пометить фазу скелетом")
        status_val, _ = fields.get("Status", ("", header_lineno))
        if status_val and status_val not in STATUSES:
            diag.error(path, header_lineno, f"item {item_id}: недопустимый статус «{status_val}»")
        has_escalation = any(
            ESCALATION_RE.match(ln) and ESCALATION_RE.match(ln).group(1) == item_id
            for ln in body_lines
        )
        items.setdefault(item_id, []).append({
            "title": title, "header_lineno": header_lineno, "fields": fields,
            "has_escalation": has_escalation,
        })

    for item_id, occurrences in items.items():
        if len(occurrences) > 1:
            lns = ", ".join(str(o["header_lineno"]) for o in occurrences)
            diag.error(path, occurrences[0]["header_lineno"],
                       f"item {item_id}: повторяется в файле (строки {lns})")

    _, handoff_body, handoff_start = _find_section(lines, PHASE_HANDOFF_HEADER_RE)
    handoff_stale = False
    if handoff_body is None:
        diag.error(path, None, "нет секции «## Phase Handoff»")
        handoff_text = None
        handoff_lineno = None
    else:
        handoff_text = "\n".join(handoff_body).strip()
        handoff_lineno = handoff_start - 1  # строка самого заголовка «## Phase Handoff»
        # P2.15/D34: маркер инвалидации — ПЕРВАЯ непустая строка блока (линуется в lint_plan)
        first_line = next((ln for ln in handoff_body if ln.strip()), "")
        handoff_stale = bool(PHASE_HANDOFF_STALE_RE.match(first_line.strip()))

    return {"status_table": status_table, "items": items, "phase_handoff": handoff_text,
            "phase_handoff_stale": handoff_stale, "phase_handoff_lineno": handoff_lineno,
            "is_skeleton": is_skeleton, "needs_clarification": needs_clarification,
            "declares_orchestration": declares_orchestration}


def parse_handoff_md(path, diag):
    lines = _read_lines(path)
    if lines is None:
        diag.error(path, None, "handoff.md отсутствует или не читается")
        return None

    title_lineno = None
    title_ref = None  # `Pn.m` (item) либо `Pn` (фаза) — резолвится в lint_plan
    for i, ln in enumerate(lines):
        if ln.startswith("# "):
            m = HANDOFF_TITLE_RE.match(ln)
            title_lineno = i + 1
            if m:
                title_ref = m.group(1)
            else:
                diag.error(path, title_lineno, HANDOFF_TITLE_HELP)
            break
    else:
        diag.error(path, None, "нет заголовка «# HANDOFF — … — after Pn.m» / «… — after Pn»")

    body_start = (title_lineno or 0) + 1
    fields = _parse_fields(lines[body_start - 1:], body_start, FIELD_RE)
    for f in HANDOFF_REQUIRED_FIELDS:
        if f not in fields:
            diag.error(path, body_start, f"нет обязательного поля «{f}»")

    return {"title_ref": title_ref, "title_lineno": title_lineno,
            "fields": fields, "lines": lines}


# --- линт одного плана ---------------------------------------------------

def lint_plan(plan_dir, diag):
    """Проверяет один план (plans/<PLAN-ID>/…). Возвращает распарсенную модель (dict)."""
    plan_dir = Path(plan_dir)
    plan_id = plan_dir.name
    plan_md = plan_dir / "plan.md"
    meta, status_board = parse_plan_md(plan_md, diag)

    # P4.3: warning-проверки идентичности (ID / workflow-скрипты / supersedes) — D24/D27/D28.
    # meta здесь — сырой dict[name]=(value,lineno) до маппинга в модель ниже.
    _meta_raw = meta if isinstance(meta, dict) else {}
    _lint_plan_identity_20(plan_dir, plan_id, _meta_raw, plan_md, diag)

    # m7/D10: опциональная секция `## 7. Contracts` (нет секции — пустая модель, молча).
    plan_lines = _read_lines(plan_md)
    contracts = (parse_contracts(plan_lines, plan_md, diag) if plan_lines is not None
                 else {"exported": [], "consumed": []})

    phases_dir = plan_dir / "phases"
    phase_files = {}  # phase_id -> Path
    if phases_dir.is_dir():
        for f in sorted(phases_dir.glob("*.md")):
            m = PHASE_FILENAME_RE.match(f.name)
            if m:
                phase_files[m.group(1)] = f
            else:
                diag.error(f, None, "имя файла фазы не соответствует шаблону Pn.md")
    board_phase_ids = set()
    if status_board:
        board_phase_ids = {row.get("Phase") for row, _ in status_board if row.get("Phase")}

    for pid in board_phase_ids - set(phase_files):
        diag.error(plan_md, None, f"фаза {pid} есть в Status Board, но нет phases/{pid}.md")
    for pid in set(phase_files) - board_phase_ids:
        diag.error(phase_files[pid], None, f"фаза {pid} есть как phases/{pid}.md, но нет в Status Board")

    phases = {}
    all_items = {}  # item_id -> {"phase": pid, "title":..., "status":..., "fields":...}
    for pid, path in phase_files.items():
        parsed = parse_phase_md(path, pid, diag)
        phases[pid] = {"path": str(path), **(parsed or {})}
        if not parsed:
            continue
        # --- консистентность Phase Status(таблица) vs item.Status -----------
        table_by_id = {row.get("ID"): (row, lineno) for row, lineno in parsed["status_table"]}
        for item_id, occurrences in parsed["items"].items():
            item = occurrences[0]  # диагностика дублей уже выдана выше; для сверки берём первый
            status_val, _ = item["fields"].get("Status", ("", item["header_lineno"]))
            all_items[item_id] = {
                "phase": pid, "title": item["title"], "status": status_val,
                "fields": {k: v[0] for k, v in item["fields"].items()},
            }
            row = table_by_id.pop(item_id, None)
            if row is None:
                diag.error(path, item["header_lineno"],
                           f"item {item_id}: нет строки в «## Phase Status»")
            else:
                row_dict, row_lineno = row
                if row_dict.get("Status") != status_val:
                    diag.error(path, row_lineno,
                               f"item {item_id}: статус в Phase Status «{row_dict.get('Status')}» "
                               f"≠ статусу item «{status_val}»")
        for orphan_id, (row_dict, row_lineno) in table_by_id.items():
            diag.error(path, row_lineno,
                       f"Phase Status: строка «{orphan_id}» без соответствующего item")

        # --- item 🟢/🟠 ⇒ Completion Notes; 🟠 ⇒ Known Deviations -----------
        for item_id, occurrences in parsed["items"].items():
            item = occurrences[0]
            status_val, status_lineno = item["fields"].get("Status", ("", item["header_lineno"]))
            cn_val, cn_lineno = item["fields"].get("Completion Notes", ("", item["header_lineno"]))
            kd_val, kd_lineno = item["fields"].get("Known Deviations", ("", item["header_lineno"]))
            if status_val in (STATUS_DONE, STATUS_DEVIATIONS) and _is_empty(cn_val):
                diag.error(path, cn_lineno,
                           f"item {item_id}: статус «{status_val}» требует непустых Completion Notes")
            if status_val == STATUS_DEVIATIONS and _is_empty(kd_val):
                diag.error(path, kd_lineno,
                           f"item {item_id}: статус «{status_val}» требует непустых Known Deviations")

            # --- 🔴 ⇔ ESCALATION-блок ⇔ Escalation Needed: yes ---------------
            en_val, en_lineno = item["fields"].get("Escalation Needed", ("", item["header_lineno"]))
            en_norm = (en_val or "").strip().lower()
            # 2.0 канонизировал (P0.3 рек#4, SKILL §5): у Escalation Needed — и ТОЛЬКО
            # у него — маркер `no` равноправен «—»; оба принимаются без диагностики.
            if en_norm in ("", EMPTY_PLACEHOLDER, "no"):
                en_yes = False
            elif en_norm == "yes":
                en_yes = True
            else:
                diag.error(path, en_lineno,
                           f"item {item_id}: Escalation Needed «{en_val}» — ожидается yes/no/—")
                en_yes = None
            is_blocked = status_val == STATUS_BLOCKED
            has_escalation = item["has_escalation"]
            if en_yes is not None and not (is_blocked == en_yes == has_escalation):
                parts = (f"Status={'🔴' if is_blocked else '≠🔴'}",
                         f"Escalation Needed={'yes' if en_yes else 'no/—'}",
                         f"ESCALATION-блок={'есть' if has_escalation else 'нет'}")
                diag.error(path, item["header_lineno"],
                           f"item {item_id}: рассогласованы {', '.join(parts)} (должны совпадать)")

            # --- WARNING: пустые Required Reads/Validation у не-⬜ item -------
            if status_val and status_val != "⬜ Not started":
                rr_val, rr_lineno = item["fields"].get("Required Reads", ("", item["header_lineno"]))
                va_val, va_lineno = item["fields"].get("Validation", ("", item["header_lineno"]))
                if _is_empty(rr_val):
                    diag.warning(path, rr_lineno, f"item {item_id}: пустые Required Reads при статусе «{status_val}»")
                if _is_empty(va_val):
                    diag.warning(path, va_lineno, f"item {item_id}: пустая Validation при статусе «{status_val}»")

    # --- глобальная уникальность ID item ---------------------------------
    seen = {}
    for pid, phase in phases.items():
        for item_id in phase.get("items", {}):
            seen.setdefault(item_id, []).append(pid)
    for item_id, pids in seen.items():
        if len(pids) > 1:
            diag.error(plan_dir, None, f"item {item_id}: ID переиспользован в фазах {sorted(set(pids))}")

    # --- дубли Title среди items (WARNING) --------------------------------
    titles = {}
    for item_id, info in all_items.items():
        titles.setdefault(info["title"], []).append(item_id)
    for title, ids in titles.items():
        if len(ids) > 1:
            diag.warning(plan_dir, None, f"дубль Title «{title}» среди items: {sorted(ids)}")

    # --- Status Board согласован с фазами: счётчик 🟢/всего и статус фазы --
    board_by_phase = {row.get("Phase"): (row, lineno) for row, lineno in status_board}
    for pid in phases:
        row = board_by_phase.get(pid)
        if row is None:
            continue  # уже отражено как отдельная ошибка выше (phase without Status Board row)
        row_dict, row_lineno = row
        phase_item_ids = list(phases[pid].get("items", {}).keys())
        total = len(phase_item_ids)
        done = sum(1 for iid in phase_item_ids
                   if all_items.get(iid, {}).get("status") == STATUS_DONE)
        items_cell = row_dict.get(STATUS_BOARD_ITEMS_COL, "")
        m = DONE_TOTAL_RE.match(items_cell)
        if not m:
            diag.error(plan_md, row_lineno,
                       f"Status Board {pid}: колонка «{STATUS_BOARD_ITEMS_COL}» = «{items_cell}» "
                       f"— ожидается формат N/M")
        elif (int(m.group(1)), int(m.group(2))) != (done, total):
            diag.error(plan_md, row_lineno,
                       f"Status Board {pid}: «{STATUS_BOARD_ITEMS_COL}» = «{items_cell}» "
                       f"≠ фактическому {done}/{total}")

        phase_status = row_dict.get("Status", "")
        item_statuses = [all_items[iid]["status"] for iid in phase_item_ids if iid in all_items]
        if item_statuses and any(s == STATUS_BLOCKED for s in item_statuses) and phase_status != STATUS_BLOCKED:
            diag.error(plan_md, row_lineno,
                       f"Status Board {pid}: есть 🔴 Blocked item, но статус фазы «{phase_status}» ≠ 🔴 Blocked")
        if item_statuses and all(s == STATUS_DONE for s in item_statuses) and phase_status != STATUS_DONE:
            diag.error(plan_md, row_lineno,
                       f"Status Board {pid}: все items 🟢 Done, но статус фазы «{phase_status}» ≠ 🟢 Done")

        # --- 2.0 WARNING: [NEEDS CLARIFICATION] в фазе 🟡+ = DoR-гейт не пройден --
        if phase_status and phase_status != "⬜ Not started":
            nc = phases[pid].get("needs_clarification") or []
            if nc:
                diag.warning(phases[pid]["path"], nc[0],
                             f"фаза {pid} в статусе «{phase_status}», но несёт "
                             f"{len(nc)} маркер(ов) [NEEDS CLARIFICATION] "
                             f"(строки {nc}) — DoR-гейт не пройден (SKILL §7)")

        # --- P4.6 WARNING: workflow-как-DoR (D29) — фаза со статусом 🟡+, ЗАЯВЛЯЮЩАЯ
        # оркестрацию (грепаемый признак), но у плана нет workflow-скрипта в
        # `plans/<ID>/workflows/`. Условность: без признака оркестрации — молчит
        # (ручное item-by-item исполнение workflow не требует). warning-only.
        if (phase_status and phase_status != "⬜ Not started"
                and phases[pid].get("declares_orchestration")
                and not _plan_has_workflow_script(plan_dir)):
            diag.warning(phases[pid]["path"], None,
                         f"фаза {pid} заявляет оркестрацию (multi-agent/fan-out), но нет "
                         f"workflow-скрипта в `plans/{plan_id}/workflows/` — DoR §7 (D29)")

        # --- фаза 🟢/🟠 ⇒ Phase Handoff непуст --------------------------
        if phase_status in (STATUS_DONE, STATUS_DEVIATIONS):
            handoff_text = phases[pid].get("phase_handoff")
            if handoff_text is None:
                pass  # отсутствие секции уже отражено отдельной ошибкой
            elif _is_empty(handoff_text):
                diag.error(phases[pid]["path"], None,
                           f"фаза {pid} статус «{phase_status}», но «## Phase Handoff» пуст")

        # --- P2.15/D34 WARNING: зеркальный гейт — фаза НЕтерминальна, а Phase Handoff
        # УТВЕРЖДАЕТ закрытие и не помечен маркером инвалидации (H2, SKILL §3, 4-й шаг).
        # WARNING, не ERROR: три плана флота (истинно-положительные, carve-out D34) иначе
        # получили бы недостижимый commit-гейт в ЧУЖИХ репозиториях.
        elif phase_status and phase_status not in TERMINAL_STATUSES:
            handoff_text = phases[pid].get("phase_handoff")
            if (handoff_text and not _is_empty(handoff_text)
                    and PHASE_HANDOFF_CLOSURE_RE.search(handoff_text)
                    and not phases[pid].get("phase_handoff_stale")):
                diag.warning(phases[pid]["path"], phases[pid].get("phase_handoff_lineno"),
                             f"Phase Handoff протух: фаза {pid} НЕ закрыта (статус "
                             f"«{phase_status}»), а блок утверждает закрытие фазы — поставь "
                             f"его первой строкой маркер «> УСТАРЕЛ — фаза реопенена <D#>» "
                             f"(SKILL §3, 4-й шаг реопена: блок не удаляется, его перезапишет "
                             f"plan-close при следующем закрытии фазы)")

    # --- phase-first (WARNING): активные 🟡 items в фазе N+1 при не-терминальной N
    numbered = sorted(
        ((int(PHASE_TOKEN_RE.match(pid).group(1)), pid) for pid in board_by_phase if PHASE_TOKEN_RE.match(pid)),
    )
    by_num = dict(numbered)
    for n, pid in numbered:
        nxt_pid = by_num.get(n + 1)
        if nxt_pid is None:
            continue
        cur_status = board_by_phase[pid][0].get("Status", "")
        if cur_status in TERMINAL_STATUSES:
            continue
        nxt_items = phases.get(nxt_pid, {}).get("items", {})
        active = [iid for iid in nxt_items if all_items.get(iid, {}).get("status") == STATUS_IN_PROGRESS]
        if active:
            diag.warning(plan_dir, None,
                         f"phase-first: {nxt_pid} содержит активные 🟡 items {sorted(active)}, "
                         f"хотя {pid} ещё не терминальна (статус «{cur_status}»)")

    # --- handoff.md ---------------------------------------------------------
    handoff_path = plan_dir / "handoff.md"
    handoff = parse_handoff_md(handoff_path, diag)
    if handoff:
        next_val, next_lineno = handoff["fields"].get("Next", ("", None))

        # Заголовок формы `after Pn` (фаза, D30) — ссылка обязана резолвиться, иначе
        # расширение regex'а просто «разрешило всё». Форма `after Pn.m` существованием
        # item'а НЕ гейтится: 12 планов флота несут `after P0.0` (плана ещё не касались,
        # item'а P0.0 не бывает) — гейт на неё = новые ERROR флоту, back-compat запрещает.
        title_ref = handoff.get("title_ref")
        if title_ref and "." not in title_ref and title_ref not in phases:
            diag.error(handoff_path, handoff.get("title_lineno"),
                       f"заголовок: фаза «{title_ref}» не существует в плане")

        # --- 2.0 WARNING: launch-block в handoff.Next (SKILL §8) ------------------
        # Таблица `| Model | …` и code-block грепаются по всему файлу: шаблон кладёт
        # launch-block продолжением Next, но точное место не гейтим (warning-уровень).
        # Для целиком закрытого плана («план закрыт») запускать нечего — не требуем.
        if "план закрыт" not in next_val.lower():
            has_table = any(LAUNCH_TABLE_ROW_RE.match(ln) for ln in handoff["lines"])
            has_fence = any(CODE_FENCE_RE.match(ln) for ln in handoff["lines"])
            if not (has_table and has_fence):
                missing = []
                if not has_table:
                    missing.append("таблицы `| Model | …`")
                if not has_fence:
                    missing.append("code-block с командой")
                diag.warning(handoff_path, next_lineno,
                             "Next без launch-block: нет " + " и ".join(missing) +
                             " (форма — snippets/launch-block-template.md)")
        plan_closed = bool(all_items) and all(
            info["status"] in TERMINAL_STATUSES for info in all_items.values())

        def _check_plan_id(ref_plan_id):
            if ref_plan_id != plan_id:
                diag.error(handoff_path, next_lineno,
                           f"Next: PLAN-ID «{ref_plan_id}» ≠ фактическому «{plan_id}»")

        def _check_phase(ref_phase):
            if ref_phase not in phases:
                diag.error(handoff_path, next_lineno,
                           f"Next: фаза «{ref_phase}» не существует в плане")

        def _check_item(ref_item):
            if ref_item not in all_items:
                diag.error(handoff_path, next_lineno,
                           f"Next: item «{ref_item}» не существует ни в одной фазе")

        # Резолвер enum'а (SKILL §8) — от специфичного к общему; первая сматчившая
        # форма определяет проверку ссылок, остальные не пробуются (D4). «план закрыт»
        # проверяется СРАЗУ после plan-exec (а не среди прочих regex-форм): это цельное
        # утверждение о состоянии плана, а не slash-команда — Next закрытого плана иногда
        # УПОМИНАЕТ следующую команду прозой («… решает владелец: `/task:plan-close
        # archive <ID>` либо …», см. EDUFY-2), и эта проза не должна перехватывать резолвер.
        is_closed_text = "план закрыт" in next_val.lower()
        m_exec = PLAN_EXEC_RE.search(next_val)
        m_design_item = None if (m_exec or is_closed_text) else PLAN_DESIGN_ITEM_RE.search(next_val)
        m_design_phase = None if (m_exec or is_closed_text or m_design_item) \
            else PLAN_DESIGN_PHASE_RE.search(next_val)
        m_audit = None if (m_exec or is_closed_text or m_design_item or m_design_phase) \
            else PLAN_AUDIT_RE.search(next_val)
        m_close_archive = None if (m_exec or is_closed_text or m_design_item or m_design_phase or m_audit) \
            else PLAN_CLOSE_ARCHIVE_RE.search(next_val)
        m_close = None if (m_exec or is_closed_text or m_design_item or m_design_phase
                            or m_audit or m_close_archive) \
            else PLAN_CLOSE_RE.search(next_val)
        is_manual = MANUAL_RUN_MARKER in next_val

        if m_exec:
            ref_plan_id, ref_item = m_exec.group(1), m_exec.group(2)
            _check_plan_id(ref_plan_id)
            _check_item(ref_item)
        elif is_closed_text:
            if not plan_closed:
                diag.error(handoff_path, next_lineno,
                           "Next: «план закрыт», но не все items терминальны")
        elif m_design_item:
            ref_plan_id, ref_item = m_design_item.group(1), m_design_item.group(2)
            _check_plan_id(ref_plan_id)
            _check_item(ref_item)
        elif m_design_phase:
            ref_plan_id, ref_phase = m_design_phase.group(1), m_design_phase.group(2)
            _check_plan_id(ref_plan_id)
            _check_phase(ref_phase)
        elif m_audit:
            ref_plan_id, ref_phase = m_audit.group(1), m_audit.group(2)
            _check_plan_id(ref_plan_id)
            _check_phase(ref_phase)
            if ref_phase in phases:
                row = board_by_phase.get(ref_phase)
                phase_status = row[0].get("Status", "") if row else ""
                if phase_status not in TERMINAL_STATUSES:
                    diag.warning(handoff_path, next_lineno,
                                 f"Next: /task:plan-audit {ref_phase} — фаза в статусе "
                                 f"«{phase_status}», не терминальна (аудит гоняется по "
                                 f"закрытой фазе, SKILL §13)")
        elif m_close_archive:
            ref_plan_id = m_close_archive.group(1)
            _check_plan_id(ref_plan_id)
            if not plan_closed:
                diag.warning(handoff_path, next_lineno,
                             "Next: /task:plan-close archive — план ещё не терминален целиком")
        elif m_close:
            ref_plan_id, ref_phase, ref_suffix = m_close.group(1), m_close.group(2), m_close.group(3)
            _check_plan_id(ref_plan_id)
            _check_phase(ref_phase)
            if ref_suffix:
                _check_item(ref_phase + ref_suffix)
        elif is_manual:
            pass  # «ЗАПУСК ВРУЧНУЮ: <model/effort>» — форма без slash-команды, ссылок нет
        else:
            diag.error(handoff_path, next_lineno, NEXT_FORMS_HELP)

    return {
        "id": plan_id,
        "path": str(plan_dir),
        "meta": {k: v[0] for k, v in (meta or {}).items()},
        "contracts": contracts,
        "status_board": [row for row, _ in status_board],
        "phases": {
            pid: {
                "path": ph["path"],
                "status_table": [row for row, _ in ph.get("status_table", [])],
                "items": {
                    iid: {"title": occ[0]["title"], "fields": {k: v[0] for k, v in occ[0]["fields"].items()}}
                    for iid, occ in ph.get("items", {}).items()
                },
                "phase_handoff": ph.get("phase_handoff"),
            }
            for pid, ph in phases.items()
        },
        "handoff": {
            "path": str(handoff_path),
            "title_ref": (handoff or {}).get("title_ref"),
            "fields": {k: v[0] for k, v in (handoff or {}).get("fields", {}).items()},
        } if handoff else None,
    }


# --- root-level проверки (path = plans/ целиком, не одиночный plans/<ID>) -----

def lint_plans_root(root, models, diag):
    """Проверки, применимые только к каталогу `plans/` целиком (см. discover_plan_dirs:
    отличается от одиночного `plans/<ID>` тем, что там нет `plan.md` рядом с собой).
    `models` — {plan_id: model|None} уже пролинтованных подкаталогов (для сверки, что
    Active указывает на реально существующий каталог-план, и для подсчёта 🟡 In progress).

    (а) есть plans/ACTIVE.md → поле «**Active:**» обязано быть «—» либо именем
        существующего каталога-плана, иначе ERROR;
    (б) нет ACTIVE.md и ≥2 планов со статусом «🟡 In progress» (Meta plan.md) →
        WARNING «активный план неоднозначен»;
    (в) плоские *.md в корне plans/ (кроме ACTIVE.md/README.md) — черновики plan mode,
        оставшиеся без протокола, → одно WARNING со списком и подсказкой from-draft;
    (г) cross-plan сверка `## 7. Contracts`: Pinned потребителя ≠ Версии донора того же
        корня → WARNING «уведомление не разнесено» (m7/D10, §11).
    """
    root = Path(root)
    _lint_contracts_cross_plan(models, diag)

    active_path = root / ACTIVE_FILENAME
    active_lines = _read_lines(active_path)
    if active_lines is not None:
        value, value_lineno = None, None
        for i, ln in enumerate(active_lines):
            m = ACTIVE_FIELD_RE.match(ln)
            if m:
                value, value_lineno = m.group(1).strip(), i + 1
                break
        if value is None:
            diag.error(active_path, None, "нет поля «**Active:**» в ACTIVE.md")
        elif value != EMPTY_PLACEHOLDER and value not in models:
            diag.error(active_path, value_lineno,
                       f"Active «{value}» не указывает на существующий план "
                       f"(нет каталога plans/{value}/)")
    else:
        in_progress = sorted(
            pid for pid, model in models.items()
            if (model or {}).get("meta", {}).get("Status") == STATUS_IN_PROGRESS
        )
        if len(in_progress) >= 2:
            diag.warning(root, None,
                         "активный план неоднозначен: нет plans/ACTIVE.md, а планов со "
                         f"статусом «{STATUS_IN_PROGRESS}» {len(in_progress)}: {in_progress}")

    drafts = sorted(
        p.name for p in root.glob("*.md")
        if p.is_file() and p.name not in (ACTIVE_FILENAME, README_FILENAME)
    )
    if drafts:
        diag.warning(root, None,
                     "черновики plan mode: " + ", ".join(drafts) +
                     " — разверни /task:plan-design from-draft")


# --- дискавери множества планов ----------------------------------------------

ARCHIVE_DIR_NAME = "archive"  # N3/D14: контейнер архивных планов, сам планом не является


def discover_plan_dirs(root):
    """path — либо сам plans/<ID> (есть plan.md), либо plans/ (перебор подкаталогов).
    `plans/archive/` в переборе НЕ участвует как план (N3/D14) — вместо неё в перебор
    попадают её подкаталоги `plans/archive/<ID>` (архивные планы линтуются как планы)."""
    root = Path(root)
    if (root / "plan.md").is_file():
        return [root]
    if not root.is_dir():
        return None
    dirs = []
    for p in sorted(root.iterdir()):
        if not p.is_dir():
            continue
        if p.name == ARCHIVE_DIR_NAME:
            dirs.extend(sorted(a for a in p.iterdir() if a.is_dir()))
            continue
        dirs.append(p)
    return dirs


# --- --baseline: детерминированный счёт новых ошибок (P1.2/B1/D5/D6) ---------

def _git_run(args, cwd, timeout=15):
    """`check=False`, перехватывает `FileNotFoundError`/таймаут — линтер обязан
    работать вне git-репо (гоняют по Brain-vault'у и чужим корням, P1.2 Implementation
    Rules). None — команда не выполнилась вовсе (нет git / таймаут)."""
    try:
        return subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True,
                               timeout=timeout, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _baseline_diag_keys(root, ref):
    """Прогоняет lint на дереве `ref` для того же `root`-пути (git archive во временный
    каталог, БЕЗ файла-состояния — источник истины git). Возвращает
    `(normalized_keys, None)` либо `(None, причина)` при недоступности baseline —
    graceful degrade (git отсутствует / не репозиторий / ref не найден / archive упал)."""
    root = Path(root).resolve()

    proc = _git_run(["rev-parse", "--show-toplevel"], cwd=root)
    if proc is None or proc.returncode != 0:
        return None, "не git-репозиторий (или git не установлен)"
    git_root = Path(proc.stdout.decode("utf-8", "replace").strip())

    try:
        relpath = root.relative_to(git_root)
    except ValueError:
        return None, f"путь «{root}» вне git-репозитория «{git_root}»"

    verify = _git_run(["rev-parse", "--verify", f"{ref}^{{commit}}"], cwd=git_root)
    if verify is None or verify.returncode != 0:
        return None, f"ref «{ref}» не найден"

    archive = _git_run(["archive", ref, "--", str(relpath)], cwd=git_root, timeout=30)
    if archive is None or archive.returncode != 0 or not archive.stdout:
        return None, f"«git archive {ref} -- {relpath}» не удался"

    with tempfile.TemporaryDirectory(prefix="plan-lint-baseline-") as tmp:
        tmpdir = Path(tmp)
        try:
            with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r|") as tar:
                tar.extractall(path=tmpdir)
        except tarfile.TarError as exc:
            return None, f"распаковка архива не удалась: {exc}"

        baseline_root = tmpdir / relpath
        baseline_dirs = discover_plan_dirs(baseline_root)
        if not baseline_root.exists() or baseline_dirs is None:
            return None, f"путь «{relpath}» отсутствует в «{ref}» (новый план?)"

        baseline_diag = Diagnostics()
        models = {}
        for plan_dir in baseline_dirs:
            models[plan_dir.name] = lint_plan(plan_dir, baseline_diag)
        is_root = not (baseline_root / "plan.md").is_file()
        if is_root:
            lint_plans_root(baseline_root, models, baseline_diag)

        return baseline_diag.normalized_keys(baseline_root), None


# --- CLI ----------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="plan-lint.py",
        description="Детерминированный валидатор plan-протокола (plans/<PLAN-ID>/…).",
    )
    parser.add_argument("path", help="путь к plans/<PLAN-ID> или к plans/")
    parser.add_argument("--json", action="store_true",
                         help="вывести распарсенную модель (планы→фазы→items) в stdout как JSON")
    parser.add_argument("--baseline", nargs="?", const="HEAD", default=None, metavar="REF",
                         help="git-ref для счёта НОВЫХ ошибок от рабочего дерева (K, B1/D5/D6); "
                              "без значения — HEAD")
    parser.add_argument("--gate", choices=("all", "new"), default="all",
                         help="exit-код по всем диагностикам (all, дефолт — back-compat CI) "
                              "или только по новым от --baseline (new); при недоступном "
                              "baseline gate=new деградирует к all (красное не пропускается)")
    args = parser.parse_args(argv)

    root = Path(args.path)
    plan_dirs = discover_plan_dirs(root)
    if plan_dirs is None:
        print(f"ERROR: путь не найден: {root}", file=sys.stderr)
        return 1

    # discover_plan_dirs: одиночный план — это (root/"plan.md").is_file() → [root];
    # тот же признак используем здесь, чтобы root-проверки (ACTIVE.md/черновики)
    # не применялись к одиночному `plan-lint.py plans/<ID>` (там ACTIVE.md вне видимости).
    is_plans_root = not (root / "plan.md").is_file()

    if not plan_dirs and not is_plans_root:
        print(f"нет планов для проверки в {root}")
        return 0

    diag = Diagnostics()
    models = {}
    for plan_dir in plan_dirs:
        models[plan_dir.name] = lint_plan(plan_dir, diag)

    if is_plans_root:
        lint_plans_root(root, models, diag)

    new_count = None
    if args.baseline is not None:
        base_keys, reason = _baseline_diag_keys(root, args.baseline)
        if reason is not None:
            diag.warning(root, None,
                         f"baseline «{args.baseline}» недоступен: {reason} — "
                         f"счёт новых ошибок не вычислен")
        else:
            diff = Counter(diag.normalized_keys(root)) - Counter(base_keys)
            new_count = sum(diff.values())

    for msg in diag.errors:
        print(f"ERROR: {msg}", file=sys.stderr)
    for msg in diag.warnings:
        _core_warn(msg)

    if args.json:
        print(json.dumps({"plans": models}, ensure_ascii=False, indent=2))
    else:
        status = "OK" if diag.ok else "ПРОВАЛ"
        suffix = f"; новых от рабочего дерева: {new_count}" if new_count is not None else ""
        print(f"plan-lint: {status} ({len(plan_dirs)} план(ов), "
              f"{len(diag.errors)} ошибок, {len(diag.warnings)} предупреждений{suffix})")

    if args.gate == "new" and new_count is not None:
        return 0 if new_count == 0 else 1
    return 0 if diag.ok else 1


if __name__ == "__main__":
    sys.exit(main())
