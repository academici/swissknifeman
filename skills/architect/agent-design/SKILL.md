---
name: agent-design
bucket: architect
version: 0.1.0
description: Проектирование агентов, agentic loop, tool contracts, harness, permission gates
risk: draft
persona: architect
tags: [agentic, architecture]
requires: [architecture]
produces_for: [eval-design]
outputs: ["docs/03_Dev/Agent_Design.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Agent Design

Применять когда: проектирование агента, agentic workflow, tool contracts, harness design, agentic loop audit, MVP agent blueprint.

---

## Предусловие

Агентная архитектура пишется **только после утверждённого BRD**. Если BRD нет — сначала прочитать `.ai/skills/pm/brd.md`. Для продуктов с PII/финансами — `.ai/skills/architect/security-design.md` параллельно.

---

## Ключевой принцип

> Модель **предлагает** действия. Harness — валидирует, авторизует, выполняет, фиксирует.

Модель не выполняет действия напрямую. Каждый tool call возвращает результат — даже если это отказ или ошибка.

---

## 7 Loop Invariants (обязательный checklist)

Agentic loop корректен, если выполнены все 7:

- [ ] **One-to-one** — каждый tool call возвращает ровно один result block
- [ ] **Pre-execution validation** — схема и параметры проверяются до выполнения
- [ ] **Permission gate** — рисковые действия проходят policy-check вне модели
- [ ] **Bounded results** — результаты инструментов ограничены по размеру
- [ ] **Hard budgets** — есть лимиты: шаги, токены, время, стоимость
- [ ] **Evidence-based conclusions** — финальный ответ подтверждён наблюдениями из loop, не предположениями
- [ ] **Structured failure** — ошибки и отказы структурированы и логируются

---

## Уровни автономии (выбрать до проектирования)

| Уровень | Режим | Когда использовать |
|:---|:---|:---|
| 0 | Answer-only | Только ответы, нет действий |
| 1 | Draft-only | Готовит, не отправляет |
| **2** | **Approval-gated** | **Default — действует после подтверждения** |
| 3 | Supervised autonomous | Автономно, с human review gate |
| 4 | Long-running autonomous | Полная автономия с checkpoint'ами |

**Правило:** по умолчанию Level 2. Переход на 3–4 только после доказанной надёжности на 2.

---

## MVP Blueprint — 15 компонентов

```
1.  Domain objective      — что агент делает и что не делает
2.  Autonomy level        — один из 0–4 (выбрать явно)
3.  Provider-neutral loop — модель подключена через контракт, не напрямую
4.  Typed tool registry   — каждый инструмент: схема + timeout + output limit
5.  Permission matrix     — allow / deny / ask_user / approval_required
6.  Structured results    — tool call всегда возвращает typed result
7.  Context architecture  — что входит в контекст, в каком порядке
8.  External memory       — хранение состояния вне разговора
9.  Auto-compaction       — сжатие контекста до превышения лимита
10. Planning mode         — approval-gated перед многошаговыми задачами
11. Goal-like loops       — checkpoints + measurable done condition
12. Skills/connectors     — внешние API подключены как typed skills
13. Cost-aware layout     — stable prefix + кэш-оптимизированный порядок
14. Observability         — traces: operational events, не reasoning
15. Evals                 — тесты harness, не только модели
```

---

## Tool & Permission Design

**Risk taxonomy для инструментов:**

| Класс | Примеры | Политика |
|:---|:---|:---|
| read-only | поиск, чтение файлов, metadata | allow |
| write-local | создание файлов, черновики | allow |
| write-external | email, webhook, push | approval_required |
| financial | платёж, транзакция | approval_required + audit |
| destructive | удаление, drop, wipe | ask_user |

**Draft-commit pattern** — обязателен для financial / destructive / regulated:

```
draft_action() → preview → user_confirm() → commit_action()
```

Параллельность: только независимые read-only операции. Writes, sends, deletes — всегда последовательно.

---

## Cost & Caching

- **Stable prefix** — system prompt + статичные инструкции идут первыми (кэшируются)
- **Dynamic suffix** — история разговора в конце (не кэшируется)
- **Append-only history** — не перестраивать историю, сохранять cache reuse
- **Deterministic tool order** — порядок инструментов в схеме не меняется
- **Budget limits** — все 4 типа обязательны: step_limit, token_limit, time_limit, cost_limit

---

## Pre-launch Checklist

```
Безопасность:
- [ ] Тест prompt injection (внешний контент как данные, не инструкция)
- [ ] Тест approval bypass (попытка пропустить permission gate)
- [ ] Тест context overflow (поведение при переполнении)
- [ ] Secrets не попадают в context модели

Надёжность:
- [ ] Traces и evals определены до деплоя
- [ ] Shadow mode / limited rollout на первом релизе
- [ ] Cost telemetry работает
- [ ] Structured errors для всех tool failures

Качество:
- [ ] Eval покрывает: injection, misuse, bypass, overflow
- [ ] Harness тестируется независимо от модели
```

---

## Формат agentного раздела в Architecture doc

Добавить секцию `## Agent Design` в `docs/03_Dev/Architecture_[Name].md`:

```markdown
## Agent Design

### Уровень автономии
[Level X: описание]

### Tool Registry
| Tool | Класс риска | Схема | Timeout | Output limit |
|:---|:---|:---|:---|:---|

### Permission Matrix
| Действие | Политика | Условие |
|:---|:---|:---|

### Loop Budget
- step_limit: N
- token_limit: N
- time_limit: Xs
- cost_limit: $N

### Context Architecture
[Что в system prompt, что в history, что из внешней памяти]
```

---

## Жёсткие запреты

НЕЛЬЗЯ:
- Давать модели прямой доступ к execute без harness
- Параллелить write/send/delete операции
- Запускать на Level 3–4 без проверенного Level 2
- Хранить secrets в context модели
- Деплоить без traces и evals
- Оставлять budgets неопределёнными

---

## Референс

`https://github.com/DenisSergeevitch/agents-best-practices` — полные reference files: agentic-loop, tools-and-permissions, mvp-blueprint, security-evals, prompt-caching, workflow-orchestration.
