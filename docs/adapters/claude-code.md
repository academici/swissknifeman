# Адаптер: Claude Code

Полный цикл интеграции с Claude Code: плагины (скиллы) + permissions.

Основной механизм — **нативный plugin marketplace**: swissknifeman является
маркетплейсом плагинов (`.claude-plugin/marketplace.json`), каждый bucket —
отдельный плагин. Скиллы не копируются в репозиторий проекта: они живут в кэше
Claude Code и обновляются из этого репо.

## Один раз на машину: добавить marketplace

```bash
claude plugin marketplace add ~/projects/packages/swissknifeman
```

Источник — локальная папка: пуш не нужен, но версия плагина привязана к git SHA,
поэтому правки подтягиваются **после локального коммита** (затем
`/plugin marketplace update swissknifeman` + `claude plugin update <p>@swissknifeman`
или перезапуск сессии).

## На каждый проект: подключить плагины

```bash
cd ~/projects/my-app && swissknifeman connect
```

Команда определяет тип проекта (те же маркеры, что и `swissknifeman vendor`;
корень проекта находится автоматически от текущей директории) и записывает
в `.claude/settings.local.json` проекта:

```json
{
  "extraKnownMarketplaces": {
    "swissknifeman": {
      "source": { "source": "directory", "path": "/home/<you>/projects/packages/swissknifeman" }
    }
  },
  "enabledPlugins": {
    "php@swissknifeman": true,
    "quality@swissknifeman": true
  }
}
```

Файл `settings.local.json` не коммитится — локальный путь не попадает в
репозиторий проекта. Merge идемпотентный: явный `false` не перетирается,
лишние включённые плагины не отключаются (только репортятся).

Полезные флаги: `--profile`, `--plugins a,b,c`, `--list`, `--dry-run`,
`--cleanup-vendored`, `--file settings.json`.

## Плагины и неймспейсы

Плагин = bucket (+ мета-плагин `generate-skill`). Скиллы плагинов получают
неймспейс `<плагин>:<скилл>`: `php:laravel-packages`, `quality:code-review`,
`devops:docker-php`. У скиллов из `imported/` имя берётся из frontmatter, а не
из папки: `imported:ai-agent-super-skill`.

Манифесты (`.claude-plugin/plugin.json` в каждом bucket-е и корневой
`marketplace.json`) **генерируются** — после добавления/перемещения скилла
запускайте `swissknifeman registry`; `validate.sh` ловит устаревшие.

## Обновления

- Версия плагина = git SHA репозитория (поле `version` не задаётся намеренно),
  поэтому правка скилла видна в проектах **после локального коммита** в этом репо.
- Подтянуть: `/plugin marketplace update swissknifeman`, затем
  `claude plugin update <plugin>@swissknifeman` (или перезапуск сессии).

## Миграция со старого вендоринга

Раньше скиллы копировались в `.claude/skills/` проекта (вендоринг — теперь
`swissknifeman vendor --agent claude`, deprecated для Claude Code).
`swissknifeman connect` находит старый манифест
`.swissknifeman-manifest.json` и по флагу `--cleanup-vendored` удаляет **только**
вендоренные копии — собственные скиллы проекта не трогаются.

## Переключение на GitHub-источник (другая машина / CI)

Локальный путь работает только на этой машине. Где репо доступен по git:

```json
{
  "extraKnownMarketplaces": {
    "swissknifeman": {
      "source": { "source": "github", "repo": "academici/swissknifeman" }
    }
  }
}
```

Такой источник можно класть и в коммитимый `.claude/settings.json`
(`swissknifeman connect --file settings.json` + ручная правка source). Для фоновых
автообновлений приватного репо нужен `GITHUB_TOKEN` в окружении.

## Permissions

После плагинов подтяните пресеты разрешений:

```bash
./scripts/apply-permissions.sh --target ~/projects/my-app
```

Подробности — в [гайде по permissions](/configs/claude-permissions).

## Delta-файлы

Специфика Claude Code внутри скилла выносится в `adapters/claude.md` —
overrides для CLAUDE.md-специфики. Формат — в
[спецификации адаптерных дельт](/guide/adapter-deltas).

## Вендоринг (deprecated для Claude Code)

`swissknifeman vendor --agent claude` (из каталога проекта) по-прежнему
работает (плоская раскладка + манифест), но для Claude Code предпочтителен
marketplace: единый
источник, обновления без переустановки, ничего лишнего в репо проекта.
Вендоринг остаётся основным путём для Cursor и других агентов — см.
[Установку скиллов](/guide/installation).
