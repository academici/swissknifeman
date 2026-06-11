---
name: runbook
bucket: operator
version: 0.1.0
description: Шаблон operational runbook на каждый P1/P2-алерт — symptoms, диагностика, mitigation steps, escalation, post-actions
risk: draft
persona: operator
tags: [ops, incident]
requires: []
produces_for: [incident-response]
outputs: ["03_Dev/Runbooks/[AlertName].md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Runbook

Применять когда: появился алерт в проде, который может разбудить on-call. Каждый P1/P2-алерт **обязан** иметь runbook — иначе разбуженный в 3 ночи человек гадает что делать. Runbook = пошаговая инструкция от «увидел алерт» до «починил или эскалировал».

Не применять: для алертов которые не пейджатся (SEV-3/SEV-4 тикеты), либо для алертов которые планируется выключить (тогда — выключайте, а не пишите runbook).

---

## Когда НЕ применять

- Информационные алерты (notify-only) — runbook избыточен
- Алерты в стадии «настраиваем, проверяем что не шумит» — сначала валидируйте, потом runbook
- Алерты на single-user issue (это не runbook, это support flow)
- Если нет процесса incident-response — нет смысла, см. `incident-response` сначала

---

## Шаг 1. Один алерт = один runbook

**Не валим всё в один документ.** На каждый алерт — отдельный файл `03_Dev/Runbooks/<alert_name>.md`. Имя файла = имя алерта в системе (Prometheus rule name, Datadog monitor name, etc.). Это критично для on-call: алерт пришёл → ссылка на runbook прямо из page'а → один клик.

**Anti-pattern:** «общий runbook» с разделами на 30 алертов. Никто не будет в 3 ночи листать оглавление.

---

## Шаг 2. Структура runbook'а — обязательные секции

```markdown
# Runbook: <AlertName>

**Severity:** SEV-X
**Owner:** team / @person
**Last updated:** YYYY-MM-DD by @author
**Linked alert:** <ссылка на правило в Prometheus/Datadog/etc>

## Symptoms
Что видит юзер / что в дашборде. Чёткий критерий «это — оно».

## Likely causes
Топ-3 причины по частоте за последние N месяцев. Если новый алерт — гипотезы.

## Diagnostic steps
1. Открыть дашборд X → проверить Y
2. Запросить логи `query: ...`
3. Проверить статус апстрима / зависимости Z

## Mitigation
Что сделать чтобы юзеру стало лучше **сейчас**.
- Опция A: rollback deploy (команда: ...)
- Опция B: scale up replicas (команда: ...)
- Опция C: feature flag off (команда: ...)

## Verification
Как убедиться что mitigation сработал. Конкретный сигнал, не «посмотрите вроде ок».

## Escalation
Когда эскалировать и к кому.
- Если diagnostic не выявил причину за 15 мин → @team-X
- Если затронут платёжный flow → @payments + Comms Lead

## Post-actions
Что сделать **после** resolve:
- Открыть postmortem ticket (если SEV-1/2)
- Создать issue на root cause
- Записать в `tech-debt-audit` если структурная проблема
```

---

## Шаг 3. Diagnostic steps — что писать

**Правило:** конкретные команды, ссылки, queries — не «проверьте здоровье сервиса».

| Хорошо | Плохо |
|:---|:---|
| `kubectl get pods -n api -l app=checkout` | «посмотрите статус подов» |
| Открыть дашборд: <ссылка> панель "p99 latency" | «проверьте метрики» |
| Datadog: `service:checkout status:error` за 15 мин | «логи» |
| `psql -c "SELECT count(*) FROM jobs WHERE status='stuck'"` | «глянуть в БД» |

Если шаг требует доступа к prod — указать **какого уровня** доступ и что делать если нет (быстрый эскалейт).

---

## Шаг 4. Mitigation — приоритет реверсивности

Порядок предпочтения митигаций:

1. **Feature flag off** — мгновенно, реверсивно, не трогает деплой
2. **Rollback deploy** — быстро, относительно безопасно
3. **Scale (out/up)** — если capacity issue
4. **Hotfix** — последняя опция, повышает риск second-order incident

Для каждой mitigation:
- Команда / процедура (точно скопировать-вставить)
- Что подтверждает успех
- Что подтверждает провал → следующая опция

---

## Шаг 5. Поддержание актуальности

Runbook **протухает быстрее всего** в репозитории. Правила:

| Триггер | Действие |
|:---|:---|
| Использовали runbook в инциденте | После постмортема — review, update |
| Изменился сервис (новая зависимость, миграция) | Owner проходит свои runbooks |
| Алерт молчит > 6 мес | Review: всё ещё актуален? Возможно — удалить |
| Runbook не помог в инциденте | Постмортем явно указывает что fix'ить в runbook |

**Метрика здоровья:** % использований runbook'а где он реально помог (опрос после инцидента: helpful / partially / not at all).

---

## Шаг 6. Связь с алертом — операционная связка

Алерт **обязан** содержать ссылку на runbook в самом payload:

```yaml
# Prometheus alert example
- alert: HighErrorRate
  annotations:
    summary: "5xx rate > 5%"
    runbook_url: "https://github.com/org/repo/blob/main/03_Dev/Runbooks/HighErrorRate.md"
```

Без `runbook_url` алерт не должен пэйджить — это policy. CI проверка опционально (linter поверх Prometheus rules).

---

## Что агент добавляет сам

- Шаблон runbook (готовый markdown, скопировать-заменить)
- Связка с `incident-response`: указать в Runbook'е какие severity/IC роли применимы
- Подсказка по структуре каталога: `03_Dev/Runbooks/<AlertName>.md` (одно имя файла = одно имя алерта)
- Чек-лист «runbook ready»: есть symptoms / diagnostic ≥ 3 шагов / mitigation ≥ 2 опций / verification конкретный
- Предупреждение про PII в runbook'ах: не вставлять реальные пользовательские данные в примеры — только маски

---

## Структура output-файла `[AlertName].md`

См. Шаг 2 — это и есть структура файла. Файл назван по имени алерта:

```
03_Dev/Runbooks/
├── HighErrorRate.md
├── DatabaseConnectionsExhausted.md
├── PaymentWebhookFailure.md
└── _README.md  ← оглавление, кто owner, когда review
```

---

## Жёсткие запреты

НЕЛЬЗЯ:
- Pageable алерт без runbook'а (CI должен ловить — если есть)
- Один runbook на множество алертов («общий troubleshooting»)
- Diagnostic steps формата «погуглите» / «спросите архитектора»
- Mitigation без `verification` секции (как понять что починили?)
- Hotfix как первая опция mitigation (риск-проблема)
- Реальные PII / секреты в примерах команд
- Молчаливое устаревание: если runbook не трогали > 6 мес — review-метка
- Хранить runbook'и вне репо (Confluence-only, Notion-only) — теряются при ротации tooling
