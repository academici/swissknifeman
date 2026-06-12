---
layout: home

hero:
  name: SwissKnifeMan
  text: Швейцарский нож для работы с AI-агентами
  tagline: Один реестр скиллов, конфигов и пермиссий — установка в любой проект и любую IDE за одну команду
  actions:
    - theme: brand
      text: Начать
      link: /guide/
    - theme: alt
      text: Установка
      link: /guide/installation
    - theme: alt
      text: GitHub
      link: https://github.com/academici/swissknifeman

features:
  - icon: 🧰
    title: Всё в одном месте
    details: 65+ скиллов в 10 bucket-ах, пресеты permissions, профили проектов, адаптеры под IDE. Один источник истины вместо копипасты между проектами.
  - icon: 🎯
    title: Контекстная установка
    details: CLI swissknifeman сам определяет тип проекта — Laravel, PHP-пакет, Obsidian vault — и подключает подходящий набор скиллов. Одна команда — и проект готов к работе с AI.
  - icon: 🔓
    title: Пресеты permissions
    details: Готовые .claude/settings.json с максимально разрешённым доступом — git, composer, artisan, npm, docker. Никаких бесконечных permission-промптов в новом проекте.
  - icon: 🔄
    title: Upstream-sync
    details: Внешние скиллы отслеживаются через upstream.json — еженедельный CI проверяет обновления источников и открывает PR с диффом.
  - icon: 🧩
    title: Provider-neutral
    details: Скилл — это папка с SKILL.md и snippets/. Один формат работает в Claude Code, Cursor и Perplexity через адаптеры.
  - icon: 📦
    title: Provenance и валидация
    details: skills.json хранит источник, версию и sha256 каждого скилла. validate.sh проверяет frontmatter, манифесты и профили локально и в CI.
---
