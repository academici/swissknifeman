# Recon-отчёт по репозиторию 2026-07-31 (слой 1)

**Слой 1.** Разведка субагентом (`Explore`, read-only) + прямые проверки автора плана,
2026-07-31, дерево `ebd42655` (`main`, чисто). Все числа — с якорями `file:line`.
Потребители: **все семь фаз**.

> Дисциплина: это сырьё. Синтез и целевые структуры — `research/`, решения — D-лог.

## 1. Измеритель `skiller budget --first-turn` (вход P1)

Единственный модуль — `packages/skiller/lib/skiller/budget.py` (927 строк).

| Поверхность | Якорь |
|:--|:--|
| CLI-обработчик | `budget.py:635` `cmd_budget`; флаг `budget.py:640`; ветка `:678–693` |
| Сборка отчёта | `budget.py:505` `first_turn_report(...)` |
| Формат вывода | `budget.py:534` `format_first_turn_report` |
| Пороги | `FIRST_TURN_TARGET_MAX = 7_000` `:193` · `FIRST_TURN_WARN = 10_000` `:194` |
| Лестница вердикта | `:525–530` (OK / ELEVATED / WARN); `--strict` падает только на WARN `:690–692` |

**Пять считаемых источников** (`budget.py:516–523`):

1. `_measure_skills` `:338` — листинг активного набора; `min(raw, context_window × fraction)`,
   кап записи **1 536 симв** (`_listing_entry_tokens` `:243`) — совпадает с апстрим-капом
   `description`+`when_to_use` (см. `rag-2026-07-31-native-skill-fields.md` §1);
2. `_measure_agents` `:361` — `.claude/agents/*.md`, только `name` + `description`;
3. `_measure_claude_md` `:378` — весь `CLAUDE.md` **+** `.claude/rules/*.md`,
   **исключая те, у которых во frontmatter есть `paths:`** (`:399–400`);
4. `_measure_hooks` `:458` — **живой прогон** команд `SessionStart` из `.claude/settings.json`
   (+ `settings.local.json`), таймаут `HOOK_TIMEOUT = 10` `:195`;
5. `_measure_mcp` `:476` — имена серверов из `.mcp.json` → статическая таблица
   `KNOWN_MCP_TOOLS` `:200–204` (11 серверов) × `TOKENS_PER_MCP_TOOL = 150` `:206`;
   неизвестный сервер → `FALLBACK_MCP_TOOLS = 5` `:205`. **Живых схем не читает** `:479–480`.

**Что НЕ считается (проверенные отсутствия):**

- marketplace/установленные **плагины** — кодового пути нет вовсе; расширение `budget.py`
  чтением `~/.claude/plugins/**` **отвергнуто** (`docs/rejected-optimizations.md`, D142;
  `plans/archive/2026.07.25-ECO-OPT/research/28-P7.3-redesign-2026-07-29.md:60`);
- slash-команды, output-styles, statusline;
- `.claude/rules/*.md` **с** `paths:` — намеренно (`:399`);
- хуки не-`SessionStart` (`:459`);
- реальные схемы MCP-инструментов (только оценка);
- пользовательский `~/.claude/CLAUDE.md`.

**Интеграции с `claude plugin details` в коде НЕТ.** Есть только проза-инструкция:
`CLAUDE.md:84` ← генератор `packages/harness/configs/common/instructions/root/claude-code.md:6`.
Замер прецедента: ~449 ток на один плагин
(`plans/archive/2026.07.25-ECO-OPT/findings/P7.3-plugin-cost-and-procedure.md:15,25`).

**Потребитель по флоту:** `packages/maind/lib/maind/doctor.py:128,152` — вызывает
`skiller budget --first-turn --target <p> --json` по каждому проекту (`doctor --context` `:193`).

**CI:** `packages/skiller/scripts/validate.sh:1286` гоняет только `--check-core --strict`,
**`--first-turn` в CI нет**.

**Тесты:** `packages/skiller/tests/test_budget_first_turn.py` (10 кейсов, класс `:27`),
`test_budget.py` (15), `test_budget_listing_providers.py` (13), `test_profile_listing_budget.py` (4);
флот — `packages/maind/tests/test_doctor.py:209,239`.

## 2. `packages/harness` (вход P4)

Раскладка: `bin/harness` (63 стр.), `lib/harness/` (20 модулей), `commands/` (6 md),
`configs/{claude-code,codex,common}/`, `tests/` (44 `test_*.py`), `docs/`, `scripts/`.
Каталога `skills/` в пакете **нет**.

Подкоманды — `packages/harness/lib/harness/cli.py:19–30` (`COMMANDS`):
`permissions` (алиас `apply`) · `mcp` · `hooks` · `router` · `agent-packs` · `safe-dirs` ·
`instructions` · `doctor` · `wf`. Bash-whitelist — `bin/harness:52`.

Корневой роутер: `bin/swissknifeman:47` — `env <args>` — **полный passthrough** в
`packages/harness/bin/harness`. Следовательно `swissknifeman env run …` требует ровно одного:
регистрации `run` в `COMMANDS` + whitelist.

**Драйвера/раннера/исполнителя планов в дереве НЕТ** — ни класса, ни функции
(`Executor`/`run_plan`/`execute_plan` встречаются только литералом в
`packages/task/tests/test_canon_literals.py`). Ближайшее: `lib/harness/wf_status.py` —
read-only парсер фоновых workflow-прогонов.

**Единственный кластер запуска `claude` процессом** — в skiller, не в harness:

- `packages/skiller/lib/skiller/quality/eval.py:377` `claude_bin()` (env `SKM_CLAUDE_BIN` `:53`);
- `:388` `build_run_cmd()` → `[claude, "-p", prompt, "--output-format", "json"]`
  + `--append-system-prompt` `:391–394`;
- `:414` `run_case(...)`, `DEFAULT_TIMEOUT = 180` `:49`; тесты с фейковым бинарём —
  `packages/skiller/tests/test_eval.py:244,486,508,524`.
- **Вызова `claude -p /task:…` (slash-команда как промпт) в дереве нет ни одного.**

## 3. `core/` (вход P6)

20 файлов плоским списком. Кластер `provider_*` — 7 файлов, **152 КБ**:

| Файл | Байт | `@dataclass` | Роль |
|:--|--:|--:|:--|
| `provider.py` | 8 686 | 9 | Неизменяемые доменные значения (`CapabilityId`, `ProviderId`, …) |
| `provider_config.py` | 11 445 | 5 | Резолв провайдер-конфига нейтральных носителей |
| `provider_manifest.py` | 27 170 | 6 | Парсер корневого манифеста + `provider_manifest_sha256` |
| `provider_artifact.py` | 17 994 | 6 | Чистые render-планы |
| `provider_lock.py` | 68 070 | 5 | Версионированный sidecar-lock, fail-closed plan/apply |
| `provider_registry.py` | 11 441 | 5 | `AdapterCatalog` / `AdapterDescriptor` / `AdapterSelection` |

Остальные: `__init__.py` (фасад, 16 ре-экспортных строк `:16–62`, `__all__` `:64`),
`block.py`, `cli.py`, `env.py`, `http.py`, `io.py`, `pathology.py` (16 729),
`paths.py`, `proc.py`, `project.py`, `repo.py`, `runs.py`, `term.py`, `text.py`,
`usage.py` (10 496; импортирует только stdlib, без `core.*`).

**Паттерн конфиг-объекта уже существует:** 38 объявлений `@dataclass` в `core/*.py` —
**все 38 `frozen=True`**. Вне provider-кластера: `core/env.py` (`BaseEnv`), `core/runs.py`.

`core/tests/` — плоский каталог, зеркало 1:1 `core/<mod>.py` → `core/tests/test_<mod>.py`
для 12 из 20 модулей. Без выделенного файла: `block`, `cli`, `env`, `http`, `paths`,
`proc`, `project`, `repo`, `term` (частично покрыты `test_core.py`).

## 4. Инвентарь скиллов (вход P3)

229 `SKILL.md` · 228 `SKILL.ru.md` · 48 бакетов.

**Использование нативных полей во frontmatter (не в теле):**

| Поле | Файлов |
|:--|--:|
| `allowed-tools` | **0** |
| `paths` | **0** — единственное вхождение грепа это ТЕКСТ ТЕЛА в `packages/skiller/skills/general/context-economy/SKILL.md:40` |
| `context` | **0** |
| `model` | **0** |
| `effort` | **0** |
| `disable-model-invocation` | **10** |
| `when_to_use` | **0** |

Десять с `disable-model-invocation`: `architect/codebase-design`, `architect/domain-modeling`,
`general/git-safety`, `general/grill-with-docs`, `general/implement`, `oss-dev/issue-triage`,
`oss-dev/resolving-merge-conflicts`, `oss-dev/to-issues`, `quality/diagnosing-bugs`,
`quality/tdd-discipline`.

**Описания:** `≥100` симв — **205 / 229**; длина min/median/max = **60 / 212 / 421**;
**кириллица в `description` — 0** (русский канон живёт в параллельных `SKILL.ru.md`,
`SKILL.md` — английский SSOT, раздаваемый клиентам).

Полная перепись ключей frontmatter: `name` 229 · `description` 229 · `version` 213 ·
`bucket` 213 · `adapters` 212 · `sha256` 212 · `risk`/`persona`/`tags`/`requires`/
`produces_for` 202 · `outputs` 200 · `snippets` 153 · `license` 30 · `metadata` 20 ·
`disable-model-invocation` 10 · `upstream` 8 · `level` 4 · `role_agent_pack` 4 ·
`author` 2 · `lifecycle` 2 · `compatibility` 1 · `filament_version` 1.

## 5. Вендоренные скиллы (вход P5)

Отдельного дерева `vendor/` нет — внешние скиллы лежат **на месте**, в
`packages/skiller/skills/<bucket>/<name>/`, помечены соседним `upstream.json`.

- **Количество — 56** файлов `upstream.json` (не 54, как в оценке брифа).
- Схема: `schema_version`, `source`, `repo`, `strategy` (`notify` / `replace` / `fork`),
  `license`, `files[]{path, url, sha256, fetched_at}`, опц. `body_path`, `notes`.
- Потребители: `packages/skiller/lib/skiller/registry.py:66–85` (провенанс в `skills.json`;
  битый JSON → `die` `:74`), `common.py:41` (`SKILL_IGNORE` — не копируется в проект),
  `vendor.py:214,291`, `packages/skiller/lib/skiller/quality/eval.py:973,978` (eval-стандарт — только к локальным),
  `packages/skiller/scripts/check-translations.sh:75` (внешние освобождены от RU-паритета).
- **Инструмент сверки sha256 существует:** `packages/skiller/scripts/update-upstreams.sh`
  (20 258 Б), режимы `--check` (дефолт, read-only) / `--apply` `:32–43,58`, коды выхода
  `:16–19` (10 = найден дрейф), `sha256_bytes()` `:97`, сравнение `:222–296`.
- **Чего НЕТ:** IOC/prompt-injection скана содержимого — только целостность байтов.

## 6. `configs/provider-capabilities.json` (вход P5)

- **Закоммичен, не gitignored** (`git ls-files configs/` → ровно этот файл), 48 917 Б.
- **Генератора у файла НЕТ** — это корневой SSOT, ведомый вручную; все ссылки на него —
  **читатели**.
- `scripts/provider-docs.py` генерирует **доки ИЗ** манифеста (`--write` `:323` / `--check`
  `:324`), а не сам манифест.
- Читатели: `packages/skiller/lib/skiller/config.py:191`, `publication.py:44`,
  `packages/maind/lib/maind/config.py:460`, `provider_deploy.py:511`,
  `packages/harness/lib/harness/provider_audit.py:124`, `profiles.py:18`,
  `packages/task/lib/task/command_render.py:209`.
- Парсер/хеш: `core/provider_manifest.py` (`load_provider_manifest`,
  `provider_manifest_sha256`, экспорт `core/__init__.py:36`).

**Вердикт:** предположение аудита «похоже на сгенерированный артефакт» — **неверно**;
файл рукописный. Предмет P5 — не «найти генератор», а **зафиксировать провенанс явно**
(правило `root.generated-artifacts` к нему не применяется, и это надо сказать вслух).

## 7. MCP-конфиг (вход P2)

- Флаг `mcp.emit_example`, **дефолт `false`**: объявление — `config.example.json:131`
  (док `:129`); чтение (единственное) — `packages/maind/lib/maind/provision/deploy.py:294`
  `bool((config.get("mcp") or {}).get("emit_example"))` — **константы-дефолта в схеме нет**.
- Точка эффекта: `deploy.py:344–346` → `write_example(...)` + `reconcile_gitignore(...)`.
- Модуль гигиены: `packages/maind/lib/maind/mcpconfig.py`, `check_hygiene()` `:150–168`
  (диагнозы `tracked-in-git` / `missing-example`), комментарий про флаг `:157`.
- Пресеты harness: `packages/harness/configs/{claude-code,codex,common}/mcp/`;
  CLI `harness mcp` → `lib/harness/mcp.py` (merge-only).

## 8. `plan-lint` (вход P5)

- Модуль `packages/task/lib/task/plan_lint.py` (2 408 строк); лаунчер
  `packages/task/scripts/plan-lint.py` (25 строк).
- **`--conflicts` НЕ существует** — ноль вхождений (перепроверено 2026-07-31).
- Аргументы `main()` `:2338`: `path` `:2343`, `--json` `:2344`, `--baseline`
  `:2346` (`nargs="?", const="HEAD"`), `--gate {all,new}` `:2349`.
- `--baseline`: `_baseline_diag_keys(root, ref)` `:2287` — `git archive <ref>` во временный
  каталог `:2312` и повторный линт; сравнение по нормализованным ключам `:918,940`.
- Closure Protocol v1 реализован: `CLOSURE_META_FIELD` `:448`, `_lint_closure_reports_81`
  `:594`, гейт `Consequences` `:1776`, гейт `Возобновление:` `:1886`; писатель —
  `packages/task/commands/plan-close.md:190` (шаг 4a).

## 9. `.claude/rules` и генерация CLAUDE.md (вход P2)

**Path-scoped rules в ЭТОМ репозитории — НЕТ.** Каталога `.claude/rules/` нет ни в корне,
ни в пакетах (`.claude/` содержит `agents/ analyst/ analyze/ output-styles/ runs/ skills/
worktrees/` + settings).

Где `.claude/rules` встречается — **только как цель эмиссии в проект-потребитель**:

- источники agent-pack'ов: `packages/harness/configs/claude-code/agent-packs/{_common,
  backend-laravel,dart-flutter,laravel-package,node-frontend,python-backend}/rules/` (6 каталогов);
- цели в манифестах: `packages/harness/configs/claude-code/agent-packs/_common/pack.json:19`, `dart-flutter/pack.json:247,253,259,265,277`,
  `laravel-package/pack.json:275–299`, `python-backend/pack.json:237,243,249`;
- литералы override-паттернов: `packages/harness/lib/harness/agentpacks.py:944–945`;
- шаблон path-scoped правила: `packages/skiller/skills/general/context-economy/SKILL.md:40`
  + `packages/skiller/skills/general/context-economy/snippets/index.json:6`.

**Генерация CLAUDE.md/AGENTS.md** — `packages/harness/lib/harness/instructions.py` (88 КБ):

- писатель блоков `:1454–1457` (`<!-- swissknifeman:instructions:{scope}:{provider}:{kind}:begin -->`,
  внутри — `<!-- semantic:{id} -->`); сборка `:1448–1449`;
- операции `:1563–1564` → `plan` `:372`, `check` `:388`, `apply/update` `:404`,
  `repair` `:427`, `adopt` `:466`; CLI `cmd_instructions` `:1589`;
- **SSOT содержимого**: `packages/harness/configs/common/instructions/catalog.json`
  + `root/{common,claude-code,codex}.md` + `packages/<pkg>/{common,claude-code,codex}.md`
  (5 пакетов × 3 = 15 файлов);
- артефакты: корневые `CLAUDE.md` (88 строк) / `AGENTS.md` (92) + пер-пакетные.

**Следствие для P2:** «диета CLAUDE.md» в этом репо — правка **источников инструкций**,
а не самого `CLAUDE.md` (он генерируемый; правило `root.generated-artifacts`).

## 10. Журнал (вход P4)

`packages/task/lib/task/journal.py` (432 строки), файл `journal.jsonl` `:35`.

- `REQUIRED_FIELDS` `:47–50` — ровно 14: `ts, plan_id, item_id, command, session_id,
  run_id, attempt, actor, friction, result, cost_usd, num_turns, duration_ms, note`;
  опциональное аддитивное `trace_ref` `:262,266–270`.
- `COMMANDS` `:39` = `plan-exec, plan-run, plan-close, plan-audit, plan-design`.
- `RESULT_VALUES` `:43–46` = `in-progress, closed-green, closed-deviations, blocked,
  escalated, no-op, audit-green, audit-red`.
- `FRICTION_VALUES` `:40–42` = `escalation, routing-blocked, red-audit, deviation, retry, no-op`.
- API: `new_entry(...)` `:260`, `append(plan_dir, entry)` `:292` (валидация до записи `:296`,
  соответствие `plan_id` каталогу `:298–302`).
- CLI: `python3 -m task.journal append …` (парсер `:326`, `main()` `:367`),
  флаги `--cost-usd`, `--num-turns`, `--duration-ms`, `--attempt`, `--friction` `:331–353`.

**Следствие для P4:** item `journal` — **не новый формат**, а вызов существующего API из
драйвера. Поля `cost_usd`/`num_turns`/`duration_ms` уже есть — воркеру остаётся их добыть
из `--output-format json` (`eval.py:388` — готовый образец разбора).

## 11. Фактические расхождения с оценками брифа (для честности, не в упрёк)

| Утверждение брифа | Замер 2026-07-31 | Где |
|:--|:--|:--|
| «54 вендоренных скилла» | **56** `upstream.json` | §5 |
| «paths 1/229» | **0/229** во frontmatter; единственный хит — текст тела `packages/skiller/skills/general/context-economy/SKILL.md:40` | §4 |
| «fork 0/229» | подтверждено: `context` 0/229 | §4 |
| «EN-описания … закрывает долг 69 описаний» | описания **уже английские** (кириллица 0/229); долг 69 — это отсутствие **триггер-фразы**, реестр `packages/skiller/scripts/desc-trigger-burndown.txt` | §4 + `roadmap/skill-description-quality.md` |
| «`provider-capabilities.json` — похоже на генерируемый» | генератора нет, файл рукописный | §6 |
