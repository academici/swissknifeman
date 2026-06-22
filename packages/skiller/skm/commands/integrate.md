---
description: Полный визард интеграции проекта через skiller (скиллы + хуки + permissions + память + hub).
argument-hint: "[minimal|recommended|full|custom]"
allowed-tools: Bash(skiller:*)
---
Интеграция проекта через **skiller integrate**. Ввод: «$ARGUMENTS».
Лаунчер — `skiller` (после `./install.sh`). В неинтерактивном режиме выбор уточняешь ты.

## Шаги
1. **Bundle**: `recommended` (дефолт) · `full` · `minimal` · `custom`. Если в «$ARGUMENTS» нет — спроси.
2. **Предпросмотр**: `skiller integrate --dry-run` — покажи чеклист (скиллы / permissions / auto-approve / память / hub / docs-sync).
3. **Применение** по подтверждению: `skiller integrate --yes --bundle <B>`.
4. **Отчёт**: что включено по каждому блоку.
