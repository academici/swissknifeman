# HANDOFF — 2026-07-25 — after P1.2

**Committed item tree: `589c320e`** (item-коммит, форма `git commit --only -- <пути>` — чужой
дифф в индексе/дереве остался ровно там же и в том же виде). Этот файл коммитится следом
бухгалтерией (`plans/2026.07.24-AGENT-RELIABILITY` + `plans/ACTIVE.md`); собственный хеш в него
не вписывается.

**P1.2 закрыт `🟠 Done with deviations`.** 13 приватных root-bootstrap identities (класс A)
канонизированы: двуязычные каноны `packages/skiller/skills/repository-bootstrap/<id>/
{SKILL.ru.md,SKILL.md}` заменяют рукописные дубли 26 тонкими генерируемыми проекциями
(`.claude/skills/<id>/SKILL.md` + `.agents/skills/<id>/SKILL.md` — только trigger-метаданные +
canonical path/sha256 + версия, без копии тела) + одним `adapters/repository-bootstrap/
publication-lock.json`. Единственный производитель — новый рендерер `publication.py::
render_repository_bootstrap_projections`, вызываемый из `registry.py`. `build_publication_catalog`
исключает приватный бакет из ЛЮБОГО обычного Claude/Codex/marketplace юнита (D31);
`skillset.py`/`lock.py` отклоняют его из vendor/connect consumer-выбора. `configs/
publication-versions.json` (D27) развёл package API SemVer и per-unit content_version:
`core`/`skm` → 0.4.1 вместе с `packages/skiller/package.json`, остальные юниты остались
byte-identical на замороженной базе 0.4.0. Шесть дублирующих root core-identities
(`anti-drift`/`context-economy`/`plan-protocol`/`query-craft`/`session-handoff`/`verify-claims`)
удалены из `.agents/skills/` после доказательства покрытия `core@0.4.1`. Детали, числа и команды
— `phases/P1.md` P1.2 Completion Notes/Known Deviations.

**Коммит-гигиена, живое предупреждение (не изменилось, ухудшилось незначительно по числу).**
Рабочее дерево по-прежнему несёт чужой дифф параллельного процесса — **28 путей** (было
упомянуто 12 в индексе на момент P1.1; сейчас `assert_generated_scope.py generated-scope`
насчитывает 28 uncommitted foreign paths вне owner-набора P1.2: `docs/develop.md`,
`docs/reference.md`, `docs/rejected-optimizations.md`, `packages/analyst/docs/roadmap.md`,
`packages/harness/{docs/configs/agent-packs.md,lib/harness/agentpacks.py,tests/
test_agentpacks.py,tests/test_agentpacks_upgrade_fact.py,tests/test_settings_audit_fieldcase.py}`,
`packages/skiller/skills/general/workflow-craft/{SKILL.md,SKILL.ru.md}`, 15× `roadmap/*.md`).
Item-коммит `589c320e` сделан формой `git commit --only -- <пути>` — единственная форма, которая
гарантированно НЕ подмешивает уже застейдженное чужое содержимое индекса (обычный `git add
<пути> && git commit` НЕ сработал бы: чужие `roadmap/*.md`-удаления были staged в индексе ДО
старта этого item'а — `git commit --only` игнорирует staged-контент вне явного pathspec).
Каждое закрытие в этом дереве обязано проверять `git diff --cached --stat` перед `git commit` и
использовать `--only`, если индекс мог быть заражён; stash/revert/reset чужих правок запрещены.

**Next:** P1.3 — исправить task/harness projection и runtime dedup (удалить 6 root task-адаптеров,
поднять task/harness версии, доказать характеризационным тестом поведение seam'ов
`2026.07.19-DUAL-PROVIDER` перед изменением, D54). Routing (`plan.md` §3): `implementation/high` /
`manual` / `Review=full` — выше пина `plan-exec` (`sonnet/medium`), routing-гейт обязан отклонить
`/task:plan-exec`. Форма — **ЗАПУСК ВРУЧНУЮ** (эквивалент: `/model sonnet` + `/effort high` +
`/task:plan-run`). `roadmap.md` числит P1.3 как `solo` — одиночный запуск, не группа.

| Параметр | Значение |
|:--|:--|
| Model | sonnet (`implementation` по §3 Routing; renderer-таблица roadmap, D33) |
| Thinking | high — публикационная мутация против низкодоверенного seam'а (D54), correctness-critical |
| Capabilities | `command.subagents` |
| Context | `continue (/clear) — ручной item` |
| Суть | Сделать канонические task-команды provider-executable, удалить шесть root task-коллизий, обеспечить одну активную semantic identity для task/core/hooks; поднять task→0.3.1, harness package→0.3.0, harness plugin→0.2.0 |

````
РЕЖИМ: task:plan-run 2026.07.24-AGENT-RELIABILITY P1.3 (Routing = manual, implementation/high; НЕ plan-exec — тот пинит sonnet/medium и по гейту протокола обязан отклонить этот item).
ВХОД: plans/2026.07.24-AGENT-RELIABILITY/plan.md → handoff.md → phases/P1.md Phase Context + P1.3 целиком → Required Reads P1.3 (30 пунктов, порядок как в ТЗ).
ПРЕДУСЛОВИЕ: P1.2 закрыт 🟠 на item-коммите `589c320e` (Done with deviations — сверь Known Deviations phases/P1.md ПЕРЕД стартом: (1) baseline carrier P1.2 записан вручную из-за грязного дерева на старте, (2) generated-scope P1.2 red от 28 чужих uncommitted путей, (3) item-коммит P1.2 нёс правку validate.sh вне его Files) — сверить по `phases/P1.md` Phase Status ДО любой мутации.
ПОРЯДОК (шаг 0 первым, до любой другой owned-записи): `python3 plans/2026.07.24-AGENT-RELIABILITY/artifacts/P1.1/assert_generated_scope.py baseline --repo . --owner P1.3 --scope-map plans/2026.07.24-AGENT-RELIABILITY/artifacts/P1.1/remediation-map.json --baseline-file plans/2026.07.24-AGENT-RELIABILITY/artifacts/P1.3/base-sha.txt --capture-or-verify`; ЕСЛИ owner-пути P1.3 на старте грязны чужим uncommitted-процессом (как было у P1.2 — проверь `git status --porcelain` по owner-путям ПЕРЕД вызовом) — capture упадёт по dirty-check: не stash/revert/commit чужое (запрещено), а запиши `artifacts/P1.3/base-sha.txt` вручную байт-в-байт (`git rev-parse HEAD` + `\n`) — это задокументированный P1.2 Known Deviation (1), тот же путь применим здесь; при resume dirty-check не выполняется вовсе. ITEM_BASE_SHA берётся ТОЛЬКО через `baseline --verify-and-print`.
СКОУП: строго Scope Included P1.3 — ровно шесть root task-коллизий (`task-design`, `task-plan-{audit,close,design,exec,run}`) удаляются ПОСЛЕ доказательства сгенерированного `task@0.3.1` bundle/marketplace; `command_render.py` planning/apply API переиспользуются как есть (НЕ regex `.claude→.codex`, не ручные pointer-файлы); версии task/harness подняты по ledger (`generated-artifact-version-v1.md`); P1.2 `repository-bootstrap@0.1.0` — read-only вход (registry check доказывает byte-identical, не re-own).
НЕ ТРОГАТЬ: канонический task purpose/state behavior; external consumer install; new workflow types; class-A root-bootstrap (P1.2, заморожен); `packages/skiller/skills/general/workflow-craft/*` (P1.5, чужой параллельный дифф — НЕ трогай, даже если видишь его модифицированным в git status).
D54 (низкое доверие к `2026.07.19-DUAL-PROVIDER`): `command_render.py`, Codex-адаптеры команд и marketplace-публикация родом из терминального 🟠-плана — их текущее поведение доказывается характеризационным тестом ЗДЕСЬ (на фактический текущий выход ДО изменения), не наследуется как «уже зелёное».
ЗАКРЫТИЕ: полный цикл 1–8 протокола — вся Validation P1.3 зелёная ДО item-коммита (включая `generated-scope` — ожидай тот же класс foreign-diff шума, что и P1.2, если чужой процесс ещё не закоммитил; документируй как Known Deviation, не блокируй на этом), item-коммит ПО PATHSPEC (провекряй `git diff --cached --stat` на посторонний контент перед commit — используй `git commit --only -- <пути>`, если индекс заражён), bookkeeping-коммит плановых путей, handoff.md с реальным хешем, plan-lint --baseline HEAD.
````

**Done:**
- `packages/skiller/skills/repository-bootstrap/<id>/{SKILL.ru.md,SKILL.md}` × 13 — полные
  двуязычные каноны (RU источник, EN компактный канон промтом `claude-canon-from-ru.md` +
  `check-translations.sh --stamp`).
- `packages/skiller/configs/repository-bootstrap-skills.json` — 13 sorted/unique identities,
  generator/lock_path.
- `packages/skiller/configs/publication-versions.json` — D27 per-unit version map
  (`default_unit_version=0.4.0`, `units.core/skm=0.4.1`, `units.repository-bootstrap=0.1.0`).
- `publication.py`: `PublicationUnit.content_version`, приватный-бакет exclusion в
  `build_publication_catalog`, `render_repository_bootstrap_projections` (+
  `load_repository_bootstrap_config`) — 26 проекций + lock, no-op на повторном рендере.
- `registry.py`: `_publication_versions`, `build_repository_bootstrap_publication`, wiring в
  `write_plugin_manifests`/`check_drift`/`cmd_registry` (graceful skip без конфига).
- `skillset.py::private_source_buckets` + фильтр `_registry_index` + explicit die на
  `buckets: [repository-bootstrap]`; `lock.py::_registry_map` та же фильтрация.
- `packages/skiller/package.json` 0.4.0→0.4.1; `.agents/skills/{anti-drift,context-economy,
  plan-protocol,query-craft,session-handoff,verify-claims}/` удалены.
- `packages/skiller/scripts/validate.sh` — `private_source_only` exemption в per-bucket
  `.claude-plugin/plugin.json` check (вне буквальных Files, см. Known Deviations (3)).
- 5 тестовых файлов расширены (72 теста, все зелёные): exclusion (Claude/Codex), 26+1
  artifacts/no-op (Codex), vendor bucket/include rejection.
- `CHANGELOG.md` — запись `[Unreleased]`.

**Remaining:** 16/22 items `⬜`+🟠 (плюс P0.4 🟠, P1.2 🟠). Порядок фаз не изменился: P0 → P1
(P1.2 ✅ → **P1.3** → P1.5 → P1.4, D41) → P2 → P3 → P4. Следующий — P1.3.

**Sources of truth:** `plan.md` v1.12.7 (§0 Last Updated, §6 Update Log) · `phases/P1.md`
(Phase Status таблица, P1.2 Completion Notes/Known Deviations) · `packages/skiller/configs/
{repository-bootstrap-skills,publication-versions}.json` · `packages/skiller/skills/
repository-bootstrap/` (13 канонов) · `packages/skiller/adapters/repository-bootstrap/
publication-lock.json` · `journal.jsonl`.

**Open risks:**
- **28 незакоммиченных чужих путей остаются в дереве** (см. «Коммит-гигиена» выше) — `generated-
  scope` Validation P1.2 красная ИМЕННО из-за них (owned=85/foreign_commit=0/undeclared_drift=28,
  ни один owned-путь не задет). Владелец — чужой параллельный процесс (похоже на P1.5/roadmap-
  ревизию); следующий item обязан повторить ту же проверку `git status --porcelain` ПЕРЕД
  `baseline --capture-or-verify` и ожидать тот же класс шума, если чужой процесс ещё не
  закоммитил свою работу.
- **`packages/task/scripts/validate.sh` красный — доitem-ный дефект** (унаследовано от P1.1,
  `packages/task/tests/test_provider_command_parity.py:25` держит архивированный путь
  `2026.07.19-DUAL-PROVIDER`). Владелец — P1.3 (пакет `task` в его Files) либо отдельный fix-item;
  этот item его не чинил (`task/`-файлы вне Files P1.2).
- 21 недекларированный файл в root-поверхности (P1.1) — 12 из них (6 SKILL.md + 6
  agents/openai.yaml, core-identities) исчезли этим item'ом; остаток (task/architect) закрывает
  P1.3/P1.5.
- `command.interactive-user-input` отсутствует в каталоге capability (P1.1 находка) — владелец
  P1.3 (D23 proposal/ADR/SemVer).
- Claude enabled-set остаётся `unknown` (P1.1 долг, read-only команда не объявлена).
- Прежний долг без изменений: три находки A2; A1 F11; Claude-проекция `workflow-craft` (P1.5);
  расхождение провенанса harness-CLI ↔ maind-адаптера (из P0.4).
- `plans/README.md` § «Очередь планов» показывает устаревший счётчик item'ов этого плана — вне
  Files/carve-out этого item'а, не трогалось.

**Workarounds/Deferred/Open questions:**
- workarounds: baseline carrier P1.2 записан вручную (Known Deviation (1) phases/P1.md P1.2) —
  функционально идентично `--capture-or-verify` на чистом дереве, документировано, повторяемо
  для P1.3/P1.5/P2.2/P2.3, если та же foreign-dirty ситуация повторится;
- deferred: doctor.py «old-cache» диагностика не добавлена отдельным кодом — покрыта `registry
  --check` (P1.2 Pending Work); добавление capability id `command.interactive-user-input`
  (требует D23-гейта); расхождение провенанса harness-CLI ↔ maind-адаптера (из P0.4, владельца нет);
- open_questions: —.
