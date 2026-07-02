# SKM-MASTER-002 — Операционная система планов, телеметрия и специализация стеков

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | SKM-MASTER-002 |
| Title | Операционная система планов, телеметрия и специализация стеков |
| Version | 1.0 |
| Status | 🟡 In progress |
| Document Type | execution protocol |
| Authoring Model | fable |
| Last Updated | 2026-07-02 |
| Repository | academici/swissknifeman |
| Related Packages | task, skiller, harness, maind, analyst, core |
| Execution Mode | phased / context-reset-safe |
| Target Operator Models | sonnet (exec), opus (design/audit) |
| Approval Owner | repository owner |

## 1. Context

Финализируем операционную модель монорепо: «сильная модель проектирует, дешёвая исполняет»,
утечки токенов видимы и анализируемы, generated-ассеты защищены от молчаливых правок,
стек-паки соответствуют типу проекта (боль: azguard/chatom — Laravel-ПАКЕТЫ, а reviewer
у них app-ориентированный). Восемь фаз: P1 — plan-протокол (скилл + plan-lint + 4 команды
/task:plan-*); P2 — токен-телеметрия end-to-end (run-report SCHEMA=2, core/usage.py, тренд);
P3 — каталог патологий и детекторы (core/pathology.py, Detect ≠ Gate); P4 — analyst learning
loop (token-report, агент-аналитик, proposals); P5 — защита generated-ассетов (provenance-header,
drift-детект, base+overlay); P6 — отдельный стек-пак laravel-package + пилоты azguard/chatom;
P7 — bucket-аудит и разгрузка монолитов (thin-navigator); P8 — rollout и глобальная приёмка.
Волны исполнения: 1 — P1/P2/P5 параллельно; 2 — P3 (после P2) и P6 (после P5);
3 — P4 (после P2+P3) и P7; 4 — P8. Основа — foundation-draft
`research/swissknifeman_master_plan_v2.md`, проработанный Explore/Plan-агентами и
верифицированный RAG 2026-07-02. Первый шаг исполнения — транскрипция этого плана
в `plans/SKM-MASTER-002/` (dogfooding формата).

## 2. Execution Rules

- Один item за раз; статус обновляется В ПЛАНЕ до завершения работы.
- Статусы — 6 канонических строк байт-в-байт (plan-protocol §5).
- План разошёлся с кодом → НЕ импровизировать, эскалировать (plan-protocol §8).
- После закрытия item/фазы — перезаписать `plans/SKM-MASTER-002/handoff.md` и прогнать
  `python3 packages/task/scripts/plan-lint.py plans/SKM-MASTER-002`.
- Не ломать инварианты монорепо: stdlib-only (никаких pip); merge-only запись в проекты;
  lock schema 1 — только аддитивно; имена плагинов/бакетов не переименовывать (back-compat);
  зашитые пути maind в `.mcp.json` онбордженных проектов; читатели run-report SCHEMA=1
  не должны ломаться; privacy analyst (сырьё LOCAL, наружу — числа/абстракции);
  хуки никогда не роняют сессию.
- Каждая фаза закрывается по release-discipline: validate.sh затронутых пакетов →
  `skiller registry` → CHANGELOG [Unreleased] → PR (Conventional Commits, на русском).
- Сообщения die/warn — на русском; атомарная запись JSON — через core.io.
- Использованные внешние источники отмечать в docs/reference.md.

## 3. Routing

Действуют дефолты SSOT-матрицы plan-protocol §7 (отклонений нет). Items, помеченные
«⭐ strong-model» в Implementation Rules, исполняются opus-исполнителем через plan-design.

## 4. Phase Index & Status Board

| Phase | Title | Items 🟢/всего | Status |
|:--|:--|:--|:--|
| P1 | Plan-протокол (фаза A) | 7/10 | 🟡 In progress |
| P2 | Токен-телеметрия end-to-end (фаза B) | 5/5 | 🟢 Done |
| P3 | Каталог патологий и детекторы (фаза C) | 0/4 | ⬜ Not started |
| P4 | Analyst learning loop (фаза D) | 0/3 | ⬜ Not started |
| P5 | Generated Asset Protection (фаза E) | 4/7 | 🟡 In progress |
| P6 | laravel-package stack + пилоты (фаза F) | 0/9 | ⬜ Not started |
| P7 | Bucket optimization (фаза G) | 0/6 | ⬜ Not started |
| P8 | Rollout & Acceptance (фаза H) | 0/4 | ⬜ Not started |

## 5. Decision Log

| D# | Дата | Решение | Почему |
|:--|:--|:--|:--|
| D1 | 2026-07-02 | Мастер-планы живут в `plans/` в корне монорепо; research/ остаётся скретчпадом | планы — исполняемые артефакты, не черновики |
| D2 | 2026-07-02 | Носитель протокола — расширение task-плагина + скиллы skiller, не новый пакет | границы команд = границы model/effort-профилей; пакет уже есть |
| D3 | 2026-07-02 | Формат планов — чистый Markdown (MD-only), без sidecar JSON | двойная запись агентом = неизбежный дрейф; JSON — производный `plan-lint --json` |
| D4 | 2026-07-02 | Файл-на-фазу: `plan.md + phases/Pn.md + handoff.md` | plan-exec грузит ~3 компактных файла, не монолит |
| D5 | 2026-07-02 | plan-exec самозакрывающийся: обновление плана + handoff + lint — часть исполнения | «сделал, но не записал» = незавершённое исполнение |
| D6 | 2026-07-02 | USD НЕ считаем — сырые токены model-keyed | прайс-хардкод протухает; токены — стабильная единица регрессий |
| D7 | 2026-07-02 | Телеметрия local-first JSONL, без OTel в этой волне | минимум механики, stdlib-only, приватность |
| D8 | 2026-07-02 | core/usage.py вендорится в хук копией `_usage.py` + sync-скрипт + cmp-гейт в validate | хук обязан работать без чекаута монорепо; дрейф ловит гейт |
| D9 | 2026-07-02 | Detect ≠ Gate: патологии дают ATTENTION/info, никогда не RED | RED зарезервирован за упавшими проверками |
| D10 | 2026-07-02 | Provenance-header детерминированный, БЕЗ timestamp; хеш считается ВМЕСТЕ с header | иначе strip-логика в 4 местах и слом инварианта disk_sha==base_sha256 |
| D11 | 2026-07-02 | Extension zones = base+overlay (user_owned rules-файлы), НЕ зоны в шаблонах | ноль новой механики; бинарное правило «файл не трогай, пиши в тот» для cheap-моделей |
| D12 | 2026-07-02 | Отдельный пак `laravel-package`, не bool-режим backend-laravel | bool-режим уже выпилен в 0.9.0; у reviewer заменяется ~60% тела |
| D13 | 2026-07-02 | Монолиты → thin-navigator + references/full.md, НЕ резка на подскиллы | резка растит tier-0; перевод on-trigger→on-demand экономит ~240K токенов |
| D14 | 2026-07-02 | P7 НЕ переименовывает/не сливает бакеты; для будущего — alias-механизм | 13 проектов на marketplace-канале: rename ломает enabledPlugins |
| D15 | 2026-07-02 | Пилоты rollout — azguard + chatom | оба Laravel-пакеты (главная боль), живые проекты с телеметрией |
| D16 | 2026-07-02 | Агент-аналитик digest-first: скрипты дают JSON, raw-транскрипты агенту запрещены | токен-экономия; агент делает только то, что скрипты не могут |

## 6. Update Log

| Дата | Кто (role/model) | Что |
|:--|:--|:--|
| 2026-07-02 | issue-planner/fable | Bootstrap-транскрипция одобренного мастер-плана в формат plan-protocol (item P1.5) |
| 2026-07-02 | orchestrator/fable | Реконсиляция статусов волны 1 по факту validate.sh-зелёных прогонов: P1.1–P1.7 → 🟢 Done (P1 остаётся 🟡, хвосты P1.8–P1.10); P2 целиком → 🟢 Done (Phase Handoff заполнен); P5.1–P5.4 → 🟢 Done, P5.5 → 🟠 Done with deviations (P5 остаётся 🟡, P5.6–P5.7 не исполнялись) |
