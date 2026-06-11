# Адаптер: Claude Code

Полный цикл интеграции с Claude Code: скиллы + permissions.

## Установка скиллов

```bash
# В проект (рекомендуется)
./install.sh --target ~/projects/my-app --agent claude

# Глобально для всех проектов
./install.sh --target ~ --agent claude
```

Флаг `--agent claude` обязателен для корректной раскладки: Claude Code не видит
вложенные bucket-структуры, поэтому скиллы раскладываются **плоско** —
`.claude/skills/<name>/SKILL.md`. Коллизии имён между bucket-ами разрешаются
префиксом bucket-а.

## Permissions

После скиллов подтяните пресеты разрешений:

```bash
./scripts/apply-permissions.sh --target ~/projects/my-app
```

Подробности — в [гайде по permissions](/configs/claude-permissions).

## Delta-файлы

Специфика Claude Code внутри скилла выносится в `adapters/claude.md` —
overrides для CLAUDE.md-специфики. При установке адаптер накладывает их поверх
основного `SKILL.md`. Формат — в
[спецификации адаптерных дельт](/guide/adapter-deltas).

## Манифест и переустановка

Установщик пишет манифест `.swissknifeman-manifest.json` рядом со скиллами.
Переустановка удаляет **только** то, что ставила сама, — скиллы из других
источников в общем `~/.claude/skills` не трогаются.

::: warning Коллизии в общем каталоге
Установка в `~/.claude/skills` может перекрыть одноимённые скиллы, поставленные
не отсюда. Для изоляции ставьте в проект (`--target <проект>`), а не в home.
:::
