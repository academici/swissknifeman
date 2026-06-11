---
name: postmortem
bucket: operator
version: 0.1.0
description: Blameless postmortem после SEV-1/2 инцидента — таймлайн, root cause (5 Whys), contributing factors, action items, дистрибуция знаний
risk: draft
persona: operator
tags: [incident, ops]
requires: [incident-response]
produces_for: []
outputs: ["03_Dev/Postmortems/[YYYY-MM-DD]_[ShortName].md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Postmortem

Применять когда: инцидент SEV-1 или SEV-2 закрыт (`incident-response` → RESOLVE), и требуется зафиксировать **что произошло, почему, и что меняем**. Постмортем — обязательная часть incident lifecycle, не опциональная.

Не применять: для SEV-3/4 (избыточно), либо когда инцидент явно повторяет уже разобранный кейс (вместо нового PM — обновить старый + action items).

---

## Когда НЕ применять

- SEV-3/4 (тикет в backlog достаточно)
- Повторение уже разобранного инцидента — обновить существующий PM + поднять unresolved action items
- Внешний инцидент (vendor outage) без нашей реакции — короткая заметка достаточна
- «Near miss» который остался незамеченным юзерами — опционально, но обычно полезно

---

## Шаг 1. Blameless principle

Постмортем разбирает **системы и процессы**, не людей. Запрещено:
- Указывать конкретное имя как root cause («Alice deployed broken code»)
- Формулировки «должен был знать», «следовало проверить»
- Personal performance discussion (это отдельный канал)

Разрешено:
- Описывать действия людей нейтрально («engineer deployed»)
- Обсуждать что в системе сделало эту ошибку возможной (отсутствие staging, нет canary, нет смоук-тестов)

**Цель:** второй такой же инцидент должен быть невозможен независимо от того, кто на смене.

---

## Шаг 2. Структура — обязательные секции

```markdown
# Postmortem: <ShortName> — <Date>

**Severity:** SEV-X
**Duration:** HH:MM (от detect до resolve)
**Impact:** N users affected, $X revenue lost / Y errors / Z downtime min
**Owner:** @person
**Status:** Draft / In Review / Finalized

## Summary
2-3 предложения. Что произошло, какой эффект, что починили.

## Timeline (UTC)
| Time | Event | Source |
|:---|:---|:---|
| HH:MM | Алерт сработал | PagerDuty |
| HH:MM | IC объявлен | #incident-N |
| HH:MM | Гипотеза X | log message |
| HH:MM | Rollback deploy abc123 | git log |
| HH:MM | 5xx нормализовался | dashboard |
| HH:MM | SEV закрыт | IC |

## Root Cause
Что **на самом деле** сломалось. Технический + системный уровень.
**Технический:** запрос N+1 в новой версии checkout-service вызвал DB connection pool exhaustion.
**Системный:** PR прошёл review без нагрузочного теста; staging не имел нагрузки приближённой к prod.

## Contributing Factors
- Не было canary deployment
- Алерт на connection pool сработал с задержкой 8 мин (порог слишком высокий)
- Runbook DatabaseConnectionsExhausted указывал на старую процедуру

## What went well
- IC объявлен быстро
- Rollback сработал чисто
- Comms обновляли status page вовремя

## What went poorly
- Не было canary → весь трафик ушёл на сломанную версию
- Runbook устарел → SME 5 мин искал актуальную команду
- Юзеры узнали раньше из Twitter, чем мы со statuspage

## Action Items
| Action | Owner | Due | Priority |
|:---|:---|:---|:---|
| Включить canary deployment | @bob | 2 weeks | P1 |
| Снизить порог alert N | @anna | 1 week | P1 |
| Update runbook DatabaseConnectionsExhausted | @carol | 3 days | P2 |
| Add staging load test для checkout | @bob | 1 month | P2 |

## Lessons
1-3 урока в формате «правила». Подходят для перенесения в `tech-debt-audit` если структурные.
```

---

## Шаг 3. Root Cause Analysis — 5 Whys (или вариант)

Не останавливаемся на первом «why» — копаем до системы.

**Пример:**
1. Why: чекаут падал в 5xx → connection pool исчерпан
2. Why: pool исчерпан → новый код делал N+1 запрос
3. Why: код прошёл review → нагрузочного теста не было, на small dataset N+1 не виден
4. Why: нет нагрузочного теста → staging-окружение без realistic data volume
5. Why: staging без volume → исторически dev-only, не дотянули до prod-parity

**Правило:** ≥ 3 уровней «why», иначе action items получатся косметическими.

**Альтернатива:** Fishbone diagram, Causal map — для очень сложных multi-system инцидентов.

---

## Шаг 4. Action Items — критерии качества

Каждый AI обязан иметь:
- **Owner** (один человек, не «команда»)
- **Due date** (конкретная, не «когда сможем»)
- **Priority** (P1 = до следующего деплоя, P2 = в этот квартал, P3 = backlog)
- **Verifiable** — как поймём что сделано

**Anti-pattern AI:**
- «Будем внимательнее» (не verifiable)
- «Документировать процесс» (нет owner'а / due)
- «Обсудить с командой» (это не action)

**Правило:** AI без owner+due — это не AI, это wish. Возвращаем в черновик.

---

## Шаг 5. Review process

| Этап | Кто | Срок |
|:---|:---|:---|
| Draft | IC или назначенный owner | 48 часов после resolve |
| Internal review | Тех. команда | 1 неделя |
| Cross-team broadcast (если impact > одной команды) | Owner | 2 недели |
| Action items tracked | Owner + team lead | До закрытия всех P1 |

**Опубликовать постмортем:** в репо (этот скилл), и линкнуть в incident channel. Search-able. Не Notion-only, не «потерялось в Slack».

---

## Шаг 6. Метрики постмортем-процесса

| Метрика | Цель | Что значит превышение |
|:---|:---|:---|
| Drafted within 48h | ≥ 90% | Процесс умирает |
| Action items P1 closed within deadline | ≥ 80% | AI пишутся «на бумаге» |
| Repeat incidents same root cause | < 10% | Lessons не работают |
| Postmortem reviewed by ≥ 2 people | 100% | Нужен внешний взгляд |

---

## Что агент добавляет сам

- Шаблон Markdown готов к копированию
- Подсказка по naming convention файла: `YYYY-MM-DD_<ShortName>.md` (хронологическая сортировка)
- Импорт action items в issue tracker — оставить hook (не делаем сами, но в шаблоне есть ссылка-якорь)
- Связка с `tech-debt-audit`: lessons формата «структурная проблема» → строки в Tech_Debt_Register с импактом high
- Связка с `runbook`: если runbook устарел / отсутствовал → AI на update/create runbook
- Чек-лист blameless: проверить что в timeline нет имён в негативном контексте, нет формулировок «должен был»

---

## Структура output-файла `[YYYY-MM-DD]_[ShortName].md`

См. Шаг 2 (полная структура). Папка:

```
03_Dev/Postmortems/
├── 2025-03-14_checkout-5xx.md
├── 2025-04-02_payment-webhook-down.md
└── _index.md  ← перечень + статус action items
```

---

## Жёсткие запреты

НЕЛЬЗЯ:
- Указывать конкретное имя как root cause / contributing factor
- Закрывать SEV-1/2 без постмортема (process violation)
- Action items без owner+due+priority
- Action items уровня «be more careful» / «communicate better»
- Прятать постмортем во внутреннем чате — обязательно в репо
- Финализировать без хотя бы одного external reviewer (минимум 2 глаза)
- Игнорировать `What went well` — это часть культуры, без неё постмортем становится только наказанием
- Закрывать постмортем без 5 Whys (или альтернативного RCA метода) до структурного уровня
