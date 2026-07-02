---
name: pm-super-skill
bucket: pm
version: 0.1.0
description: Comprehensive product management skill merging Perplexity Computer's 6 PM skills with Claude Code's product team skills. Covers feature specs, roadmaps, metrics, competitive analysis, stakeholder comms, user research, RICE prioritization, agile ceremonies, UX research, UI design systems, and persistent planning. Use for PRDs, roadmap planning, sprint management, user research synthesis, stakeholder updates, or any product management work.
license: MIT
metadata:
  author: get-zeked
  version: '1.0'
adapters: [claude, cursor, fable]
sha256: ""
---

> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

# Супер-скилл продуктового менеджмента — навигатор

Тонкий навигатор над полным внешним справочником в
[`references/full.md`](references/full.md) (~79KB, апстрим
`get-zeked/pm-super-skill`): сквозной PM-хендбук, объединяющий шесть PM-скиллов
Perplexity Computer с тулкитом продуктовой команды Claude Code — шаблоны,
фреймворки и чек-листы по всему PM-воркфлоу.

**Сначала роутинг.** Для конкретной задачи предпочти гранулярный нативный
скилл `pm/` (глубже, без пересечений): `brd` · `prd-from-brd` ·
`product-roadmap` · `requirement-critic` · `unit-economics` ·
`monetization-design` · `go-to-market` · `pmf-diagnostics` ·
`business-process`. Справочник — только для сквозного обзора или темы, не
покрытой ни одним отдельным скиллом (механика спринтов/agile, user research,
дизайн-системы UI, конкурентный анализ, коммуникации со стейкхолдерами).

**Правило использования:** НЕ грузи `references/full.md` целиком. Найди раздел
под конкретный вопрос и читай только его.

## Карта разделов ([`references/full.md`](references/full.md))

| Задача | Раздел |
|:--|:--|
| Покрытие PM-скиллов Perplexity vs Claude Code | §1 Gap Analysis |
| Структуры PRD, one-page PRD, эпики, MoSCoW, критерии приёмки | §2 Feature Specs & PRDs |
| RICE/ICE/2×2, Now-Next-Later, OKR-роадмапы, capacity, зависимости | §3 Roadmap & Prioritization |
| Церемонии, velocity, прогноз Монте-Карло, ретро, DoD | §4 Sprint & Agile Management |
| North Star, метрики L1/L2, OKR, ритм ревью, дашборды | §5 Metrics & OKRs |
| Выбор метода, интервью, синтез, персоны, journey, юзабилити | §6 User Research & UX |
| Дизайн-токены, компоненты, доступность | §7 UI Design Systems |
| Фреймворки конкурентов, позиционирование | §8 Competitive Analysis |
| Апдейты, ADR, коммуникации с руководством | §9 Stakeholder Communications |
| Файловые шаблоны трекинга плана/инсайтов | §10 Persistent Planning (File-Based) |
| Инструментарий, специфичный для Perplexity Computer | §11 Perplexity Computer Unique Capabilities |
| Сквозные многораздельные воркфлоу | §12 Cross-Skill Workflows |
| Быстрый выбор фреймворка, ловушки, чек-листы PRD/research | §13 Quick Reference & Templates Index |

## Сопровождение (для мейнтейнеров реестра)

Апстрим `strategy: notify`; отслеживаемое тело — `references/full.md`. SKILL.md
написан вручную — `scripts/update-upstreams.sh` его не перезаписывает. Полный
русский перевод тела удалён при переносе на thin-navigator (P2.3
SKM-MASTER-003) — доступен в git-истории этого файла.
