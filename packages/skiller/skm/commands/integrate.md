---
description: Полный визард интеграции проекта через skiller (скиллы + хуки + permissions + память + hub).
argument-hint: "[minimal|recommended|full|custom]"
allowed-tools: Bash(skiller:*)
---
Интеграция проекта через **skiller integrate**. Ввод: «$ARGUMENTS».
Лаунчер — `skiller` (после `./install.sh`). В неинтерактивном режиме выбор уточняешь ты.

## Шаги
1. **Bundle**: `recommended` (дефолт) · `full` · `minimal` · `custom`. Если в «$ARGUMENTS» нет — спроси.
2. **Канал скиллов** (СПРОСИ через AskUserQuestion — касается ТОЛЬКО скиллов):
   - **connect** — плагины marketplace; файлы не в репо, нужен доступ к реестру swissknifeman;
   - **vendor** — физ. копии в `.claude/skills/` (через `sync`), коммитятся в репо → работают у
     внешних разработчиков без swissknifeman. → флаг `--skills-channel connect|vendor`.
   Рекомендуй **vendor**, если проект отдают сторонним разработчикам.
3. **Предпросмотр**: `skiller integrate --dry-run [--skills-channel <C>]` — покажи чеклист (скиллы / permissions / auto-approve / память / hub / docs-sync).
4. **Применение** по подтверждению: `skiller integrate --yes --bundle <B> [--skills-channel <C>]`.
5. **Отчёт**: что включено по каждому блоку.
