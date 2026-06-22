# Интеграции

swissknifeman раздаёт скиллы и конфиги. Этот раздел — каталог **внешних
инструментов**, которые подключаются к Claude Code рядом: MCP-серверы (дают агенту
новые инструменты) и не-MCP утилиты (процессы поверх агента).

Каталог решает две задачи: даёт проверенное описание каждого инструмента (что это,
зачем, подводные камни) и для курированного набора MCP — готовый пресет, который
ставится одной командой.

## Как ставится

- **Пресетом через `integrate`** (рекомендуется для курированного набора). Проверенные
  конфиги серверов лежат в `configs/claude-code/mcp/<name>.json`; `integrate` вливает их
  в `<проект>/.mcp.json` merge-only (чужие серверы целы, бэкап `*.bak`):

  ```bash
  skiller integrate --mcp playwright,filesystem
  ```

  `context7` входит в dev-дефолт и ставится без флага (во всё, кроме obsidian-vault).
  Остальные пресеты — **opt-in** через `--mcp`.
- **Вручную** — скопировать пример конфига со страницы инструмента в `.mcp.json` проекта.

::: tip Хаб себя не конфигурирует
swissknifeman **раздаёт** пресеты в проекты-потребители, а не правит собственный
`.mcp.json`. Корневой `.mcp.json` реестра держит машинно-специфичные серверы — его не
трогаем.
:::

## MCP-серверы

| Инструмент | Пресет | Назначение |
|---|---|---|
| [Context7](./context7) | `context7` (dev-дефолт) | актуальная документация библиотек в контексте |
| [Playwright MCP](./playwright-mcp) | `playwright` | браузерная автоматизация, E2E |
| [filesystem](./filesystem) | `filesystem` | доступ к файлам в заданных каталогах |
| [fetch](./fetch) | `fetch` | HTTP-запросы → markdown |
| [memory](./memory) | `memory` | knowledge graph между сессиями |
| [sequential-thinking](./sequential-thinking) | `sequential-thinking` | пошаговое рассуждение |
| [GitHub MCP](./github) | `github` (remote) | Issues / PR / репозитории |
| [Task Master AI](./task-master) | — (docs-only) | управление задачами из PRD |

## Не-MCP инструменты

| Инструмент | Тип | Назначение |
|---|---|---|
| [GitHub Spec Kit](./spec-kit) | CLI + шаблоны | spec-driven development |
| [Claude Code Router](./claude-code-router) | прокси | роутинг между моделями — ⚠️ под сомнением |

## Состав курированного набора

Пресеты `playwright`, `filesystem`, `fetch`, `memory`, `sequential-thinking`, `github` —
**opt-in**: по умолчанию не ставятся, только по `--mcp`. По умолчанию в среды разработки
едет только `context7`. Полный список пресетов — `configs/claude-code/mcp/`, см. также
[обзор конфигов](../configs/).
