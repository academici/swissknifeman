# Repository baseline — 2026-07-19

**Тип источника:** repo recon  
**Маркер:** RAG:— (repo-grounded: дерево swissknifeman на 2026-07-19)

## Масштаб

- 216 canonical skills в `packages/skiller/skills/`.
- 54 Claude plugin manifests/directories в текущем registry.
- 32 task commands, из них 11 в основном task workflow.
- 8 MCP presets, 10 agent packs, 25 проектов в корневом `config.json`.
- `plans/2026.07.18-FOREMAN`: 9 из 33 item'ов закрыты; P0 закрыта, P1 — 3/4,
  следующий item до паузы — P1.4.

Числа являются baseline первого design-pass и должны быть детерминированно пересчитаны
в P0.1 перед запечатыванием capability contract; они не являются вечными константами.

## Главные Claude-coupled seams

| Пакет | Текущая связность | Основные поверхности миграции |
|:--|:--|:--|
| `skiller` | registry и connect ориентированы на `.claude-plugin`/`.claude` | manifests, marketplace, connect/vendor/update, skills lock |
| `harness` | исходные конфиги живут под `configs/claude-code` | settings, permissions, hooks, MCP, agents/agent packs |
| `maind` | deploy targets — Claude/Cursor/VSCode; default `.mcp.json` | provider targets, trust, sync provisioners, project loop |
| `task` | команды несут Claude model/effort и slash/tool vocabulary | общий command contract, routing, два набора adapters |
| `analyst` | sessions/runs читаются из `.claude` и `~/.claude/projects` | neutral events/runs и provider readers |
| `core` | отдельные Claude path/default assumptions | provider ids, config schema, resolver, shared diagnostics |

Приблизительный первичный поиск Claude-specific текста дал 665 файлов. Runtime-срез:
`core` — 7 файлов/14 строк, `skiller/lib` — 17/121, `harness/lib` — 12/108,
`maind/lib` — 11/78, `analyst/lib` — 10/41, `task/lib` — 0. Это карта разведки,
не критерий завершения: строка может быть допустимым Claude adapter'ом.

## Fleet-config

В `config.json` зарегистрированы 25 проектов: 22 имеют MCP-конфигурацию, 22 используют
Perplexity, 15 помечены как code projects, 6 имеют Cursor targets. Поля `providers` сейчас
нет ни у одного проекта. Значит миграция должна добавить схему и defaults без массового
переписывания всех проектов в первой волне.

## Временный Codex bootstrap

- Корневой `AGENTS.md` и `.agents/skills/*` уже позволяют этой сессии видеть тонкие
  adapters; canonical content они не дублируют.
- `.mcp.json.example` дополнен Serena; локальная `.serena/` и глобальная Codex MCP
  конфигурация пока являются bootstrap state, а не финальным distribution contract.
- mAInd status на 2026-07-19: memory daemon доступен на `127.0.0.1:4111`, graph federation
  содержит 291 node / 1007 edges, проект `swissknifeman` — connected/trusted.

