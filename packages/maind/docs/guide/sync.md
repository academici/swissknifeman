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
| `memory` | upsert базового факта о связях только в `project:<id>` | `seed.py` |
| `memory-hook` | `MODE=manual`: снять digest и оставить native off; `MODE=maind`: явно включить SessionStart digest | `health.py` |
| `health-hook` | opt-in SessionStart-хук (`observability.session_start_health_hook`; по умолчанию снят) | `health.py` |
| `health-doc` | управляемый блок «приоритет №1» в `CLAUDE.md` | `health.py` |
| `feature-log-hook` | opt-in SessionEnd-публикация коммита (`code_graph.feature_log_hook`; по умолчанию снята) | `health.py` |
| `ecosystem-skill` | управляемый скилл `ecosystem-mcp` (что за MCP-инструменты, связи, починка) в `.claude/skills/` | `skilldoc.py` |
| `setup-skill` | управляемый скилл `ecosystem-setup` (дерево решений тулинга проекта) в `.claude/skills/` | `skilldoc.py` |
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

В корневом репозитории SwissKnifeMan `ecosystem-mcp` и `ecosystem-setup` также существуют как
тонкие проекции `repository-bootstrap`, принадлежащие `skiller registry`. Если файл явно
указывает этот `canonical` и `generator`, `maind sync` возвращает `foreign-owner` и не
перезаписывает ни одну из двух проекций скилла. `maind doctor --skill-drift` не считает их
дрейфом шаблона maind; исправлять такие проекции нужно через `skiller registry`.

## Как узнать, что sync вообще нужен (drift-gate)

`sync` детерминирован (content-hash), но **сам себя не вызывает**. Шаблоны провиженеров
(`templates/skills/ecosystem-mcp/SKILL.md` и т.п.) и реестр скиллов (`skiller`) со временем
улучшаются, но уже онбордженным проектам это не прилетает, пока кто-то вручную не перезапустит
sync — «регулярно докатывает» из примечания выше требует триггера. Read-only проверка, что
триггер назрел:

```bash
maind doctor --skill-drift        # ecosystem-mcp/ecosystem-setup: absent/stale по флоту enabled-проектов
skiller doctor --vendor-drift     # vendor-скиллы (buckets/include CORE_SKILLS): add/update/remove по флоту
```

Оба — сухой прогон (`plan_sync`/`_apply_managed_skill(..., dry=True)`), ничего не пишут; в
обычном `doctor` (без флагов) — по одной summary-строке. Прогоняй после ЛЮБОГО точечного
(`--only`) онбординга/интеграции — не только после `--all`: `--only` синки чаще всего и
оставляют «половину проекта» несинхронизированной, потому что применяют не весь набор
провиженеров. Реальный инцидент (2026-07): проект `agelto` две недели работал без графа кода
Serena — `ecosystem-mcp` был раскатан ДО того, как в шаблон добавили правило «сначала граф,
потом grep», и никто не перезапустил sync, чтобы это подхватить; агент тихо читал файлы
целиком вместо `find_symbol`, drift был не виден без этой команды.

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
