---
description: Выбрать и применить бакеты скиллов swissknifeman в проект — канал connect (Claude marketplace) или vendor (физ.копии для Cursor/др).
argument-hint: "[connect|vendor] [bucket1,bucket2 | --profile P]"
allowed-tools: Bash(swissknifeman:*)
---
Подбор скиллов проекту через **swissknifeman**. Ввод: «$ARGUMENTS».
Лаунчер — `swissknifeman` (после `./install.sh`).

## Шаги
1. **Канал** (ВСЕГДА уточни, если не задан в «$ARGUMENTS»):
   - `connect` — для **Claude Code**: активация плагин-marketplace, скиллы не копируются (живут в реестре, авто-обновляются);
   - `vendor` — для **Cursor / других агентов**: физический перенос SKILL.md в проект (`.cursor/skills` / `.ai/skills`).
2. **Что доступно** — перечисли бакеты реестра (из `buckets.json` / `skills.json` репозитория swissknifeman): architect, php, frontend, devops, quality, operator, pm, founder, python, oss-dev, roles, system, general, blender, imported, generate-skill.
3. **Выбор** — уточни у пользователя нужные бакеты (или профиль). Это и есть «чекбоксы»: спрашиваешь — собираешь список.
4. **Применение**:
   - connect: `swissknifeman connect --plugins <bucket1,bucket2>` (или `--profile <P>`);
   - vendor: `swissknifeman vendor --agent <claude|cursor|generic>` (набор — из `.swissknifeman/config.json`; для разовой выборки уточни состав).
5. **Отчёт**: что подключено/скопировано. Для vendor обнови карту: `swissknifeman lock`.
