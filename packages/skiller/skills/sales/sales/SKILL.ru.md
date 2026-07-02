> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: sales-super-skill
bucket: sales
version: 1.0.0
description: Comprehensive end-to-end sales skill merging Perplexity Computer's 6 built-in sales skills with Claude Code's customer interview analysis, brand voice analysis, content research, RICE prioritization, and UX research. Covers the full sales cycle from prospecting to close. Use when doing account research, call prep, competitive intelligence, outreach drafting, asset creation, daily briefings, customer interview analysis, deal prioritization, or prospect research.
license: MIT
metadata:
  author: get-zeked
  version: '1.0'
adapters: [claude, cursor, fable]
sha256: ""
---

# Супер-скилл продаж — навигатор

Полноценная операционная система продаж — 6 встроенных скиллов продаж
Perplexity Computer, объединённых с фреймворками Claude Code по PM/UX/бренд-войсу
и контенту; полный цикл от поиска клиентов до закрытия сделки. Полный плейбук
(~90KB) — шаблоны, форматы вывода, банки вопросов, рубрики скоринга — в
[`references/full.md`](references/full.md). Этот файл — только навигатор.

**Правило:** открывай `references/full.md` точечно — один раздел на конкретную
задачу. Никогда целиком: не влезет в разумный контекстный бюджет.

## Карта разделов ([`references/full.md`](references/full.md))

| Задача | Раздел |
|:--|:--|
| Фразы-триггеры по воркфлоу | How to Trigger This Skill |
| Вклад Perplexity vs Claude Code по возможностям | §1 Gap Analysis Table |
| Исследование компании/персоны + шаблон "Research:" (Quick Take, Profile, Key People, Qualification Signals, Recommended Approach) | §2 Account Research & Prospect Intelligence |
| Подготовка по типу встречи (discovery/demo/переговоры/QBR), банки вопросов, шаблон "Call Prep:" | §3 Call Prep & Meeting Readiness |
| Батлкарды, talk tracks, landmine-вопросы, win/loss, позиционирование по бренд-войсу | §4 Competitive Intelligence & Positioning |
| AIDA-аутрич на основе исследования, шаблон "Outreach Draft:" (email + LinkedIn, follow-up, валидация бренд-войса) | §5 Outreach & Content Creation |
| 7-фазное создание ассетов (лендинги, презентации, one-pager), матрица репурпозинга | §6 Sales Assets & Deliverables |
| RICE-скоринг для сделок, шаблон "Daily Briefing" | §7 Deal Prioritization & Pipeline Management |
| Воркфлоу, зависящие от live-данных/обогащения/CRM | §8 Unique Perplexity Computer Capabilities |

Выбор раздела по задаче: исследовать компанию → §2 · подготовить звонок → §3 ·
против конкурента → §4 · написать аутрич → §5 · собрать ассет → §6 ·
ранжировать сделки/дневной брифинг → §7.

## Сопровождение (для мейнтейнеров реестра)

Апстрим `strategy: notify`; отслеживаемое тело — `references/full.md`. SKILL.md
написан вручную — `scripts/update-upstreams.sh` его не перезаписывает. Полный
русский перевод тела удалён при переносе на thin-navigator (P2.3
SKM-MASTER-003) — доступен в git-истории этого файла.
