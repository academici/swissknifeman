# CLI

Лаунчер `bin/maind` — тонкий bash-обёртка: проверяет окружение и вызывает
`python3 -m maind <repo_root> <cmd> [args]`. Корень узла — каталог установки maind.

## Команды

```bash
maind start [--only memory|graph]      # поднять воркеры узла
maind status [--json]                  # сводка: память, граф, агенты, проекты

maind memory start                     # запустить демон памяти (Node)
maind memory run                       # foreground (exec node) — для systemd
maind memory stop                      # остановить (только свой, чужой не трогает)
maind memory status [--json]

maind service install                  # systemd --user: автозапуск демона памяти
maind service {start|stop|restart|status|logs|uninstall}   # управление юнитом

maind graph query --from project:brain --depth 2 [--edge-types depends_on,uses] [--json]
maind graph neighbors --node project:maind --direction in
maind graph stats [--json]
maind graph --project flexcrm          # граф одного проекта (федерация)
maind graph --cross [--namespace NS]   # межпроектный слой (_index.db), опц. одна группа
maind graph derive [--project ID | --all]   # собрать графы из composer/Brain/override/skills
maind graph rebuild                    # пересобрать _index.db
maind graph export --project flexcrm   # граф проекта → Mermaid (копи-пейст в .md)
maind graph export --cross [--raw]     # весь межпроектный слой → Mermaid (--raw: без ```-обёртки)

maind agents register <id> [--project P --pid N --kind K]
maind agents heartbeat <id>
maind agents list [--all --json]
maind agents kill <id> [--force]

maind projects list [--namespace NS] [--json]
maind projects health [--project ID | --namespace NS | --all] --evidence-set FILE --json
maind projects sync --from brain [--path DIR]
maind namespaces [--json]              # namespace-группы экосистемы и их проекты-члены

maind deploy [--project ID | --all] [--with-code] [--dry-run]   # MCP-серверы хаба (= sync --only mcp)
maind sync [--project ID | --namespace NS | --all] [--only mcp,graph,memory,memory-hook,health-hook,health-doc,ecosystem-skill] \
           [--mode install|update|auto] [--dry-run] [--json]        # раскатать управляемые артефакты
maind health [--cwd | --project ID] [--fix] [--strict] [--json]     # healthcheck связи проекта с хабом
maind workspace sync [--dry-run] [--no-allow] [--no-mode]           # доверие Claude к проектам экосистемы
maind workspace status [--json]
maind run <project> <capability> [-- args]   # дёрнуть команду brain / swissknifeman

maind fleet manifest                                      # проекты + группы по общим пакетам (JSON)
maind fleet duplicates [--group PKG | --projects a,b] [--min-tokens N] [--json]  # кросс-проектные дубли (jscpd)
maind fleet similar [--group PKG | --projects a,b] [--threshold T] [--json]  # семантически похожий код (эмбеддинги)
maind fleet log "<что сделал>" [--project ID]            # feature-факт в общую память
maind fleet features [--namespace NS]                    # feature-факты группы

maind onboard <project> [--with-code] [--with-brain]            # единый онбординг

maind migrate from-brain <.projects.json> [--force]
maind migrate from-agentmemory <dir> [--force]

maind mcp                              # запустить как MCP-сервер (stdio)
maind doctor [--quiet]                 # диагностика окружения
maind doctor --audit mcp|claude|deny|core|pao|settings|all [--json]  # fleet-аудит по проектам
maind doctor --context [--json]        # флот-агрегация always-on футпринта первого хода
                                        #   (skiller budget --first-turn по каждому проекту)
maind doctor --skill-drift             # дрейф ecosystem-mcp/ecosystem-setup от шаблона, по проектам
maind doctor --channel-drift           # дубль-канал skiller (connect+vendor на один бакет)
maind doctor --gitignore-drift [--project ID] [--block] [--json]
                                        # .gitignore/tracking каждого проекта vs карта служебных файлов
                                        #   (configs/gitignore-policy.json); --block — готовые строки .gitignore
maind verify [--json]                  # пруф работы 3 плоскостей: пишут реально или вхолостую
maind analyze [--cwd | --project ID] [--session ID] [--no-health] [--json]
                                        # post-run verdict с проверкой provenance run-report
maind version                          # git SHA + путь к узлу
```

`analyze` доверяет legacy run-report только после сверки project/session/provider identity.
Абсолютные `files_changed` вне выбранного проекта также считаются конфликтом provenance. Такой
отчёт исключается из RED-причин и возвращается как `ATTENTION` с
`RUN_REPORT_PROJECT_MISMATCH`; отсутствие доверенного report понижает confidence, но не доказывает
ошибку продукта.

## Как это устроено

- Разбор аргументов — `common.parse_args` (флаги `--x` + позиционные), не argparse.
- Каждая команда — функция `cmd_X(env, argv)` из словаря `COMMANDS` в `cli.py`.
- Контекст запуска — frozen-dataclass `Env` (корень узла, команда, HOME) — передаётся
  явно, без модульных глобалей. Поэтому всё легко тестируется.

Дальше: [MCP-сервер →](./mcp)
