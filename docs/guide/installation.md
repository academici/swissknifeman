# Установка скиллов

Два канала доставки:

| Агент | Механизм | Что попадает в проект |
|---|---|---|
| **Claude Code** | нативный plugin marketplace → [`connect-claude.sh`](/adapters/claude-code) | только записи в `.claude/settings.local.json` |
| **Cursor / generic** | вендоринг копий → `install.sh` | сами скиллы в `.cursor/skills` / `.ai/skills` |

## Claude Code: marketplace

```bash
# один раз на машину
claude plugin marketplace add ~/projects/packages/swissknifeman

# на каждый проект (автодетект профиля)
~/projects/packages/swissknifeman/scripts/connect-claude.sh --target ~/projects/my-app
```

Скиллы живут в кэше Claude Code и обновляются из репо — подробности в
[адаптере Claude Code](/adapters/claude-code).

## Cursor / generic: install.sh

Установщик `install.sh` сам определяет тип проекта и ставит подходящий набор
скиллов. Никакой конфигурации для старта не нужно.

```bash
# Laravel-проект (artisan + composer.json) → architect, php, devops, quality, operator
cd ~/projects/my-laravel-app
~/projects/packages/swissknifeman/install.sh --target . --agent cursor

# Obsidian vault (.obsidian/) → architect, pm, founder, operator, roles, imported
~/projects/packages/swissknifeman/install.sh --target ~/vaults/brain
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
в корне — `install.sh` и `connect-claude.sh` прочтут его автоматически:

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
Файл проходит схема-валидацию: неизвестный ключ или неверный тип — понятная
ошибка с подсказкой (`unknown key 'bucket' — did you mean 'buckets'?`).
Ключи, начинающиеся с `_`, считаются комментариями.
Шаблон — [.swissknife.example.json](https://github.com/academici/swissknifeman/blob/main/.swissknife.example.json).

## Манифест, переустановка и коллизии

Установщик пишет манифест `.swissknifeman-manifest.json` рядом со скиллами —
в обоих режимах раскладки (плоской и bucket). Переустановка сначала удаляет
**только** перечисленное в манифесте, затем ставит заново — чужие скиллы не
трогаются.

Если целевая папка скилла уже существует и не числится в манифесте, установка
прерывается со списком коллизий. Перезаписать осознанно: `--force`.

## Режим `--agent claude` (deprecated)

Вендоринг для Claude Code оставлен для совместимости (плоская раскладка
`.claude/skills/<name>/SKILL.md`, коллизии разрешаются префиксом bucket-а),
но предпочтительный путь — [marketplace](/adapters/claude-code).

## Legacy-режим

Старый формат вызова (копия bucket-а как есть) — deprecated, но работает:

```bash
./install.sh ~/.ai/skills php
```

## Что дальше

После установки скиллов подтяните пресеты permissions, чтобы агент сразу мог
работать без промптов — см. [Permissions для Claude Code](/configs/claude-permissions).
