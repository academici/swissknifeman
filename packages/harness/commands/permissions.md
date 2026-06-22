---
description: "Влить permissions-пресеты Claude Code в .claude/settings*.json текущего проекта (autodetect стека)."
---
Примени permissions-пресеты харнеса к текущему проекту.

1. Уточни цель: текущий каталог (`--target .`) или другой путь.
2. По умолчанию стек определяется автоматически (base + laravel/php-package/node/python/docker). Явный набор — `--preset base,laravel`.
3. Покажи доступные пресеты при просьбе: `harness permissions --list`.
4. Сначала предложи `--dry-run`, затем запиши.

Запуск (через Bash):
```
harness permissions --target . [--preset a,b] [--file settings.json|settings.local.json] [--dry-run]
```
Merge-only: существующие правила сохраняются, файл бэкапится в `*.bak`. Аргументы пользователя — «$ARGUMENTS».
