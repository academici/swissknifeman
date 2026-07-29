---
name: maind-overview
bucket: repository-bootstrap
version: 0.1.0
description: "Краткая схема работы хаба mAInd — что это, два механизма связывания (код-граф/Serena = граф кода, agent-memory = память/контекст), модель namespace'ов и ключевые команды. Используй, когда работаешь в репозитории maind или с любым проектом экосистемы academici и нужно понять, как устроены общая память, граф связей и их изоляция по namespace."
risk: read
persona: oss-dev
tags: [maind, ecosystem, memory, graph, root-bootstrap]
requires: []
produces_for: []
outputs: [chat]
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# mAInd — схема работы (кратко)

**mAInd** — хаб/шина экосистемы academici. Через него проходит весь поток информации между
проектами (`brain`, `swissknifeman`, `flexcrm`, `azguard`, …). Хаб связывает проекты **двумя
независимыми механизмами** — у них разные задачи, но общая цель «связать проекты»:

| Механизм | Что связывает | Как живёт |
|:--|:--|:--|
| **agent-memory** | память/контекст (факты, поток изменений) | Node-демон на хабе; в проекты раскатывается MCP-клиент |
| **код-граф (Serena)** | **код внутри** проекта (символы/ссылки/реализации) | per-project MCP-сервер `serena` (через `uvx`) |

Плюс собственный **maind-граф** — топология **между** проектами (кто от кого зависит, общие
пакеты, скиллы): федерация (граф на проект + индекс), строится `derive` из источников истины
(composer/Brain/`.maind.graph.json`/skills-lock), а не из ручного дубля.

## Namespaces — изоляция (общее правило для всех трёх)

Проект объявляет группы полем `projects[].namespaces` в `config.json`. **Внутри группы —
общее, между группами — изолировано.** `["*"]` — общая инфраструктура (видна всем).

- **Граф**: межпроектное ребро A↔B строится, только если A и B делят namespace.
- **Память**: бакеты `project:<id>` (приватно) · `ns:<имя>` (группа) · `global` (вся экосистема,
  wildcard). `recall`/MCP читают `project:<id>` + `ns:<свои группы>` + `global`.

**Дайджест на старте сессии (SessionStart-хук) — по умолчанию только `project:<id>`**
(`shared_max=0`, context-economy: чужой ns/global-контекст не течёт в каждую сессию без
спроса). Общий контекст группы поднимается ЯВНО, когда задача реально межпроектная — гайдлайн
и команды: [ecosystem-mcp] → «Межпроектная задача», доктрина — [docs/guide/memory.md].

[ecosystem-mcp]: ../ecosystem-mcp/SKILL.md
[docs/guide/memory.md]: ../../../../../packages/maind/docs/guide/memory.md

## Ключевые команды

```bash
# онбординг / провижининг
maind onboard <project>            # подключить проект: скиллы + память + граф + MCP
maind deploy <project>             # MCP-серверы хаба в .mcp.json (agentmemory + maind [+ код-граф])
maind sync --all                   # раскатать управляемые артефакты (mcp/graph/memory/health-*)
# здоровье / пруф-оф-лайф
maind health --cwd [--fix]         # связь проекта с хабом (не блокирует; --fix авто-чинит)
maind verify [--cwd]               # ПРУФ-ОФ-ЛАЙФ 3 плоскостей: реально ли ПИШУТ память,
                                   #   покрытие графа, поднята ли Serena — отличает «поднято» от «живёт»
maind doctor                       # диагностика узла (python/Node/agentmemory/конфиг/демон)
# граф / память
maind graph --project <id>         # граф одного проекта;  --cross [--namespace NS];  derive — пересборка
maind memory <recall|remember|forget|status>   # прямая работа с памятью по scope
# реестры / оркестрация
maind status                       # сводка узла (память/граф/агенты/проекты)
maind projects | agents | namespaces           # реестры узла (read-only листинги)
maind workspace <project>          # доверие Claude к проекту (.claude/settings.local.json)
maind run <…>                      # оркестрация (subprocess к skiller и пр.)
maind fleet <manifest|duplicates|similar|log>  # межпроектный слой (jscpd/эмбеддинги/feature-log)
maind migrate <…>                  # миграции состояния
maind mcp [--scope project:<id>]   # запустить как MCP-сервер (stdio JSON-RPC, 11 tools)
```

`health` vs `verify`: health отвечает «связь поднята/настроена», verify — «реально ли по этим
каналам ИДУТ данные» (seed vs last-write памяти, покрытие графа, живая Serena). Диагностируешь
«вроде подключили, а не работает» — это `verify`.

## MCP-инструменты хаба (11; per-project сервер `maind` из `.mcp.json`)

`maind mcp --scope project:<id>` (так раскатывает `deploy`) **изолирован к своему проекту**:
память/граф других проектов недоступны (scope сводится к `recall_scopes`: приватный + `ns:группы` +
`global`; графовые — только проекты, делящие namespace). Хаб-режим (`--scope global`) или
`MAIND_MCP_ALLOW_CROSS_SCOPE=1` снимают изоляцию (админ).

| Группа | Инструменты |
|:--|:--|
| память (3) | `maind_memory_store` · `maind_memory_recall` · `maind_memory_forget` (по `scope`) |
| граф (4) | `maind_graph_query` · `maind_graph_neighbors` · `maind_graph_path` · `maind_graph_project` |
| смешанные/реестры (4) | `maind_memory_links` (связи+ecosystem-link память) · `maind_agents_list` · `maind_projects_list` · `maind_projects_status` |

## Где смотреть в коде

- `lib/maind/federation.py` — раскладка графа + `graph_reader` (единый фасад чтения).
- `lib/maind/derive.py` — построение графа из источников истины.
- `lib/maind/namespaces.py` — изоляция связей + scope-бакеты памяти.
- `lib/maind/seed.py` — seed-память по namespace'ам.
- `lib/maind/mcp.py` — MCP-сервер (11 tools).
- Документация: `docs/ecosystem.md` (философия) → `docs/architecture.md` → `docs/guide/*`.
- Конвенции — `CLAUDE.md` в корне (stdlib-only, `Env` явно, atomic JSON, ru-сообщения).

## Провенанс (root-bootstrap, P1.2)

Класс A private/source-only root-bootstrap identity (D31/D38, `plans/2026.07.24-AGENT-RELIABILITY`):
канонический источник — этот файл; тонкие проекции — `.claude/skills/maind-overview/SKILL.md`
и `.agents/skills/maind-overview/SKILL.md` (генерируются `skiller registry`, не редактируются
руками). Бакет `repository-bootstrap` — приватный, не публикуется как обычный unit/core/marketplace,
не вендорится/коннектится в проекты-потребители.
