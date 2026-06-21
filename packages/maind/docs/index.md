---
layout: home

hero:
  name: mAInd
  text: Центральный узел экосистемы
  tagline: Память агентов · граф связей · реестр агентов и проектов · MCP-сервер
  actions:
    - theme: brand
      text: Что такое mAInd
      link: /guide/
    - theme: alt
      text: Установка
      link: /guide/installation
    - theme: alt
      text: Архитектура
      link: /architecture

features:
  - title: 🧠 Общая память
    details: Один демон agent-memory на хаб, изоляция проектов по namespace (scope). Общие факты — в scope global.
  - title: 🕸 Граф связей
    details: Один граф на экосистему. Проекты, агенты, память, скиллы — узлы; depends_on / belongs_to / uses — рёбра. Это и есть «общая связь».
  - title: 🤖 Реестр агентов
    details: register / heartbeat / list / kill. Состояние alive·stale·dead выводится из heartbeat и живости pid.
  - title: 📦 Реестр проектов
    details: config.json (в корне монорепо) — надмножество brain .projects.json, с fallback на legacy и синком из brain.
  - title: 🔌 MCP-сервер
    details: maind mcp — stdio JSON-RPC. 11 tools поверх памяти, графа, ecosystem-связей, агентов и проектов для любого агента.
  - title: 🐍 Python + bash
    details: Ядро на stdlib (как swissknifeman / brain). npm — только для демона памяти и документации.
---
