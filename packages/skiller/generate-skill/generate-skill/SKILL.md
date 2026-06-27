---
name: generate-skill
bucket: meta
version: 0.1.0
description: "Meta-skill for creating new skills from SKILL_TEMPLATE"
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
5. **Заведи evals/** (eval-first): `skiller eval <bucket>/<name> --scaffold` →
   заполни `evals.json` (кейсы + программные ассершены), `pressure.json`
   (сценарии-соблазны «пропустить скилл») и `triggers.json` (точность срабатывания
   описания). Прогон — `skiller eval <bucket>/<name>` (требует CLI `claude`).
6. Запусти `skiller registry`

> **Eval-first.** Скилл без evals — непроверяемое утверждение. Заведи кейсы
> вместе со скиллом: что он должен делать (evals) и от чего удерживать под
> давлением (pressure). `validate.sh` показывает покрытие evals одной строкой.
