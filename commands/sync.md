---
description: Перераскатать управляемые артефакты mAInd (MCP, граф, память, хуки, скилл) на подключённые проекты.
argument-hint: "[<project-id> | --all | --namespace NS]"
allowed-tools: Bash(maind:*)
---
Синхронизация управляемых артефактов хаба **mAInd**. Ввод: «$ARGUMENTS».
Лаунчер — `maind` (фолбэк: `${CLAUDE_PLUGIN_ROOT}/bin/maind`).

## Шаги
1. **Цель** из «$ARGUMENTS»: конкретный `<project-id>` · `--all` (все enabled) · `--namespace <NS>`. Если пусто — спроси (по умолчанию предложи `--all`).
2. **Предпросмотр**: `maind sync <target> --dry-run --json` — покажи, что изменится.
3. **Применение** по подтверждению: `maind sync <target> --json`.
4. **Отчёт**: по каждому проекту/провиженеру — ok / skip / без изменений. Набор можно сузить флагом `--only`: `mcp,code-graph,graph,memory,health-hook,health-doc,feature-log-hook,ecosystem-skill`.
