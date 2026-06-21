# Миграция

## Из brain (проекты)

```bash
maind migrate from-brain ~/Vaults/Brain/.projects.json [--force]
```

Собирает `config.json` (в корне монорепо; legacy-имя `.maind.json` всё ещё подхватывается)
из brain-кэша проектов (реальная схема brain маппится в формат maind), прописывает
`integrations.brain` и **материализует граф** (проекты как узлы). Отказывается
перезаписывать существующий `config.json` без `--force`.

## Из agent-memory (конфиг демона)

```bash
maind migrate from-agentmemory ~/Vaults/Brain/.agentmemory [--force]
# alias: maind migrate from-skm ...
```

Переносит `iii-config.yaml` в `config/memory/iii-config.yaml` узла, проставляя
`service_name: maind`. **Источник не изменяется** — перенос недеструктивный.

## Перенос памяти Brain в maind (рекомендованный сценарий)

maind становится каноничным домом памяти; Brain — клиентом. Безопасно и обратимо:

1. **Конфиг**: `maind migrate from-agentmemory ~/Vaults/Brain/.agentmemory`.
2. **Данные** (не теряем существующую память): скопировать (не переносить!)
   `~/Vaults/Brain/data/state_store.db` и `stream_store/` в `maind/data/`.
3. **Порты**: maind держит тот же `4111/4112` — клиенты Brain (его `.mcp.json`) продолжают
   работать против демона maind прозрачно. Если на время нужно гонять оба демона — задайте
   maind свой `AGENTMEMORY_PORT` в `.env`.
4. **Регистрация**: добавить `maind` в MCP-карту Brain (`.mcp.json` / `CLAUDE.md`).

::: tip Обратимость
`.agentmemory/` в Brain остаётся на месте (помечен как superseded), данные копируются, а
не переносятся — откат тривиален. maind никогда не убивает чужой (не свой) демон.
:::
