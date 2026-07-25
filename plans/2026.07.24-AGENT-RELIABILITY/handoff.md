# HANDOFF — 2026-07-25 — after P1.3

**Committed item tree: `c1c4a1f9`** (item-коммит, форма `git commit --only -- <пути>` — чужой
дифф в индексе/дереве остался ровно там же и в том же виде). Этот файл коммитится следом
бухгалтерией (`plans/2026.07.24-AGENT-RELIABILITY` + `plans/ACTIVE.md`); собственный хеш в него
не вписывается.

**P1.3 закрыт `🟢 Done`.** task@0.3.1 Codex/Claude projection перегенерирована новым тонким
CLI-фронтом `packages/task/scripts/render-provider-commands.py` (`--write --repair-owned` /
`--check`), который переиспользует ТОЛЬКО существующие `command_render.py` planning/apply API
(`plan_codex_command_render`/`plan_claude_command_render`/`plan_codex_command_apply`/
`apply_codex_command_plan`/`apply_claude_command_plan`) — ни одной новой строки рендер-логики,
ни regex `.claude→.codex`, ни ручных pointer-файлов. `task` plugin/routing `0.3.0→0.3.1`,
`harness` package `0.2.0→0.3.0`, `harness` plugin `0.1.0→0.2.0` (D27 ledger); оба marketplace
перегенерированы `skiller registry` и остались byte-identical (записи плагинов версии не несут).
Шесть root task-коллизий (`task-design`, `task-plan-{audit,close,design,exec,run}`) удалены из
`.agents/skills/` ПОСЛЕ доказательства покрытия сгенерированным `task@0.3.1` bundle (24
артефакта, `test_codex_command_adapter.py`). `AGENTS.md` переформулирован: root-адаптеры —
generator-owned bootstrap-only проекции для identities, не обслуженных authoritative installed
bundle, канон — приватный бакет `repository-bootstrap`. Доitem-ный дефект
`test_provider_command_parity.py:25` (доархивный путь `plans/2026.07.19-DUAL-PROVIDER/...`
вместо `plans/archive/2026.07.19-DUAL-PROVIDER/...`, унаследовано из P1.1 Pending Work)
синхронизирован тем же item'ом. Характеризация D54: существующие provider-command тесты
прогнаны на фактическом текущем выходе ДО изменения (20/20 зелёных) — низкое доверие к
`2026.07.19-DUAL-PROVIDER` снято точечным доказательством, а не унаследовано. Детали, числа и
команды — `phases/P1.md` P1.3 Completion Notes/Known Deviations.

**Коммит-гигиена, живое предупреждение (не изменилось по классу, чуть выросло числом).**
Рабочее дерево по-прежнему несёт чужой дифф параллельного процесса — `assert_generated_scope.py
generated-scope --owner P1.3` насчитывает **25 uncommitted foreign paths** вне owner-набора
P1.3 (было 28 у P1.2, набор частично пересекается: `docs/*`, `packages/harness/lib/harness/
agentpacks.py` + его тесты, `packages/skiller/skills/general/workflow-craft/{SKILL.md,
SKILL.ru.md}`, ~15× `roadmap/*.md`). Item-коммит `c1c4a1f9` сделан формой `git commit --only --
<пути>` — та же форма, что P1.2 (`589c320e`): обычный `git add <пути> && git commit` подмешал
бы уже застейдженные чужие удаления `roadmap/*.md`, присутствовавшие в индексе до старта этого
item'а. Каждое следующее закрытие в этом дереве обязано проверять `git diff --cached --stat`
перед `git commit` и использовать `--only`, если индекс мог быть заражён.

**Живой риск для P1.5 конкретно:** чужой параллельный процесс сейчас правит
`packages/skiller/skills/general/workflow-craft/{SKILL.md,SKILL.ru.md}` — те же файлы, что
P1.5 читает как канонический источник class-B записи (Required Reads #17). P1.5 обязан
проверить `git status --porcelain -- packages/skiller/skills/general/workflow-craft` ПЕРЕД
`baseline --capture-or-verify` (owner-путь P1.5 не включает этот каталог напрямую как Files,
но чтение канона обязано быть согласовано с фактическим committed состоянием на момент старта —
если канон ещё не закоммичен чужим процессом, читать его текущие байты как «канон на старте»
и зафиксировать это чтение в Completion Notes, а не молчать).

**Next:** P1.5 — закрыть newly measured collisions (D40–D43): удалить четыре root `architect`-
дубля по доказанному ownership, добавить class-B запись `workflow-craft` (Codex-only,
`repository-bootstrap@0.2.0`), ввести read-only детектор core↔donor-bucket (D42) в
`doctor.py` и проверку «root-набор провайдера == declared target set». Routing (`plan.md` §3):
`implementation/high` / `manual` / `Review=full` — выше пина `plan-exec` (`sonnet/medium`),
routing-гейт обязан отклонить `/task:plan-exec`. Форма — **ЗАПУСК ВРУЧНУЮ** (эквивалент:
`/model sonnet` + `/effort high` + `/task:plan-run`). `roadmap.md` числит P1.5 как `solo` —
одиночный запуск, не группа; исполняется ПЕРЕД терминальным гейтом P1.4 (D41).

| Параметр | Значение |
|:--|:--|
| Model | sonnet (`implementation` по §3 Routing; renderer-таблица roadmap, D33) |
| Thinking | high — публикационная мутация против низкодоверенного seam'а (D54), correctness-critical |
| Capabilities | `command.subagents` |
| Context | `continue (/clear) — ручной item` |
| Суть | Удалить четыре root `architect`-дубля по доказанному ownership, добавить class-B `workflow-craft`, ввести core↔donor-детектор и root-набор==target-set проверку; поднять skiller API 0.4.1→0.4.2, `repository-bootstrap` 0.1.0→0.2.0 |

````
РЕЖИМ: task:plan-run 2026.07.24-AGENT-RELIABILITY P1.5 (Routing = manual, implementation/high; НЕ plan-exec — тот пинит sonnet/medium и по гейту протокола обязан отклонить этот item).
ВХОД: plans/2026.07.24-AGENT-RELIABILITY/plan.md → handoff.md → phases/P1.md Phase Context + P1.5 целиком → Required Reads P1.5 (28 пунктов, порядок как в ТЗ).
ПРЕДУСЛОВИЕ: P1.3 закрыт 🟢 на item-коммите `c1c4a1f9` (Known Deviations — процесс-отклонения, не material: см. phases/P1.md P1.3 Known Deviations ПЕРЕД стартом) — сверить по `phases/P1.md` Phase Status ДО любой мутации. P1.2 committed 🟠 (`589c320e`) остаётся read-only входом (class-A 13/26 неприкосновенны).
ЖИВОЙ РИСК: `packages/skiller/skills/general/workflow-craft/{SKILL.md,SKILL.ru.md}` сейчас правит чужой параллельный процесс (не закоммичено) — это ТОТ ЖЕ файл, что P1.5 читает как канон class-B записи (Required Reads #17). Проверь `git status --porcelain -- packages/skiller/skills/general/workflow-craft` ПЕРЕД чтением канона; если файл всё ещё грязен на момент старта — читай текущие байты как канон на старте и зафиксируй это явно в Completion Notes (не блокирующий инцидент, но обязана быть названная запись, не молчаливое чтение).
ПОРЯДОК (шаг 0 первым, до любой другой owned-записи): `python3 plans/2026.07.24-AGENT-RELIABILITY/artifacts/P1.1/assert_generated_scope.py baseline --repo . --owner P1.5 --scope-map plans/2026.07.24-AGENT-RELIABILITY/artifacts/P1.1/remediation-map.json --baseline-file plans/2026.07.24-AGENT-RELIABILITY/artifacts/P1.5/base-sha.txt --capture-or-verify`; ЕСЛИ owner-пути P1.5 на старте грязны чужим uncommitted-процессом (проверь `git status --porcelain` по owner-путям ПЕРЕД вызовом) — capture упадёт по dirty-check: не stash/revert/commit чужое (запрещено), а запиши `artifacts/P1.5/base-sha.txt` вручную байт-в-байт (`git rev-parse HEAD` + `\n`) — задокументированный P1.2/P1.3 Known Deviation, тот же путь применим здесь; при resume dirty-check не выполняется вовсе. ITEM_BASE_SHA берётся ТОЛЬКО через `baseline --verify-and-print`.
СКОУП: строго Scope Included P1.5 — ровно четыре root-каталога `architect`-дублей (`architecture`, `codebase-design`, `domain-modeling`, `package-contribution-protocol`) удаляются ТОЛЬКО после доказательства ownership (frontmatter `name:` канона == frontmatter root-адаптера, identity достижима из installed bundle после удаления — совпадение по display-префиксу/байтам НЕ доказательство); class-B запись `workflow-craft` (config + `root-bootstrap-extension-map.json` + генерируемая thin Codex-проекция + lock, Codex-only, precondition «no enabled unit serves this identity»); read-only детектор core↔donor-bucket mutual exclusion в `doctor.py --provider-distribution`; проверка «root-набор == declared target set» в генераторе/`registry --check`; версии `skiller API 0.4.1→0.4.2`, `repository-bootstrap 0.1.0→0.2.0`, весь прочий publication unit byte-identical.
НЕ ТРОГАТЬ: 13 class-A identity и их 26 проекций (P1.2, обязаны остаться байт-идентичными); публикация донорских бакетов (`general`/`research`/`oss-dev`) и состав курируемого `core`; Claude-проекция `workflow-craft` (требует `skiller budget --first-turn`, вне скоупа); task/harness projection (P1.3, закрыт); user-owned enabled-множество провайдера (только диагностика, D42).
D54 (низкое доверие к `2026.07.19-DUAL-PROVIDER`): все 30 рукописных root-адаптеров `.agents/skills/` пришли одним коммитом `e8f5b477` мимо генератора, без provenance/hash — root-поверхность и root-bootstrap renderer проверяются тестом здесь, ни один вывод того плана не принимается доказанным по факту его закрытия.
ЗАКРЫТИЕ: полный цикл 1–8 протокола — вся Validation P1.5 зелёная ДО item-коммита (включая `generated-scope` — ожидай тот же класс foreign-diff шума, что P1.2/P1.3, если чужой процесс ещё не закоммитил; документируй как Known Deviation, не блокируй на этом), негативная D42-фикстура обязательна (9 именованных пар + precondition-ошибка class-B, молчание = отказ item'а), item-коммит ПО PATHSPEC (проверяй `git diff --cached --stat` на посторонний контент перед commit — используй `git commit --only -- <пути>`, если индекс заражён), bookkeeping-коммит плановых путей, `findings/P1.5-collision-closure.md`, handoff.md с реальным хешем, `python3 packages/task/scripts/plan-lint.py plans/2026.07.24-AGENT-RELIABILITY`.
````

**Done:**
- `packages/task/scripts/render-provider-commands.py` — новый stdlib CLI-фронт (`--write
  --repair-owned` / `--check`) над `command_render.py` planning/apply API.
- `task` plugin/routing `plugin_version` 0.3.0→0.3.1 (`command-routing.json`,
  `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`); `harness` package 0.2.0→0.3.0;
  `harness` plugin 0.1.0→0.2.0.
- `packages/task/adapters/codex/{publication-lock.json,provider-artifacts.lock.json}` —
  перегенерированы под 0.3.1 (24 артефакта, provenance/hash обновлены).
- `packages/task/tests/fixtures_data/claude-command-golden/plugin.json` — синхронизирован
  byte-for-byte с реальным `.claude-plugin/plugin.json`.
- `packages/task/tests/test_provider_command_parity.py` — `CONTRACT_PATH` синхронизирован на
  `plans/archive/2026.07.19-DUAL-PROVIDER/...` (доitem-ный дефект из P1.1 Pending Work).
- Шесть `.agents/skills/task-*/` каталогов удалены (12 файлов).
- `AGENTS.md` — раздел «Codex bootstrap» переформулирован под generator-owned bootstrap-only
  модель.
- `CHANGELOG.md` — запись `[Unreleased]`.

**Remaining:** 15/22 items `⬜`+🟠 (плюс P0.4 🟠, P1.2 🟠). Порядок фаз не изменился: P0 → P1
(P1.2 ✅ → P1.3 ✅ → **P1.5** → P1.4, D41) → P2 → P3 → P4. Следующий — P1.5.

**Sources of truth:** `plan.md` v1.12.8 (§0 Last Updated, §6 Update Log) · `phases/P1.md`
(Phase Status таблица, P1.3 Completion Notes/Known Deviations) · `packages/task/configs/
command-routing.json` · `packages/task/adapters/codex/` (24 артефакта + 2 lock) ·
`packages/task/scripts/render-provider-commands.py` · `journal.jsonl`.

**Open risks:**
- **25 незакоммиченных чужих путей остаются в дереве** (см. «Коммит-гигиена» выше) —
  `generated-scope` Validation P1.3 красная ИМЕННО из-за них (owned=26/foreign_commit=0/
  undeclared_drift=25, ни один owned-путь не задет). Владелец — чужой параллельный процесс
  (похоже на P1.5/roadmap-ревизию); следующий item обязан повторить ту же проверку `git status
  --porcelain` ПЕРЕД `baseline --capture-or-verify` и ожидать тот же класс шума.
- **Живой конфликт файлов с P1.5** (см. «Живой риск» выше): `packages/skiller/skills/general/
  workflow-craft/{SKILL.md,SKILL.ru.md}` уже правит чужой процесс — P1.5 обязан явно
  зафиксировать, чьи байты он читал как канон на старте.
- 21 недекларированный файл в root-поверхности (P1.1) — 6 из них (task SKILL.md +
  6 agents/openai.yaml) исчезли этим item'ом; остаток (4 `architect` + `workflow-craft`)
  закрывает P1.5.
- `command.interactive-user-input` отсутствует в каталоге capability (P1.1 находка, ранее
  назван P1.3 как возможный владелец) — этот item его НЕ добавил: новый public capability id
  требует D23 proposal/ADR/SemVer review, что вне Scope Included P1.3; остаётся named debt без
  переназначенного владельца (кандидат — отдельный fix-item, не молчаливое расширение P1.5).
- Claude enabled-set остаётся `unknown` (P1.1 долг, read-only команда не объявлена).
- Прежний долг без изменений: три находки A2; A1 F11; расхождение провенанса harness-CLI ↔
  maind-адаптера (из P0.4).
- `plans/README.md` § «Очередь планов» показывает устаревший счётчик item'ов этого плана — вне
  Files/carve-out этого item'а, не трогалось.

**Workarounds/Deferred/Open questions:**
- workarounds: baseline carrier P1.3 записан вручную (Known Deviation phases/P1.md P1.3) —
  функционально идентично `--capture-or-verify` на чистом дереве, документировано, повторяемо
  для P1.5/P2.2/P2.3, если та же foreign-dirty ситуация повторится;
- deferred: `command.interactive-user-input` capability id (требует D23-гейта); расхождение
  провенанса harness-CLI ↔ maind-адаптера (из P0.4, владельца нет);
- open_questions: —.
