---
name: content-creative-super-skill
bucket: creative
version: 1.0.0
description: Comprehensive creative studio skill merging Perplexity Computer's video production, speech synthesis, image generation, and website building with Claude Code's canvas design, algorithmic art, brand guidelines, frontend design, artifacts builder, content frameworks, content calendar, and prompt engineering. Use when creating visual content, designing interfaces, building brands, generating videos/images/audio, writing content, planning content calendars, or doing any creative production work.
license: MIT
metadata:
  author: get-zeked
  version: '1.0'
adapters: [claude, cursor, fable]
sha256: ""
---

> 🌐 Справка для человека. Агент использует SKILL.md, не этот файл.

# Супер-скилл «Контент и креатив» — навигатор

Тонкий навигатор над импортированным **get-zeked/content-creative-super-skill**
(`strategy: notify`). Полное руководство по креативному производству (~90KB: 10 разделов,
деревья решений, приложение) — в [`references/full.md`](references/full.md).
**Открывай точечно нужный раздел под конкретный вопрос, не целиком** (экономия контекста).

## Карта разделов ([`references/full.md`](references/full.md))

| Задача | Раздел |
|:--|:--|
| Сравнение возможностей экосистем, выбор инструмента | §1 Gap Analysis Table |
| Canvas-дизайн, AI-генерация изображений, визуальные брифы | §2 Visual Design & Canvas |
| Архетипы бренда, фреймворк голоса, брифы идентичности | §3 Brand Identity & Guidelines |
| Веб-артефакты (React+shadcn), Tailwind-паттерны, лендинги | §4 Frontend Design & Web Artifacts |
| Алгоритмическое искусство p5.js, GIF, AI-видео, раскадровки | §5 Generative Art & Animation |
| TTS, транскрипция, продакшн подкастов/озвучки | §6 Audio & Speech |
| Копирайтинг, хуки, шаблоны blog/social/email/SEO/PR | §7 Content Creation & Copywriting |
| Контент-столпы, месячные календари, матрица репурпозинга | §8 Content Calendar & Planning |
| Креативные промпт-шаблоны и оптимизация | §9 Prompt Engineering for Creative Work |
| Нативные инструменты Perplexity Computer | §10 Unique Perplexity Computer Capabilities |
| Быстрый выбор метода · зависимости | Quick Reference: Decision Trees · Appendix |

## Сопровождение (для мейнтейнеров реестра)

Апстрим `strategy: notify`; отслеживаемое тело — `references/full.md` (`body_path`
в `upstream.json`). SKILL.md написан вручную — `scripts/update-upstreams.sh` его
не перезаписывает. Полный русский перевод тела (126KB) удалён при переносе на
thin-navigator (P7.3) — доступен в git-истории этого файла.
