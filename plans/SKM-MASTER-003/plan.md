# SKM-MASTER-003 — Финализация: per-project plan-система + хвосты с рецензией

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | SKM-MASTER-003 |
| Title | Финализация: per-project plan-система + хвосты с рецензией |
| Version | 1.0 |
| Status | 🟠 Done with deviations |
| Document Type | execution protocol |
| Authoring Model | fable |
| Last Updated | 2026-07-02 |
| Repository | academici/swissknifeman |
| Related Packages | task, skiller, harness, maind, analyst |
| Execution Mode | одна волна: цепочка P1 ∥ независимые P2-items / context-reset-safe |
| Target Operator Models | sonnet (exec), opus (design/audit) |
| Approval Owner | repository owner |

## 1. Context

Финализация после SKM-MASTER-002. Две части. (1) Фича «plan-система per-project» (P1):
планы Claude Code живут В ПРОЕКТЕ — ключ `plansDirectory` в settings.json раскатывается
тремя слоями (harness-ручка → maind-провижионер → skiller integrate), активный план
трекается файлом `plans/ACTIVE.md`, конвенция — hashed-блоком в CLAUDE.md, мост
встроенного plan mode → протокол — режимом `plan-design from-draft`, цикл владельца
«фаза → handoff → /clear» закреплён в командах и скилле; plan-protocol входит в CORE.
(2) Хвосты волн 1–4 SKM-MASTER-002 по проведённой рецензии — принятый набор из 9 items (P2).
Верифицированные факты: `plansDirectory` существует в settings.json Claude Code
(глобальный/проектный/локальный; относительный путь — от корня проекта); hook-события
ExitPlanMode НЕТ, официального registry активного плана НЕТ (доки 2026-06); команды
`/task:plan-*` уже CWD-relative, `plan-lint` монорепо-независим, плагин task авто-включён
в каждом проекте (`default_command_plugins`); скилл plan-protocol пока НЕ в CORE (доезжает
только с бакетом general). Календарные хвосты SKM-MASTER-002 (P8.5→P8.2–P8.4, P7.4)
остаются в том плане и сюда не переносятся. Раскатка фичи — пилот-сначала (D2).

## 2. Execution Rules

- Один item за раз; статус обновляется В ПЛАНЕ до завершения работы.
- Статусы — 6 канонических строк байт-в-байт (plan-protocol §5).
- План разошёлся с кодом → НЕ импровизировать, эскалировать (plan-protocol §8).
- После закрытия item/фазы — перезаписать `plans/SKM-MASTER-003/handoff.md` и прогнать
  `python3 packages/task/scripts/plan-lint.py plans/SKM-MASTER-003`.
- Не ломать инварианты монорепо: stdlib-only (никаких pip); merge-only запись в проекты;
  имена плагинов/бакетов не переименовывать (back-compat); зашитые пути maind в `.mcp.json`
  онбордженных проектов; сообщения die/warn на русском; атомарная запись JSON — core.io.
- **Правила волны:** агенты-исполнители НЕ трогают CHANGELOG.md (батч оркестратора),
  НЕ коммитят, НЕ используют perplexity-web; отчёты — с deviations; реконсиляция плана,
  plan-lint, CHANGELOG и коммиты — оркестратор.
- Порядок волны: цепочка P1 (P1.1 → P1.2/P1.4 → P1.3 → P1.5 → P1.6/P1.7 → P1.8 → P1.9)
  ∥ независимые P2.1–P2.9 (разные файлы; P2.9 — после P1.8, оба правят plan-protocol).
  Пилот P1.10 — после всего. P1 ∥ P2 — осознанное отклонение от phase-first
  (lint-WARNING допустим).
- `skiller registry` в волне — ОДИН сериализованный финальный прогон после P1.9/P2.3/P2.4
  (оркестратор); при одиночном исполнении item'а вне волны — гонять как обычно.
- CHANGELOG (пост-обработка оркестратора): корневой [Unreleased] (волна SKM-MASTER-003) +
  laravel-package@0.1.1 (P2.5) + maind (провижионеры).

## 3. Routing

Действуют дефолты SSOT-матрицы plan-protocol §7 (отклонений нет).

## 4. Phase Index & Status Board

| Phase | Title | Items 🟢/всего | Status |
|:--|:--|:--|:--|
| P1 | Plan-система per-project | 9/10 | 🟠 Done with deviations |
| P2 | Хвосты с рецензией | 6/9 | 🟠 Done with deviations |

## 5. Decision Log

| D# | Дата | Решение | Почему |
|:--|:--|:--|:--|
| D1 | 2026-07-02 | Хвосты SKM-MASTER-002: принят весь рекомендованный рецензией набор — T1, T2, T4, T5, T6а, T7, T13, R1 + T12-проверка (фаза P2) | рецензия «варианты + рекомендация» проведена; принятое покрывает реальные дефекты без спекулятивных фич |
| D2 | 2026-07-02 | Раскатка plan-системы — пилот-сначала: монорепо + azguard end-to-end; фан-аут на ~17 проектов потом одной командой `maind sync --only plans-dir,plans-doc` после зелёного пилота | не раскатывать непроверенное на всю экосистему; sync делает фан-аут одной командой |
| D3 | 2026-07-02 | plan-protocol → CORE_SKILLS девятым (резидентно ~+43 ток → ~705/750; тело on-trigger) | в типовом проекте команды /task:plan-* есть (task авто-включён), а SSOT-схем/шаблонов нет — скилл обязан доезжать без бакета general |
| D4 | 2026-07-02 | T8 (cost-enrichment USD) — отклонён | противоречит D6 SKM-MASTER-002: USD не считаем, сырые токены model-keyed |
| D5 | 2026-07-02 | T9 (статус «done кроме тайм-гейтового хвоста») — закрыт | уже решён follow-up-правилом волны 4 SKM-MASTER-002: «тайм-гейтовый Deliverable — отдельный item» (внесено в plan-design.md) |
| D6 | 2026-07-02 | T3 (per-workflow токены в run-report → analyst --by phase) — триггерный, в план не входит | триггер: после недели живых пилотных планов |
| D7 | 2026-07-02 | T6б (extension-point dev-loop.js/rules/tests.md) и T6в (flake PACKAGE_NAMESPACE) — триггерные, в план не входят | триггер T6б: второй случай потери специфики; триггер T6в: рецидив flake |
| D8 | 2026-07-02 | T10 (merge-вердикты 3 псевдо-overlap super-skill) и T11 (chatom .gitignore / run-report.env.ini) — решения владельца вне плана | требуют человеческого вердикта (эскиз топологии 45→~34; владелец chatom), не агентской работы |
| D9 | 2026-07-02 | Field-feedback пилота P1.10: F1/F2/F4 (дыры протокола — bootstrap-handoff, Next закрытого плана, Meta.Status при закрытии) починены оркестратором сразу пост-волной (plan-design.md, plan-close.md, plan_lint.py +2 теста); F3 (JSON `changed` у plans-dir) — deferred | прецедент волны 4 SKM-MASTER-002 (правки текстов команд по findings); F3 требует прокидывания stdout из run_capability — не текстовая правка |

## 6. Update Log

| Дата | Кто (role/model) | Что |
|:--|:--|:--|
| 2026-07-02 | issue-planner/fable | Bootstrap-транскрипция одобренного мастер-плана (~/.claude/plans/perplexity-snappy-platypus.md) в формат plan-protocol |
| 2026-07-02 | orchestrator/fable | Волна wf_f2230ded-396 исполнена (22 агента, 0 ошибок): P1.1–P1.9 закрыты исполнителями, P2.1–P2.9 закрыты исполнителями, closer зелёный (registry · budget 705/750 · upstreams 0 failed · bucket-audit CORE resident · все validate) |
| 2026-07-02 | orchestrator/fable | Реконсиляция P1.10 (пилот azguard 7/7, 🟠), фазы P1/P2 закрыты, план закрыт целиком: Meta.Status 🟠, ACTIVE.md → «—»; микрофиксы F1/F2/F4 по field-feedback пилота (D9) |
