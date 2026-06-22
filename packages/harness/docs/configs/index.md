# Конфиги: швейцарский нож для агентов

Скиллы — половина дела. Чтобы агент в новом проекте работал сразу, нужны ещё
и **конфиги**: разрешения, настройки, специфика IDE. Раздел `configs/` собирает
готовые конфиги в одном месте — по тому же принципу, что и скиллы: один
источник истины, установка одной командой.

## Что уже есть

| Конфиг | Где лежит | Что делает |
|---|---|---|
| [Пресеты permissions для Claude Code](/harness/configs/claude-permissions) | `configs/claude-code/` | готовые `settings.json` с максимально разрешённым доступом: git, composer, artisan, npm, docker — по стекам |
| MCP-серверы | `configs/claude-code/mcp/` | пресеты `.mcp.json`; `context7` ставит `skiller integrate` по умолчанию, курированный сабсет (playwright, filesystem, fetch, …) — opt-in через `--mcp`. Каталог: [Интеграции](/harness/integrations/) |

## Сценарий

Подняли новый проект — например, на Laravel. Две команды, и агент полностью
готов к работе:

```bash
# 1. Скиллы: автодетект → architect, php, devops, quality, operator
skiller connect

# 2. Permissions: автодетект → base + laravel + node (+ docker, если есть Dockerfile)
~/projects/packages/swissknifeman/packages/skiller/scripts/apply-permissions.sh --target .
```

После этого Claude Code может запускать `php artisan`, `composer`, тесты,
линтеры и git-команды без permission-промптов, а секреты (`.env`, ключи,
`~/.ssh`) остаются под запретом.

## Что планируется

Раздел будет расти по мере накопления практики:

- **Агенты** — преднастроенные субагенты (`.claude/agents/`) под типовые роли;
- **Хуки** — `settings.json`-хуки: автоформатирование после правок, валидация
  перед коммитом;
- **Больше MCP-серверов** — `context7` раздаётся по умолчанию, курированный сабсет
  (playwright, filesystem, fetch, memory, sequential-thinking, github) — opt-in через
  `--mcp`; каталог инструментов — раздел [Интеграции](/harness/integrations/). Дальше — новые
  проверенные конфигурации `.mcp.json`;
- **Конфиги других IDE** — правила Cursor, настройки Perplexity.

Принцип тот же, что у скиллов: всё проверено в бою, всё в одном месте,
ставится одной командой.
