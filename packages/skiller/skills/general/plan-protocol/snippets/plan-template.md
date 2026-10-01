# Шаблон plan.md — скопировать в plans/<PLAN-ID>/plan.md

Скелет мастер-плана по протолу `plan-protocol`. PLAN-ID нового плана —
`<ГГГГ>.<ММ>.<ДД>-№<N>-<КОДОВОЕ-ИМЯ>` (напр.),
где `N` — положительный номер, уникальный внутри даты; Title начинается с
`План №N — …`. Старые датовые и `[A-Z][A-Z0-9-]+` IDs сохраняются только для
back-compat. Новый план получает Meta `Short ID | PLAN<N>`: постоянный номер по репозиторию,
включая архив, независимо от дневного №N. Внешние ссылки: `PLAN<N>.D35`, `PLAN<N>.P2.3`;
правило назначения и legacy fallback — `references/work-references.md`.
Номера не выдумывать и не считать вручную: `python3 packages/task/scripts/plan-id.py --codename <КОДОВОЕ-ИМЯ>`
(сканирует `plans/` и `plans/archive/`) отдаёт готовые `plan_id`, `title_prefix` и `short_id` — подставить как есть.
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
| Short ID | PLAN<следующий свободный номер по репозиторию> |
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

<ПОСТРОЧНОЕ покрытие всех items. Batch/Review обязательны: `solo` только с конкретной
причиной; связные adjacent items одной фазы группировать, если общий контекст экономит
повторное чтение/setup/validation. Группа не пересекает audit/close и не смешивает Exec.
Review выбирается по конкретному item risk или прямому требованию владельца: неизвестность
сначала собирает evidence и не превращается автоматически в full. По умолчанию Review=`none`;
независимое ревью — отдельный пункт `Ревью Pn` (read-only, verdict-файл) в конце фазы, у большой
фазы — срезами. Не пиши `Independent review` в Validation пункта.
Только semantic classes `economy|implementation|frontier`, не provider selectors.
Design finish поднимает batch до максимума class/effort/review и фиксирует
exact admission в `roadmap.md` execution sheet.>

| Batch | Items | Model class/effort | Exec | Review | Почему |
|:--|:--|:--|:--|:--|:--|
| B1 | <Pn.m> | <implementation/high> | manual | none | recommended: <low-risk; self-check + affected tests; общие reads/setup> |
| B1 | <Pn.(m+1)> | <implementation/high> | manual | light | recommended: <bounded integration seam требует targeted review> |
| solo | <Pn.k> | <frontier/high> | plan-exec | full | <названный security/public/irreversible risk или owner requirement> |

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
