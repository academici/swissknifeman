# SKM-AUDIT-004 — Аудит и стабилизация swissknifeman перед stable-тегом

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | SKM-AUDIT-004 |
| Title | Аудит и стабилизация перед stable-тегом |
| Version | 0.1.0 |
| Status | 🟡 In progress |
| Document Type | Executable Master Plan |
| Authoring Model | fable |
| Last Updated | 2026-07-07 |
| Repository | swissknifeman (монорепо academici) |
| Related Packages | maind, skiller, harness, analyst, task, core |
| Execution Mode | phase-first |
| Target Operator Models | sonnet (exec) · haiku (LOW) · opus (review/audit/analysis) |
| Approval Owner | Dmitry Vostrikov |

## 1. Context

За 3 дня (2026-07-04..07) в main влито 17 коммитов (~1120 строк, 37 файлов) —
диапазон `ea8e4d3..HEAD` (base = merge PR #136). Писали дешёвые модели: фичи
doctor --skill-drift / --vendor-drift (fleet-проверки), run-report хук → авто
`analyst digest` (петля обучения), фиксы maind `_ensure_project` / skiller
`topology init` / analyst «сигнал A», расширения plan-протокола (пакет task).
Нужен независимый аудит перед тегом стабильной версии: (1) code review диффа —
корректность + соответствие философии корневого CLAUDE.md (stdlib-only, дедуп
в core/, детерминированная генерёжка, провенанс); (2) полировка репо (docs
drift: пакет `packages/task` не описан в корневом CLAUDE.md); (3) анализ
накопленной статистики онбордженных проектов (~17, analyst/maind) на предмет
токен-экономии — известный сигнал: CORE-резидент превышает
RESIDENT_BUDGET_TARGET (`skiller budget --check-core`); (4) аудит
permissions-слоя: perplexity-web промптит в проектах несмотря на глобальный
allow, safe-dirs (harness) — сквозная проверка; цель — минимум промптов.
Финал — stable-тег (только с approve человека).

## 2. Execution Rules

- Один item за раз; статус обновляется В ПЛАНЕ до завершения работы.
- Статусы — 6 канонических строк байт-в-байт (см. plan-protocol §5).
- План разошёлся с кодом → не импровизировать, эскалировать (§8).
- После закрытия item/фазы — перезаписать plans/SKM-AUDIT-004/handoff.md.
- **P1 — read-only**: находки пишем в `plans/SKM-AUDIT-004/findings/`, код НЕ
  правим (все фиксы — P2). Severity-enum находок: `blocker | major | minor | nit`.
- Формат находки: `severity · file:line · суть · сценарий отказа/репро`.
- Внешние факты (семантика настроек Claude Code, API) — верифицировать через
  RAG (context7 → perplexity-web), не по памяти (методология корневого CLAUDE.md).
- Коммиты — Conventional Commits на русском, мелкими порциями по смыслу.
- Перед любым коммитом кода: validate.sh затронутого пакета зелёный.

## 3. Routing

| Item | Model/Effort | Почему |
|:--|:--|:--|
| P1.2 | opus/xhigh | adversarial-ревью кода дешёвых моделей — вердикт-фаза |
| P1.3 | opus/high | вердикт соответствия философии/архитектуре |
| P3.2 | opus/high | синтез рекомендаций по статистике |
| P4.1 | opus/high | диагностика конфликта настроек — тонкая семантика precedence |

Остальное — дефолты SSOT-матрицы plan-protocol §7.

## 4. Phase Index & Status Board

| Phase | Title | Items 🟢/всего | Status |
|:--|:--|:--|:--|
| P1 | Ревью трёхдневного диффа (read-only) | 3/3 | 🟢 Done |
| P2 | Фиксы находок и полировка репо | 3/3 | 🟢 Done |
| P3 | Статистика проектов и токен-экономия | 3/3 | 🟢 Done |
| P4 | Permissions-слой: perplexity-web и safe-dirs | 3/3 | 🟢 Done |
| P6 | Laravel PAO: обязательная установка на PHP-проекты | 3/4 | 🟠 Done with deviations |
| P5 | Релиз: CHANGELOG и stable-тег | 1/2 | 🟡 In progress |

## 5. Decision Log

| D# | Дата | Решение | Почему |
|:--|:--|:--|:--|
| D1 | 2026-07-07 | Plan ID SKM-AUDIT-004 — продолжение нумерации SKM-MASTER-002/003 | единый ряд планов репо |
| D2 | 2026-07-07 | Ревью двухступенчатое: механические гейты (sonnet) отдельно от adversarial-вердикта (opus/xhigh); фиксы вынесены в P2 | ревью остаётся read-only, дешёвая механика не тратит opus-контекст |
| D3 | 2026-07-07 | node_modules в packages/analyst — НЕ находка: devDependency VitePress (docs), задокументирован в package.json, git status clean ⇒ gitignored | ложный сигнал исходного запроса; проверка .gitignore остаётся в P1.1 |
| D4 | 2026-07-07 | Релиз — последняя фаза (P5), после P3/P4 | фиксы permissions-слоя (harness) должны войти в stable-тег |
| D5 | 2026-07-07 | Надёжность моста perplexity-web (profile lock, таймауты deep) — вне scope | внешний сервер, не этот репо; P4 — только permission-промпты |
| D6 | 2026-07-07 | Из P3 внедряем только safe quick-wins (P3.3); крупные оптимизации — в roadmap/ | философия репо: спекулятивное не внедряем на упреждение |
| D7 | 2026-07-07 | Смена Active: — → SKM-AUDIT-004 | новый план создан |
| D8 | 2026-07-07 | Добавлена фаза P6 (Laravel PAO) по field-feedback: онбординг Agelto прошёл GREEN, но `laravel/pao` не установлен. **Порядок:** P6 логически ПЕРЕД финалом P5 — фикс токен-экономии должен войти в stable-тег; выпустить раньше — только отдельным follow-up patch-тегом. Решение — за Approval Owner | дыра контракта «доставка скилла ≠ установка зависимости»; PAO — прямая токен-экономия, baseline для PHP |
| D9 | 2026-07-07 | Laravel PAO и Laravel Boost — РАЗНЫЕ независимые пакеты, не смешивать. Boost = MCP-сервер инспекции (у нас только MCP, без скиллов); PAO = обёртка вывода инструментов (токен-экономия). P6 — про PAO; orphaned `laravel-boost` MCP-запись в Agelto — отдельная гигиена (P6.4, помечена как не-PAO) | исходная подмена PAO↔Boost едва не увела фазу; RAG-верификация (блог laravel.com + скилл repo) развела |
| D10 | 2026-07-07 | Эскалация P6.4 разрешена по варианту (a): миграция тест-стека Agelto (pest v3→v4 + phpunit v11→v12) вынесена из scope swissknifeman как задача владельца Agelto; P6.4 закрыт 🟠 Done with deviations, P6 терминальна (4/4), путь к P5 разблокирован | Контракт репо по P6 выполнен (install-шаг P6.2 + doctor-гейт P6.3 под тестами; fleet-скан затронул только Agelto; Boost-гигиена закрыта). Блокер PAO в Agelto — внутренняя миграция потребителя, вне контракта тулинга; P5 (релиз swissknifeman) от неё не зависит. Держать фазу заблокированной на внешнем проекте нарушает phase-first и «не проектируем под внешнее состояние». Deviation зафиксирован, follow-up отслеживается как owner-task |
| D11 | 2026-07-07 | Эскалация P5.1 разрешена: Approval Owner напрямую убрал строку `"Read(**/CHANGELOG.md)"` из `permissions.deny` в `.claude/settings.local.json`. Read CHANGELOG.md подтверждён рабочим; P5.1 разморожен → `⬜ Not started` | Deny-строка блокировала Required Read/Edit CHANGELOG.md для P5.1 (конфликт правил); соседствовала в списке с генерируемыми/шумными файлами (skills.json, *.lock), а не секретами — сужение/снятие не задевает философию репо (stdlib-only, дедуп в core/ и т.д.) |
| D12 | 2026-07-07 | Фиксы P3.3/P4.3/P6.2/P6.3 (Update Log считал «закрытыми») оказались незакоммиченными в рабочем дереве при старте P5.1 — докоммичены 4 коммитами по смыслу перед CHANGELOG (шаг 1 release-discipline: коммит фикса до CHANGELOG), без нового кода | Не архитектурный вопрос (код уже написан и провалидирован в своих item'ах, эскалация не triggers-enum), а мехническое довыполнение release-discipline; иначе тег ставился бы поверх незакоммиченного кода |

## 6. Update Log

| Дата | Кто (role/model) | Что |
|:--|:--|:--|
| 2026-07-07 | plan-design/fable | План создан (5 фаз, 14 items), ACTIVE → SKM-AUDIT-004 |
| 2026-07-07 | plan-exec/sonnet | P2.3 закрыт: финальный прогон всех 9 гейтов P1.1 зелёный, регрессий нет; фаза P2 терминальна (3/3) |
| 2026-07-07 | plan-exec/sonnet | P3.1 закрыт: findings/P3-stats.md собран (4 таблицы), read-only подтверждён; CORE-резидент 705/750 (OK, сигнал плана устарел) |
| 2026-07-07 | plan-exec/sonnet | P3.2 закрыт: findings/P3-recommendations.md (R1–R6); единственный quick-win — R1 (текст CLAUDE.md skiller), R3/R4-гипотезы P3.1 перепроверены и сняты как non-issue |
| 2026-07-07 | plan-design/opus | Спроектирована фаза P6 (Laravel PAO, 4 items): root-cause + install-шаг онбординга + doctor-гейт + fleet-ремонт. Диагноз verified (WebFetch блога PAO + скилл repo + состояние Agelto: PHP ^8.4, скилл доставлен, `vendor/laravel/pao` нет). Код не тронут — только plan-артефакты |
| 2026-07-07 | plan-exec/sonnet | P3.3 закрыт: R1 внедрён (`packages/skiller/CLAUDE.md`, 8→9 CORE_SKILLS + `plan-protocol`, устаревшая фраза «резидент превышает target» поправлена); R6 материализован `roadmap/analyst-fleet-coverage.md`; резидент 705/750 → 705/750 (без изменений, ожидаемо); фаза P3 терминальна (3/3) |
| 2026-07-07 | plan-exec/sonnet | P4.1 закрыт: findings/P4-perplexity.md собран, две независимые первопричины подтверждены репро (`claude mcp list` × 7 проектов) — Класс A (плагинный `core` дублирует perplexity-web под именем `plugin_core_perplexity-web`, mismatch с user-scope allow) и Класс B (project-scoped `.mcp.json`-сервер вечно `Pending approval` фактически на всём флоте); фаза P4 стартовала (1/3) |
| 2026-07-07 | plan-exec/sonnet | P4.2 закрыт: findings/P4-safedirs.md собран, вердикт (a)–(d) OK/не-проявлено, покрытие флота 18/19 (vintera/vintera — hook отсутствует, но это yolo-пресет bypassPermissions, не дефект); активных фиксов для P4.3 по safe-dirs нет |
| 2026-07-07 | plan-exec/sonnet | P4.3 закрыт: оба класса (A/B) устранены одним изменением `settings.global.json` (allow `mcp__plugin_core_perplexity-web` + top-level `enabledMcpjsonServers: ["perplexity-web"]`, семантика верифицирована context7) + один прогон `harness permissions --global`; apply-permissions.sh получил union-merge для `enabledMcpjsonServers` + тест; репро на 4 проектах (botkit/flexcrm/agelto/dterema-app): `⏸ Pending` → `✓ Connected`; фаза P4 терминальна (3/3) |
| 2026-07-07 | plan-exec/sonnet | P6.1 закрыт: findings/P6-pao.md собран (F-pao-1/2 major, F-pao-3 nit), repro Agelto подтверждён напрямую (PHP 8.5.8, `vendor/laravel/pao` нет, скилл доставлен, orphaned `laravel-boost` MCP-запись зафиксирована для P6.4); read-only, код не тронут; фаза P6 стартовала (1/4) |
| 2026-07-07 | plan-exec/sonnet | P6.2 закрыт: новый провиженер `maind/lib/maind/pao.py` (детект по файловым фактам + `php -v`) подключён шагом `pao` в `provision/onboard.py`; интерактивно предлагает `composer require laravel/pao --dev`, на `--yes`/неинтерактиве — громкий warn, не молчаливая установка; opt-out `project.pao_opt_out`; decision-tree получил секцию «PHP-инструменты: PAO»; F-pao-3 исправлен (`nunomaduro/pao`→`laravel/pao`, внешне верифицировано WebSearch) в SKILL.ru.md/SKILL.md, `skiller registry` прогнан; 11 новых тестов, maind 370/370 и validate.sh обоих пакетов зелёные; фаза P6 (2/4) |
| 2026-07-07 | plan-exec/sonnet | P6.4 эскалирован: fleet-скан `maind doctor --audit pao` (20 проектов) показал только Agelto без PAO, остальные PHP-проекты флота уже `pao✓`; Boost-гигиена Agelto закрыта (`laravel/boost:^2.4` установлен по решению владельца); установка `laravel/pao` в Agelto упёрлась в реальный каскад зависимостей (pest ^3.8→^4.6 требует phpunit ^11.5→^12.5) — связная мини-миграция тест-стека Agelto, не предвиденная диагностикой P6.1; эскалировано на `/task:plan-design SKM-AUDIT-004 P6.4`, фаза P6 остаётся 🟡 (3/4) |
| 2026-07-07 | plan-exec/sonnet | P6.3 закрыт: F-pao-2 устранён — новое измерение `pao` в fleet-audit (`maind doctor --audit pao\|all`, `analysis/audit.py`), переиспользует `pao.status()` из P6.2 (детект-логика не задублирована); печатает `pao⚠(missing: composer require laravel/pao --dev)` для php/laravel-проекта без PAO, `pao✓`/`pao·<state>` для installed/n-a/opt-out/php-too-old; help-текст `doctor.py --audit` расширен; 6 новых тестов (mock `pao._php_version`, без реального composer/php), maind 376/376 и validate.sh зелёные; фаза P6 (3/4) |
| 2026-07-07 | plan-design/opus | Эскалация P6.4 разрешена (D10, вариант a): миграция тест-стека Agelto вынесена из scope как owner-task, P6.4 закрыт 🟠 Done with deviations, Escalation снят; фаза P6 терминальна (4/4 🟠), Status Board и Phase Handoff синхронизированы, handoff.md → Next P5.1. Код и target-репо не тронуты (только plan-артефакты) |
| 2026-07-07 | plan-exec/sonnet | P5.1 эскалирован: Required Read «существующий CHANGELOG» упёрся в `permissions.deny` (`.claude/settings.local.json`) — `"Read(**/CHANGELOG.md)"` блокирует Read и транзитивно Edit/Write CHANGELOG.md; обход через Bash/Grep не предпринимался (нарушил бы дух настройки). Эскалировано на `/task:plan-design SKM-AUDIT-004 P5.1`, фаза P5 🔴 Blocked (0/2) |
| 2026-07-07 | Approval Owner | Эскалация P5.1 разрешена (D11): deny-строка `Read(**/CHANGELOG.md)` убрана владельцем напрямую из `.claude/settings.local.json`; Read CHANGELOG.md подтверждён рабочим. P5.1 разморожен → `⬜ Not started`, эскалация снята, фаза P5 → `⬜ Not started` (0/2), готова к обычному `/task:plan-exec SKM-AUDIT-004 P5.1` |
| 2026-07-07 | plan-exec/sonnet | P5.1 закрыт (D12): докоммичены недостающие фиксы P3.3/P4.3/P6.2/P6.3 (4 коммита), `CHANGELOG.md` `[Unreleased]` дополнен 6 группами записей, `skiller registry` идемпотентен (207/53), финальный прогон всех 9 гейтов P1.1/P2.3 на итоговом HEAD — 🟢 PASS; findings/P5-release.md — паспорт релиза, предложена версия v0.8.0; фаза P5 (1/2 🟡), следующий item — P5.2 (approve владельца + тег) |
