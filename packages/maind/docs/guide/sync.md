# Sync — единый провижининг

`maind sync` — одна команда, которая анализирует `config.json` и раскатывает **управляемые
артефакты** на подключённые проекты. Фан-аут по проектам и резолв пути/scope вынесены в общий
контекст (`sync.py`), чтобы не дублировать цикл в каждом модуле; `maind deploy` — это
`sync --only mcp`.

## Команда

```bash
maind sync --all                                   # все enabled-проекты, все провиженеры
maind sync --project flexcrm                       # один проект
maind sync --namespace axioma                      # фан-аут по namespace-группе
maind sync --all --only mcp,graph --mode update    # сузить набор и режим
maind sync --all --dry-run --json                  # план без записи, машинно-читаемо
```

Выбор проектов (`select_projects`) — ровно один из `--project` / `--namespace` / `--all`.

## Провиженеры (в порядке применения)

| Провиженер | Что делает | Модуль |
|:--|:--|:--|
| `mcp` | пишет MCP-серверы хаба (agent-memory + maind [+ код-граф]) в `.mcp.json` проекта | `deploy.py` |
| `code-graph` | стартовый `.serena/project.yml` (при `code:true`, движок Serena) — язык + игноры + initial_prompt | `codegraph.py` |
| `graph` | `derive` графа проекта из источников + пересборка `_index.db` | `derive.py` |
| `memory` | seed базового факта о связях в `project:<id>` + `ns:<группа>` | `seed.py` |
| `memory-hook` | SessionStart-инжект дайджеста памяти + `autoMemoryEnabled:false` для проектов на `MODE=maind` (revert для ушедших на native/off) — авто-загрузка памяти | `health.py` |
| `health-hook` | SessionStart-хук связи с хабом в `.claude/settings.json` | `health.py` |
| `health-doc` | управляемый блок «приоритет №1» в `CLAUDE.md` | `health.py` |
| `feature-log-hook` | SessionEnd-хук фиксации нового коммита в общую память (при `code_graph.feature_log_hook`) | `health.py` |
| `ecosystem-skill` | управляемый скилл `ecosystem-mcp` (что за MCP-инструменты, связи, починка) в `.claude/skills/` | `skilldoc.py` |
| `skills-catalog` | `skiller update` — пере-резолв каталога скиллов (buckets/exclude с диска); новый скилл уже выбранного бакета (напр. `pao` в `php`) доезжает без ручного re-run | `orchestrate.py` → `skm:update` |
| `agent-pack` | детерминированная раскатка/апгрейд agent-pack(ов) профиля проекта | `orchestrate.py` → `env:agent-pack` |
| `output-style` | `outputStyle: lean` (терсе-голос агента, токен-экономия) во все `.claude/settings.local.json`; опт-аут — `project.output_style: "off"` | `orchestrate.py` → `env:hooks` |
| `router-config` | каталог intent-router (`.claude/agent-router.config.json`), только для проектов с включённым хуком | `orchestrate.py` → `env:router` |

> `memory-hook` читает «намерение» памяти из `<project>/.claude/memory.env.ini` (`MODE`),
> который пишет `maind onboard --memory`. Так авто-загрузку можно докатить на уже подключённые
> проекты без полного onboard: `maind sync --all --only memory-hook`.
>
> `skills-catalog`/`output-style` — тот же принцип для скиллов и терсе-голоса: `skiller
> integrate` (и через него `maind onboard`) ставит их только на **новых** онбордингах;
> `maind sync --all` регулярно докатывает то же самое на уже подключённые проекты.

`--only mcp,graph,...` ограничивает набор (имена сверяются с реестром, опечатка → ошибка).

## Режимы (`--mode`)

«Метод синка по области»:

| mode | поведение |
|:--|:--|
| `install` | создать, только если артефакта нет |
| `update` | обновить уже существующее (drift по content-hash) |
| `auto` (по умолчанию) | и то, и другое: нет → install, устарело → update, свежо → skip |

`changed` в отчёте — честный: graph-провиженер сравнивает содержимое стора (сериализация
детерминирована), а doc/hook — content-hash блока. `--dry-run` ничего не пишет и показывает план.

## Пример вывода

```
sync (mode=auto, проектов 1, провиженеры: mcp, graph, memory, memory-hook, health-hook, health-doc, ecosystem-skill)
  ✓ mcp             flexcrm            .mcp.json
  ✓ graph           flexcrm            12n/9e (code 7, doc 1)
  ○ memory          flexcrm            демон памяти не запущен
  ✓ health-hook     flexcrm            установлен
  ✓ health-doc      flexcrm            обновлён
  ✓ ecosystem-skill flexcrm            .claude/skills/ecosystem-mcp/SKILL.md
```

Дальше: [Доверие (workspace) →](./workspace)
