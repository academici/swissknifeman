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
import ast
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

# task.journal — SSOT схемы записи 2026.07.18-FOREMAN P1.1 и historical exception sidecar; лint
# журнала реюзает её вместо дубля правил (Code Guidance 2026.07.18-FOREMAN P1.4 «анти-подгонка»), тот же
# пакет `task`, тот же lib/ на sys.path (см. scripts/plan-lint.py лаунчер).
from task import journal as _journal
from task import plan_layout
from task import plan_status
# task.task_contract — единственный владелец строкового теста «внешности» execution
# input'а (task-contract-v1.md §Portability, frozen 2026.07.24-AGENT-RELIABILITY P0.2); tiered-portability lint (2026.07.24-AGENT-RELIABILITY P2.2)
# зовёт его, а не пересказывает список префиксов вторым списком (Implementation Rules P2.2).
from task import task_contract

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
V2_CORE_META_FIELDS = ("Plan ID", "Title")
V2_STATUS_META_FIELDS = ("Version", "Status", "Last Updated")
META_TABLE_COLUMNS = ("Поле", "Значение")
# Полный канон item-полей — SKILL.ru.md §4 / snippets/phase-template.md, строго в этом
# порядке (порядок здесь не гейтится, только присутствие — см. lint_plan).
REQUIRED_ITEM_FIELDS = (
    "Status", "Intent", "Why", "Scope Included", "Scope Excluded", "Inputs", "Files",
    "Required Reads", "Implementation Rules", "Code Guidance", "Validation",
    "Deliverables", "Completion Notes", "Pending Work", "Known Deviations",
    "Escalation Needed",
)
ITEM_SPEC_FIELDS = (
    "Intent", "Why", "Scope Included", "Scope Excluded", "Inputs", "Files",
    "Required Reads", "Implementation Rules", "Code Guidance", "Validation",
    "Deliverables",
)
ITEM_STATE_FIELDS = (
    "Status", "Completion Notes", "Pending Work", "Known Deviations",
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
# Bootstrap-форма стартового handoff'а: план ещё не тронут, фазы `P0` не бывает (D37).
# Ровно эта строка — не «любая фаза P0» и не «любой item .0»: расширение = дыра в гейте.
HANDOFF_TITLE_BOOTSTRAP = "P0.0"
PLAN_EXEC_RE = re.compile(r"/task:plan-exec\s+(\S+)\s+(P\d+\.\d+)")
# Форма m8/B1/N1/N2 (+D8): `handoff.Next` допускает закрытый enum 9 форм (SKILL §8) —
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
# Батч-серия roadmap (SKILL §8): одна сессия закрывает диапазон items текущей моделью.
PLAN_RUN_RE = re.compile(r"/task:plan-run\s+(\S+)\s+(P\d+\.\d+)(?:\s*-\s*(P\d+\.\d+))?")
# Pre-exec design-ревью всего плана (plan-audit, режим design).
PLAN_AUDIT_DESIGN_RE = re.compile(r"/task:plan-audit\s+(\S+)\s+design\b")
PLAN_AUDIT_RE = re.compile(r"/task:plan-audit\s+(\S+)\s+(P\d+)(?!\.\d)\b")
PLAN_CLOSE_ARCHIVE_RE = re.compile(r"/task:plan-close\s+archive\s+(\S+)")
PLAN_CLOSE_RE = re.compile(r"/task:plan-close\s+(\S+)\s+(P\d+)(\.\d+)?\b")
SEMANTIC_NEXT_RE = re.compile(
    r"^(exec-items|run-items|audit-design|design-phase|design-item|audit-phase|close|archive|"
    r"terminal|manual|waiting):\s*(.*)$")
SEMANTIC_NEXT_COMMANDS = {
    "exec-items": ("task:plan-exec", "exec"),
    "run-items": ("task:plan-run", "run"),
    "audit-design": ("task:plan-audit", "audit-design"),
    "design-phase": ("task:plan-design", "design-phase"),
    "design-item": ("task:plan-design", "design-item"),
    "audit-phase": ("task:plan-audit", "audit"),
    "close": ("task:plan-close", "close"),
    "archive": ("task:plan-close", "close-archive"),
}
MANUAL_RUN_MARKER = "ЗАПУСК ВРУЧНУЮ"  # Exec=manual (§9): форма без slash-команды, ищется подстрокой
LITERAL_WAITING = "ОЖИДАНИЕ:"  # 9-я форма Next (§8, D8): здоровое ожидание внешнего времени/гейта, ищется подстрокой
NEXT_FORMS_HELP = (
    "Next не соответствует ни одной из допустимых форм (SKILL §8): "
    "`<kind>: task:<plan-command> <arguments>` (provider-neutral канон) · "
    "/task:plan-exec <ID> Pn.m · /task:plan-run <ID> Pn.a[-Pn.b] · "
    "/task:plan-design <ID> Pn · /task:plan-design <ID> Pn.m · "
    "/task:plan-audit <ID> Pn · /task:plan-audit <ID> design · "
    "/task:plan-close <ID> Pn[.m] · /task:plan-close archive <ID> · "
    "«план закрыт» · «ЗАПУСК ВРУЧНУЮ: <model/effort>» · «ОЖИДАНИЕ: <условие> → <целевая форма>»"
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
# 2026.07.13-PLAN-PROTOCOL-GAP P3.8/D52: append-only блок `## Audit Pn` ИСКЛЮЧЁН из региона грепов по фазе. Аудитор
# отчитывается о проверке предиката («маркеров X — 0») и обязан УПОМЯНУТЬ маркер дословно;
# греп по всему файлу бил бы по честному отчёту (A4: первая версия `## Audit P3` уронила
# гейт собственной строкой). Регион гейтов кончается на ПЕРВОМ `## Audit` — ниже него живого
# ТЗ фазы нет (блок append-only, дописывается ПОСЛЕ items и Phase Handoff).
AUDIT_BLOCK_HEADER_RE = re.compile(r"^##\s+Audit\b")
# RAG-маркеры несущих фактов (SKILL §7, enum из трёх значений — D29) — эвристика по
# D-логу. `RAG:—` (repo-grounded) пишется через em dash, как EMPTY_PLACEHOLDER;
# ASCII-дефис не канонизирован.
RAG_MARKER_RE = re.compile(r"RAG:✅|RAG:" + EMPTY_PLACEHOLDER + r"|\[UNVERIFIED\]")
# launch-block в handoff.Next (SKILL §8): таблица с `| Model |` + (строка `| Команда |`
# В ТОЙ ЖЕ таблице ИЛИ code-block ниже — P5.8, аддитивно: обе формы валидны, back-compat
# 26+ живых планов флота, писавших только code-block, не ломается).
LAUNCH_TABLE_ROW_RE = re.compile(r"^\|\s*Model(?:\s+class)?\s*\|")
LAUNCH_COMMAND_ROW_RE = re.compile(r"^\|\s*Команда\s*\|")
CODE_FENCE_RE = re.compile(r"^\s*```")
# `Context` launch-block'а (SKILL §8 «Session-restart discipline», D16/D30) — РОВНО три
# значения. Реестр НЕ используется НИГДЕ вне `--conflicts` (2026.07.31-SKM-LEAN P5.9): до этого
# item'а поле `Context` не гейтилось ни одним registry ни разу — сверка канон↔реализация для
# него добавляется здесь ВПЕРВЫЕ, а не переиздаётся из существующего гейта (Pending Work P5.9
# называет расширение до live-гейта отдельной задачей — этот item лишь делает класс сверяемым).
CONTEXT_VALUES = (
    "same-session — item",
    "cold-start — orchestration",
    "cold-start — plan-step",
)
# Директива непереводимого литерала (D28) — тот же формат, что грепает
# `check-translations.sh` и (до P5.9) дублировал `test_canon_literals.py`; единственный
# владелец регекса теперь этот модуль (`--conflicts` и тест реюзают его, не переиздают).
I18N_KEEP_RE = re.compile(r"<!--\s*i18n-keep:\s*(.+?)\s*-->")
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

# --- 2026.07.10-SKM-ROADMAP-005 P4.3: канон ID / места-имени workflow-скрипта / supersedes (D24/D27/D28) --
# Регулярка PLAN-ID (D16/D24) — union: датовый канон `ГГГГ.ММ.ДД-КОДОВОЕ-ИМЯ`
# и старый паттерн (back-compat: живые планы SKM-ROADMAP-005/SKM-AUDIT-004 матчат
# старый → 0 warning; несоответствие ни одному — WARNING, никогда не ERROR).
PLAN_ID_DATED_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2}-[A-Z][A-Z0-9-]*$")
PLAN_ID_LEGACY_RE = re.compile(r"^[A-Z][A-Z0-9-]+$")
# Маркер workflow-скрипта в теле .js — детект ПОДСТРОКОЙ (не eval/import JS,
# прецедент 2026.07.10-SKM-ROADMAP-005 P2.1/D19 `parse_script_meta`).
WORKFLOW_META_MARKER = "export const meta"
WORKFLOW_DIR_NAME = "workflows"  # единственный дом скриптов плана (D28)
# Резидентный agent-pack класс (harness dev-loop.js) — не плановый артефакт, exempt по
# имени файла от места/имени-проверки (findings A4, 2026.07.15-PLANFLOW-UX P3.3).
DEV_LOOP_EXEMPT_NAME = "dev-loop.js"

# --- 2026.07.10-SKM-ROADMAP-005 P4.6: workflow-как-DoR — грепаемый признак заявленной оркестрации (D29) ---
# КОНСЕРВАТИВНЫЙ набор маркеров в теле фазы: явный `scriptPath` launch-block'а,
# «оркестрац», «мультиагент»/`multi-agent`. Правило Code Guidance «при сомнении НЕ
# срабатывать» перевешивает буквальный список: бумерный `fan-out` НАМЕРЕННО исключён —
# как одиночное слово он ловит нерелевантную прозу (напр. «искажение при fan-out» в
# Known Deviations про токен-учёт), давая ложный warning. Условность (D29): ручное
# item-by-item исполнение workflow не требует — маркер должен быть намеренным.
ORCHESTRATION_MARKER_RE = re.compile(r"scriptPath|оркестрац|мультиагент|multi-agent", re.IGNORECASE)

# --- 2026.07.13-PLAN-PROTOCOL-GAP P2.15/D34: протухший `## Phase Handoff` при реопене фазы (H2) --------------
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
# 2026.07.13-PLAN-PROTOCOL-GAP P2.16). Регистронезависимо (флот пишет и «Терминальн…», и «терминальн…»).
PHASE_HANDOFF_CLOSURE_LITERALS = ("терминальн", "фаза закрыта", "Сдано:")
PHASE_HANDOFF_CLOSURE_RE = re.compile(
    "|".join(re.escape(lit) for lit in PHASE_HANDOFF_CLOSURE_LITERALS), re.IGNORECASE)
# 2026.07.13-PLAN-PROTOCOL-GAP P3.7/D50: гейт судит по СУБЪЕКТУ утверждения, а не по встреченному слову. Закрывающий
# литерал ищется ТОЛЬКО в ПЕРВОЙ непустой строке блока (там же, где ищется маркер
# `> УСТАРЕЛ`), и гасится ОТРИЦАНИЕМ на той же строке. Основание (J1, живая форма флота
# `themeon/2026.07.12-BASE/P5`): «**Фаза P5 НЕ закрыта.** Терминальны только P5.1 и P5.2
# (2/10)» — слово «Терминальны» относится к ITEMS, блок буквально отрицает закрытие фазы,
# а греп по всему блоку давал ЛОЖНО-положительный WARNING. Отрицание проверяется на ТОЙ ЖЕ
# строке, а не по блоку: «фаза закрыта … но P5.3 ещё не закрыта» ниже по тексту не должно
# гасить истинное срабатывание (форма `vaulter/VLT-REMED/P5` обязана остаться WARNING).
PHASE_HANDOFF_NEGATION_LITERALS = ("не закрыт",)
PHASE_HANDOFF_NEGATION_RE = re.compile(
    "|".join(re.escape(lit) for lit in PHASE_HANDOFF_NEGATION_LITERALS), re.IGNORECASE)

# --- 2026.07.24-AGENT-RELIABILITY P2.2/D26/D47: tiered-portability lint (plan-portability-v1.md, task_contract.py) ---
# Классификация РОЛИ пути (execution input vs provenance) — ПОЗИЦИОННЫЙ тест: путь
# execution-input, только если появляется в ЗНАЧЕНИИ полей Inputs/Required Reads/Validation
# КОНКРЕТНОГО item'а (то самое «что item реально читает» — plan-portability-v1.md
# §Provenance vs execution input). Прочая проза плана (Implementation Rules, Code Guidance,
# brief/, findings/) НЕ сканируется вовсе — упоминание пути там по построению не может стать
# execution input, что и есть self-conformance fixture этого плана (tmp/-ссылка в
# brief/00-brief.md обязана проходить). Регекс по подстроке `tmp/` для ЭТОГО шага (роль)
# ЗАПРЕЩЁН (D47) — используется только позиция поля. Строковый тест «внешности» пути
# (абсолютный/`~`/`../`/URL/`tmp/`-корень) — ОТДЕЛЬНЫЙ шаг ПОСЛЕ того, как роль уже решена
# позиционно (task_contract.is_external_path, task-contract-v1.md §Portability, frozen 2026.07.24-AGENT-RELIABILITY P0.2).
# Severity-cutoff (тот же паттерн, что у BRIEF_CANON_DATE/JOURNAL_CANON_DATE): датовые
# планы ОТ этой даты — ERROR, старее — WARNING. Дата НАМЕРЕННО позже дня запечатывания
# правила (2026-07-26, P2.2): fleet-замер на живом дереве (`bash
# packages/task/scripts/validate.sh`) вскрыл ~40 `~`/абсолютных путей в Required
# Reads/Validation ДРУГИХ активных планов (`2026.07.18-FOREMAN`, `2026.07.25-ECO-OPT`) —
# датируй правило раньше их даты, и чужая поверхность (И2) ловит новые ERROR без их
# участия. Правило само по себе уже применено и протестировано (юнит-тесты гоняют его на
# ERROR-тир синтетическими датовыми фикстурами); отложенный cutoff — только про то, какие
# УЖЕ СУЩЕСТВУЮЩИЕ планы флота не красятся задним числом (back-compat §2).
PORTABILITY_TIER_CANON_DATE = "2026.07.27"
PORTABILITY_ROLE_FIELDS = ("Inputs", "Required Reads", "Validation")
# Shell-редирект (`> файл` / `>> файл`) в поле Validation — ЦЕЛЬ записи диагностики
# (output её собственной команды), не execution input; вырезается ДО скана путей, иначе
# скретч-редирект `>/tmp/…` читался бы как «item читает /tmp/…» (ложное срабатывание).
PORTABILITY_SHELL_REDIRECT_RE = re.compile(r">>?\s*\S+")
# Путь-кандидат — любой path-like токен (≥1 `/`, path-safe символы), backtick-цитата или
# голый (снипеты/фикстуры протокола закавычивание не требуют) — сканируется по ВСЕМУ тексту
# поля, а не по одному «атомарному» backtick-спану (тот часто несёт целую команду). Префикс
# `./` (repo-relative CLI-инвокация вида `./packages/skiller/bin/skiller`) — ОТДЕЛЬНАЯ ветка
# от голого `/` (абсолютный путь): без неё ведущая точка «съедалась» бы регексом, и
# `./packages/…` читался бы как `/packages/…` (абсолютный, внешний) — ложное срабатывание.
PORTABILITY_PATH_RE = re.compile(
    r"(?:~/|\.\./|\./|/)?[A-Za-z0-9_.][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_.][A-Za-z0-9_.-]*)+")


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
    в `plans/<ID>/workflows/` — признак «готового workflow» для DoR-проверки 2026.07.10-SKM-ROADMAP-005 P4.6 (D29).
    Детект БЕЗ исполнения JS (подстрока-маркер, прецедент 2026.07.10-SKM-ROADMAP-005 P2.1/D19)."""
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
        self._raw_errors = []  # (path, msg) — для normalized_keys (2026.07.13-PLAN-PROTOCOL-GAP P1.2/B1)
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
        2026.07.13-PLAN-PROTOCOL-GAP P1.2/D5/D6): путь — относительно `base_dir` (если под ним, иначе как есть),
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


def _lines_before_audit(lines):
    """Строки фазы ДО первого append-блока `## Audit` — регион грепов по фазе (D52).
    Префикс исходного списка ⇒ номера строк (i + 1) остаются валидными для диагностик."""
    for i, ln in enumerate(lines):
        if AUDIT_BLOCK_HEADER_RE.match(ln):
            return lines[:i]
    return lines


def _lint_audit_scope_payload(lines, path, plan_id, diag):
    """Scope-payload launch-block'а в блоках `## Audit Pn` (SKILL §8, D-канон 2026-07-17).

    Аудит с вердиктом RED/ATTENTION ПЕРЕДАЁТ находки следующей сессии, и голая команда их
    теряет: принимающая сессия переоткрывает находки сама, а `handoff.md` в этот момент ещё
    указывает на ПРЕДЫДУЩИЙ шаг и уводит мимо. Инцидент-основание — аудит P0 плана
    2026.07.16-INS-EVO: launch-block `/task:plan-design <ID> P0` без payload'а владелец
    прочитал как «фазу предлагают разрабатывать заново», а `plan-audit.md` ровно голую
    команду и предписывал. Правило cold-start («пути входных доков») существовало и до
    инцидента — не хватало формы и гейта.

    Гейтится ПРИСУТСТВИЕ четырёх строк; содержательность `СКОУП:`/`НЕ ТРОГАТЬ:` машина не
    меряет (report-quality — дело следующего аудита). Severity — как у brief/launch-block:
    датовые планы от BRIEF_CANON_DATE — ERROR, старее/legacy — WARNING (back-compat §2:
    живые планы флота писались до канона и красить их задним числом нельзя).
    """
    header_idxs = _section_header_indexes(lines)
    for idx in header_idxs:
        if not AUDIT_BLOCK_HEADER_RE.match(lines[idx]):
            continue
        body, _ = _section_body(lines, idx, header_idxs)
        if not body:
            continue
        body_text = "\n".join(body)
        verdict = AUDIT_VERDICT_RE.search(body_text)
        # Блок без строки вердикта — не отчёт аудита по форме (свободная заметка): не гейтим,
        # иначе линтер начнёт требовать payload от произвольного `## Audit …`-заголовка.
        if not verdict or verdict.group(1) not in AUDIT_FINDINGS_VERDICTS:
            continue
        missing = []
        if not any(LAUNCH_TABLE_ROW_RE.match(ln) for ln in body):
            missing.append("таблицы `| Model | …`")
        if not any(CODE_FENCE_RE.match(ln) for ln in body):
            missing.append("code-block с командой")
        missing.extend("строки `%s`" % m for m in SCOPE_PAYLOAD_MARKERS if m not in body_text)
        if not missing:
            continue
        msg = (f"«{lines[idx].strip()}»: вердикт {verdict.group(1)} передаёт находки, но "
               f"launch-block неполон — нет " + ", ".join(missing) +
               " (scope-payload — SKILL §8, snippets/launch-block-template.md)")
        if PLAN_ID_DATED_RE.match(plan_id) and plan_id[:10] >= BRIEF_CANON_DATE:
            diag.error(path, idx + 1, msg)
        else:
            diag.warning(path, idx + 1, msg)


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
    (fields, duplicates): fields — dict[name] = (value, lineno) ПОСЛЕДНЕГО вхождения
    (back-compat: потребители как читали dict, так и читают); duplicates —
    [(name, first_lineno, first_value, dup_lineno, dup_value)] на КАЖДОЕ повторное
    вхождение ключа, по порядку появления (D90: `**Поле:**`-строка внутри свободной прозы
    другого поля — напр. `**Validation:**`, дописанная в Completion Notes, — матчит тот же
    `field_re` и молча подменяет собой раннее легитимное значение поля; вызывающий решает,
    диагностировать находку или пропустить — handoff-поля вне Scope 2026.07.31-SKM-LEAN P5.9,
    только item-поля)."""
    fields = {}
    first_seen = {}
    duplicates = []
    cur_key = cur_lineno = None
    cur_val = []

    def flush():
        if cur_key is not None:
            value = "\n".join(cur_val).strip()
            if cur_key in first_seen:
                prev_lineno, prev_value = first_seen[cur_key]
                duplicates.append((cur_key, prev_lineno, prev_value, cur_lineno, value))
            else:
                first_seen[cur_key] = (cur_lineno, value)
            fields[cur_key] = (value, cur_lineno)

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
    return fields, duplicates


def _preview(text, limit=72):
    """Первая непустая строка значения, усечённая до `limit` (D90-диагностика: обе стороны
    расхождения в одной строке отчёта — полное многострочное значение там не читается)."""
    first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    return first_line if len(first_line) <= limit else first_line[:limit].rstrip() + "…"


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

__all__ = tuple(name for name in globals() if not name.startswith("__"))
