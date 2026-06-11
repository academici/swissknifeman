# Пресеты permissions для Claude Code

Готовые наборы разрешений для `.claude/settings.local.json` — чтобы новый проект
сразу работал без бесконечных permission-промптов.

| Пресет | Что разрешает |
|---|---|
| `base` | git (push — с подтверждением), gh, файловые операции, curl/wget, jq/rg/sed; deny на секреты (`.env`, ключи, `~/.ssh`) и `sudo` |
| `laravel` | `php artisan`, composer, pest/phpunit/pint/phpstan/rector, sail, npm/vite; деструктивные миграции — с подтверждением |
| `php-package` | composer, pest/phpunit/pint/phpstan/rector/infection — без artisan |
| `node` | node/npm/npx/pnpm/yarn, tsc, vitest, eslint, prettier; publish — с подтверждением |
| `python` | python/pip/pytest, uv, poetry, ruff/black/mypy |
| `docker` | docker + docker compose; удаление контейнеров/volumes/prune — с подтверждением |
| `yolo` | `bypassPermissions` — только для контейнеров и VM, см. предупреждение в доке |

## Быстрый старт

```bash
# base + автодетект стека по маркерам проекта (artisan, package.json, pyproject.toml, ...)
./scripts/apply-permissions.sh --target ~/projects/my-laravel-app

# явный набор
./scripts/apply-permissions.sh --target . --preset base,laravel,docker

# превью без записи
./scripts/apply-permissions.sh --target . --dry-run
```

Скрипт объединяет `allow`/`ask`/`deny` с уже существующими правилами цели
(ничего не затирает, дубликаты убирает) и делает бэкап `settings.local.json.bak`.

Подробный разбор синтаксиса правил и логики пресетов — в
[документации](../../docs/configs/claude-permissions.md).
