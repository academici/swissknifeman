# Шаблон plan.md — скопировать в plans/<PLAN-ID>/plan.md

Скелет мастер-плана по протолу `plan-protocol`. PLAN-ID нового плана —
`<ГГГГ>.<ММ>.<ДД>-№<N>-<КОДОВОЕ-ИМЯ>` (напр. `2026.08.12-№1-TASK-RESILIENCE`),
где `N` — положительный номер, уникальный внутри даты; Title начинается с
`План №N — …`. Старые датовые и `[A-Z][A-Z0-9-]+` IDs сохраняются только для
back-compat. В кодовых/docstring/PR/review комментариях item ссылается полной
формой `<PLAN-ID> Pn.m`; голый `Pn.m` допустим только внутри носителей самого плана.
Хранимый формат — только Markdown с жёсткими маркерами; JSON — производный
артефакт парсера, не источник истины.

Развилка дизайна живёт в секции `## Обсуждение` (провенанс: варианты + обязательный
статус — `Exploration` / `Decision pending` / `Resolved → D#`); всё, что НЕ `Resolved`,
дополнительно ведётся в `plans/<PLAN-ID>/open-questions.md` (трекер незакрытого);
протокол — SKILL раздел 3.
Неоднозначность в тексте — маркер `[NEEDS CLARIFICATION: <вопрос>]` (раздел 7).

```markdown
# <PLAN-ID> — План №N — <Title>

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | <PLAN-ID> |
| Title | План №N — <краткое имя плана> |
| Layout | v2 |
| Version | 0.1.0 |
| Document Type | Executable Master Plan |
| Authoring Model | frontier |
| Repository | <repo> |
| Related Packages | <pkg1, pkg2> |
| Execution Mode | phase-first |
| Target Operator Classes | implementation (exec) · economy (LOW) · frontier (design/audit) |
| Approval Owner | <человек, утверждающий план> |
| Home | repo:<repository> |
| visibility | <необязательное: private ИЛИ public, дефолт private; public → в git только публичная выжимка, SKILL раздел 4> |
| supersedes | <необязательное: старый PLAN-ID, чью волну трека сменяет план; предшественник в plans/archive/> |
| Paused By | <необязательное: PLAN-ID перехватившего ACTIVE + дата; заполняет plan-design new; нет — «—»> |

## 1. Context

<5–15 строк: что делаем и почему. Самодостаточно — исполнитель НЕ видит
обсуждение, в котором план родился.>

## 2. Execution Rules

<Выжимка ≤20 строк + план-специфичные отклонения. Полный протокол — скилл
plan-protocol; не копировать его целиком. Минимум:>
- Один item за раз; статус обновляется В ПЛАНЕ до завершения работы.
- Статусы — 6 канонических строк байт-в-байт (см. plan-protocol §5).
- План разошёлся с кодом → не импровизировать, эскалировать (§8).
- После закрытия item/фазы — перезаписать plans/<PLAN-ID>/handoff.md.

## 3. Routing

<ТОЛЬКО отклонения от SSOT-матрицы plan-protocol §9. Пусто = дефолты SSOT-матрицы §9.>

| Items | Model class/effort | Exec | Почему |
|:--|:--|:--|:--|
| <Pn.m–Pn.k> | <frontier/high> | manual | <расфриз public-контракта: effort high+ MANDATORY> |
| <Pn.m–Pn.k> | <implementation/low> | plan-exec | <doc-cleanup без новых решений> |

## 5. Decision Log

Каталог решений: `decisions/`; собрать:
`python3 packages/task/scripts/plan-views.py decisions`.

## 6. Update Log

| Дата | Кто (role/model) | Что |
|:--|:--|:--|
| <YYYY-MM-DD> | issue-planner/frontier/high | План создан |

## 7. Contracts

<ОПЦИОНАЛЬНАЯ: только у планов, экспортирующих/потребляющих замороженные контракты.
Не экспортируешь и не потребляешь — секцию УДАЛИ (её отсутствие не дефект).>

### Exported

| Контракт | Версия | Статус | Потребители | Уведомлены |
|:--|:--|:--|:--|:--|
| <root/contracts/<name>.md> | v1.0.0 | frozen | <PLAN-ID (Pn.m)> | <YYYY-MM-DD> |

### Consumed

| Контракт | Донор-план | Pinned | Замечено | Реакция |
|:--|:--|:--|:--|:--|
| <DONOR/root/contracts/<name>.md> | <DONOR-ID> | v1.0.0 | — | — |

## Обсуждение

<ОПЦИОНАЛЬНАЯ, БЕЗ номера, последней секцией. Развилок нет — секцию УДАЛИ.>

### 1 — <развилка одной строкой>

- **(рекоменд.) Вариант A.** Плюсы … Минусы …
- **Вариант B.** Плюсы … Минусы …

**Статус:** Resolved → D# | Decision pending (нужен владелец) | Exploration
```
