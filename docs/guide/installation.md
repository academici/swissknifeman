# Установка скиллов

Установщик `install.sh` сам определяет тип проекта и ставит подходящий набор
скиллов. Никакой конфигурации для старта не нужно.

## Быстрый старт

```bash
# Laravel-проект (artisan + composer.json) → architect, php, devops, quality, operator
cd ~/projects/my-laravel-app
~/projects/packages/swissknifeman/install.sh --target . --agent claude

# Obsidian vault (.obsidian/) → architect, pm, founder, operator, roles, imported
~/projects/packages/swissknifeman/install.sh --target ~/vaults/brain

# Глобально в home (~/.claude/skills)
./install.sh --target ~ --agent claude
```

## Превью без установки

Флаг `--list` показывает, что будет установлено, не трогая файлы:

```bash
./install.sh --target ~/projects/my-app --list
```

## Явное управление

Автодетект можно переопределить:

```bash
# Явный профиль
./install.sh --target . --profile php-package

# Явный список bucket-ов
./install.sh --target . --buckets php,quality

# Исключить отдельные скиллы
./install.sh --target . --buckets php,quality --exclude botkit
```

Приоритет источников конфигурации: **флаги CLI → `.swissknife.json` → автодетект**.

## Фиксация конфигурации: `.swissknife.json`

Проект может зафиксировать свою конфигурацию установки в `.swissknife.json`
в корне — `install.sh` прочтёт его автоматически:

```json
{
  "project_type": "laravel-project",
  "buckets": ["architect", "php", "quality"],
  "exclude": ["botkit", "devops/gitops"],
  "skills_path": ".claude/skills",
  "agent": "claude"
}
```

Все ключи опциональны. Если задан `buckets`, поле `project_type` игнорируется.
Шаблон — [.swissknife.example.json](https://github.com/academici/swissknifeman/blob/main/.swissknife.example.json).

## Режим `--agent claude`

Claude Code не видит вложенные bucket-структуры, поэтому `--agent claude`
раскладывает скиллы **плоско**: `.claude/skills/<name>/SKILL.md`. Коллизии имён
разрешаются префиксом bucket-а.

::: warning Общий ~/.claude/skills
Установка в общий `~/.claude/skills` может перекрыть одноимённые скиллы,
поставленные не отсюда. Переустановка чистит только то, что ставила сама —
по манифесту `.swissknifeman-manifest.json`.
:::

## Legacy-режим

Старый формат вызова (копия bucket-а как есть) — deprecated, но работает:

```bash
./install.sh ~/.ai/skills php
```

## Что дальше

После установки скиллов подтяните пресеты permissions, чтобы агент сразу мог
работать без промптов — см. [Permissions для Claude Code](/configs/claude-permissions).
