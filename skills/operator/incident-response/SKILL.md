---
name: incident-response
bucket: operator
version: 0.1.0
description: Процесс реагирования на инциденты в проде — severity-уровни, роли (IC/Comms/SME), коммуникация, action log, переход к postmortem
risk: draft
persona: operator
tags: [incident, ops]
requires: []
produces_for: [postmortem]
outputs: ["docs/03_Dev/Incident_Response.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Incident Response

Применять когда: сервис работает в проде и стоит вопрос «как мы реагируем когда что-то ломается». Нужен документированный процесс — severity, кто принимает решения, как общаемся с пользователями, как фиксируем действия. Обычно — сразу после первого реального инцидента, либо когда команда выросла до 3+ инженеров.

Не применять: до прода, для прототипов, либо если уже есть зрелый incident management в материнской компании (наследуем оттуда).

---

## Когда НЕ применять

- Pre-prod / прототип — некого спасать
- Соло-разработчик без SLA — incident-response = «чиню когда замечу»
- Внутренний инструмент команды без зависимых пользователей
- Если уже есть корпоративный incident process — не дублировать, только адаптировать

---

## Шаг 1. Severity-уровни

| Severity | Описание | Пример | Реакция |
|:---:|:---|:---|:---|
| **SEV-1** | Полный outage критичного сервиса, потеря данных, security breach | Сайт не открывается, БД корраптится | Page всех on-call, IC назначен в 5 мин, статус-страница обновлена в 15 мин |
| **SEV-2** | Деградация значительной части пользователей / функций | Checkout не работает, 30% запросов 5xx | Page on-call, IC в 15 мин, статус обновлён в 30 мин |
| **SEV-3** | Деградация некритичной функции либо проблема для < 5% юзеров | Поиск медленный, фоновая job застряла | Тикет в очередь, разбираем в рабочее время |
| **SEV-4** | Косметика / single-user issue | Лейбл криво | Обычный bug-flow |

**Правило:** severity определяет **скорость**, не **важность**. SEV-3 баг может быть критичным для бизнеса, но это backlog, не инцидент.

---

## Шаг 2. Роли в инциденте

| Роль | Ответственность | Когда назначается |
|:---|:---|:---|
| **Incident Commander (IC)** | Принимает решения, не чинит сам. Координирует. | Сразу при объявлении SEV-1/2 |
| **Subject Matter Expert (SME)** | Тот, кто чинит. Может быть несколько. | По мере привлечения |
| **Communications Lead (Comms)** | Статус-страница, юзеры, внутренние стейкхолдеры | SEV-1, либо если инцидент > 30 мин |
| **Scribe** | Ведёт action log в реальном времени | SEV-1, опционально SEV-2 |

**Правило:** IC ≠ SME. Если человек чинит — он не может одновременно координировать. Для маленькой команды (≤ 3 чел) — IC и Comms может быть один.

---

## Шаг 3. Lifecycle инцидента

```
1. DETECT      — алерт сработал / юзер сообщил / увидели метрику
   ↓
2. DECLARE     — IC объявляет инцидент, severity, открывает channel
   ↓
3. INVESTIGATE — SME ищут root cause, IC координирует, Scribe пишет лог
   ↓
4. MITIGATE    — восстановили сервис (не обязательно вылечили — могли откатить, отключить фичу)
   ↓
5. RESOLVE     — корневая причина устранена либо подтверждено что митигация надёжна
   ↓
6. POSTMORTEM  — см. скилл postmortem (обязательно для SEV-1/2)
```

**Mitigate vs Resolve:** митигировали ≠ пофиксили. Откат деплоя — митигация, фикс бага в коде — resolve. Постмортем пишется после resolve.

---

## Шаг 4. Channels & communication

| Канал | Когда | Кто пишет |
|:---|:---|:---|
| `#incident-<id>` в Slack/Discord | SEV-1/2 — выделенный канал на инцидент | Все участники |
| Status page (statuspage.io / instatus / самописная) | SEV-1/2 — публичная | Comms Lead |
| Внутренняя рассылка / channel announce | SEV-1 — каждые 30 мин | IC |
| Postmortem doc | После resolve | Owner назначается IC'ом |

**Правило:** один источник правды — incident channel. Не плодим обсуждения в DM. Всё в канал.

**Шаблон статус-страницы:**
- `Investigating`: «We're aware of [problem] affecting [scope]. Investigating.»
- `Identified`: «Cause identified as [X]. Working on fix.»
- `Monitoring`: «Fix deployed. Monitoring.»
- `Resolved`: «Resolved at HH:MM. Postmortem to follow.»

---

## Шаг 5. Action Log

В incident channel — обязательно с таймстампами. Каждое действие, гипотеза, наблюдение.

```
14:32 [Алерт] api-5xx-rate > 5% за 5 мин
14:34 [IC] @anna объявляю SEV-2, IC=я
14:35 [SME] @boris посмотрю метрики api-server
14:38 [SME] boris: 5xx идут из /checkout, остальное ок
14:40 [Гипотеза] последний деплой 14:20 затронул checkout
14:42 [Действие] откатываю деплой → SHA abc123
14:45 [Митигация] 5xx упал до baseline
14:50 [Решение] оставляем откаченную версию, фикс отдельно
15:10 [Resolve] SEV-2 закрыт
```

Зачем: основа для postmortem, тайм-линия фактов без интерпретации.

---

## Шаг 6. Эскалация

**Critical decision: когда будить второго / третьего человека.**

| Условие | Действие |
|:---|:---|
| SEV-1 объявлен | Page primary on-call немедленно |
| Primary on-call не ответил за 15 мин | Page secondary |
| SEV-1 > 1 часа без митигации | Эскалация к management |
| Затрагивает legal / compliance / PII | Comms Lead уведомляет legal/security сразу |
| Требуется решение за пределами полномочий on-call (например, оплата сторонней услуги) | Эскалация к management |

---

## Что агент добавляет сам

- Чек-лист «первые 5 минут инцидента» для on-call (закреплён в Runbook'ах)
- Шаблон incident channel topic: `SEV-X | IC: @name | Status: investigating | Started: HH:MM`
- Рекомендация инструмента для page'инга (PagerDuty / Opsgenie / Grafana OnCall) — выбор по бюджету и стеку
- Предупреждение про blameless culture: в action log и постмортеме — действия и факты, не оценки людей
- Связка с архитектурными артефактами: каждый алерт должен ссылаться на runbook (см. `runbook`), runbook — на architectural context

---

## Структура output-файла `Incident_Response.md`

```markdown
# Incident Response Process: [ProjectName]

## 1. Severity matrix (SEV-1..4 с примерами под этот продукт)
## 2. Роли (IC/SME/Comms/Scribe) + кто может быть IC
## 3. Lifecycle (DETECT → POSTMORTEM)
## 4. Channels & communication (где что пишем)
## 5. Status page (URL + кто обновляет)
## 6. Escalation matrix (когда будим кого)
## 7. Action log template
## 8. Связь с on-call rotation и runbooks
```

---

## Жёсткие запреты

НЕЛЬЗЯ:
- IC одновременно фиксит руками (теряет координацию)
- Обсуждать инцидент в DM минуя channel (action log неполный)
- Объявлять SEV-1 без четких критериев (devalues severity)
- Закрывать инцидент без записи postmortem owner'а (SEV-1/2)
- Указывать вину людей в action log («Х накосячил») — только действия и факты
- Менять severity вниз без согласия IC (легко скрыть SEV-2 как SEV-3)
- Деплоить fix в прод без code review во время SEV-1 «потому что горит» (одна катастрофа порождает следующую) — кроме явных rollback'ов
