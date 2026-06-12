# Адаптер: Cursor

## Установка скиллов

```bash
# Из каталога проекта — вендоринг в .cursor/skills/
swissknifeman vendor --agent cursor

# Точечно — скопируйте нужный SKILL.md в .cursor/skills/ проекта
cp -r skills/php/laravel-testing ~/projects/my-app/.cursor/skills/
```

## Delta-файлы

Специфика Cursor выносится в `adapters/cursor.md` внутри скилла — там только
overrides для `.cursor/rules`, основной `SKILL.md` остаётся provider-neutral.
Формат — в [спецификации адаптерных дельт](/guide/adapter-deltas).

## Что учесть

- Cursor читает скиллы из `.cursor/skills/` проекта и глобального каталога;
- правила (`.cursor/rules`) — отдельный механизм: если скиллу нужны
  специфичные правила, они описываются в его delta-файле;
- формат `SKILL.md` (frontmatter + markdown-инструкции) Cursor понимает без
  преобразований.
