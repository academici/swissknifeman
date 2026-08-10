# roadmap — отложенные направления swissknifeman

Здесь живут **спеки на будущее внедрение** — идеи, которые исследованы и осознанно отложены.
Каждый файл — самодостаточный план: зачем, как, критерий «когда внедрять».

> **Правило каталога (2026-07-25):** полностью реализованная спека **удаляется** — история
> задумки живёт в git и в закрывшем её плане (`plans/archive/<ID>`), а каталог показывает
> только незакрытую работу. Частично реализованные записи остаются, но их **Статус** называет
> ровно ОСТАТОК. Колонка **Статус** — источник истины.

Источник большинства решений «отложить» — глубокий research-аудит (см.
[`docs/reference.md`](../docs/reference.md), там же плюсы/минусы исследованных репозиториев).

## Критерий сработал — ждёт внедрения

| Файл | Что | Статус | Критерий / связь с планами |
|:--|:--|:--|:--|
| [`provider-docs-snapshot-daemon-noise.md`](provider-docs-snapshot-daemon-noise.md) | `test_committed_outputs_are_exact_and_check_is_no_write` снимает хеши ВСЕГО дерева, ловит чужой mAInd-демон (`packages/maind/data/state_store.db/mem%3Ahealth.bin`), не дрейф манифеста | ⬜ к внедрению | **Пере-открывается ПЕРВЫМ item'ом, правящим `scripts/test-provider-docs.py`** (проверяемое событие: `git log --diff-filter=M --oneline 90afaff1..HEAD -- scripts/test-provider-docs.py` даёт непустой вывод). Измерено `2026.07.31-SKM-LEAN` P6.3, D70 — три изолированных прогона, все `FAILED` на одном пути. Живого потребителя у записи нет: названный ею владелец адреса P5.2 терминален ещё до её появления — критерий пере-открытия назначен `2026.07.31-SKM-LEAN` P7.3 (D113) |
| [`memory-recall-shared-namespace-priority.md`](memory-recall-shared-namespace-priority.md) | `_recall_union` (mid-session `maind_memory_recall`) не наследует D10 «shared по умолчанию не тянется» — тянет `ns:axioma` наравне с приватным scope, `RECALL_LIMIT=200` на каждый | ⬜ к внедрению | Измерено 2026-08-06 на Agelto: приватная память 2 записи vs `ns:axioma` 47; live-запрос «workflow» — 6/7 результатов и ~9,3 КБ ответа из axioma. Масштаб выгоды не подтверждён (частота вызовов `maind_memory_recall`/сессию не измерена) — см. §3 файла |

## Частично реализовано — остаток здесь

| Файл | Остаток | Статус | Критерий остатка |
|:--|:--|:--|:--|
| [`workflow-craft.md`](workflow-craft.md) | Активация конструктора (ч.1/1.5/1.6) внедрена SKM-ROADMAP-005. **Остаток — ч.2: fleet-синтез накопленных `plans/*/workflows/*.js` через analyst** | 🟡 остаток | 10+ полевых скриптов ИЛИ повтор «изобрели то, что уже было шаблоном» |
| [`skill-description-quality.md`](skill-description-quality.md) | Гейт триггер-фразы в `description` введён + blocker-набор (39 < 100 симв) починен (`2026.07.29-HARNESS-AGNOSTIC` P3.5). **Остаток — 69 длинных описаний без триггера** (унаследованный долг в `desc-trigger-burndown.txt`) и рычаг №4 владельца (сжатие ради слотов, D74 АРХИВНОГО плана `plans/archive/2026.07.25-ECO-OPT`) | 🟡 остаток | Следующая содержательная правка каждого скилла (one-way burn-down) ИЛИ решение владельца включить рычаг №4 |
| [`artifex-thin-wrapper.md`](artifex-thin-wrapper.md) | Тонкая обвязка исполнения планов (остаток поглощённого супервизор-трека `2026.07.18-FOREMAN`): каркас пакета, ядро fresh-session цикла, retry-лестница, run-folder, unattended-профиль, каналы эскалации, раскатка и пилот — 14 items донора без дома | 🟡 ровно остаток | N = 5 боевых exec-волн (`journal.jsonl`, класс НЕ синтетический) с суммарной долей вмешательств драйвера < 25 % (`2026.07.31-SKM-LEAN` D119; фикстурная волна P4.6 — 0/2 — в накопление не засчитывается) ИЛИ `decide` стал импортируемым модулем в `packages/**` ИЛИ измеренный выигрыш стоимости ≥2× против Workflow-марафона |

## Отложено — критерий не сработал

| Файл | Что | Критерий внедрения |
|:--|:--|:--|
| [`upstream-notify-diet-fork.md`](upstream-notify-diet-fork.md) | Систематическая миграция раздутых вендорных скиллов `notify` → `fork` (механизм есть, нужен критерий отбора + плейбук) | Любое из двух проверяемых событий: (а) item плана правит **тело** вендорного бандла со `strategy: notify` в `upstream.json` ради диеты; (б) `packages/skiller/scripts/update-upstreams.sh --check` показал дрейф апстрима у любого из шести раздутых `notify`-кандидатов §«Измеренный разрыв». Прежняя проза «диета-фаза упирается в notify-скилл» приведена к структурной форме `2026.07.31-SKM-LEAN` P7.3: сверка показала, что условие (а) фазой P3 того плана НЕ выполнено — правились `description`/`when_to_use`/`context: fork` (frontmatter), тела вендорных бандлов не трогались, а `context: fork` Claude Code — не `strategy: fork` skiller |
| [`plan-lesson-capture.md`](plan-lesson-capture.md) | Шаг протокола для находок владельца ПОСЛЕ закрытия item'а (`/task:plan-lesson`) | Повтор на ещё одном плане/проекте (пока один замер — `dterema` P6.2/P6.3) |
| [`plan-design-vs-exec-status-check.md`](plan-design-vs-exec-status-check.md) | Агент рекомендует `plan-design` вместо `plan-exec`, не проверив фактический статус фазы | Повтор на ещё одном плане/проекте (пока один замер — `insiders` P1) |
| [`2026.08.09-plan-roadmap-batching-gate.md`](plan-roadmap-batching-gate.md) | Roadmap не доказывает grouping, а direct item invocation обходит текущую batch-карту, свежесть `finish` и commit boundary | Критерий сработал: Agelto `2026.08.09-RELEASE-READINESS` — после появления P0.0 finish 74→75 потребовал D52; direct `P1.3` был предложен при canonical запуске `P1.2-P1.5` |
| [`2026.08.10-audit-before-close-phase-gate.md`](2026.08.10-audit-before-close-phase-gate.md) | Phase close создаёт handoff до независимой проверки и может породить фиктивный close→audit→reopen цикл | Критерий сработал: Agelto `2026.08.09-RELEASE-READINESS` P1 — owner потребовал audit terminal phase до Phase Handoff; следующий change plan-protocol обязан внедрить gate |
| [`2026.08.10-plan-evidence-anchor-audit-loop.md`](2026.08.10-plan-evidence-anchor-audit-loop.md) | Single product anchor самоинвалидируется, когда изменённые `Files` входят в digest bundle, а Validation требует fresh projections на том же commit; аудиты чинят симптомы слоями | Критерий сработал: Agelto P1.7 `7f203014` не содержит execution inputs и неизбежно делает bundle stale; нужен spec→product→closure evidence graph и seam-level remediation |
| [`2026.07.25-memory-hub-service.md`](2026.07.25-memory-hub-service.md) | Хаб памяти как сервис: авторизация по scope, отзыв доступа, серверное назначение конфигов, аудит — тяжёлая часть, ВНЕ скоупа реализованного LAN-хоста | §12 самой записи, любой из четырёх: появился второй человек, которому нужна память экосистемы · машин стало больше двух ИЛИ появилась машина вне LAN/tailnet · потребовалось разграничение памяти по проектам (NDA-проект) · объём памяти вырос до тысяч записей (сегодняшний ориентир — 251) |

## Отклонено решением

| Файл | Что | Решение |
|:--|:--|:--|
| [`otel-preset.md`](otel-preset.md) | OTEL-пресет harness (opt-in телеметрия Claude Code) | ⛔ Skipped by decision (D7, CONTEXT-ECONOMY P5.4) — стаб; строка вердикта в [`docs/rejected-optimizations.md`](../docs/rejected-optimizations.md). Вернуться при реальном коллекторе |

## Закрыто и удалено

Спеки реализованы; текст — в git-истории, ТЗ и решения — в закрывших планах.

| Спека | Где живёт результат |
|:--|:--|
| `agent-command-router-hook.md` | `packages/harness/configs/claude-code/hooks/agent-router/` + `harness router` + провиженер `router-config` в `maind sync` |
| `playwright-mcp-output-dir.md` | `--output-dir .playwright-mcp` + пиновка `@playwright/mcp@0.0.78` на трёх носителях обоих провайдеров (`2026.07.31-SKM-LEAN` P5.6) |
| `plan-audit-loop.md` | Правила остановки — `packages/task/commands/plan-audit.md` (две ступени, порог severity, потолок 2 раунда). CLI-ступень — `plan-lint.py --conflicts` (`packages/task/lib/task/plan_lint.py`, `2026.07.31-SKM-LEAN` P5.9), названа первой, дешёвой командой конфликт-скана в `plan-audit.md` §1 |
| `settings-doctor.md` | `harness doctor --settings` (`lib/harness/settings_audit.py`) · `skiller doctor --settings` · `maind doctor --audit settings` |
| `workflow-status-cli.md` | `harness wf status` (`lib/harness/wf_status.py`), роутинг `swissknifeman wf` |
| `plan-homes.md` | plan-protocol §12 «два дома», канон имён + `supersedes`, `brain` CLI |
| `plan-routing-tier-granularity.md` | plan-protocol §9 Tier policy + Гранулярность; DoR-гейт `plan-design` |
| `changelog-discipline.md` | хук `changelog-gate` (harness) + `skiller release` (`lib/skiller/release.py`) + скилл `oss-dev/release-engineering` |
| `php-package-stack-pack.md` | `packages/harness/configs/claude-code/agent-packs/laravel-package/` |
| `analyst-suggest-draft-skill.md` | `packages/analyst/lib/analyst/suggest.py` (+ `commands/analyst.md`) |
| `self-learning-memory.md` | ядро — пакет `analyst` (`digest`→`confidence`→`promote`→`memory-digest-hook`); остаток P5 (потоковый capture) ведёт [`packages/analyst/docs/roadmap.md`](../packages/analyst/docs/roadmap.md) |
| `agent-packs-upgrade-drift.md` | `do_upgrade` строит план из хэшей (источник/диск против `base_sha256` лока), пропавший target восстанавливается при равной версии, дрейф источника без бампа — warn; `doctor` предупреждает о targets двух паков (`shared_targets` в `--json`). Тесты — `packages/harness/tests/test_agentpacks_upgrade_fact.py` |
| `2026.07.15-workflow-global-cachebust-fullpipeline-rerun.md` | per-item `asOf` — канон `packages/task/workflows/README.md` §«Правила заполнения слотов»; чек-пункт «глобальный ли cache-bust маркер?» перед третьим resume — скилл `general/workflow-craft` §4.1 |
| `ecosystem-glossary.md` | механизм — скилл `architect/domain-modeling` (CONTEXT.md, Rule of Two, term-index) + ревью-паки; наполнение term-index — ТЗ `plans/archive/2026.07.10-SKM-ROADMAP-005/phases/P6.md` (P6.4, vault) |
| `budget-first-turn-plugin-visibility.md` | `packages/skiller/lib/skiller/plugins.py` + `skiller budget --first-turn --with-plugins` (аддитивные ключи `plugins`/`session_total`/`session_verdict`, D13/D14/D16) — `plans/archive/2026.07.31-SKM-LEAN` P1.1 |
| `mcp-config-example-emit.md` | `mcp.emit_example` default-on с opt-out (`EMIT_EXAMPLE_DEFAULT`, `packages/maind/lib/maind/constants.py` + `config.py::merge_defaults`) — `plans/archive/2026.07.31-SKM-LEAN` P2.4 |
| `codex-publication-consumer-acceptance.md` | Изолированный consumer-acceptance гейт `packages/skiller/tests/test_codex_consumer_acceptance.py` (temp `CODEX_HOME` → `codex plugin`/`debug prompt-input` живым CLI) + регистрация в `validate.sh` (гейт 18, явный skip без `codex`) — `plans/archive/2026.07.31-SKM-LEAN` P5.5 |
| `instruction-authorize-order.md` | `INSTRUCTION_WRITE_FORBIDDEN` от `apply_instructions` печатает ожидаемый порядок целей (алфавитный по `target_path`, копипастопригодный) через новое поле `message` — `packages/harness/lib/harness/instructions.py::_write_refusal`/`apply_instructions`, `_print_report` — `plans/archive/2026.07.31-SKM-LEAN` P5.7 |
| `2026.07.29-launch-block-command-row.md` | Команда — строка `| Команда |` таблицы launch-block (последняя), отдельный code-block стал опциональным («ровно один из двух»); аддитивный гейт `plan_lint.py`, пять команд + пять Codex-зеркал + golden-фикстуры, version bump скилла `plan-protocol` (2.23.0) — `plans/archive/2026.07.31-SKM-LEAN` P5.8 |
| `agent-scoped-skill-loading-vs-connect-default.md` | Вердикт владельца «не делаем» — дефолт `connect` не меняется, резидентную ось фактически закрыли диета канона/хаб-блок/измеритель/сжатие листинга (D116); строка вердикта — [`docs/rejected-optimizations.md`](../docs/rejected-optimizations.md) — `plans/archive/2026.07.31-SKM-LEAN` P7.1 |
| `skill-rules-sidecar.md` | Вердикт владельца «не делаем» — закрыт нативным эквивалентом (`when_to_use` + `context: fork`, D117); строка вердикта — [`docs/rejected-optimizations.md`](../docs/rejected-optimizations.md) — `plans/archive/2026.07.31-SKM-LEAN` P7.1 |
| `project-freshness-agent.md` | Вердикт владельца «не делаем» — новых ролей не заводим (D118); строка вердикта — [`docs/rejected-optimizations.md`](../docs/rejected-optimizations.md) — `plans/archive/2026.07.31-SKM-LEAN` P7.1 |
| `codex-skill-listing-fallback-overflow.md` | OQ-8 закрыт веткой (A) «принять деградацию» — рычаги 1–3 Claude-only, рычаг 4 арифметически недостаточен (D120); строка вердикта — [`docs/rejected-optimizations.md`](../docs/rejected-optimizations.md) — `plans/archive/2026.07.31-SKM-LEAN` P7.1 |
| `analyst-plan-scan.md` | Переехала в [`packages/analyst/docs/roadmap.md`](../packages/analyst/docs/roadmap.md) §«Перенесено из корневого `roadmap/`» — `plans/archive/2026.07.31-SKM-LEAN` P7.2 |
| `analyst-fleet-coverage.md` | Переехала в [`packages/analyst/docs/roadmap.md`](../packages/analyst/docs/roadmap.md) §«Перенесено из корневого `roadmap/`» — `plans/archive/2026.07.31-SKM-LEAN` P7.2 |
| `cross-machine-memory.md` | Вариант 1 стаба (единственный демон-хост + сетевые клиенты) реализован фазой P4 АРХИВНОГО плана `plans/archive/2026.07.25-ECO-OPT`: ADR `packages/maind/docs/adr/ADR-0001-cross-machine-memory.md` (P4.1, D78/D80) · `memory.role` standalone/host/client + bearer-аутентификация в `packages/maind` (P4.2) · роль-осознанный `scripts/bootstrap-machine.sh` + `packages/maind/docs/deploy.md` (P4.3). Остаток — не дизайн, а доказательство: три клиент-специфичных гейта требуют второй физической машины и ведутся Pending Work P4.3 того же архивного плана. Класс присвоен `plans/archive/2026.07.31-SKM-LEAN` P7.3 (находка F1) |
| `codex-subagent-offload.md` | Постановка закрыта вердиктом D84 АРХИВНОГО плана `plans/archive/2026.07.25-ECO-OPT` (P7.1–P7.3): Codex — ВТОРОЙ ВОДИТЕЛЬ, а не канал делегирования мелочи; плагин `codex-plugin-cc` установлен, always-on цена измерена (~449 ток), правило активации текстовое. Карточка провенанса — [`docs/reference.md`](../docs/reference.md) § openai/codex-plugin-cc; готовый (сознательно не запущенный) протокол числового пилота A/B — `plans/archive/2026.07.25-ECO-OPT/research/16-P7-target-design.md` §2. Класс присвоен `plans/archive/2026.07.31-SKM-LEAN` P7.3 (находка F1) |

## Принцип

Не внедрять спекулятивно. Каждый пункт включается **по факту измеренной проблемы**, а не «на
вырост» — это прямое следствие гейтов `anti-drift`/`code-simplifier` и анти-bloat-политики репо.

Сами «измерения» ловит скилл `field-feedback-loop` (`.claude/skills/`): отклонение, пойманное
в полевой работе над проектом, он либо чинит сразу (очевидный баг), либо оформляет сюда спекой
с критерием внедрения (новое/сомнительное) — чтобы специфика проектов не терялась.
