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
| [`codex-publication-consumer-acceptance.md`](codex-publication-consumer-acceptance.md) | Изолированный гейт `source → marketplace → install/cache → clean consumer → fresh session` для Codex plugins + circuit breaker item-исполнения | ⬜ к внедрению | Сработал (azguard 2026-07-21: формальный GREEN при пустых скиллах новой сессии). **Решение владельца 2026-07-25:** оформить item'ом плана (ECO-OPT P7.3 либо AGENT-RELIABILITY) — гейт трогает publication-поверхность, которую AR перестраивает; смежно AR P1/P3.4 (self-host canary, consumer-запись исключена) |
| [`2026.07.29-launch-block-command-row.md`](2026.07.29-launch-block-command-row.md) | launch-block: команда — последняя строка таблицы параметров, отдельный code-block с голым промптом — только при отклонении от стандартного маршрута | ⬜ к внедрению | Сработал (2026-07-29: двукратная неверная выдача в одной сессии из-за конструкции формата). Готово к оформлению отдельным маленьким планом, независимым от `HARNESS-AGNOSTIC` |
| [`codex-skill-listing-fallback-overflow.md`](codex-skill-listing-fallback-overflow.md) | Девять из десяти поставляемых профилей превышают фолбэк-бюджет обнаружения Codex (8 000 симв) — рычаги 1–3 владельца (D74) сузку Claude-оси уже сняли, Codex не закрывают | ⬜ к внедрению | Сработал (замер `2026.07.29-HARNESS-AGNOSTIC P3.4`, `artifacts/P3-skill-listing-budget.md`, WARN-гейт `validate.sh` §17). Решение владельца между Codex-специфичным профилем / принятой деградацией / отложить до живого прогона Codex CLI (OQ-7, D29) |

## Частично реализовано — остаток здесь

| Файл | Остаток | Статус | Критерий остатка |
|:--|:--|:--|:--|
| [`plan-audit-loop.md`](plan-audit-loop.md) | Правила остановки аудита внедрены (`packages/task/commands/plan-audit.md`: две ступени, порог severity, потолок 2 раунда). **Остаток — детерминированная CLI-ступень** `plan-lint --conflicts` (машинная сверка трёх SSOT перед дорогим проходом) | 🟡 остаток | Ручной конфликт-скан повторно съедает opus-раунды — тогда механизируем |
| [`workflow-craft.md`](workflow-craft.md) | Активация конструктора (ч.1/1.5/1.6) внедрена SKM-ROADMAP-005. **Остаток — ч.2: fleet-синтез накопленных `plans/*/workflows/*.js` через analyst** | 🟡 остаток | 10+ полевых скриптов ИЛИ повтор «изобрели то, что уже было шаблоном» |
| [`mcp-config-example-emit.md`](mcp-config-example-emit.md) | Эмит `.mcp.json.example` + ведение `.gitignore` реализованы **opt-in** (`mcp.emit_example`). **Остаток — default-on** | 🟡 остаток | Повторная утечка абс.путей/секретов ИЛИ внешний разработчик не поднял MCP без `.example`. Файл также — якорь ссылки из `.claude/skills/project-tooling-runbook` (не трогать до AR P1) |

## Отложено — критерий не сработал

| Файл | Что | Критерий внедрения |
|:--|:--|:--|
| [`upstream-notify-diet-fork.md`](upstream-notify-diet-fork.md) | Систематическая миграция раздутых вендорных скиллов `notify` → `fork` (механизм есть, нужен критерий отбора + плейбук) | Диета-фаза упирается в notify-скилл, который жалко сжимать без гарантии сохранности |
| [`skill-description-quality.md`](skill-description-quality.md) | Гейт триггер-фразы в `description` (134/207 скиллов без явного «Use when») | Рычаг **№4** по решению владельца (ECO-OPT D74): включается, только если рычаги 1–3 листинговой гигиены (ECO-OPT P3.1/P3.5) переполнение не сняли |
| [`analyst-plan-scan.md`](analyst-plan-scan.md) | `analyst digest` читает Known Deviations/Pending Work закрытых `plans/*` как источник уроков | ≥2–3 плана с содержательными Known Deviations — ручной просмотр перестаёт масштабироваться |
| [`analyst-fleet-coverage.md`](analyst-fleet-coverage.md) | Покрытие analyst-цикла по флоту: хук `run-report` включён у 5/20 проектов, analyst-state — 2/20 | Осознанное решение по umbrella-политике хуков на чужих проектах (не одностороннее включение) |
| [`plan-lesson-capture.md`](plan-lesson-capture.md) | Шаг протокола для находок владельца ПОСЛЕ закрытия item'а (`/task:plan-lesson`) | Повтор на ещё одном плане/проекте (пока один замер — `dterema` P6.2/P6.3) |
| [`plan-design-vs-exec-status-check.md`](plan-design-vs-exec-status-check.md) | Агент рекомендует `plan-design` вместо `plan-exec`, не проверив фактический статус фазы | Повтор на ещё одном плане/проекте (пока один замер — `insiders` P1) |
| [`playwright-mcp-output-dir.md`](playwright-mcp-output-dir.md) | `--output-dir` в шаблоне `.mcp.json` + пиновка версии: скриншоты с явным `filename` мусорят в корне | Повтор на ещё одном проекте ИЛИ решение владельца внедрить сразу (правка одной строки) |
| [`skill-rules-sidecar.md`](skill-rules-sidecar.md) | Генерируемый `skill-rules.json` сайдкар для роутинга скиллов | Замеренные мис-активации скиллов (нативной автозагрузки обычно достаточно) |
| [`project-freshness-agent.md`](project-freshness-agent.md) | Агент освежения проекта (дрейф стека/конвенций против реестра) | Реальный случай, где устаревшее знание проекта привело к ошибке ревью/разработки — не на упреждение |
| [`context-notify-tmp-cleanup.md`](context-notify-tmp-cleanup.md) | Стартовая уборка `context-notify.sh` не чистит осиротевшие `*.tmp` (3/40 SIGKILL-прогонов, ECO-OPT P6.1) | Следующая содержательная правка того же скрипта |
| [`instruction-authorize-order.md`](instruction-authorize-order.md) | Order-sensitivity `apply_instructions` к порядку `--authorize` (алфавитный по `target_path`) + неинформативная диагностика `INSTRUCTION_WRITE_FORBIDDEN` (`2026.07.29-HARNESS-AGNOSTIC` D84) | Следующий ложный отказ ИЛИ следующая содержательная правка `apply_instructions` |

## Входы активных планов (не трогать вне их items)

| Файл | Роль | План |
|:--|:--|:--|
| [`cross-machine-memory.md`](cross-machine-memory.md) | Постановка «память между машинами» (D12 CONTEXT-ECONOMY) | вход **ECO-OPT P4** (ADR + remote-host режим maind) |
| [`2026.07.25-memory-hub-service.md`](2026.07.25-memory-hub-service.md) | Хаб-как-сервис: авторизация по scope, раздача конфигов — тяжёлая часть, ВНЕ скоупа P4 | смежно **ECO-OPT P4** (P4 делает только подготовку); критерии активации — в самом файле §12 |
| [`codex-subagent-offload.md`](codex-subagent-offload.md) | `openai/codex-plugin-cc`: разгрузка квот + кросс-модельное ревью | вход **ECO-OPT P7** (Codex как второй водитель) |

## Отклонено решением

| Файл | Что | Решение |
|:--|:--|:--|
| [`otel-preset.md`](otel-preset.md) | OTEL-пресет harness (opt-in телеметрия Claude Code) | ⛔ Skipped by decision (D7, CONTEXT-ECONOMY P5.4) — стаб; строка вердикта в [`docs/rejected-optimizations.md`](../docs/rejected-optimizations.md). Вернуться при реальном коллекторе |

## Закрыто и удалено (2026-07-25)

Спеки реализованы; текст — в git-истории, ТЗ и решения — в закрывших планах.

| Спека | Где живёт результат |
|:--|:--|
| `agent-command-router-hook.md` | `packages/harness/configs/claude-code/hooks/agent-router/` + `harness router` + провиженер `router-config` в `maind sync` |
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

## Принцип

Не внедрять спекулятивно. Каждый пункт включается **по факту измеренной проблемы**, а не «на
вырост» — это прямое следствие гейтов `anti-drift`/`code-simplifier` и анти-bloat-политики репо.

Сами «измерения» ловит скилл `field-feedback-loop` (`.claude/skills/`): отклонение, пойманное
в полевой работе над проектом, он либо чинит сразу (очевидный баг), либо оформляет сюда спекой
с критерием внедрения (новое/сомнительное) — чтобы специфика проектов не терялась.
