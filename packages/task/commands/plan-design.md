---
description: "План-протокол: создать/детализировать мастер-план в plans/ — новый план, фаза Pn или ТЗ подпункта Pn.m. Пинит Opus/high."
argument-hint: "[new <название> | <PLAN-ID> [Pn[.m]]]"
model: opus
effort: high
---
Это ПРОЕКТИРОВАНИЕ мастер-плана (plan-протокол). Ввод пользователя: «$ARGUMENTS».
Модель/effort запинены (Opus/high) — не переключай вручную. SSOT протокола — скилл
`plan-protocol` (general): схемы, статусы, эскалация, routing-матрица; шаблоны — его
`snippets/{plan,phase,handoff}-template.md`. Ты пишешь план, который дешёвая модель
исполнит БЕЗ доступа к этому чату.

## Режимы (по $ARGUMENTS)

1. **`new <название>`** — новый план: выбери `PLAN-ID` (`[A-Z][A-Z0-9-]+`, напр. `AUDIT-W2`),
   создай `plans/<ID>/plan.md` по шаблону (все секции 0–6), скелеты фаз `plans/<ID>/phases/Pn.md`
   (Phase Context + Phase Status + items-скелеты с «—») и `handoff.md` (Next: первый item).
2. **`<PLAN-ID> Pn`** — спроектировать фазу: заполнить `## Phase Context` (5–10 строк,
   самодостаточно — фаза исполнима без чтения других фаз) и разложить на items
   `### Pn.m — Title` со всеми полями; синхронизировать Status Board в plan.md.
3. **`<PLAN-ID> Pn.m`** — довести один item до исполняемого ТЗ: дозаполнить все поля
   до уровня «sonnet исполнит без вопросов».

## Схема (компактная выжимка — на случай отсутствия скилла)

- `plan.md`: `## 0. Meta` (таблица: Plan ID / Title / Version / Status / Document Type /
  Authoring Model / Last Updated / Repository / Related Packages / Execution Mode /
  Target Operator Models / Approval Owner) · `## 1. Context` (5–15 строк, самодостаточно) ·
  `## 2. Execution Rules` (выжимка ≤20 строк) · `## 3. Routing` (ТОЛЬКО отклонения от
  SSOT-матрицы; пусто = дефолты) · `## 4. Phase Index & Status Board`
  (`Phase | Title | Items 🟢/всего | Status`) · `## 5. Decision Log`
  (`D# | Дата | Решение | Почему`) · `## 6. Update Log` (append-only: `Дата | Кто | Что`).
- `phases/Pn.md`: `# Pn — Title` → `## Phase Context` → `## Phase Status`
  (`ID | Title | Status | Updated`) → items → `## Phase Handoff`.
- Item: заголовок СТРОГО `### Pn.m — Title`; поля СТРОГО строками `**Поле:** значение`,
  в этом порядке: Status, Intent, Why, Scope Included, Scope Excluded, Inputs, Files,
  Required Reads, Implementation Rules, Code Guidance, Validation, Deliverables,
  Completion Notes, Pending Work, Known Deviations, Escalation Needed.
  Пустое значение — канонический символ «—» (не пустая строка, не «N/A»).
- Статусы — РОВНО 6 канонических строк, байт-в-байт:
  `⬜ Not started` · `🟡 In progress` · `🟢 Done` · `🟠 Done with deviations` ·
  `🔴 Blocked` · `⛔ Skipped by decision`.
- `handoff.md`: `# HANDOFF — <ISO-дата> — after Pn.m` + Next / Done / Remaining /
  Sources of truth / Open risks / Workarounds-Deferred-Open questions; перезаписывается целиком.

## Требования к качеству

- **Каждый item исполним sonnet'ом без доп. контекста**: Required Reads конечны и
  упорядочены (не «посмотри по репо»), **Code Guidance обязателен** (стиль решения,
  запреты, обязательные тесты, запрещённые shortcuts — то, что дешёвая модель не выведет
  сама), Validation — конкретные команды (что прогнать и что считается зелёным).
- **Спорные решения принимай сам** и фиксируй в `## 5. Decision Log` — НЕ выноси
  вопросами пользователю; правку плана отметь строкой в `## 6. Update Log`.
- Phase-first: items не прыгают между фазами; фазы закрываются последовательно.

## Финал

Прогони линтер: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plan-lint.py" plans/<ID>`
(переменная не задана или скрипта нет — предупреди и пропусти, не блокер).
Красное линтера почини в созданных файлах.

**Expected output:** список созданных/изменённых файлов + число items + строка
«Готово к: /task:plan-exec <ID> Pn.m».
