> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: ai-agents
bucket: ai
version: 0.2.0
description: "Навигатор по справочнику построения AI-агентов (vendored super-skill get-zeked): паттерны агентов, MCP-серверы, RAG, координация субагентов, промпт-инжиниринг, деплой. Активируй при проектировании AI-агентов, создании MCP-серверов, RAG-конвейеров, оркестрации мультиагентных систем, оптимизации промптов."
risk: read
persona: architect
tags: [ai, agents, mcp, rag, orchestration, prompt-engineering, subagents]
requires: []
produces_for: []
---

# AI Agent Builder — навигатор

Тонкая обёртка над импортированным super-skill **get-zeked/ai-agent-super-skill** (vendored,
`strategy: fork`). Полный справочник (~2700 строк, 12 разделов + приложения) — в
[`references/source.md`](references/source.md). **Читай нужный раздел по требованию, не целиком** —
это сохраняет контекст (см. скилл `context-economy`).

> ⚠️ Идентификаторы моделей и pricing в справочнике — пример на 2026-06-11 (дата апстрима).
> Сверяйся с актуальным прайсом: https://www.anthropic.com/pricing. Текущие ID моделей — в скилле `claude-api`.

## Маршрутизация по [`references/source.md`](references/source.md)

| Задача | Раздел |
|:--|:--|
| Выбор паттерна, gap-анализ возможностей | §1 Gap Analysis |
| Паттерны архитектуры (ReAct, Plan-Execute, Reflexion, multi-agent) | §2 Agent Architecture & Design Patterns |
| Построить MCP-сервер | §3 MCP Server Development |
| Собрать RAG-конвейер | §4 RAG System Construction |
| Координация субагентов, worktree-изоляция | §5 Subagent Coordination |
| Планирование выполнения и верификация | §6 Execution Planning & Verification |
| Промпт-инжиниринг и оптимизация | §7 Prompt Engineering & Optimization |
| ML-интеграция в агентов | §8 ML Integration for Agents |
| Создание новых скиллов/возможностей | §9 Skill & Capability Creation |
| Бэкенд-инфраструктура агентов | §10 Backend Infrastructure for Agents |
| Деплой и мониторинг | §11 Agent Deployment & Monitoring |
| Возможности Perplexity Computer | §12 Unique Perplexity Computer Capabilities |
| Быстрый выбор паттерна · ADR · оценка MCP · типовые сбои | Приложения A–D |

## Сопровождение (для мейнтейнеров реестра)

Это форк: апстрим зеркалится в `references/source.md`, наши правки живут в этом SKILL.md.
Обновление — `scripts/update-upstreams.sh` (`--check` → при дрейфе `--apply` кладёт
`upstream/source.incoming.md` + ставит `review_pending`; перенеси нужное сюда и `--resolve`).
Детали — `docs/guide/upstream-sync.md`.
