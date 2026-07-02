---
name: marketing-super-skill
bucket: marketing
version: 1.0.0
description: Comprehensive end-to-end marketing skill merging Perplexity Computer's 6 built-in marketing skills with Claude Code's best community marketing skills. Covers campaign planning, brand voice, competitive analysis, SEO, content creation, performance analytics, copywriting frameworks, and marketing ops. Use when planning campaigns, analyzing competitors, creating content, building brand guidelines, tracking marketing metrics, or optimizing conversion funnels.
license: MIT
metadata:
  author: get-zeked
  version: '1.0'
adapters: [claude, cursor, fable]
sha256: ""
---

> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

# Маркетинговый супер-скилл — навигатор

Тонкий навигатор над полным апстримным плейбуком в
[`references/full.md`](references/full.md) (~57KB): фреймворки, шаблоны для
заполнения и воркфлоу, объединяющие маркетинговые скиллы комьюнити Claude Code
со встроенными маркетинговыми скиллами Perplexity Computer.

**Открывай `references/full.md` точечно — переходи к разделу, отвечающему на
текущий вопрос. Не грузи файл целиком.**

## Карта разделов ([`references/full.md`](references/full.md))

| Задача | Раздел |
|:--|:--|
| Что покрывает Claude Code vs Computer, матрица возможностей | Gap Analysis |
| Посты блога, сценарии видео, репурпозинг, подписи, формулы заголовков, SEO-брифы, контент-календарь | Content Creation & SEO |
| Брифы кампаний, плейбук demand-gen, чек-лист запуска, журнал экспериментов, распределение бюджета | Campaign Planning & Demand Gen |
| KPI-дашборды, атрибуция, таксономия UTM, когорты, MMM, incrementality-тесты | Analytics & Performance |
| Батлкарды конкурентов, win/loss-анализ, share of voice, карты позиционирования | Competitive Intelligence & PMM |
| Keyword-исследование для app store, оптимизация листинга, CVR, метрики ASO | App Store Optimization (ASO) |
| Принципы промпт-инжиниринга + готовая библиотека маркетинговых промптов | Prompt Engineering for Marketing |
| Симуляция персон, конкурентная разведка в реальном времени, шаблоны PR-коммуникаций | Unique Computer Capabilities |

## Когда что использовать

- Планируете кампанию/запуск → Campaign Planning (бриф + чек-лист).
- Пишете контент/копирайт/SEO-брифы → Content Creation & SEO.
- Измеряете или атрибутируете performance → Analytics & Performance.
- Изучаете конкурентов или позиционирование → Competitive Intelligence & PMM.
- Рост мобильного приложения → ASO. Промпты для маркетинговых задач → Prompt Engineering.

## Сопровождение (для мейнтейнеров реестра)

Апстрим `strategy: notify`; отслеживаемое тело — `references/full.md`. SKILL.md
написан вручную — `scripts/update-upstreams.sh` его не перезаписывает. Полный
русский перевод тела удалён при переносе на thin-navigator (P2.3
SKM-MASTER-003) — доступен в git-истории этого файла.
