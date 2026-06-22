# GitHub Spec Kit

## Что это

GitHub Spec Kit — тулкит для **spec-driven development**: заставляет AI-агента написать
спецификацию до кода. Это не MCP-сервер, а CLI `specify` + набор шаблонов и slash-команд,
которые встраиваются в агента (поддерживает Claude Code, Copilot, Cursor, Gemini CLI и др.).

- Репозиторий: <https://github.com/github/spec-kit>
- Документация: <https://github.github.com/spec-kit/>

## Рабочий цикл

Четыре фазы, каждая — markdown-файл, который читает следующая:

```
Specify → Plan → Tasks → Implement
```

После `specify init` агент получает slash-команды (`/specify`, `/plan`, `/tasks`,
`/implement` и др.) — от описания требований до генерации задач и реализации.

## Установка

Через `uvx` (Python/uv), интеграция под Claude Code:

```bash
uvx --from git+https://github.com/github/spec-kit.git specify init my-project \
  --integration claude
```

## Связь с практиками хаба

::: tip Уже есть пересекающиеся практики
В swissknifeman дисциплина «спека/решение до кода» закрыта скиллами:
`general/spec-interview` (интервью и ТЗ перед кодом), `general/task-brief-template`
(цель/границы/инварианты/DoD), `architect/architecture` и
`architect/package-contribution-protocol` (ADR-шаблон, граница «проект ↔ пакет»).
Spec Kit — это внешний *тулинг* того же подхода со своими slash-командами; бери его, если
нужен готовый каркас spec→plan→tasks→implement, а не как замену этим скиллам.
:::

Спецификация Spec Kit хорошо ложится в PRD для [Task Master](./task-master).

## Ограничения

- Ценность — в соблюдении процесса, а не в технологии: без дисциплины шаблоны просто лежат.
- Требует `uv` (Python).
- Базовые материалы — на английском; для русскоязычной команды адаптируй формулировки.
