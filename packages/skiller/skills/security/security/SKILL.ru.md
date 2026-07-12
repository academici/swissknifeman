> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: agent-security-super-skill
bucket: security
version: 0.1.0
description: AI agent security: prompt injection defense, skill/plugin validation, memory poisoning prevention, permission auditing, tool-use safety, exfiltration prevention, incident response. Use when installing skills, processing untrusted content, auditing permissions, validating memory, reviewing MCP configs, or hardening agents.
license: MIT
metadata:
  author: get-zeked
  version: '1.0'
adapters: [claude, cursor, fable]
sha256: ""
---

# Супер-скилл безопасности агентов — навигатор

Оборонительный плейбук безопасности для AI-агентов (Claude Code, Codex, Cursor,
Copilot, любая автономная система на базе LLM). Полное операционное
руководство (~102KB) — чек-листы, паттерны детекции/regexp, процедуры
реагирования — в [`references/full.md`](references/full.md). Этот файл — только
навигатор.

**Правило:** открывай `references/full.md` точечно — один раздел на конкретный
вопрос. Никогда целиком: не влезет в разумный контекстный бюджет.

> **Связанное:** дизайн-тайм secure-by-design / threat modeling —
> `architect/security-design` (этот скилл — про run-time / agent-ops).

## Карта разделов ([`references/full.md`](references/full.md))

| Задача | Раздел |
|:--|:--|
| Типы атак, матрица severity, sleeper/zombie-агенты, Rule of Two | §1 Threat Model Overview |
| Чек-листы детекции по типу контента, протокол до обработки, red-flag фразы, spotlighting | §2 Content Ingestion Defense |
| Чек-лист аудита перед установкой скилла/плагина/MCP-сервера, red flags, supply chain, тайпсквоттинг | §3 Skill & Plugin Validation |
| Протоколы валидации/аудита памяти, карантин, безопасные обновления | §4 Memory Hygiene & Poisoning Prevention |
| Минимум привилегий, детекция эскалации, предотвращение эксфильтрации, confused deputy | §5 Permission & Tool Safety |
| Подозрение на компрометацию: сдерживание, классификация, аудит памяти, карантин скилла | §6 Incident Response |
| Чек-листы: настройка агента, до сессии, обработка контента, установка скилла, аудит памяти | §7 Hardening Checklists |
| OWASP LLM/Agentic Top 10, статистика, инструменты, CVE, источники | §8 Reference |
| Флоучарты решений · community security-скиллы · secrets-never-in-context | Приложения A–C |

## Сопровождение (для мейнтейнеров реестра)

Апстрим `strategy: notify`; отслеживаемое тело — `references/full.md`. SKILL.md
написан вручную — `scripts/update-upstreams.sh` его не перезаписывает. Полный
русский перевод тела удалён при переносе на thin-navigator (P2.3
SKM-MASTER-003) — доступен в git-истории этого файла.
