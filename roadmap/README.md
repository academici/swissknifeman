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
| [`2026.08.11-plan-views-history-cli-contract.md`](2026.08.11-plan-views-history-cli-contract.md) | `plan-views history` расходится с задокументированными callers: stdout implicit, но `--stdout` отвергается | ⬜ к внедрению | Следующая правка history CLI выбирает один канонический интерфейс, регенерирует callers и доказывает исполнимость emitted command regression-тестом. |
| [`2026.08.11-roadmap-batch-selection-is-authoritative.md`](2026.08.11-roadmap-batch-selection-is-authoritative.md) | Direct item invocation обходит обязательный roadmap batch и дробит общий runtime context | ⬜ к внедрению | **Критерий сработал:** Agelto B3-READINESS, P3.1–P3.5, 2026-08-11. Следующая правка batch selection должна ввести schema-validated map и fail-closed `ROADMAP_BATCH_REQUIRED` для неполного запуска. |
| [`2026.08.14-validation-repair-without-redesign.md`](2026.08.14-validation-repair-without-redesign.md) | Локальный PHPStan repair в соседнем committed slice был ошибочно превращён в `plan-design`, хотя канон требует continue-first | ⬜ к внедрению | **Критерий сработал:** Insiders `2026.07.30-SITE-HARDENING` P6.5, 2026-08-14. Следующая правка repair classifier/projections должна запретить redesign recommendation для qualified bounded validation repair. |
| [`2026.08.14-repeat-audit-evidence-reuse-budget.md`](2026.08.14-repeat-audit-evidence-reuse-budget.md) | Один full audit на material baseline; повторные проходы используют digest-bound evidence и режимы delta/gate-rebind | ⬜ к внедрению | **Критерий сработал:** swissknifeman `2026.08.02-PROVIDER-CONTRACT-LOCALE` P0 дошёл до третьего full audit (минимум 2 557 повторённых package tests), хотя attempt 3 заблокирован shared audit runtime, а не новым P0 product defect. |
| [`memory-recall-shared-namespace-priority.md`](memory-recall-shared-namespace-priority.md) | `_recall_union` (mid-session `maind_memory_recall`) не наследует D10 «shared по умолчанию не тянется» — тянет `ns:axioma` наравне с приватным scope, `RECALL_LIMIT=200` на каждый | ⬜ к внедрению | Измерено 2026-08-06 на Agelto: приватная память 2 записи vs `ns:axioma` 47; live-запрос «workflow» — 6/7 результатов и ~9,3 КБ ответа из axioma. Масштаб выгоды не подтверждён (частота вызовов `maind_memory_recall`/сессию не измерена) — см. §3 файла |

## Частично реализовано — остаток здесь

| Файл | Остаток | Статус | Критерий остатка |
|:--|:--|:--|:--|
| [`workflow-craft.md`](workflow-craft.md) | Активация конструктора (ч.1/1.5/1.6) внедрена SKM-ROADMAP-005. **Остаток — ч.2: fleet-синтез накопленных `plans/*/workflows/*.js` через analyst** | 🟡 остаток | 10+ полевых скриптов ИЛИ повтор «изобрели то, что уже было шаблоном» |
| [`skill-description-quality.md`](skill-description-quality.md) | Гейт триггер-фразы в `description` введён + blocker-набор (39 < 100 симв) починен (`2026.07.29-HARNESS-AGNOSTIC` P3.5). **Остаток — 69 длинных описаний без триггера** (унаследованный долг в `desc-trigger-burndown.txt`) и рычаг №4 владельца (сжатие ради слотов, D74 АРХИВНОГО плана `plans/archive/2026.07.25-ECO-OPT`) | 🟡 остаток | Следующая содержательная правка каждого скилла (one-way burn-down) ИЛИ решение владельца включить рычаг №4 |
| [`artifex-thin-wrapper.md`](artifex-thin-wrapper.md) | Тонкая обвязка исполнения планов (остаток поглощённого супервизор-трека `2026.07.18-FOREMAN`): каркас пакета, ядро fresh-session цикла, retry-лестница, run-folder, unattended-профиль, каналы эскалации, раскатка и пилот — 14 items донора без дома | 🟡 ровно остаток | N = 5 боевых exec-волн (`journal.jsonl`, класс НЕ синтетический) с суммарной долей вмешательств драйвера < 25 % (`2026.07.31-SKM-LEAN` D119; фикстурная волна P4.6 — 0/2 — в накопление не засчитывается) ИЛИ `decide` стал импортируемым модулем в `packages/**` ИЛИ измеренный выигрыш стоимости ≥2× против Workflow-марафона |
| [`2026.08.11-local-repair-vs-escalation-classifier.md`](2026.08.11-local-repair-vs-escalation-classifier.md) | Continue-first observations, автоматический local repair, block-candidate reducer, provider parity и installed attestation внедрены. **Остаток:** closed all-five repair-evidence carrier + enforcement вне `Files` и полевые метрики первых 10 repairs | 🟡 остаток | Следующая правка Files/diff gate закрывает продуктовый остаток; 10 полевых repairs закрывают measurement residue |
| [`2026.08.11-terminal-final-continuity-receipt.md`](2026.08.11-terminal-final-continuity-receipt.md) | Task-level terminal receipt, stale digest и `FINAL_BEFORE_TERMINAL_FORBIDDEN` внедрены. **Остаток:** transport lifecycle seam для 31+ s heartbeat, quiet preference, interrupted/resumed run и фактического запрета provider `final` | 🟡 остаток | Следующая правка harness/Codex/Claude terminal lifecycle обязана внедрить остаток поверх готового Task receipt |
| [`2026.08.14-p10.6-provider-final-incident.md`](2026.08.14-p10.6-provider-final-incident.md) | Agelto P10.6: provider многократно отправил `final` при active nonterminal plan-run, несмотря на Task receipt и явный запрет владельца; Swissknifeman/Artifex не владеет conversational final write-site | ⬜ к внедрению | Внешняя правка provider transport обязана добавить pre-final verifier с active run/receipt и proof-test на 40 границ turn; объединить с остатком `terminal-final-continuity-receipt` |
| [`2026.08.11-terminal-handoff-recommendation-receipt.md`](2026.08.11-terminal-handoff-recommendation-receipt.md) | Task receipt связывает exact `Next`, route, recommendation и handoff digest; команды и обе provider-проекции требуют точную метку. **Остаток:** runtime/harness проверка фактического final transcript | 🟡 остаток | Следующая правка terminal transcript/run-completion seam обязана валидировать receipt и не принимать краткий несовпавший final |
| [`2026.08.10-plan-evidence-anchor-audit-loop.md`](2026.08.10-plan-evidence-anchor-audit-loop.md) | Material-only candidate fingerprint и immediate-close regression внедрены. **Остаток:** полный spec→product→closure graph, ancestor/collision gates, closure deliverable proof и commit-qualified citations | 🟡 остаток | Следующая правка evidence topology должна реализовать оставшийся graph; audit-bookkeeping drift повторно чинить не нужно |

## Отложено — критерий не сработал

| Файл | Что | Критерий внедрения |
|:--|:--|:--|
| [`upstream-notify-diet-fork.md`](upstream-notify-diet-fork.md) | Систематическая миграция раздутых вендорных скиллов `notify` → `fork` (механизм есть, нужен критерий отбора + плейбук) | Любое из двух проверяемых событий: (а) item плана правит **тело** вендорного бандла со `strategy: notify` в `upstream.json` ради диеты; (б) `packages/skiller/scripts/update-upstreams.sh --check` показал дрейф апстрима у любого из шести раздутых `notify`-кандидатов §«Измеренный разрыв». Прежняя проза «диета-фаза упирается в notify-скилл» приведена к структурной форме `2026.07.31-SKM-LEAN` P7.3: сверка показала, что условие (а) фазой P3 того плана НЕ выполнено — правились `description`/`when_to_use`/`context: fork` (frontmatter), тела вендорных бандлов не трогались, а `context: fork` Claude Code — не `strategy: fork` skiller |
| [`plan-lesson-capture.md`](plan-lesson-capture.md) | Шаг протокола для находок владельца ПОСЛЕ закрытия item'а (`/task:plan-lesson`) | Повтор на ещё одном плане/проекте (пока один замер — `dterema` P6.2/P6.3) |
| [`plan-design-vs-exec-status-check.md`](plan-design-vs-exec-status-check.md) | Агент рекомендует `plan-design` вместо `plan-exec`, не проверив фактический статус фазы | Повтор на ещё одном плане/проекте (пока один замер — `insiders` P1) |
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
| `2026.08.10-plan-run-routing-blocked-terminal-loop.md` | `routing-rejected` стал durable nonterminal observation: не меняет state/attempt, не создаёт owner gate/return-loop; `plan-run` больше не пишет `blocked` на route preflight. Закрыто `2026.08.12-№1-TASK-RESILIENCE` P0.2/P0.3. |
| `2026.08.10-audit-before-close-phase-gate.md` | Lifecycle `terminal items → audit candidate → GREEN → phase close` реализован командами и fresh fingerprint gate; lint принимает `audit-phase` до формального close только когда все items фазы терминальны. Закрыто `2026.08.12-№1-TASK-RESILIENCE` P0.3. |
| `2026.08.09-plan-roadmap-batching-gate.md` | Design superseded более точной активной спекой `2026.08.11-roadmap-batch-selection-is-authoritative.md`; второй конфликтующий SSOT удалён. Snapshot сохранён в артефактах `2026.08.12-№1-TASK-RESILIENCE`. |
| `2026.08.10-adaptive-plan-governance.md` | Material-triggered `phase_audit_policy`, same-root audit-fixer, reducer-confirmed RED и material-only candidate устранили status-driven повторный audit. |
| `2026.08.11-codex-effective-route-observability.md` | Codex thread-state/argv adapters дают provider-bound route, unknown отделён как `ROUTE-UNVERIFIABLE`; caller self-attestation не допускает route. |
| `2026.08.12-task-installed-authority-frame-resolution.md` | `authority-frame.json` резолвится package-relative с installed-layout regression. |
| `2026.08.12-task-orchestration-negation-lint.md` | Shared line-scoped predicate различает explicit negation и positive workflow declaration в source и projections. |
| `2026.08.12-task-plan-run-installed-command-path.md` | `task.command_catalog.package_command_path()` резолвит inherited `plan-exec` в source и installed package без monorepo literal. |
| `2026.08.12-task-plan-run-terminal-delivery-gap.md` | Task-owned gap закрыт: subject-aware receipt, запрет restart terminal subject и installed version/command-digest attestation; внешний transcript seam ведут две terminal receipt записи выше. |
| `2026.08.12-task-v2-lint-closed-items-read-budget.md` | Next-item bundle/read-budget gate больше не блокируется historical closed siblings; target остаётся fail-closed. |
| `2026.08.12-terminal-deviation-repair-forward.md` | `validation-admission/v1`, green-only terminal evidence, mandatory `repair_exhausted` и route-run receipt не позволяют local prerequisite стать terminal deviation. |
| `2026.08.13-claude-code-launch-provenance-adapter.md` | Добавлены Claude session JSONL adapter и provider-neutral resolver; exact/undershoot/unverifiable различимы. |
| `2026.08.13-terminal-deviation-must-not-replace-repair.md` | Journal, lint и delivery требуют green всех Validation carriers до terminal result; D# сначала обновляет spec и не отменяет новый green. |
| `2026.08.13-p10.6-false-terminal-block.md` | Scope-aware block reducer и regression на broad PHPStan inventory удерживают in-scope acceptance в repair-forward. |
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
