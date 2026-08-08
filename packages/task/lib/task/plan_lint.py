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


def _portability_execution_paths(fields):
    """Пути (path-like токены, backtick-цитата или голые) в значениях ролевых полей
    item'а (ROLE-тест, D47): другие поля (Implementation Rules/Code Guidance/Why/…)
    НЕ сканируются — упоминание там не даёт пути роль execution input."""
    paths = []
    for name in PORTABILITY_ROLE_FIELDS:
        value = fields.get(name, "") or ""
        cleaned = PORTABILITY_SHELL_REDIRECT_RE.sub(" ", value)
        paths.extend(PORTABILITY_PATH_RE.findall(cleaned))
    return paths


def _plan_declares_committed_bundle_tier(plan_dir):
    """plan-portability-v1.md §Classification rule — tier(work) применительно к
    исполняемому мастер-плану целиком: план протокола ПО КОНСТРУКЦИИ несёт `handoff.md`
    (multi-session/handoff всегда true — обязательный носитель SKILL §8) → committed-bundle.
    План без `handoff.md` (ещё не дошёл до схемы) этим гейтом не разбирается — другая
    диагностика уже требует сам файл."""
    return (Path(plan_dir) / "handoff.md").is_file()


def _lint_tiered_portability_22(plan_dir, plan_id, all_items, phases, diag):
    """2026.07.24-AGENT-RELIABILITY P2.2/D26/D47: план tier=committed-bundle (что верно для любого исполняемого
    мастер-плана по конструкции, см. `_plan_declares_committed_bundle_tier`) обязан
    нести ≥1 committed/predecessor-produced execution input и не содержать внешний
    (host/chat/mAInd/tmp/foreign) путь В РОЛИ execution input — иначе `plan_lint`
    отказывает (`task_contract.PORTABILITY_INPUT_MISSING`/`PORTABILITY_EXTERNAL_INPUT`).
    Датовые планы от PORTABILITY_TIER_CANON_DATE — ERROR, старее/legacy — WARNING
    (back-compat, тот же паттерн, что у brief/roadmap/journal-гейтов)."""
    if not _plan_declares_committed_bundle_tier(plan_dir):
        return
    report = (diag.error if (PLAN_ID_DATED_RE.match(plan_id)
                             and plan_id[:10] >= PORTABILITY_TIER_CANON_DATE) else diag.warning)
    found_committed = False
    for item_id, info in sorted(all_items.items()):
        item_path = phases.get(info.get("phase"), {}).get("path", plan_dir)
        for raw_path in _portability_execution_paths(info.get("fields", {})):
            if task_contract.is_external_path(raw_path):
                report(item_path, None,
                       f"item {item_id}: execution input «{raw_path}» — внешний путь "
                       f"(host/chat/mAInd/tmp/foreign, PORTABILITY_EXTERNAL_INPUT, "
                       f"plan-portability-v1.md)")
            else:
                found_committed = True
    if not found_committed:
        report(Path(plan_dir) / "plan.md", None,
               f"план несёт handoff.md (tier=committed-bundle, plan-portability-v1.md "
               f"§Classification rule) без единого committed execution input ни в одном "
               f"item'е (PORTABILITY_INPUT_MISSING)")


# --- 2026.07.24-AGENT-RELIABILITY P4.4/D91: машинный гейт напечатанных кодов границ (ремонт находки Ф2) ------
# findings/P3.11-terminal-audit-2.md § Ф2, событие 2 из 2: канон уже требовал печати ОБОИХ
# кодов write-site (`plan-audit.md` чеклист), но проверка была НЕ машинной — пять items
# подряд (P3.6-P3.10) прошли аудит перепрогоном предиката ВРУЧНУЮ (все пять → allow/allow),
# сама ЗАПИСЬ в Completion Notes осталась отсутствующей. Якорь скоупа — ДАТА ITEM'а
# (колонка `Updated` таблицы «## Phase Status», ISO), А НЕ дата плана: паттерн
# BRIEF_CANON_DATE/JOURNAL_CANON_DATE/PORTABILITY_TIER_CANON_DATE здесь промахнулся бы —
# этот план датирован `2026.07.24`, то есть его собственные будущие items P4.* остались бы
# вне гейта, а красить закрытые задним числом запрещено (D91, третий проход по записи
# отвергнут отчётом Ф2). Формат константы — ISO ДЕФИС (`YYYY-MM-DD`), а НЕ ТОЧКА, как у
# датовых plan_id-констант выше: сравнение идёт со значением ЯЧЕЙКИ `Updated`, которая несёт
# дефисы — сравнение разноформатных строк друг с другом ломает лексикографический порядок.
# Дата НАМЕРЕННО на день позже дня авторства правила (2026-07-26) — тот же приём, что у
# PORTABILITY_TIER_CANON_DATE: items, закрываемые ЭТОЙ же фазой в день авторства, не красятся
# задним числом; правило доказывается синтетическими датированными фикстурами
# (test_plan_lint.py), а не самоприменением к текущему прогону.
WRITE_SITE_CODES_CANON_DATE = "2026-07-27"
ITEM_UPDATED_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Канон кодов — `task_contract.evaluate()`: `pre_mutation` ∈ {allow, block:<CODE>};
# `pre_final` ∈ {allow, block:<CODE>, n/a} (D76: `n/a` — НЕ зелёное).
# --- 2026.07.25-ECO-OPT P10.1/D88/D102: каноническая строка вместо re.search по всему полю --------
# Старая форма (`WRITE_SITE_PRE_MUTATION_RE.search(clean)` по ВСЕМУ Completion Notes)
# ошибалась в ОБЕ стороны: (1) fail-open — item без своих кодов, но ЦИТИРУЮЩИЙ чужие в
# прозе, проходил гейт; (2) ложный ERROR — item со своими `allow`, процитировавший ВЫШЕ
# по тексту `block:*`/`n/a` чужого item'а, краснел, потому что `search` берёт ПЕРВОЕ
# вхождение. Обе цены реальны с даты активации гейта. Починка: ОДНА каноническая строка
# `write-site: pre_mutation: <код> · pre_final: <код>` (D88) — коды item'а живут ТОЛЬКО
# на строке с этим префиксом; прозаические цитаты на других строках гейт не видит.
WRITE_SITE_LINE_FORM = "write-site: pre_mutation: <код> · pre_final: <код>"
_WRITE_SITE_CODE = r"(allow|n/a|block:[A-Za-z0-9_]+)"
WRITE_SITE_LINE_PREFIX_RE = re.compile(r"^write-site:\s*(.*)$")
WRITE_SITE_CODE_PAIR_RE = re.compile(
    r"^pre_mutation:\s*" + _WRITE_SITE_CODE + r"\s*\W+\s*"
    r"pre_final:\s*" + _WRITE_SITE_CODE + r"\s*\.?\s*$")


def _write_site_canonical_codes(completion_notes):
    """Находит каноническую строку `write-site:` (D88) в Completion Notes и
    возвращает `(pre_mutation, pre_final)` — ПОСТРОЧНО (поле парсер отдаёт
    многострочным), а не `re.search` по всему полю. Markdown-обёртка строки
    (бэктики, `**`, ведущие `- `/`> `, пробелы) срезается ДО матча — форма печати
    несёт их. Строки БЕЗ префикса `write-site:` (цитаты, объяснения) не
    рассматриваются вовсе, даже если в них встречаются `pre_mutation:`/`pre_final:` —
    ровно это закрывает fail-open. Строка С префиксом, но не разбирающаяся в форму
    (сломан порядок/разделитель, ЛИБО это прозаическая цитата шаблона строки —
    `` `write-site: pre_mutation: <код> · pre_final: <код>` `` как объяснение
    правила, — с обёрнутой строки такая цитата тоже начинается) НЕ считается
    канонической и не останавливает поиск: перебор продолжается дальше по полю.
    Ни одной разбирающейся строки во всём поле → `None`, ERROR «кодов нет»."""
    for raw_line in (completion_notes or "").replace("`", "").splitlines():
        line = raw_line.replace("*", "").strip()
        while line[:1] in ("-", ">"):
            line = line[1:].strip()
        prefix = WRITE_SITE_LINE_PREFIX_RE.match(line)
        if not prefix:
            continue
        pair = WRITE_SITE_CODE_PAIR_RE.match(prefix.group(1).strip())
        if pair:
            return pair.group(1), pair.group(2)
    return None


def _lint_write_site_codes_44(status_table, items, path, diag):
    """2026.07.24-AGENT-RELIABILITY P4.4/D91 (ремонт находки Ф2), точность — 2026.07.25-ECO-OPT P10.1/D88/D102: item со статусом
    🟢/🟠, чей `Updated` (Phase Status) ISO-датирован ≥ WRITE_SITE_CODES_CANON_DATE,
    обязан нести каноническую строку `write-site:` (см. `_write_site_canonical_codes`)
    с ОБОИМИ кодами `allow` (D76: `n/a` — не зелёное). Непарсимая/отсутствующая дата =
    item вне скоупа — МОЛЧАНИЕ, а не WARNING (И10: ни один существующий закрытый item
    не краснеет задним числом). Внутри скоупа — ERROR (правило уже канон:
    `plan-audit.md` чеклист «write-site»; машинная проверяемость — P4.4/P10.1)."""
    updated_by_id = {row.get("ID"): row.get("Updated", "") for row, _ in status_table}
    for item_id, occurrences in items.items():
        item = occurrences[0]
        status_val, _ = item["fields"].get("Status", ("", item["header_lineno"]))
        if status_val not in (STATUS_DONE, STATUS_DEVIATIONS):
            continue
        updated = updated_by_id.get(item_id, "") or ""
        if not ITEM_UPDATED_ISO_RE.match(updated) or updated < WRITE_SITE_CODES_CANON_DATE:
            continue
        cn_val, cn_lineno = item["fields"].get("Completion Notes", ("", item["header_lineno"]))
        codes = _write_site_canonical_codes(cn_val)
        if codes is None:
            diag.error(path, cn_lineno,
                       f"item {item_id}: закрыт «{status_val}» без напечатанных кодов границ "
                       f"pre_mutation/pre_final в Completion Notes (ожидается строка "
                       f"`{WRITE_SITE_LINE_FORM}`)")
            continue
        pre_mutation, pre_final = codes
        if pre_mutation != "allow":
            diag.error(path, cn_lineno,
                       f"item {item_id}: pre_mutation: {pre_mutation} при статусе "
                       f"«{status_val}» — закрытие на не-allow (D76)")
        if pre_final != "allow":
            diag.error(path, cn_lineno,
                       f"item {item_id}: pre_final: {pre_final} при статусе "
                       f"«{status_val}» — закрытие на не-allow (D76)")


# --- 2026.07.25-ECO-OPT P8.1/D42: отчёт закрытия фазы `closure/<Pn>.json` (схема v1) --------------
# Класс свидетельства фазы не фиксировался нигде: `Phase Handoff` — проза плюс git-хеш, и
# синтетика читается как результат (research/11-P8-target-design.md §1). Отчёт закрытия —
# машиночитаемый файл на фазу, ВКЛЮЧАЕТСЯ opt-in полем `## 0. Meta` → `Closure Protocol | v1`:
# плана без поля правило не касается НИ ОДНОЙ строкой диагностики (аддитивность — тест, а не
# обещание; закрытые записи живых планов не переписываются). Ревалидация ПОСЛОЙНАЯ (рамка
# переноса, findings/rayt-deep-2026-07-25.md §8.3 #17/#29): один JSON на фазу + две уже
# распарсенные таблицы; обхода дерева и пересчёта хешей файлов плана здесь нет.
# У КАЖДОГО хеша схемы назван потребитель (иначе «provenance theatre», §9.6): `git.head_sha` —
# якорь чисел §8 канона; `inputs_sha256` — детект правки ТЗ фазы после закрытия (`plan-audit`).
CLOSURE_META_FIELD = "Closure Protocol"
CLOSURE_PROTOCOL_V1 = "v1"  # ЕДИНСТВЕННОЕ легальное значение поля (D42)
CLOSURE_DIR_NAME = "closure"
CLOSURE_SCHEMA_VERSION = 1
# Класс свидетельства — enum РОВНО из трёх (D42): на каких ДАННЫХ получен результат.
# НЕ путать с закрытым перечнем классов ДОКАЗАТЕЛЬСТВА `recomputed`/`cross-checked`/
# `pinned-not-recomputable`/`unknown` (`source-evidence-verification-v1.md`, другая ось —
# выводимо ли утверждение из коммиченного bundle'а): оба словаря действуют, ни один не
# заменяет другой (канон `plan-protocol` §8, реконсайл 2026-07-26).
CLOSURE_EVIDENCE_CLASSES = ("real", "synthetic", "baseline_pending")
CLOSURE_REQUIRED_KEYS = ("schema_version", "plan", "phase", "closed_at", "closed_by",
                         "phase_status", "git", "inputs_sha256", "items", "gates",
                         "metrics", "limitations", "external_side_effects")
CLOSURE_CLOSED_BY_KEYS = ("command", "actor")
CLOSURE_GIT_KEYS = ("head_sha", "branch", "dirty")
# `items`/`gates` — записи с классом свидетельства; `metrics` несёт его в `label`
# (числа нет ⇒ `baseline_pending` с причиной, а НЕ отсутствие строки — ради этого приём и взят).
CLOSURE_ENTRY_KEYS = {"items": ("id", "status", "evidence_class", "evidence"),
                      "gates": ("id", "status", "evidence_class", "evidence"),
                      "metrics": ("name", "value", "label")}
CLOSURE_LIST_KEYS = ("items", "gates", "metrics", "limitations", "external_side_effects")


def _closure_report_path(plan_dir, phase_id):
    """Дом отчёта закрытия — `plans/<PLAN-ID>/closure/<Pn>.json` (D42)."""
    return Path(plan_dir) / CLOSURE_DIR_NAME / f"{phase_id}.json"


def _closure_load(report_path, diag):
    """Читает отчёт закрытия; любой отказ НАЗЫВАЕТ файл и причину (рамка переноса:
    fail-closed без имени объекта запрещён — findings §8.3 issue #19). None = не разобран."""
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as error:
        diag.error(report_path, None, f"отчёт закрытия не читается: {error}")
        return None
    except json.JSONDecodeError as error:
        diag.error(report_path, None, f"отчёт закрытия не разбирается как JSON: {error}")
        return None
    if not isinstance(data, dict):
        diag.error(report_path, None,
                   f"отчёт закрытия: ожидался объект схемы v{CLOSURE_SCHEMA_VERSION}, "
                   f"получен {type(data).__name__}")
        return None
    return data


def _closure_lint_schema(data, report_path, plan_id, phase_id, diag):
    """Проверка 1 — схема v1: отсутствие ключа = ОШИБКА СХЕМЫ, а не «нет данных»
    («нет данных» выражается ЗНАЧЕНИЕМ — `baseline_pending` с причиной, D42).
    Проверка 3 — `evidence_class: "real"` при пустом `evidence` = ERROR с id записи."""
    for key in CLOSURE_REQUIRED_KEYS:
        if key not in data:
            diag.error(report_path, None, f"отчёт закрытия: нет обязательного ключа «{key}»")
    if data.get("schema_version") != CLOSURE_SCHEMA_VERSION:
        diag.error(report_path, None,
                   f"отчёт закрытия: schema_version «{data.get('schema_version')}» ≠ "
                   f"{CLOSURE_SCHEMA_VERSION} (иных версий схемы не существует)")
    for key, expected in (("plan", plan_id), ("phase", phase_id)):
        if key in data and data.get(key) != expected:
            diag.error(report_path, None,
                       f"отчёт закрытия: «{key}» = «{data.get(key)}» ≠ фактическому «{expected}»")
    for key, subkeys in (("closed_by", CLOSURE_CLOSED_BY_KEYS), ("git", CLOSURE_GIT_KEYS),
                         ("inputs_sha256", ())):
        value = data.get(key)
        if key in data and not isinstance(value, dict):
            diag.error(report_path, None,
                       f"отчёт закрытия: «{key}» — ожидался объект, получен {type(value).__name__}")
            continue
        for subkey in subkeys:
            if isinstance(value, dict) and subkey not in value:
                diag.error(report_path, None,
                           f"отчёт закрытия: нет обязательного ключа «{key}.{subkey}»")
    if isinstance(data.get("inputs_sha256"), dict) and not data["inputs_sha256"]:
        diag.error(report_path, None,
                   "отчёт закрытия: «inputs_sha256» пуст — потребитель (plan-audit) ловит по "
                   "нему правку ТЗ фазы после закрытия; хеш без потребителя не пишем, "
                   "потребителя без хеша — тем более")
    for key in CLOSURE_LIST_KEYS:
        if key in data and not isinstance(data[key], list):
            diag.error(report_path, None,
                       f"отчёт закрытия: «{key}» — ожидался список, получен "
                       f"{type(data[key]).__name__}")
    for key, entry_keys in CLOSURE_ENTRY_KEYS.items():
        for pos, entry in enumerate(data.get(key) if isinstance(data.get(key), list) else []):
            if not isinstance(entry, dict):
                diag.error(report_path, None,
                           f"отчёт закрытия: «{key}[{pos}]» — ожидался объект, получен "
                           f"{type(entry).__name__}")
                continue
            name = entry.get("id") or entry.get("name") or f"{key}[{pos}]"
            for subkey in entry_keys:
                if subkey not in entry:
                    diag.error(report_path, None,
                               f"отчёт закрытия: «{key}» запись «{name}» без ключа «{subkey}»")
            # Носитель класса и носитель ДОКАЗАТЕЛЬСТВА различаются по виду записи:
            # items/gates несут `evidence_class` + `evidence` (команда и её вывод),
            # metrics — `label` + `value` (само число). Пустое доказательство при классе
            # `real` = fail-closed: это либо `synthetic`, либо `baseline_pending` с причиной.
            klass_key, proof_key = (("label", "value") if key == "metrics"
                                    else ("evidence_class", "evidence"))
            klass = entry.get(klass_key)
            if klass_key in entry and klass not in CLOSURE_EVIDENCE_CLASSES:
                diag.error(report_path, None,
                           f"отчёт закрытия: «{key}» запись «{name}»: {klass_key} «{klass}» вне "
                           f"enum'а {list(CLOSURE_EVIDENCE_CLASSES)}")
            if klass == "real" and _is_empty(str(entry.get(proof_key, "") or "")):
                diag.error(report_path, None,
                           f"отчёт закрытия: «{key}» запись «{name}» заявлена "
                           f"«real» с пустым {proof_key} — класс real требует команду и её вывод "
                           f"(иначе это synthetic либо baseline_pending с причиной)")


def _closure_lint_correspondence(data, report_path, phase_id, parsed_phase, board_row, diag):
    """Проверка 4 — `items[]` ↔ строки `## Phase Status` фазы (лишний/недостающий id либо
    иной статус); проверка 5 — `phase_status` ↔ строка фазы в Status Board (`plan.md`).
    Обе — на УЖЕ распарсенных таблицах: отдельного обхода дерева гейт не делает."""
    if board_row is not None:
        board_status = board_row[0].get("Status", "")
        if "phase_status" in data and data.get("phase_status") != board_status:
            diag.error(report_path, None,
                       f"отчёт закрытия: phase_status «{data.get('phase_status')}» ≠ статусу "
                       f"фазы {phase_id} в Status Board «{board_status}»")
    if parsed_phase is None:
        return  # файла фазы нет — отдельная диагностика уже выдана, дублировать нечем
    table = {row.get("ID"): row.get("Status", "")
             for row, _ in parsed_phase.get("status_table", [])}
    reported = {}
    for entry in (data.get("items") if isinstance(data.get("items"), list) else []):
        if isinstance(entry, dict) and entry.get("id"):
            reported[entry["id"]] = entry.get("status")
    for item_id in sorted(set(reported) - set(table)):
        diag.error(report_path, None,
                   f"отчёт закрытия: item «{item_id}» есть в items[], но нет строки в "
                   f"«## Phase Status» фазы {phase_id}")
    for item_id in sorted(set(table) - set(reported)):
        diag.error(report_path, None,
                   f"отчёт закрытия: item «{item_id}» есть в «## Phase Status» фазы "
                   f"{phase_id}, но отсутствует в items[]")
    for item_id in sorted(set(table) & set(reported)):
        if reported[item_id] != table[item_id]:
            diag.error(report_path, None,
                       f"отчёт закрытия: item «{item_id}»: status «{reported[item_id]}» ≠ "
                       f"статусу в «## Phase Status» «{table[item_id]}»")


def _lint_closure_reports_81(plan_dir, plan_id, meta, phases, board_by_phase, diag):
    """2026.07.25-ECO-OPT P8.1/D42, все пять проверок отчёта закрытия. Активация — opt-in Meta-поле
    `Closure Protocol | v1`: без него функция молчит целиком (аддитивность). Проверка 2 —
    фаза терминальна, поле включено, файла нет → ERROR с ОЖИДАЕМЫМ ПУТЁМ (fail-closed
    называет объект). Нетерминальная фаза отчёта не обязана иметь; но ЕСЛИ файл лежит —
    он разбирается по той же схеме (иначе включённый протокол молча пропускал бы мусор)."""
    plan_md = Path(plan_dir) / "plan.md"
    declared, meta_lineno = (meta or {}).get(CLOSURE_META_FIELD, (None, None))
    if declared is None:
        return
    declared = declared.strip()
    if declared != CLOSURE_PROTOCOL_V1:
        diag.error(plan_md, meta_lineno,
                   f"Meta «{CLOSURE_META_FIELD}»: значение «{declared}» — единственное "
                   f"легальное «{CLOSURE_PROTOCOL_V1}» (канон plan-protocol §8)")
        return
    for phase_id in sorted(set(phases) | set(board_by_phase)):
        report_path = _closure_report_path(plan_dir, phase_id)
        board_row = board_by_phase.get(phase_id)
        board_status = board_row[0].get("Status", "") if board_row else ""
        if not report_path.is_file():
            if board_status in TERMINAL_STATUSES:
                diag.error(plan_md, board_row[1] if board_row else None,
                           f"фаза {phase_id} терминальна («{board_status}») при "
                           f"`{CLOSURE_META_FIELD} | {CLOSURE_PROTOCOL_V1}`, но отчёта "
                           f"закрытия нет — ожидается файл {report_path}")
            continue
        data = _closure_load(report_path, diag)
        if data is None:
            continue
        _closure_lint_schema(data, report_path, plan_id, phase_id, diag)
        _closure_lint_correspondence(data, report_path, phase_id, phases.get(phase_id),
                                     board_row, diag)


# --- 2026.07.25-ECO-OPT P8.2/D103-D105: `Consequences` в D-записи (research/11 §2, research/23) ---
# Носитель — инлайн-подполе `**Consequences:**` внутри ячейки `Решение` (пятая колонка
# отклонена: шапка D-лога — литерал реестра CANON_LITERALS, её правка = переписывание
# шапки во всех планах флота, D43). Гейт — ОПТ-IN ДВАЖДЫ (та же дисциплина, что у
# `_lint_closure_reports_81`): (1) Meta-поле `Closure Protocol | v1`, (2) `Дата` D-записи
# ≥ CONSEQUENCES_CANON_DATE (forward-only — механика WRITE_SITE_CODES_CANON_DATE выше,
# И10: непарсимая/отсутствующая дата = вне скоупа, МОЛЧАНИЕ). Дата константы —
# ДЕНЬ ПОСЛЕ последней существующей записи без `Consequences` (D98, ECO-OPT
# 2026-07-27) — измерено `research/23-P8.2-refine-2026-07-27.md` §2: без даты гейт
# закрылся бы красным собственным планом (D98 нет носителя и бэкфилл ЗАПРЕЩЁН, §2).
CONSEQUENCES_CANON_DATE = "2026-07-28"
CONSEQUENCES_LITERAL = "**Consequences:**"
# Префиксный ISO-матч ячейки `Дата` (не барный `==`, D103 §2): FOREMAN D7 несёт
# `2026-07-18 (финализирован P0.4)` — суффикс после даты легален, а строгий полный
# матч читал бы это как непарсимое и терял смысл прецедента.
CONSEQUENCES_DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
# Предикат отмены/замены решения — ИЗМЕРЕННЫЙ (research/23 §1), не переписанный со
# спеки дословно: спека (`supersedes D`/`отменён`/`отменяет D`) ловит НОЛЬ записей на
# ECO-OPT (краткое причастие склоняется, «ё» факультативна — D98 несёт форму
# «отменена»); широкий стем `отмен` (любая форма) даёт 6 срабатываний, 4 из них —
# ОТРИЦАНИЕ «не отменяет»/«не отменена» (ложный ERROR). Негативный lookbehind
# `(?<!не )` СНИМАТЬ НЕЛЬЗЯ: без него 4 из 6 срабатываний на этом же плане ложные
# (D11/D19/D26 и др., research/23 §1). Стем-лист держать УЗКИМ — три семантики, не
# десять слов (Code Guidance 2026.07.25-ECO-OPT P8.2): каждый лишний стем — риск ложного ERROR на сотнях
# планов флота.
CONSEQUENCES_STEMS_RE = re.compile(
    r"supersedes D|отменяет D|(?<!не )отмен(?:ён|ен|ена|ено|ены)\b")


def _lint_consequences_82(plan_dir, plan_id, meta, plan_lines, plan_md, diag):
    """2026.07.25-ECO-OPT P8.2/D103-D105: ячейка `Решение` строки `## 5. Decision Log`, матчащая
    CONSEQUENCES_STEMS_RE (отмена/замена решения) и датированная (`Дата`) ≥
    CONSEQUENCES_CANON_DATE, обязана нести `**Consequences:**` — иначе ERROR с
    номером D-записи (fail-closed называет объект). Активация — ДВОЙНОЙ opt-in:
    без Meta `Closure Protocol | v1` функция молчит целиком (аддитивность, тест).

    Честная граница (Code Guidance P8.2, обязана быть написана вслух и здесь):
    канон требует `Consequences` у КАЖДОЙ несущей D-записи; эта проверка ловит только
    МАШИННО-ДЕТЕКТИРУЕМЫЙ подкласс — запись, явно объявляющую отмену/замену другого
    решения тремя измеренными формами выше. Полное покрытие канона гейт не даёт и
    не заявляет (findings/rayt-deep-2026-07-25.md §9.4 — формализм галочки)."""
    declared, _ = (meta or {}).get(CLOSURE_META_FIELD, (None, None))
    if declared is None or declared.strip() != CLOSURE_PROTOCOL_V1:
        return
    _, dl_body, dl_start = _find_section(plan_lines, DECISION_LOG_HEADER_RE)
    if dl_body is None:
        return
    _, rows, _ = _parse_table(dl_body, dl_start)
    for row, lineno in rows:
        decision = row.get("Решение", "") or ""
        if not CONSEQUENCES_STEMS_RE.search(decision):
            continue
        date_match = CONSEQUENCES_DATE_PREFIX_RE.match((row.get("Дата", "") or "").strip())
        if not date_match or date_match.group(1) < CONSEQUENCES_CANON_DATE:
            continue  # непарсимая/старая дата — вне скоупа, МОЛЧАНИЕ (И10, forward-only)
        if CONSEQUENCES_LITERAL not in decision:
            diag.error(plan_md, lineno,
                       f"Decision Log {row.get('D#', '?')}: маркер отмены/замены решения "
                       f"без `{CONSEQUENCES_LITERAL}` (канон plan-protocol §6, forward-only "
                       f"с {CONSEQUENCES_CANON_DATE}, D103)")


# --- 2026.07.25-ECO-OPT P8.3/D44: `CHECKPOINTED` — отказ несёт точную команду возобновления ------
# Носитель — строка `Возобновление: <команда>` в поле `Pending Work` item'а (НЕ седьмой
# статус, НЕ семнадцатое поле — оба варианта отклонены D44, ломают контракт трёх живых
# планов/`plans/cross-plan-files.py`). Активация — тот же opt-in, что у 2026.07.25-ECO-OPT P8.1/P8.2:
# Meta-поле `Closure Protocol | v1` (без даты-канона — на дату детализации в этом плане
# живых 🔴/⛔ items с включённым протоколом нет, задним числом красить нечего).
STATUS_SKIPPED = "⛔ Skipped by decision"
RESUME_LITERAL = "Возобновление:"
RESUME_LINE_RE = re.compile(r"^Возобновление:\s*(.*)$")
D_REF_RE = re.compile(r"\bD\d+\b")


def _find_resume_line(pending_work):
    """Ищет строку `Возобновление: …` в поле Pending Work — построчно (та же дисциплина,
    что `_write_site_canonical_codes`), markdown-обёртка (`-`/`>`/`` ` ``/`**`) срезается
    ДО матча. Возвращает значение ПОСЛЕ двоеточия (обрезанное) либо `None`, если строки нет."""
    for raw_line in (pending_work or "").replace("`", "").splitlines():
        line = raw_line.replace("*", "").strip()
        while line[:1] in ("-", ">"):
            line = line[1:].strip()
        m = RESUME_LINE_RE.match(line)
        if m:
            return m.group(1).strip()
    return None


def _lint_checkpointed_83(meta, items, path, diag):
    """2026.07.25-ECO-OPT P8.3/D44: item со статусом `🔴 Blocked` обязан нести в Pending Work непустую
    строку `Возобновление: <команда>` (форма `Возобновление: — (внешний блокер: …)` —
    легальное «непусто» для блокера без локального шага, Code Guidance P8.3); item со
    статусом `⛔ Skipped by decision` обязан нести РОВНО `Возобновление: —` И ссылку
    `D<номер>` в том же поле (решение о пропуске предъявляется записью, не молчанием)."""
    declared, _ = (meta or {}).get(CLOSURE_META_FIELD, (None, None))
    if declared is None or declared.strip() != CLOSURE_PROTOCOL_V1:
        return
    for item_id, occurrences in items.items():
        item = occurrences[0]
        status_val, _ = item["fields"].get("Status", ("", item["header_lineno"]))
        if status_val not in (STATUS_BLOCKED, STATUS_SKIPPED):
            continue
        pw_val, pw_lineno = item["fields"].get("Pending Work", ("", item["header_lineno"]))
        resume = _find_resume_line(pw_val)
        if status_val == STATUS_BLOCKED:
            if resume is None or _is_empty(resume):
                diag.error(path, pw_lineno,
                           f"item {item_id}: {STATUS_BLOCKED} без строки "
                           f"`{RESUME_LITERAL} <команда>` в Pending Work — отказ обязан "
                           f"нести точную команду продолжения, а не «пропущено» (D44)")
        else:
            has_d_ref = bool(D_REF_RE.search(pw_val or ""))
            if resume is None or resume != EMPTY_PLACEHOLDER or not has_d_ref:
                diag.error(path, pw_lineno,
                           f"item {item_id}: {STATUS_SKIPPED} без `{RESUME_LITERAL} "
                           f"{EMPTY_PLACEHOLDER}` и ссылки `D<номер>` в Pending Work — "
                           f"решение о пропуске обязано быть предъявлено D-записью (D44)")


# --- 2026.07.25-ECO-OPT P11.3/D129: кросс-документный чек `handoff.md` ↔ «## 4. Phase Index
# & Status Board» (F8 аудита P9: handoff соврал `P9 4/4`, доска несла `2/4`, права доска).
# Дом — plan_lint.py, не verify-citations.py (D129): это согласованность двух секций ОДНОГО
# плана, не резолв пути/цитаты — обратное решение размыло бы оба инструмента (`research/27-…`
# §2.4, Scope Excluded P10.2 остаётся в силе). Forward-only по ДАТЕ ЗАГОЛОВКА handoff'а
# (та же дисциплина, что WRITE_SITE_CODES_CANON_DATE/CONSEQUENCES_CANON_DATE): handoff старше
# канон-даты не диагностируется вовсе, даже WARNING (И10 — не красим существующий флот задним
# числом). Severity внутри скоупа — как у launch-block-гейта (D-канон 2.0): датовый `plan_id`
# от BRIEF_CANON_DATE → ERROR, легаси → WARNING (`plan_id[:10]` — дата, не handoff-дата).
HANDOFF_BOARD_CANON_DATE = "2026-07-28"
HANDOFF_TITLE_DATE_RE = re.compile(r"^#\s+HANDOFF\s+—\s*(\d{4}-\d{2}-\d{2})\s+—")
# Узкий шаблон намеренно (Code Guidance P11.3, анти-самообман): РОВНО `Pn a/b` — не «33/44»,
# не проценты, не голая проза «закрыто 4 из 4». Замер (`findings/P11-citation-gate-
# measurements.md` §4) — 3 вхождения на трёх живых планах, 1 расхождение (F8), 0 ложных;
# расширение на прозу вернуло бы шум, который узость сегодня держит на нуле.
HANDOFF_BOARD_REF_RE = re.compile(r"\bP(\d+)\s+(\d+)/(\d+)\b")


def _lint_handoff_board_113(handoff, handoff_path, plan_id, board_by_phase, diag):
    """2026.07.25-ECO-OPT P11.3/D129: каждое вхождение `Pn a/b` в handoff.md обязано совпадать
    со значением колонки `STATUS_BOARD_ITEMS_COL` строки `Pn` доски «## 4. Phase Index &
    Status Board»; расхождение — диагностика, называющая ОБЕ стороны. Фаза `Pn`, отсутствующая
    в доске, — «висячая ссылка». Непарсимая/более старая дата заголовка handoff'а — МОЛЧАНИЕ
    (forward-only, аддитивность И10), не ERROR/WARNING."""
    if not handoff:
        return
    title_lineno = handoff.get("title_lineno")
    lines = handoff.get("lines") or []
    if not title_lineno or title_lineno > len(lines):
        return
    date_m = HANDOFF_TITLE_DATE_RE.match(lines[title_lineno - 1])
    if not date_m or date_m.group(1) < HANDOFF_BOARD_CANON_DATE:
        return
    report = (diag.error if (PLAN_ID_DATED_RE.match(plan_id) and plan_id[:10] >= BRIEF_CANON_DATE)
              else diag.warning)
    for i, ln in enumerate(lines):
        for m in HANDOFF_BOARD_REF_RE.finditer(ln):
            phase_id = f"P{m.group(1)}"
            handoff_ratio = f"{m.group(2)}/{m.group(3)}"
            row = board_by_phase.get(phase_id)
            if row is None:
                report(handoff_path, i + 1,
                       f"handoff.md: «{phase_id} {handoff_ratio}» ссылается на фазу «{phase_id}», "
                       f"отсутствующую в «## 4. Phase Index & Status Board» (висячая ссылка)")
                continue
            board_ratio = row[0].get(STATUS_BOARD_ITEMS_COL, "")
            if board_ratio != handoff_ratio:
                report(handoff_path, i + 1,
                       f"handoff.md:{i + 1} говорит «{phase_id} {handoff_ratio}», доска «## 4. "
                       f"Phase Index & Status Board» несёт «{phase_id} {board_ratio}» "
                       f"(расхождение)")


# --- 2026.07.13-PLAN-PROTOCOL-GAP P2.16/D35: реестр непереводимых литералов (H3) ---------------------------
# ЕДИНСТВЕННЫЙ источник строк, которые линтер сверяет с ТЕКСТОМ ПЛАНА байт-в-байт.
# Дисциплина (гейт — tests/test_canon_literals.py):
#   * `CANON_LITERALS` — строка, которую протокол ТРЕБУЕТ писать дословно (шапки таблиц,
#     маркеры, формы `Next`). Агент флота берёт её из EN-канона `SKILL.md` ⇒ каждая обязана
#     нести директиву `<!-- i18n-keep: … -->` в `SKILL.ru.md` (гейт присутствия в EN —
#     `packages/skiller/scripts/check-translations.sh`). Тест T2 сверяет реестр с директивами.
#   * `HEURISTIC_LITERALS` — ДЕТЕКТОРЫ НАМЕРЕНИЯ в свободной прозе (стеммы, регистронезависимо):
#     автор их дословно не пишет, EN-канон их не несёт и нести не обязан ⇒ директив у них нет.
#   * Тест T1 (AST-обход этого файла) не даёт завести кириллическую сверку МИМО обоих реестров —
#     ровно так выпал `план закрыт` (H3: инлайн-строка без константы, гейт литералов к ней слеп).
# Диагностические сообщения (`diag.error`/`diag.warning`) — НЕ литералы сверки: они не грепаются
# по тексту плана, в реестр не входят. `EMPTY_PLACEHOLDER` («—») сверяется, но директиву не
# получает (H13: em dash есть в любом EN-тексте — контракта такая директива не даёт).
LITERAL_PLAN_CLOSED = "план закрыт"  # форма `Next` целиком закрытого плана (SKILL §8)
LITERAL_PHASE_HANDOFF_STALE = "> УСТАРЕЛ — фаза реопенена"  # маркер инвалидации (SKILL §3, D34)
# --- scope-payload launch-block'а, несущего находки (SKILL §8, D-канон 2026-07-17) ---
# Вердикт блока `## Audit Pn`: значения латиницей (RED/ATTENTION/GREEN) — переводу не
# подлежат by nature, директив не требуют; кириллична только сама шапка поля.
LITERAL_AUDIT_VERDICT = "Вердикт:"
AUDIT_VERDICT_RE = re.compile(LITERAL_AUDIT_VERDICT + r"\s*\**\s*(RED|ATTENTION|GREEN)\b")
# Вердикты, чей launch-block ПЕРЕДАЁТ находки следующей сессии ⇒ обязан нести scope-payload.
# GREEN находок не несёт — с него payload не требуем (иначе маркеры выродятся в ритуал).
AUDIT_FINDINGS_VERDICTS = ("RED", "ATTENTION")
# Четыре обязательные строки payload'а. Порядок в каноне фиксирован, гейт проверяет
# ПРИСУТСТВИЕ (содержательность `СКОУП:`/`НЕ ТРОГАТЬ:` машина не меряет — это report-quality).
SCOPE_PAYLOAD_MARKERS = ("РЕЖИМ:", "ВХОД:", "СКОУП:", "НЕ ТРОГАТЬ:")
CANON_LITERALS = (
    "Поле | Значение",                                        # шапка Meta (plan.md §0)
    "Items 🟢/всего",                                          # колонка Status Board (§4)
    "D# | Дата | Решение | Почему",                           # шапка Decision Log (§5)
    "Дата | Кто (role/model) | Что",                          # шапка Update Log (§6)
    "Контракт | Версия | Статус | Потребители | Уведомлены",   # шапка Contracts/Exported (§7)
    "Контракт | Донор-план | Pinned | Замечено | Реакция",     # шапка Contracts/Consumed (§7)
    "> СКЕЛЕТ — не детализирован",                            # маркер фазы-скелета (§5)
    MANUAL_RUN_MARKER,                                        # «ЗАПУСК ВРУЧНУЮ» — Exec=manual (§9)
    "[NEEDS CLARIFICATION",                                   # маркер неоднозначности (§7)
    "RAG:✅",                                                  # enum RAG-маркеров (§7, D29)
    "RAG:" + EMPTY_PLACEHOLDER,
    "[UNVERIFIED]",
    LITERAL_PLAN_CLOSED,
    LITERAL_PHASE_HANDOFF_STALE,
    LITERAL_WAITING,                                          # форма `Next` «ОЖИДАНИЕ» (SKILL §8, D8)
    LITERAL_AUDIT_VERDICT,                                    # шапка вердикта `## Audit Pn` (§8)
    *SCOPE_PAYLOAD_MARKERS,                                   # scope-payload launch-block'а (§8)
    "pre_mutation:",                                          # write-site код границы (§8, 2026.07.24-AGENT-RELIABILITY P4.4/D91)
    "pre_final:",                                             # write-site код границы (§8, P4.4/D91)
    "write-site:",                                            # каноническая строка (§8, 2026.07.25-ECO-OPT P10.1/D102:
                                                               # T1 латиницу не ловит, регистрация решением)
    CLOSURE_META_FIELD,                                       # Meta-поле активации отчёта закрытия
                                                               # (§8, 2026.07.25-ECO-OPT P8.1/D42: латиница — та же
                                                               # регистрация решением, что у write-site:)
    CONSEQUENCES_LITERAL,                                     # §6, 2026.07.25-ECO-OPT P8.2/D103-D105: латиница — та же
                                                               # регистрация решением, T1 её не ловит
    RESUME_LITERAL,                                           # §6, 2026.07.25-ECO-OPT P8.3/D44: кириллица — обязательна
                                                               # i18n-директива в SKILL.ru.md
    "Команда",                                                # строка таблицы launch-block'а (§8, P5.8/LAUNCH_COMMAND_ROW_RE)
)
# --- 2026.07.15-PLANFLOW-UX P2.1/D8: C2-детектор прозы-оговорки в объявлении `Next` (WARNING) ----------
# Автор пишет runnable slash-форму «команда есть, но не сейчас» вместо структурной формы
# «ОЖИДАНИЕ: <условие> → <целевая форма>» (recon §3.2, живой SKM-MASTER-002). Стем-лист
# УЗКИЙ и финализирован по замеру ДЕЛЬТЫ флота (§8 D53), не «на глаз»: каждый лишний стем —
# риск ложного WARNING на сотнях handoff'ов (зеркало D34). Сканируется только СТРОКА-ОБЪЯВЛЕНИЕ
# (`next_decl`), НЕ весь launch-block: guard-строка `# НЕ раньше:` законно живёт в code-block'е.
C2_WAITING_STEMS = ("не раньше", "делать нечего", "тайм-гейт", "time-gate")
C2_WAITING_STEMS_RE = re.compile(
    "|".join(re.escape(s) for s in C2_WAITING_STEMS), re.IGNORECASE)
# Формы Next, несущие исполнимую slash-команду СЕЙЧАС (не waiting/manual/closed) — только на
# них C2 срабатывает: прозаическая оговорка при runnable-команде и есть анти-паттерн.
C2_RUNNABLE_KINDS = frozenset({"exec", "run", "design-item", "design-phase", "audit",
                               "audit-design", "close", "close-archive"})

# Якоря `--conflicts` (2026.07.31-SKM-LEAN P5.9) — грепаются в SKILL.ru.md (RU-ИСТОЧНИКЕ)
# САМИМ этим модулем, не в теле плана автором. Кириллические, поэтому T1
# (`test_canon_literals.py`) их ловит; в CANON_LITERALS (⇒ директива i18n-keep, EN-фиделити)
# не идут — «--conflicts» никогда не читает `SKILL.md`, EN-параллель ему не нужна ни для
# чего. Регистрация — ниже, в HEURISTIC_LITERALS, тем же основанием, что у
# `оркестрац`/`фаза закрыта`: детектор смысла в известном (нашем же) тексте, не
# канон-токен для стороннего автора.
CONFLICTS_ANCHOR_STATUSES = "РОВНО 6 канонических строк"
CONFLICTS_ANCHOR_ITEM_FIELDS = "`**Поле:** значение`, в этом порядке:"
CONFLICTS_ANCHOR_NEXT_FORMS = "| Форма Next | Когда |"
CONFLICTS_ANCHOR_CONTEXT = "РОВНО одно из трёх значений"
CONFLICTS_ANCHOR_LAUNCH_TABLE = "| Параметр | Значение |"

# Эвристики: `оркестрац`/`мультиагент` — детект заявленной оркестрации (ORCHESTRATION_MARKER_RE,
# D29); `PHASE_HANDOFF_CLOSURE_LITERALS` — детект «блок утверждает закрытие фазы» (D34);
# `PHASE_HANDOFF_NEGATION_LITERALS` — детект отрицания в том же утверждении (D50); C2-стемы
# (кириллические) — детект прозы-оговорки в `Next` (D8); CONFLICTS_ANCHOR_* — см. комментарий
# выше. Все группы ищут СМЫСЛ в прозе автора/канона, а не канонический токен для стороннего
# читателя ⇒ присутствие в EN не требуется (i18n-keep не нужен).
HEURISTIC_LITERALS = (("оркестрац", "мультиагент") + PHASE_HANDOFF_CLOSURE_LITERALS
                      + PHASE_HANDOFF_NEGATION_LITERALS
                      + ("не раньше", "делать нечего", "тайм-гейт")
                      + (CONFLICTS_ANCHOR_STATUSES, CONFLICTS_ANCHOR_ITEM_FIELDS,
                         CONFLICTS_ANCHOR_NEXT_FORMS, CONFLICTS_ANCHOR_CONTEXT,
                         CONFLICTS_ANCHOR_LAUNCH_TABLE)
                      # 2026.07.25-ECO-OPT P8.2/D103-D105: стемы CONSEQUENCES_STEMS_RE — детектор НАМЕРЕНИЯ
                      # (отмена/замена решения) в свободной прозе D-лога; EN-канон их не
                      # несёт и нести не обязан (research/23 §3).
                      + ("отменяет", "отменён", "отменен", "отменена", "отменено", "отменены"))


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


# --- Слой 0 «бриф» — обязательный вход плана (SKILL §16) ------------------------
# С этой даты (датовый PLAN-ID) отсутствие brief/ — ERROR; старее/legacy — WARNING
# (back-compat: существующие планы не ломаем, новые без брифа утверждение не проходят).
BRIEF_CANON_DATE = "2026.07.16"


def _lint_plan_brief_20(plan_dir, plan_id, diag):
    """brief/ — слой 0 «вход»: переформулированное без потери мыслей исходное
    сообщение владельца (00-brief.md) + дописываемые датированные уточнения.
    Задача: из плана видно «что было на входе → к чему пришли». План без brief/
    не проходит утверждение (SKILL §16)."""
    plan_dir = Path(plan_dir)
    brief_dir = plan_dir / "brief"
    has_md = brief_dir.is_dir() and any(
        f.is_file() and f.stat().st_size > 0 for f in brief_dir.glob("*.md"))
    if has_md:
        return
    msg = (f"нет слоя 0 «бриф»: {plan_dir.name}/brief/ с ≥1 непустым .md "
           f"(00-brief.md — переформулированный вход владельца, уточнения дописываются; "
           f"SKILL §16)")
    if PLAN_ID_DATED_RE.match(plan_id) and plan_id[:10] >= BRIEF_CANON_DATE:
        diag.error(plan_dir / "plan.md", None, msg)
    else:
        diag.warning(plan_dir / "plan.md", None, msg)


def _lint_plan_roadmap_20(plan_dir, plan_id, phase_files, diag):
    """roadmap.md обязателен, когда план полностью детализирован (нет скелет-маркеров
    ни в одной фазе) — SKILL §8: исполнение идёт батчами по исполнительской карте,
    а не поштучным бэбиситтингом. Severity как у brief-гейта: датовые планы от
    BRIEF_CANON_DATE — ERROR, старее/legacy — WARNING."""
    plan_dir = Path(plan_dir)
    if not phase_files:
        return
    for path in phase_files.values():
        try:
            text = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if any(SKELETON_MARKER_RE.match(ln) for ln in text.splitlines()):
            return  # есть скелеты — план ещё в авторинге, roadmap не требуется
    rm = plan_dir / "roadmap.md"
    if rm.is_file() and rm.stat().st_size > 0:
        return
    msg = (f"план полностью детализирован (скелет-маркеров нет), а {plan_dir.name}/roadmap.md "
           f"отсутствует — исполнительская карта обязательна (SKILL §8)")
    if PLAN_ID_DATED_RE.match(plan_id) and plan_id[:10] >= BRIEF_CANON_DATE:
        diag.error(plan_dir / "plan.md", None, msg)
    else:
        diag.warning(plan_dir / "plan.md", None, msg)


# --- Слой журнала/индекса (2026.07.18-FOREMAN P1.4/D22) — soft/hard-гейт по дате-cutoff ------------
# Датовые планы ОТ этой даты обязаны нести валидный journal.jsonl (ERROR); старее/
# legacy — WARNING (тот же паттерн, что у brief/roadmap-гейтов, back-compat — не ломаем
# уже идущий флот). Cutoff = дата запечатывания этого канона (P1.4/D47): план
# 2026.07.18-FOREMAN сам датовый от этой даты — обязан бэкфиллить свой journal.jsonl
# ДО коммита этой правки, иначе первым же ловит собственный ERROR-гейт.
JOURNAL_CANON_DATE = "2026.07.18"


def _lint_journal_exceptions_20(plan_dir, plan_id, report):
    """Валидирует optional append-only sidecar historical schema exceptions.

    Возвращает ``target_line -> exception`` только для полностью валидных записей.
    Sidecar не является журналом событий и конструктивно не может образовать
    correction-цикл: его target всегда строка отдельного ``journal.jsonl``.
    """
    exceptions_path = Path(plan_dir) / _journal.EXCEPTIONS_FILENAME
    if not exceptions_path.is_file():
        return {}
    try:
        lines = exceptions_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        report(exceptions_path, None, "journal exceptions sidecar не читается (кодировка/IO)")
        return {}
    if not any(line.strip() for line in lines):
        report(exceptions_path, None, "journal exceptions sidecar пуст")
        return {}

    by_target = {}
    for i, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            exception = json.loads(raw)
        except json.JSONDecodeError as exc:
            report(exceptions_path, i,
                   f"строка не валидный JSON (append-only exception NDJSON): {exc}")
            continue
        try:
            _journal.validate_exception_target(
                plan_dir, exception, check_duplicate=False)
        except _journal.JournalValidationError as exc:
            report(exceptions_path, i, f"schema exception не проходит контракт: {exc}")
            continue

        target_line = exception["target_line"]
        if target_line in by_target:
            report(exceptions_path, i,
                   f"duplicate schema exception для journal.jsonl:{target_line}")
            continue
        by_target[target_line] = exception
    return by_target


def _lint_plan_journal_20(plan_dir, plan_id, diag):
    """journal.jsonl (2026.07.18-FOREMAN P1.1, root/contracts/plan-journal-schema.md) — append-only NDJSON,
    одна запись на исполнение item'а любым запуском `/task:plan-*`. Отсутствие/пустой/
    невалидный файл — ERROR для датовых планов от JOURNAL_CANON_DATE, WARNING для
    старее/legacy. Схема записи реюзается из `task.journal` (SSOT — не дублируем enum'ы)."""
    plan_dir = Path(plan_dir)
    jf = plan_dir / _journal.FILENAME
    is_dated_new = bool(PLAN_ID_DATED_RE.match(plan_id)) and plan_id[:10] >= JOURNAL_CANON_DATE
    report = diag.error if is_dated_new else diag.warning

    if not jf.is_file() or jf.stat().st_size == 0:
        report(plan_dir / "plan.md", None,
               f"нет {plan_dir.name}/{_journal.FILENAME} (append-only история "
               f"исполнения, P1.1) или файл пуст — пишется close-протоколом "
               f"/task:plan-* (lib/task/journal.py)")
        return

    try:
        lines = jf.read_text(encoding="utf-8").split("\n")
    except (OSError, UnicodeDecodeError):
        report(jf, None, "journal.jsonl не читается (кодировка/IO)")
        return

    exceptions = _lint_journal_exceptions_20(plan_dir, plan_id, report)

    for i, ln in enumerate(lines):
        if not ln.strip():
            continue
        try:
            entry = json.loads(ln)
        except json.JSONDecodeError as e:
            report(jf, i + 1, f"строка не валидный JSON (append-only NDJSON, §1): {e}")
            continue
        if isinstance(entry, dict) and entry.get("plan_id") != plan_id:
            report(
                jf,
                i + 1,
                f"event plan_id «{entry.get('plan_id')}» ≠ canonical plan directory "
                f"«{plan_id}»; mismatch не допускает schema exception",
            )
        errors = _journal.entry_validation_errors(entry)
        if errors and i + 1 not in exceptions:
            message = "; ".join(error for _, error in errors)
            report(jf, i + 1, f"запись не проходит схему P1.1: {message}")


def _lint_plan_index_20(plan_dir, plan_id, diag):
    """index.md (2026.07.18-FOREMAN P1.2, root/contracts/plan-index-schema.md) — карта файлов+провенанс,
    ОПЦИОНАЛЕН (не носитель факта, в отличие от журнала/брифа — P1.2 §1). Отсутствие —
    ВСЕГДА WARNING, независимо от даты плана (нет ERROR-ветки в отличие от журнала)."""
    plan_dir = Path(plan_dir)
    idx = plan_dir / "index.md"
    if not idx.is_file() or idx.stat().st_size == 0:
        diag.warning(plan_dir / "plan.md", None,
                     f"нет {plan_dir.name}/index.md (карта файлов + провенанс "
                     f"findings/research→фаза, P1.2, опционален) — снипет "
                     f"snippets/index-template.md")


# --- 2026.07.10-SKM-ROADMAP-005 P4.3 warning-проверки: ID / workflow-скрипты / supersedes (D24/D27/D28) ----

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
        if js.name == DEV_LOOP_EXEMPT_NAME:
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

    # --- 2026.07.13-PLAN-PROTOCOL-GAP P3.8/D52: регион ОБОИХ грепов по фазе — до первого `## Audit` (append-блок
    # аудита законно цитирует маркеры, по которым отчитывается; см. AUDIT_BLOCK_HEADER_RE)
    gate_lines = _lines_before_audit(lines)

    # --- 2.0: маркеры [NEEDS CLARIFICATION] — линуются в lint_plan по статусу фазы
    needs_clarification = [i + 1 for i, ln in enumerate(gate_lines)
                           if NEEDS_CLARIFICATION_RE.search(ln)]

    # --- 2026.07.10-SKM-ROADMAP-005 P4.6: заявляет ли фаза оркестрацию (грепаемый признак, D29) — линуется
    # в lint_plan (workflow-как-DoR: фаза с оркестрацией без workflow-скрипта = warning)
    declares_orchestration = any(ORCHESTRATION_MARKER_RE.search(ln) for ln in gate_lines)

    items = {}
    for item_id, title, header_lineno, body_lines, body_start in _find_items(lines):
        prefix_m = PHASE_TOKEN_RE.match(item_id.split(".")[0])
        if prefix_m and item_id.split(".")[0] != phase_id:
            diag.error(path, header_lineno,
                       f"item {item_id}: префикс «{item_id.split('.')[0]}» не совпадает "
                       f"с файлом фазы «{phase_id}»")
        fields, dup_fields = _parse_fields(body_lines, body_start, FIELD_RE)
        for f in REQUIRED_ITEM_FIELDS:
            if f not in fields:
                diag.error(path, header_lineno,
                           f"item {item_id}: нет обязательного поля «{f}» (item фазы-скелета "
                           f"обязан нести все 16 полей со значением «—»; детализация — "
                           f"/task:plan-design <ID> {phase_id})")

        # --- D90: повтор поля в теле item'а — последнее вхождение молча подменяет
        # раннее легитимное значение (у linter'а И у task_contract) --------------
        for name, first_ln, first_val, dup_ln, dup_val in dup_fields:
            if name in REQUIRED_ITEM_FIELDS:
                diag.error(path, dup_ln,
                           f"item {item_id}: поле «{name}» встречается повторно "
                           f"(первое {path.name}:{first_ln} → «{_preview(first_val)}», "
                           f"повтор {path.name}:{dup_ln} → «{_preview(dup_val)}») — плановый "
                           f"парсер и task_contract молча берут ПОСЛЕДНЕЕ вхождение (D90): "
                           f"строка `**{name}:**` внутри прозы другого поля (например, "
                           f"Completion Notes) подменяет собой приёмочное значение — уберите "
                           f"звёздочки/двоеточие у инлайн-упоминания или перенесите его в "
                           f"свободный текст без формы поля")

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
    handoff_first_line = ""
    if handoff_body is None:
        diag.error(path, None, "нет секции «## Phase Handoff»")
        handoff_text = None
        handoff_lineno = None
    else:
        handoff_text = "\n".join(handoff_body).strip()
        handoff_lineno = handoff_start - 1  # строка самого заголовка «## Phase Handoff»
        # 2026.07.13-PLAN-PROTOCOL-GAP P2.15/D34: маркер инвалидации — ПЕРВАЯ непустая строка блока (линуется в lint_plan);
        # 2026.07.13-PLAN-PROTOCOL-GAP P3.7/D50: по ней же судит предикат «блок утверждает закрытие фазы» (субъект, не слово)
        handoff_first_line = next((ln for ln in handoff_body if ln.strip()), "").strip()
        handoff_stale = bool(PHASE_HANDOFF_STALE_RE.match(handoff_first_line))

    return {"status_table": status_table, "items": items, "phase_handoff": handoff_text,
            "phase_handoff_stale": handoff_stale, "phase_handoff_lineno": handoff_lineno,
            "phase_handoff_first_line": handoff_first_line,
            "is_skeleton": is_skeleton, "needs_clarification": needs_clarification,
            "declares_orchestration": declares_orchestration}


def _resolve_next_form(text):
    """Резолвит форму `Next` из enum'а §8 в тексте: `(kind, match)` либо `(None, None)`.

    Порядок — от специфичной формы к общей; первая сматчившая определяет проверку ссылок,
    остальные не пробуются (D4). «план закрыт» проверяется СРАЗУ после plan-exec (а не
    среди прочих regex-форм): это цельное утверждение о состоянии плана, а не slash-команда
    — Next закрытого плана иногда УПОМИНАЕТ следующую команду прозой («… решает владелец:
    `/task:plan-close archive <ID>` либо …», см. EDUFY-2), и эта проза не должна
    перехватывать резолвер. Manual-маркер — последним: у формы нет ссылок, она резолвится
    лишь тем, что ни одна slash-форма не объявлена.

    Форма «ОЖИДАНИЕ» (D8) — ПЕРВОЙ, ДО plan-exec: её строка-объявление embed'ит целевой
    `/task:plan-exec` (запустится по снятии гейта), который иначе перехватил бы резолвер как
    `exec` — зеркало того, почему «план закрыт» стоит сразу после exec.
    """
    semantic = SEMANTIC_NEXT_RE.match(text.strip())
    if semantic:
        semantic_kind, payload = semantic.groups()
        if semantic_kind == "terminal":
            return ("closed", None) if LITERAL_PLAN_CLOSED in payload.lower() else (
                "invalid-semantic", None)
        if semantic_kind == "manual":
            return "manual", None
        if semantic_kind == "waiting":
            return "waiting", None
        expected_command, expected_kind = SEMANTIC_NEXT_COMMANDS[semantic_kind]
        command, separator, arguments = payload.partition(" ")
        if command != expected_command or not separator:
            return "invalid-semantic", None
        legacy_kind, match = _resolve_next_form("/" + command + " " + arguments)
        return (legacy_kind, match) if legacy_kind == expected_kind else (
            "invalid-semantic", None)
    if LITERAL_WAITING in text:
        return "waiting", None
    m = PLAN_EXEC_RE.search(text)
    if m:
        return "exec", m
    m = PLAN_RUN_RE.search(text)
    if m:
        return "run", m
    if LITERAL_PLAN_CLOSED in text.lower():
        return "closed", None
    for kind, rx in (("design-item", PLAN_DESIGN_ITEM_RE),
                     ("design-phase", PLAN_DESIGN_PHASE_RE),
                     ("audit-design", PLAN_AUDIT_DESIGN_RE),
                     ("audit", PLAN_AUDIT_RE),
                     ("close-archive", PLAN_CLOSE_ARCHIVE_RE),
                     ("close", PLAN_CLOSE_RE)):
        m = rx.search(text)
        if m:
            return kind, m
    if MANUAL_RUN_MARKER in text:
        return "manual", None
    return None, None


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
    # handoff-поля вне Scope 2026.07.31-SKM-LEAN P5.9 (D90 — только REQUIRED_ITEM_FIELDS
    # items'ов) — duplicates осознанно отброшены, не диагностируются здесь.
    fields, _dup_handoff_fields = _parse_fields(lines[body_start - 1:], body_start, FIELD_RE)
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

    # 2026.07.10-SKM-ROADMAP-005 P4.3: warning-проверки идентичности (ID / workflow-скрипты / supersedes) — D24/D27/D28.
    # meta здесь — сырой dict[name]=(value,lineno) до маппинга в модель ниже.
    _meta_raw = meta if isinstance(meta, dict) else {}
    _lint_plan_identity_20(plan_dir, plan_id, _meta_raw, plan_md, diag)

    # Слой 0 «бриф» обязателен (SKILL §16): новые датовые планы — ERROR, старые — WARNING.
    _lint_plan_brief_20(plan_dir, plan_id, diag)

    # m7/D10: опциональная секция `## 7. Contracts` (нет секции — пустая модель, молча).
    plan_lines = _read_lines(plan_md)
    contracts = (parse_contracts(plan_lines, plan_md, diag) if plan_lines is not None
                 else {"exported": [], "consumed": []})

    # 2026.07.25-ECO-OPT P8.2/D103-D105: `Consequences` в D-записи (opt-in `Closure Protocol | v1` + forward-only).
    if plan_lines is not None:
        _lint_consequences_82(plan_dir, plan_id, _meta_raw, plan_lines, plan_md, diag)

    phase_files = {}  # phase_id -> Path
    try:
        phase_files = plan_layout.phase_paths(plan_dir)
    except plan_layout.PlanLayoutError as exc:
        diag.error(plan_md, None, str(exc))
    board_phase_ids = set()
    if status_board:
        board_phase_ids = {row.get("Phase") for row, _ in status_board if row.get("Phase")}

    # Roadmap-гейт (SKILL §8): полностью детализированный план обязан нести roadmap.md.
    _lint_plan_roadmap_20(plan_dir, plan_id, phase_files, diag)

    # Журнал/индекс (2026.07.18-FOREMAN P1.4/D22): journal.jsonl soft/hard по дате-cutoff, index.md WARNING-only.
    _lint_plan_journal_20(plan_dir, plan_id, diag)
    _lint_plan_index_20(plan_dir, plan_id, diag)

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
        # Блоки `## Audit Pn` исключены из грепов фазы (_lines_before_audit) — свой гейт.
        phase_lines = _read_lines(path)
        if phase_lines:
            _lint_audit_scope_payload(phase_lines, path, plan_id, diag)
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

        # --- 2026.07.24-AGENT-RELIABILITY P4.4/D91: гейт напечатанных кодов границ pre_mutation/pre_final --
        _lint_write_site_codes_44(parsed["status_table"], parsed["items"], path, diag)

        # --- 2026.07.25-ECO-OPT P8.3/D44: 🔴/⛔ обязаны нести `Возобновление:` (opt-in Closure Protocol) --
        _lint_checkpointed_83(_meta_raw, parsed["items"], path, diag)

    # --- 2026.07.24-AGENT-RELIABILITY P2.2/D26/D47: tiered-portability (committed-bundle плана без committed
    # execution input, либо внешний путь в роли execution input) ----------------
    _lint_tiered_portability_22(plan_dir, plan_id, all_items, phases, diag)

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

        # --- 2026.07.10-SKM-ROADMAP-005 P4.6 WARNING: workflow-как-DoR (D29) — фаза со статусом 🟡+, ЗАЯВЛЯЮЩАЯ
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

        # --- 2026.07.13-PLAN-PROTOCOL-GAP P2.15/D34 WARNING: зеркальный гейт — фаза НЕтерминальна, а Phase Handoff
        # УТВЕРЖДАЕТ закрытие и не помечен маркером инвалидации (H2, SKILL §3, 4-й шаг).
        # WARNING, не ERROR: три плана флота (истинно-положительные, carve-out D34) иначе
        # получили бы недостижимый commit-гейт в ЧУЖИХ репозиториях.
        # 2026.07.13-PLAN-PROTOCOL-GAP P3.7/D50: утверждение о закрытии ФАЗЫ читается по ПЕРВОЙ НЕПУСТОЙ СТРОКЕ блока и
        # снимается ОТРИЦАНИЕМ на ней же — иначе гейт ловит слово, а не субъект (J1).
        elif phase_status and phase_status not in TERMINAL_STATUSES:
            handoff_text = phases[pid].get("phase_handoff")
            claim_line = phases[pid].get("phase_handoff_first_line") or ""
            if (handoff_text and not _is_empty(handoff_text)
                    and PHASE_HANDOFF_CLOSURE_RE.search(claim_line)
                    and not PHASE_HANDOFF_NEGATION_RE.search(claim_line)
                    and not phases[pid].get("phase_handoff_stale")):
                diag.warning(phases[pid]["path"], phases[pid].get("phase_handoff_lineno"),
                             f"Phase Handoff протух: фаза {pid} НЕ закрыта (статус "
                             f"«{phase_status}»), а блок утверждает закрытие фазы — поставь "
                             f"его первой строкой маркер «> УСТАРЕЛ — фаза реопенена <D#>» "
                             f"(SKILL §3, 4-й шаг реопена: блок не удаляется, его перезапишет "
                             f"plan-close при следующем закрытии фазы)")

    # --- 2026.07.25-ECO-OPT P8.1/D42: отчёт закрытия фазы (opt-in `Closure Protocol | v1`) ----------
    _lint_closure_reports_81(plan_dir, plan_id, _meta_raw, phases, board_by_phase, diag)

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

    # 2026.07.25-ECO-OPT P11.3/D129: handoff.md ↔ Status Board «Pn a/b» — вне `if handoff:`
    # блока Next-резолвера ниже (независимая проверка, форма-нейтральна к Next).
    _lint_handoff_board_113(handoff, handoff_path, plan_id, board_by_phase, diag)

    if handoff:
        next_val, next_lineno = handoff["fields"].get("Next", ("", None))

        # Заголовок (D30/D37) — ссылка обязана резолвиться, иначе расширение regex'а просто
        # «разрешило всё»: у ОБЕИХ форм (`after Pn` — фаза, `after Pn.m` — item) гейтится
        # существование ФАЗЫ `Pn`. Исключение — bootstrap `P0.0` (замер флота: единственное
        # попадание item-формы — стартовый handoff, не дефект). Существование самого ITEM'а
        # `Pn.m` НЕ гейтится: 12 планов флота несут `after P0.0` (плана ещё не касались,
        # item'а P0.0 не бывает) — гейт на неё = новые ERROR флоту, back-compat запрещает.
        # Оракул «фаза существует» — ОБЪЕДИНЕНИЕ Status Board и файлов фаз (D41): это гейт
        # висячей ССЫЛКИ, а рассинхрон board↔файлы — отдельный дефект со своей диагностикой
        # («фаза Pn есть в Status Board, но нет phases/Pn.md»), дублировать её здесь нечем.
        known_phases = set(phases) | set(board_by_phase)
        title_ref = handoff.get("title_ref")
        if title_ref and title_ref != HANDOFF_TITLE_BOOTSTRAP:
            title_phase = title_ref.split(".", 1)[0]
            if title_phase not in known_phases:
                diag.error(handoff_path, handoff.get("title_lineno"),
                           f"заголовок: фаза «{title_phase}» не существует в плане")

        # ФОРМА `Next` ОБЪЯВЛЯЕТСЯ ПЕРВОЙ НЕПУСТОЙ СТРОКОЙ поля (D40). Само поле
        # МНОГОСТРОЧНОЕ: ниже идёт launch-block (таблица Model/Thinking/Context/Суть +
        # code-block), и его проза законно ЦИТИРУЕТ другие формы enum'а — голый промпт
        # item'а, чинящего сам протокол, называет и slash-команды, и «план закрыт».
        # Резолв по ВСЕМУ полю принимал такую цитату за объявление: handoff с «ЗАПУСК
        # ВРУЧНУЮ» в первой строке ловил ложный ERROR «не все items терминальны».
        next_decl = next((ln for ln in next_val.splitlines() if ln.strip()), "")
        kind, m = _resolve_next_form(next_decl)
        if kind is None:
            # Строка-объявление не назвала формы — back-compat: планы флота, у которых
            # первая строка прозаическая, а команда живёт в launch-block'е, читаются как
            # прежде (резолв по всему полю).
            kind, m = _resolve_next_form(next_val)

        # --- C2 (D8): прозаическая gate-оговорка при runnable-форме → WARNING ------
        # Автор вписал в объявление runnable slash-форму «команда есть, но не сейчас»
        # (стем «не раньше»/«делать нечего»/time-gate) вместо структурной формы «ОЖИДАНИЕ».
        # Скан — только СТРОКА-ОБЪЯВЛЕНИЕ (`next_decl`): guard-строка `# НЕ раньше:` формы
        # «ОЖИДАНИЕ» законно живёт в code-block'е и не должна триггерить C2 (форма waiting
        # к тому же не входит в C2_RUNNABLE_KINDS). Уровень — WARNING (механизм молод, D20).
        if kind in C2_RUNNABLE_KINDS and C2_WAITING_STEMS_RE.search(next_decl):
            diag.warning(handoff_path, next_lineno,
                         "Next: runnable-форма несёт прозу-оговорку о неисполнимости сейчас "
                         "(«не раньше»/«делать нечего»/time-gate) — если шаг реален, но "
                         "заблокирован временем/гейтом, объяви форму «ОЖИДАНИЕ: <условие> → "
                         "<целевая форма>» (SKILL §8): она копипастится с guard-строкой "
                         "`# НЕ раньше:`, прозаическая оговорка — нет")

        # --- 2.0: launch-block в handoff.Next (SKILL §8) --------------------------
        # Severity как у brief-гейта: датовые планы от BRIEF_CANON_DATE — ERROR
        # (владелец не должен переспрашивать модель/настройки), старее/legacy — WARNING.
        # Таблица `| Model | …`, строка `| Команда |` и code-block грепаются по всему
        # файлу: шаблон кладёт launch-block продолжением Next, но точное место не гейтим
        # (warning-уровень).
        # Для целиком закрытого плана («план закрыт») запускать нечего — не требуем.
        # Условие СОЗНАТЕЛЬНО мягче резолвера (`kind`): любое утверждение о закрытии в
        # ЛЮБОМ месте поля снимает требование launch-block'а. Ужесточение до `kind` дало бы
        # новый WARNING живому плану флота (PILOT-AZG: первая строка несёт и «план закрыт
        # целиком», и lint-ссылку `/task:plan-exec` → резолвится как exec) — back-compat §2.
        #
        # P5.8: команда теперь либо строка `| Команда |` В ТОЙ ЖЕ таблице, либо
        # code-block ниже — «ровно один из двух» = ХОТЯ БЫ ОДИН, не «строго не оба»:
        # план, несущий и строку, и code-block (back-compat старой формы, либо
        # manual/scope-payload/ОЖИДАНИЕ item, которому code-block нужен по канону §8
        # независимо от строки), гейтом не наказывается — «ровно один из двух» описывает
        # МИНИМУМ носителя команды, а не запрет на оба сразу (SKILL §8, snippets/
        # launch-block-template.md). Решение зафиксировано тестом (test_plan_lint.py).
        if LITERAL_PLAN_CLOSED not in next_val.lower():
            has_table = any(LAUNCH_TABLE_ROW_RE.match(ln) for ln in handoff["lines"])
            has_command_row = any(LAUNCH_COMMAND_ROW_RE.match(ln) for ln in handoff["lines"])
            has_fence = any(CODE_FENCE_RE.match(ln) for ln in handoff["lines"])
            if not (has_table and (has_command_row or has_fence)):
                missing = []
                if not has_table:
                    missing.append("таблицы `| Model | …`")
                if not (has_command_row or has_fence):
                    missing.append("строки `| Команда |` в таблице или code-block'а с командой")
                _lb_msg = ("Next без launch-block: нет " + " и ".join(missing) +
                           " (форма — snippets/launch-block-template.md)")
                if PLAN_ID_DATED_RE.match(plan_id) and plan_id[:10] >= BRIEF_CANON_DATE:
                    diag.error(handoff_path, next_lineno, _lb_msg)
                else:
                    diag.warning(handoff_path, next_lineno, _lb_msg)
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

        if kind == "manual":
            pass  # «ЗАПУСК ВРУЧНУЮ: <model/effort>» — форма без slash-команды, ссылок нет
        elif kind == "waiting":
            pass  # «ОЖИДАНИЕ: <условие> → <целевая форма>» (D8): целевая команда guarded в
                  # launch-block'е; ссылки объявления не резолвим (целевая форма проверится
                  # при реальном запуске по снятии гейта). launch-block требуется — как у
                  # прочих runnable-форм (не exempt): гейт launch-block выше не смотрит kind.
        elif kind == "exec":
            ref_plan_id, ref_item = m.group(1), m.group(2)
            _check_plan_id(ref_plan_id)
            _check_item(ref_item)
        elif kind == "run":
            ref_plan_id, ref_from, ref_to = m.group(1), m.group(2), m.group(3)
            _check_plan_id(ref_plan_id)
            _check_item(ref_from)
            if ref_to:
                _check_item(ref_to)
        elif kind == "audit-design":
            _check_plan_id(m.group(1))
        elif kind == "closed":
            if not plan_closed:
                diag.error(handoff_path, next_lineno,
                           "Next: «план закрыт», но не все items терминальны")
        elif kind == "design-item":
            ref_plan_id, ref_item = m.group(1), m.group(2)
            _check_plan_id(ref_plan_id)
            _check_item(ref_item)
        elif kind == "design-phase":
            ref_plan_id, ref_phase = m.group(1), m.group(2)
            _check_plan_id(ref_plan_id)
            _check_phase(ref_phase)
        elif kind == "audit":
            ref_plan_id, ref_phase = m.group(1), m.group(2)
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
        elif kind == "close-archive":
            _check_plan_id(m.group(1))
            if not plan_closed:
                diag.warning(handoff_path, next_lineno,
                             "Next: /task:plan-close archive — план ещё не терминален целиком")
        elif kind == "close":
            ref_plan_id, ref_phase, ref_suffix = m.group(1), m.group(2), m.group(3)
            _check_plan_id(ref_plan_id)
            _check_phase(ref_phase)
            if ref_suffix:
                _check_item(ref_phase + ref_suffix)
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
        # Tooling caches/configuration are not executable-plan directories.  They
        # can be created by the validation run itself, so treating them as plans
        # makes the gate non-idempotent.
        if p.name.startswith(".") or p.name == "__pycache__":
            continue
        if p.name == ARCHIVE_DIR_NAME:
            dirs.extend(sorted(a for a in p.iterdir()
                               if a.is_dir() and not a.name.startswith(".")
                               and a.name != "__pycache__"))
            continue
        dirs.append(p)
    return dirs


# --- --conflicts: канон ↔ реализация (2026.07.31-SKM-LEAN P5.9, roadmap plan-audit-loop.md §A.1) -----
# Третья нога конфликт-скана — сверка `SKILL.ru.md` с реестрами-константами ЭТОГО модуля.
# Первые две ноги (свежесть перевода RU→EN, присутствие i18n-keep литералов в EN и в теле RU)
# уже покрыты `check-translations.sh` — не переиздаются здесь (Implementation Rule 2).
#
# Работает БЕЗ аргумента-плана (Implementation Rule 5): сверяет АРТЕФАКТЫ канона, не
# конкретный `plans/<ID>`. Каждая сверка — структурная (код-фенс/бэктик-спан/маркированный
# список — устойчивый якорь), не эвристический парс свободной прозы (Implementation Rule 3).
# Находка несёт ОБЕ стороны с `файл:строка` (Implementation Rule 4). `--conflicts` ничего не
# ОБЪЯВЛЯЕТ заново — сравнивает канон и уже существующие реестры `plan_lint.py`; единственное
# исключение — `CONTEXT_VALUES` (см. её комментарий выше), которую этот item вводит именно
# затем, чтобы для класса «значения Context» было ЧТО сравнивать (без неё сверка этого
# класса структурно невозможна — Scope Included этого item'а прямо требует её как одну из
# шести граней).

SKILL_RU_RELPATH = Path("packages/skiller/skills/general/plan-protocol/SKILL.ru.md")


def _find_skill_ru():
    """Канон-SSOT (`SKILL.ru.md`), от расположения ЭТОГО модуля вверх до корня монорепо —
    тот же приём, что `test_canon_literals.py::_find_skill_ru` (не дублируется: тест этого
    item'а импортирует функцию отсюда, см. Implementation Rules). Standalone-раскладка
    (пакет `task` вне монорепо) — `None`, не исключение: `run_conflicts_check` предупреждает
    и выходит зелёным (тот же класс деградации, что `core.term.warn`-фолбэк вверху модуля)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / SKILL_RU_RELPATH
        if candidate.is_file():
            return candidate
    return None


def _own_const_lineno(name):
    """Строка объявления `NAME = …` в исходнике ЭТОГО модуля (AST по собственному файлу) —
    self-referential приём `test_canon_literals.py`: `--conflicts` не заводит второй реестр
    «где что объявлено», читает у самого модуля."""
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"), filename=__file__)
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name):
            return node.lineno
    return None


def _fence_content(lines, open_idx):
    """Содержимое ``` fence, открытого на 0-индексной строке `open_idx`. Возвращает
    (content_lines, first_content_lineno) — 1-индексная строка первой строки внутри фенса."""
    content = []
    i = open_idx + 1
    while i < len(lines) and not CODE_FENCE_RE.match(lines[i]):
        content.append(lines[i])
        i += 1
    return content, open_idx + 2


def _find_line(lines, needle, start=0):
    """Индекс первой строки, содержащей `needle` (0-индексный), либо `None`."""
    for i in range(start, len(lines)):
        if needle in lines[i]:
            return i
    return None


NEXT_FORM_TABLE_ROW_RE = re.compile(r"^\|\s*([a-z-]+):")
CONTEXT_BULLET_RE = re.compile(r"^-\s+\*\*`([^`]+)`\*\*")


def _conflicts_statuses(skill_lines, skill_path, diag):
    """Класс 1/6: шесть канонических статусов (STATUSES) — SKILL.ru.md §6."""
    header_idx = _find_line(skill_lines, CONFLICTS_ANCHOR_STATUSES)
    if header_idx is None:
        diag.error(skill_path, None,
                   f"--conflicts статусы: не найден якорь «{CONFLICTS_ANCHOR_STATUSES}» "
                   "(SKILL.ru.md §6) — сверка невозможна")
        return
    fence_idx = _find_line(skill_lines, "```text", header_idx)
    if fence_idx is None:
        diag.error(skill_path, header_idx + 1,
                   "--conflicts статусы: код-фенс после якоря не найден")
        return
    content, content_lineno = _fence_content(skill_lines, fence_idx)
    canon_statuses = tuple(ln for ln in content if ln.strip())
    code_lineno = _own_const_lineno("STATUSES")
    if canon_statuses != STATUSES:
        diag.error(Path(__file__), code_lineno,
                   f"--conflicts статусы: канон {skill_path.name}:{content_lineno} = "
                   f"{canon_statuses!r} → реализация {Path(__file__).name}:{code_lineno} = "
                   f"{STATUSES!r}")


def _conflicts_item_fields(skill_lines, skill_path, diag):
    """Класс 2/6: 16 полей item'а и их порядок (REQUIRED_ITEM_FIELDS) — SKILL.ru.md §5."""
    anchor_idx = _find_line(skill_lines, CONFLICTS_ANCHOR_ITEM_FIELDS)
    if anchor_idx is None:
        diag.error(skill_path, None,
                   f"--conflicts 16-полей: не найден якорь «{CONFLICTS_ANCHOR_ITEM_FIELDS}» "
                   "(SKILL.ru.md §5)")
        return
    joined = " ".join(skill_lines[anchor_idx + 1:anchor_idx + 4])
    m = re.search(r"`([^`]+)`", joined)
    if not m:
        diag.error(skill_path, anchor_idx + 2,
                   "--conflicts 16-полей: бэктик-список после якоря не найден")
        return
    normalized = re.sub(r"\s+", " ", m.group(1)).strip()
    canon_fields = tuple(f.strip() for f in normalized.split(","))
    code_lineno = _own_const_lineno("REQUIRED_ITEM_FIELDS")
    if canon_fields != REQUIRED_ITEM_FIELDS:
        diag.error(Path(__file__), code_lineno,
                   f"--conflicts 16-полей: канон {skill_path.name}:{anchor_idx + 2} = "
                   f"{canon_fields!r} → реализация {Path(__file__).name}:{code_lineno} = "
                   f"{REQUIRED_ITEM_FIELDS!r}")


def _conflicts_next_forms(skill_lines, skill_path, diag):
    """Класс 3/6: закрытый enum форм `Next` — SKILL.ru.md §8 «Допустимые формы Next» ↔
    альтернация `SEMANTIC_NEXT_RE` (читается у неё самой — не переиздаётся вторым списком)."""
    header_idx = _find_line(skill_lines, CONFLICTS_ANCHOR_NEXT_FORMS)
    if header_idx is None:
        diag.error(skill_path, None,
                   f"--conflicts формы Next: не найдена шапка таблицы "
                   f"«{CONFLICTS_ANCHOR_NEXT_FORMS}»")
        return
    canon_forms = []
    canon_lineno = None
    i = header_idx + 1
    while i < len(skill_lines) and skill_lines[i].strip().startswith("|"):
        m = NEXT_FORM_TABLE_ROW_RE.match(skill_lines[i].strip())
        if m:
            if canon_lineno is None:
                canon_lineno = i + 1
            canon_forms.append(m.group(1))
        i += 1
    code_lineno = _own_const_lineno("SEMANTIC_NEXT_RE")
    gm = re.search(r"\^\((.*?)\):", SEMANTIC_NEXT_RE.pattern)
    code_forms = gm.group(1).split("|") if gm else []
    if tuple(canon_forms) != tuple(code_forms):
        diag.error(Path(__file__), code_lineno,
                   f"--conflicts формы Next: канон {skill_path.name}:{canon_lineno} = "
                   f"{canon_forms!r} → реализация {Path(__file__).name}:{code_lineno} = "
                   f"{tuple(code_forms)!r}")


def _conflicts_context_values(skill_lines, skill_path, diag):
    """Класс 4/6: три значения `Context` (CONTEXT_VALUES) — SKILL.ru.md §8 «Session-restart
    discipline». Единственный класс, где реализация ДО этого item'а не существовала вовсе
    (см. комментарий у `CONTEXT_VALUES`) — сверка новая, не переиздание старой."""
    anchor_idx = _find_line(skill_lines, CONFLICTS_ANCHOR_CONTEXT)
    if anchor_idx is None:
        diag.error(skill_path, None,
                   f"--conflicts Context: не найден якорь «{CONFLICTS_ANCHOR_CONTEXT}» "
                   "(SKILL.ru.md §8)")
        return
    canon_values = []
    canon_lineno = None
    for i in range(anchor_idx + 1, min(anchor_idx + 20, len(skill_lines))):
        m = CONTEXT_BULLET_RE.match(skill_lines[i])
        if m:
            if canon_lineno is None:
                canon_lineno = i + 1
            canon_values.append(m.group(1))
            if len(canon_values) == 3:
                break
    code_lineno = _own_const_lineno("CONTEXT_VALUES")
    if tuple(canon_values) != CONTEXT_VALUES:
        diag.error(Path(__file__), code_lineno,
                   f"--conflicts Context: канон {skill_path.name}:{canon_lineno} = "
                   f"{canon_values!r} → реализация {Path(__file__).name}:{code_lineno} = "
                   f"{CONTEXT_VALUES!r}")


def _conflicts_i18n_literals(skill_text, skill_lines, skill_path, diag):
    """Класс 5/6: литералы `i18n-keep` — CANON_LITERALS ⊆ директивы, объявленные в
    SKILL.ru.md (T2 `test_canon_literals.py` уже проверяет то же самое; здесь — тот же
    предикат, доступный из CLI без запуска unittest, Required Reads п. 4 «расширяется, не
    дублируется»: обе стороны читают один и тот же `CANON_LITERALS`/`I18N_KEEP_RE`)."""
    declared = set(I18N_KEEP_RE.findall(skill_text))
    code_lineno = _own_const_lineno("CANON_LITERALS")
    for lit in CANON_LITERALS:
        if lit in declared:
            continue
        found_idx = _find_line(skill_lines, lit)
        canon_ref = (f"{skill_path.name}:{found_idx + 1} (найден в теле, БЕЗ директивы "
                    f"`i18n-keep`)" if found_idx is not None
                    else f"{skill_path.name}: нигде не найден")
        diag.error(Path(__file__), code_lineno,
                   f"--conflicts i18n-keep: литерал «{lit}» — канон {canon_ref} → реализация "
                   f"{Path(__file__).name}:{code_lineno} несёт его в CANON_LITERALS без "
                   f"директивы `<!-- i18n-keep: {lit} -->`")


def _conflicts_launch_table_regex(skill_lines, skill_path, diag):
    """Класс 6/6: регекс-носители формы launch-block'а (LAUNCH_TABLE_ROW_RE/
    LAUNCH_COMMAND_ROW_RE) — обязаны матчить строки канон-таблицы SKILL.ru.md §8."""
    header_idx = _find_line(skill_lines, CONFLICTS_ANCHOR_LAUNCH_TABLE)
    if header_idx is None:
        diag.error(skill_path, None,
                   f"--conflicts launch-block регекс: не найдена шапка "
                   f"«{CONFLICTS_ANCHOR_LAUNCH_TABLE}»")
        return
    rows = []
    i = header_idx + 1
    while i < len(skill_lines) and skill_lines[i].strip().startswith("|"):
        rows.append((skill_lines[i], i + 1))
        i += 1
    checks = (("LAUNCH_TABLE_ROW_RE", LAUNCH_TABLE_ROW_RE, "Model class"),
             ("LAUNCH_COMMAND_ROW_RE", LAUNCH_COMMAND_ROW_RE, "Команда"))
    for const_name, pattern, label in checks:
        matched = any(pattern.match(row) for row, _ln in rows)
        if not matched:
            code_lineno = _own_const_lineno(const_name)
            diag.error(Path(__file__), code_lineno,
                       f"--conflicts launch-block регекс: {const_name} не матчит ни одну "
                       f"строку канон-таблицы {skill_path.name}:{header_idx + 2}-{i} "
                       f"(ожидалась строка «{label}») → реализация "
                       f"{Path(__file__).name}:{code_lineno}")


def run_conflicts_check(diag):
    """`--conflicts`: сверка канон↔реализация по шести классам (см. блок-докстринг выше),
    без плана на входе. Standalone-раскладка (SKILL.ru.md недоступен) — предупреждает и
    оставляет `diag` зелёным (та же деградация, что `test_canon_literals.py::skipTest`)."""
    skill_path = _find_skill_ru()
    if skill_path is None:
        # `print` напрямую, не `_core_warn` (T1 `test_canon_literals.py` иначе требует
        # регистрации этой прозы как грепаемого литерала — она им не является, это вывод
        # диагностики; `print` — задокументированное исключение T1, см. его же
        # `test_print_argument_is_not_a_grep_site`).
        print("WARN: --conflicts: standalone-раскладка — SKILL.ru.md (канон plan-protocol) "
             "не найден от расположения plan_lint.py вверх — сверка пропущена", file=sys.stderr)
        return
    skill_lines = _read_lines(skill_path)
    skill_text = skill_path.read_text(encoding="utf-8")
    _conflicts_statuses(skill_lines, skill_path, diag)
    _conflicts_item_fields(skill_lines, skill_path, diag)
    _conflicts_next_forms(skill_lines, skill_path, diag)
    _conflicts_context_values(skill_lines, skill_path, diag)
    _conflicts_i18n_literals(skill_text, skill_lines, skill_path, diag)
    _conflicts_launch_table_regex(skill_lines, skill_path, diag)


# --- --baseline: детерминированный счёт новых ошибок (2026.07.13-PLAN-PROTOCOL-GAP P1.2/B1/D5/D6) ---------

def _git_run(args, cwd, timeout=15):
    """`check=False`, перехватывает `FileNotFoundError`/таймаут — линтер обязан
    работать вне git-репо (гоняют по Brain-vault'у и чужим корням, 2026.07.13-PLAN-PROTOCOL-GAP P1.2 Implementation
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
    parser.add_argument("path", nargs="?", default=None,
                         help="путь к plans/<PLAN-ID> или к plans/ (необязателен при "
                              "--conflicts — та сверяет канон, не конкретный план)")
    parser.add_argument("--json", action="store_true",
                         help="вывести распарсенную модель (планы→фазы→items) в stdout как JSON")
    parser.add_argument("--baseline", nargs="?", const="HEAD", default=None, metavar="REF",
                         help="git-ref для счёта НОВЫХ ошибок от рабочего дерева (K, B1/D5/D6); "
                              "без значения — HEAD")
    parser.add_argument("--gate", choices=("all", "new"), default="all",
                         help="exit-код по всем диагностикам (all, дефолт — back-compat CI) "
                              "или только по новым от --baseline (new); при недоступном "
                              "baseline gate=new деградирует к all (красное не пропускается)")
    parser.add_argument("--conflicts", action="store_true",
                         help="сверка «канон (SKILL.ru.md) ↔ реализация (реестры этого "
                              "модуля)» без плана на входе (roadmap plan-audit-loop.md §A.1, "
                              "третья нога конфликт-скана); `path`, если передан, игнорируется")
    args = parser.parse_args(argv)

    if args.conflicts:
        diag = Diagnostics()
        run_conflicts_check(diag)
        for msg in diag.errors:
            print(f"ERROR: {msg}", file=sys.stderr)
        for msg in diag.warnings:
            _core_warn(msg)
        status = "OK" if diag.ok else "ПРОВАЛ"
        print(f"plan-lint --conflicts: {status} ({len(diag.errors)} расхождений, "
              f"{len(diag.warnings)} предупреждений)")
        return 0 if diag.ok else 1

    if args.path is None:
        parser.error("path обязателен без --conflicts")

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
