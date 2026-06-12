# Адаптерные дельты

`SKILL.md` — единственный источник истины, provider-neutral. Всё специфичное
для конкретного агента выносится в **дельта-файлы** `adapters/<agent>.md`
внутри папки скилла:

```
SKILL.md  ←── единственный source of truth
    │
    ├── adapters/claude.md   (только delta: overrides, доп. инструкции)
    ├── adapters/cursor.md   (только delta: .cursor/rules specific)
    └── adapters/<agent>.md  (любой другой агент по тому же принципу)
```

**Дельта НЕ дублирует SKILL.md** — она содержит только отличия.

## Когда дельта нужна

| Условие | Нужна дельта? |
|---|---|
| Агент использует другой формат вывода | ✅ да |
| У агента специфические инструменты (MCP, tools) | ✅ да |
| Агент требует особый синтаксис промпта / правил | ✅ да |
| Скилл работает одинаково везде | ❌ нет — файл не создаётся |

Отсутствие дельты — норма: большинство скиллов provider-neutral целиком.

## Формат дельты

Дельта — markdown из секций двух типов:

- `## Override: <что>` — замещает соответствующую часть SKILL.md;
- `## Additional: <что>` — добавляет инструкции, не отменяя основных.

```markdown
## Override: output_format
Вместо markdown используй JSON с полями: ...

## Additional: pre_flight
Перед выполнением проверь наличие файла composer.json
```

## Типовые секции

### Pre-flight hook

Проверка предусловий перед стартом скилла:

````markdown
## Additional: pre_flight
```bash
# выполнить перед стартом скилла
ls composer.json || echo "WARNING: не Laravel-проект"
```
````

### Output override

Перенаправление результатов под конвенции агента или проекта:

```markdown
## Override: output_paths
Записывай файлы в `infra/docker/` вместо `docker/`
```

### Пример: дельта для Cursor

```markdown
## Cursor Delta: docker-php

### Additional: rules
Добавь в .cursor/rules:
"При создании Dockerfile всегда использовать non-root user и multi-stage build"

### Override: file_creation
Создавай файлы через Cursor Edit, не через terminal write
```

### Пример: дельта для Claude Code

```markdown
## Claude Delta: docker-php

### Additional: pre_flight
Проверь `docker compose version` — скилл рассчитан на Compose v2.

### Additional: permissions
Скиллу нужны разрешения из пресета `docker` —
см. configs/claude-code/settings.docker.json
```

## Поле adapters во frontmatter

Frontmatter скилла перечисляет агентов, в которых скилл проверен:

```yaml
adapters: [claude, cursor, fable]
```

Это **декларация совместимости**, а не список дельта-файлов: скилл может быть
проверен в трёх агентах и не иметь ни одной дельты.

## Как swissknifeman vendor работает с дельтами

При установке с `--agent <name>` установщик кладёт рядом со `SKILL.md`
только дельту этого агента (если она есть) — дельты чужих агентов в целевой
проект не попадают.

## Чеклист при создании дельты

- [ ] В дельте нет текста, дублирующего SKILL.md
- [ ] Каждая секция — `Override:` или `Additional:` с понятным предметом
- [ ] Pre-flight хуки идемпотентны и безопасны (только проверки, без записи)
- [ ] Дельта упомянутого агента есть в `adapters:` frontmatter-а
