> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: operations-cx-super-skill
bucket: operator
version: 1.0.0
description: Comprehensive operations and customer experience skill merging Perplexity Computer's 5 CX skills with Claude Code's project management, file organization, invoice processing, scrum methodology, and verification workflows. Covers ticket triage, customer response drafting, escalation management, knowledge base maintenance, customer research, project management, sprint planning, file organization, and operational quality assurance. Use for support ticket handling, customer communications, escalation workflows, KB article writing, project management, sprint ceremonies, file cleanup, or any operations and CX work.
license: MIT
metadata:
  author: get-zeked
  version: '1.0'
adapters: [claude, cursor, fable]
sha256: ""
---

# Супер-скилл «Операции и клиентский опыт» — навигатор

Тонкий навигатор. Полное апстримное тело (~75KB) — в
[`references/full.md`](references/full.md). Для конкретной задачи предпочти
гранулярный нативный скилл: `operator/incident-response` ·
`operator/postmortem` · `operator/oncall-rotation` ·
`operator/capacity-planning` · `operator/runbook`. Справочник — только для
сквозных вопросов operations/CX, которые не покрывает ни один гранулярный скилл.

**Открывай `references/full.md` в разделе, отвечающем на конкретный вопрос —
никогда целиком.**

## Карта разделов ([`references/full.md`](references/full.md))

| Тема | Раздел |
|:--|:--|
| Матрица покрытия по исходным скиллам | Gap Analysis |
| Триаж тикетов, приоритеты, SLA | §2 Ticket Triage & Classification |
| Составление ответов клиентам | §3 Customer Response Drafting |
| Уровни эскалации и формат | §4 Escalation Management |
| Исследование клиентов, уровень уверенности | §5 Customer Research & Investigation |
| Ведение базы знаний | §6 Knowledge Base Management |
| Портфельный PM: WSJF/RICE, риски | §7 Project Management & Portfolio |
| Спринты и agile-операции | §8 Sprint & Agile Operations |
| Организация файлов/документов | §9 File & Document Organization |
| Обработка инвойсов/финансовых документов | §10 Invoice & Financial Document Processing |
| Верификация и планирование | §11 Operational Quality & Verification |
| Специфика Perplexity Computer | §12 Unique Perplexity Computer Capabilities |
| Сквозные воркфлоу, карточки | Приложения A–C |

## Сопровождение (для мейнтейнеров реестра)

Апстрим `strategy: notify`; отслеживаемое тело — `references/full.md`. SKILL.md
написан вручную — `scripts/update-upstreams.sh` его не перезаписывает. Полный
русский перевод тела удалён при переносе на thin-navigator (P2.3
SKM-MASTER-003) — доступен в git-истории этого файла.
