---
name: generate-skill
bucket: meta
version: 0.1.0
description: "Meta-skill для создания новых скиллов по SKILL_TEMPLATE"
risk: write
persona: architect
tags: [meta, scaffolding]
requires: []
produces_for: []
outputs: ["skills/{bucket}/{name}/SKILL.md"]
adapters: [claude, cursor, fable]
sha256: ""
---

## Контекст

Используй когда нужно создать новый скилл в реестре academici/swissknifeman.

## Алгоритм

1. Определи bucket и name
2. Скопируй SKILL_TEMPLATE.md
3. Заполни frontmatter и секции
4. Добавь snippets/ с index.json
5. Запусти `sync.sh --update-registry`
