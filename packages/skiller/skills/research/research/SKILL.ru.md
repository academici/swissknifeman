> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: research-knowledge-super-skill
bucket: research
version: 0.1.0
description: Comprehensive research and knowledge management skill merging Perplexity Computer's research, data exploration, statistical analysis, and visualization skills with Claude Code's tapestry knowledge graphs, article extraction, content research, brainstorming, RAG system building, and prompt engineering. Covers deep research workflows, knowledge graph construction, academic research, data analysis, statistical methods, content synthesis, and AI-powered information retrieval. Use for research projects, literature reviews, data analysis, knowledge management, competitive research, or any investigation requiring deep synthesis.
license: MIT
metadata:
  author: get-zeked
  version: '1.0'
adapters: [claude, cursor, fable]
sha256: ""
---

# Супер-скилл «Исследования и управление знаниями» — навигатор

Тонкий навигатор. Полный плейбук (~70KB) — в
[`references/full.md`](references/full.md): единая система для глубоких
исследований, профилирования данных, статистики, визуализации, графов знаний,
извлечения контента, RAG, мозгового штурма и итеративного обучения. Используй
для исследовательских проектов, обзоров литературы, анализа данных, управления
знаниями, конкурентных исследований.

**Открывай `references/full.md` точечно — переходи к разделу, отвечающему на
текущий вопрос; никогда не грузи файл целиком.**

> **Связанное:** для верификации внешних фактов, всплывших в ходе исследования
> (версии, «ещё актуально», рыночные данные) — используй `general/verify-claims`,
> он владеет RAG-лестницей.

## Карта разделов ([`references/full.md`](references/full.md))

| Задача | Раздел |
|:--|:--|
| Сравнение покрытия скиллов Perplexity Computer vs Claude Code | §1 Gap Analysis |
| Иерархия исследований, deep/subagent-воркфлоу, SEO и конкурентные исследования | §2 Research Methodology & Workflows |
| Извлечение сущностей, extract→link→plan, синтез из нескольких документов | §3 Knowledge Graph Construction |
| Извлечение статей/YouTube/PDF, синтез, уровни качества источников | §4 Content Extraction & Synthesis |
| Профилирование схемы/колонок, качество данных, SQL-исследование | §5 Data Exploration & Profiling |
| Меры центра, перцентили, проверка гипотез | §6 Statistical Analysis & Methods |
| Выбор графика, сторителлинг данными | §7 Data Visualization & Communication |
| Чек-листы валидации, QA анализа | §8 Data Validation & Quality Assurance |
| Идеация, сравнение подходов, дизайн-документы | §9 Creative Ideation & Brainstorming |
| RAG-пайплайны, стратегии retrieval | §10 RAG Systems & AI-Powered Research |
| Итеративное обучение по повторам, ретроспективы | §11 Iterative Learning & Feedback |
| Возможности, специфичные для платформы | §12 Unique Perplexity Computer Capabilities |
| Шаблоны отчёта/лит-обзора/конкурентного анализа/EDA/AB-теста | §13 Research Templates & Frameworks |
| Шпаргалка на один экран | Quick Reference Card |

## Сопровождение (для мейнтейнеров реестра)

Апстрим `strategy: notify`; отслеживаемое тело — `references/full.md`. SKILL.md
написан вручную — `scripts/update-upstreams.sh` его не перезаписывает. Полный
русский перевод тела удалён при переносе на thin-navigator (P2.3
SKM-MASTER-003) — доступен в git-истории этого файла.
