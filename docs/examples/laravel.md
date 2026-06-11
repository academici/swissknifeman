# Laravel-проект с нуля

Сквозной сценарий: новый Laravel-проект → полностью готовое AI-окружение
за две команды.

## Исходная точка

```bash
laravel new shop && cd shop
# или: git clone git@github.com:me/shop.git && cd shop
```

## Шаг 1. Скиллы

```bash
~/projects/packages/swissknifeman/install.sh --target . --agent claude
```

Автодетект видит `artisan` + `composer.json` → профиль `laravel-project` →
в `.claude/skills/` плоско раскладываются bucket-ы **architect, php, devops,
quality, operator**: скиллы по архитектуре, Laravel-паттернам, тестированию,
Docker, code review и инцидентам.

Проверить, что поставится, можно заранее:

```bash
~/projects/packages/swissknifeman/install.sh --target . --list
```

## Шаг 2. Permissions

```bash
~/projects/packages/swissknifeman/scripts/apply-permissions.sh --target .
```

Автодетект по маркерам: `artisan` → `laravel`, `package.json` → `node`,
`Dockerfile`/`compose.yaml` → `docker`. В `.claude/settings.local.json`
вливаются `base + laravel + node (+ docker)`:

- ✅ без промптов: `php artisan`, `composer`, `vendor/bin/pest`, `pint`,
  `phpstan`, `npm run`, `git` (кроме push), файловые операции;
- ❓ с подтверждением: `git push`, `migrate:fresh`, `db:wipe`, `rm -rf`;
- 🚫 запрещено: чтение `.env`, `*.pem`, `~/.ssh`, `sudo`.

## Шаг 3. Зафиксировать конфигурацию (опционально)

Чтобы любой клон проекта восстанавливал то же окружение:

```bash
cp ~/projects/packages/swissknifeman/.swissknife.example.json .swissknife.json
# отредактировать под проект и закоммитить
```

## Результат

```
shop/
├── .claude/
│   ├── skills/                  # 31 скилл под Laravel-разработку
│   ├── settings.local.json      # permissions: base+laravel+node
│   └── settings.local.json.bak  # бэкап, если файл существовал
├── .swissknife.json             # зафиксированная конфигурация (опц.)
└── ...
```

Открываете Claude Code — и агент сразу умеет: проектировать структуру по
скиллам architect, писать тесты по `laravel-testing`, запускать `artisan`,
`composer` и линтеры без единого промпта.

## Типичные доработки

```bash
# Исключить неактуальные скиллы
~/projects/packages/swissknifeman/install.sh --target . --profile laravel-project --exclude botkit

# Добавить docker-пресет, если автодетект его не увидел
~/projects/packages/swissknifeman/scripts/apply-permissions.sh --target . --preset docker
```
