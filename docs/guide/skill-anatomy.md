# Анатомия скилла

Скилл — это папка внутри bucket-а. Минимум — один `SKILL.md`; обычно рядом
лежат сниппеты и адаптерные delta-файлы.

```
skills/php/laravel-testing/
├── SKILL.md          # обязательный: frontmatter + инструкции для агента
├── snippets/         # примеры кода, шаблоны, справочные файлы
│   ├── index.json    # манифест сниппетов
│   └── pest-example.md
├── adapters/         # опционально: overrides под конкретные IDE
│   ├── claude.md
│   └── cursor.md
└── upstream.json     # только у внешних скиллов (см. Upstream-sync)
```

## SKILL.md

Файл состоит из YAML-frontmatter и тела с инструкциями:

```markdown
---
name: skill-name
bucket: founder|pm|architect|oss-dev|quality|operator|devops|php|roles|imported
version: 0.1.0
description: "Краткое описание скилла"
risk: read|draft|write|external
persona: founder
tags: []
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

## Контекст
Когда использовать этот скилл и почему он нужен.

## Входные данные
Что агент должен знать перед выполнением.

## Алгоритм
Пошаговые инструкции для агента.

## Выходные данные
Конкретные файлы, которые будут созданы.

## Чеклист качества
- [ ] Критерий 1

## Ссылки
- snippets/example.md
```

## Ключевые поля frontmatter

| Поле | Назначение |
|---|---|
| `name` | уникальное имя; при плоской раскладке коллизии решаются префиксом bucket-а |
| `description` | по нему агент решает, когда применить скилл — пишите конкретно |
| `risk` | `read` — только чтение, `draft` — черновики, `write` — меняет файлы, `external` — внешние вызовы |
| `requires` / `produces_for` | связи между скиллами (например, `prd-from-brd` требует выхода `brd`) |
| `snippets` | список сниппетов, которые скилл использует |
| `adapters` | в каких агентах скилл проверен |
| `sha256` | заполняется автоматически `sync.sh` |

## Сниппеты

`snippets/` — это рабочие материалы скилла: примеры кода, шаблоны документов,
справочники. Манифест `index.json` перечисляет файлы и проверяется
`validate.sh`. Сниппеты позволяют держать `SKILL.md` коротким: инструкции
отдельно, объёмные примеры отдельно.

## Delta-файлы адаптеров

Специфика конкретной IDE не смешивается с основным скиллом, а выносится в
`adapters/<agent>.md` внутри папки скилла:

- `adapters/claude.md` — overrides для CLAUDE.md-специфики Claude Code;
- `adapters/cursor.md` — overrides для `.cursor/rules`.

Так один скилл остаётся provider-neutral, а адаптеры накладывают тонкую
настройку при установке. Формат дельт (`Override:` / `Additional:`, pre-flight
хуки) — в [спецификации адаптерных дельт](/guide/adapter-deltas).

## upstream.json

Присутствует только у внешних скиллов и описывает источник и стратегию
обновления — подробно в [Upstream-sync](/guide/upstream-sync). Главное правило:
**нет `upstream.json` → скилл самописный, sync-тулинг его не трогает**.
