---
description: Показать плагины/marketplace экосистемы academici и включить нужные — maind как хаб управляет плагинами (maind · swissknifeman · brain).
argument-hint: "[enable <plugin>@<marketplace>]"
allowed-tools: Bash(jq:*), Read, Edit
---
Управление плагинами экосистемы academici из хаба **mAInd**. Ввод: «$ARGUMENTS».

## Текущее состояние (read-only)
!`jq '{enabledPlugins, marketplaces: (.extraKnownMarketplaces // {} | keys)}' ~/.claude/settings.json 2>/dev/null`

## Что сделать
1. Покажи пользователю: какие marketplace зарегистрированы и какие плагины включены (`enabledPlugins`).
2. Сопоставь с экосистемой — должны быть доступны три плагина:
   - `maind@maind` (хаб: онбординг/sync/статус/здоровье),
   - `skm@swissknifeman` (скиллы проекта: бакеты/connect/vendor/integrate),
   - `brain@brain` (docs-sync валта).
   Отметь, чего не хватает (нет marketplace или плагин выключен).
3. Если пользователь просит включить — отредактируй `~/.claude/settings.json` (Edit, сохраняя остальное):
   - впиши `"<plugin>@<marketplace>": true` в `enabledPlugins`;
   - если marketplace не зарегистрирован — добавь в `extraKnownMarketplaces` запись `{ "source": { "source": "directory", "path": "<путь к репо>" } }` (пути: maind→этот репозиторий, swissknifeman/brain — их каталоги).
4. Напомни: изменения активируются **после перезагрузки** Claude Code.

> Это и есть «хаб управляет плагинами»: maind пишет `enabledPlugins`/marketplaces, как `connect.py` у swissknifeman. Сами операции в проектах делают команды `/maind:*`, `/skm:*`, `/brain:*`.
