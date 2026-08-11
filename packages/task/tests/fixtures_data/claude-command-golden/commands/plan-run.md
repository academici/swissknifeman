---
description: "План-протокол: исполнить item Pn.m под моделью/effort ТЕКУЩЕЙ СЕССИИ (модель НЕ пинится) — для серии Exec=manual item'ов без ритуала /model+/effort на каждом."
argument-hint: "<PLAN-ID> Pn.m [Pn.k]"
---
Это ИСПОЛНЕНИЕ item'а мастер-плана под моделью сессии (D18) — третий режим `plan-exec`,
БЕЗ пина `model`/`effort`: они наследуются из настроек текущей сессии владельца.
Ввод пользователя: «$ARGUMENTS».

## DecisionRequest и isolated-child-return (P6.3)

Свободная проза не является каналом уточнения или авторизации. Когда дальнейший шаг требует
недостающего факта либо права действия, команда строит transient action по
`decision-request` v1, передаёт его единственному резолверу `task.plan_authority.authorize()` и
исполняет закрытый исход: `delegated` — продолжить только exact canonical action;
`approval_required` — материализовать `DecisionRequest` через `plan-decisions.py request` и
припарковать subject; `denied` — записать отказ и остановиться. Durable request всегда несёт
continuation identity, timeout из authority frame и объявленные варианты `escalate`/`reject`.
Уточнение авторазрешимо только закрытым allowlist систем-записей с provenance; после ответа intent
канонизируется и классифицируется заново. Модельная память, чат и свободный текст не дают approval.

Модельное суждение выполняется только как provider-neutral `isolated-child-return`: после risk
trigger либо повторного durable fingerprint root строит закрытый capsule `return-judgement` v1,
проверяет capability, независимо выбирает свежего reviewer с actor/context, отличными от executor,
и делает ровно один вызов. Full parent transcript, unrelated history, self-review и второй sample
запрещены. Capability absence даёт `cold-start-root: capability-missing`. Reviewer применяет
неизменяемый ассет `return-judgement@1.0.0`
(`packages/task/prompts/return-judgement-rubric-v1.md`,
SHA-256 `63323e5565fa2c321354e36ebe47624f37f86c3c3372ba01efaedcc61b6c2e1e`); root валидирует schema,
передаёт запись детерминированному reducer и продолжает исходный run. Неоткалиброванная пара
`model_id × rubric_sha256` и order-sensitive swap трактуются как `INSUFFICIENT_EVIDENCE`.
Raw provider flags допустимы только в additive adapter/projection.

**Путь чтения делегируемого item.** Сначала прочитай поле `Layout` в `## 0. Meta`; по дереву
файлов раскладка НЕ выводится. `Layout` отсутствует → v1: `plan.md` (Context, Execution Rules,
§3 Routing и Status Board) → `handoff.md` → `phases/Pn.md` (Phase Context + выбранный item) →
Required Reads в объявленном порядке. `Layout: v2` → РОВНО пять обязательных слотов:

1. `plans/<PLAN-ID>/plan.md` — identity, Context, Execution Rules и §3 Routing;
2. `plans/<PLAN-ID>/phases/<Pn>/<Pn>.md` — только Phase Context;
3. `plans/<PLAN-ID>/phases/<Pn>/<Pn.m>.md` — полное ТЗ выбранного item;
4. `plans/<PLAN-ID>/bundles/<Pn.m>.json` — объявленные digest-qualified inputs;
5. `plans/<PLAN-ID>/phases/<Pn>/<Pn.m>.state.md` — byte-fresh item state.

В v2 `handoff.md` НЕ входит в обязательный путь: состояние выбранного item берётся только из
fresh item state. Повторное чтение запрещено.

Прочти `packages/task/commands/plan-exec.md` ЦЕЛИКОМ и исполни его пункты 1–8 ДОСЛОВНО,
с ТРЕМЯ отличиями:

- Модель/effort НЕ запинены: действуют настройки сессии владельца.
- **Pre-mutation/Pre-final write-site (P2.7/P2.11).** В оба вызова
  `route_evidence.capture_actual(...)` передавай ТОЛЬКО `model_class`/`effort`/`model`,
  подтверждённые provider environment API (`source="provider-doctor"`). Если API не аттестует
  хотя бы нужную ось, запиши `capture_actual(None, None, source="self-attested")` и остановись
  до мутации: selector/actor/текст команды не подменяют actual evidence. Шаг остаётся
  ОБЯЗАТЕЛЬНЫМ в обеих точках `plan-exec.md`; `plan-run` меняет источник actual-route, не
  условия предиката. **Основание (D75, лестница
  разрешения маршрута исполнителя):** `plan-run` исполняет и закрывает item в ОДНОЙ сессии,
  поэтому её «фактический маршрут сессии» И ЕСТЬ маршрут исполнителя — на pre-final замена
  литерала остаётся верной той же логикой, что и на pre-mutation, без отдельной лестницы
  Completion Notes↔journal (та лестница нужна только реконсилирующему `plan-close`, который
  закрывает item, которого сам не исполнял).
- Routing-гейт п.2 инвертирован: сверяется ФАКТИЧЕСКАЯ модель/effort сессии с §3 Routing
  item'а (тир-порядок — plan-protocol §9). Недобор (модель или effort НИЖЕ предписанного)
  → ДО journal start напечатай exact legal route/continuation для этого item'а и останови
  только текущий dispatch; product status и journal НЕ меняются. Перебор → исполнять, запись в Known Deviations (§6
  `plan-exec.md`). Exec = plan-design → СТОП, ре-дизайн.
  Routing reject до product work не является attempt и не создаёт `blocked`/`routing-blocked`
  event: route correction — dispatch evidence, а не исход продукта.

**Граница честности.** Самоатрибуция модели/effort агентом не является доказательством (класс
B2 аудита REGHUB). Без provider-attested API отчёт обязан нести `Session: unknown/unknown`
с `source=self-attested`; запрещено подставлять selector или актор. Жёсткий машинный гейт
остаётся за `plan-exec` — `plan-run` этот гейт НЕ заменяет, только снимает ритуал ручного
переключения модели/effort перед серией manual-item'ов под одной моделью.

Всё остальное (эскалация, validation, топология закрытия, status-rule, якорь дерева,
launch-block) — БЕЗ ИЗМЕНЕНИЙ из `plan-exec.md`; повторно здесь не транскрибируется
(правило двух SSOT).

Каждая journal-запись, которую `plan-run` наследует из `plan-exec.md`, передаёт тот же
`--session-id "$(python3 packages/task/scripts/plan-session.py current --id)"`; resolver обязан
найти ровно один provider adapter, иначе append не выполняется. Это provider-neutral правило:
raw runtime identity принадлежит только adapter'у, а не canonical command. Перед start вычисли
`run_id = task.journal.derive_run_id(plan_id, item_id, attempt, session_id)` и передай тот же
непустой `--run-id` в start и terminal; повторный terminal close возвращает существующий pointer
и не дописывает journal.
