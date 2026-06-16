---
description: Онбординг проекта в экосистему mAInd — скиллы + память + граф + MCP. Уточняет набор диалогом, затем зовёт `maind onboard`.
argument-hint: "[путь-или-id] [recommended|full|minimal]"
allowed-tools: Bash(maind:*)
---
Подключаем проект к хабу **mAInd**. Ввод пользователя: «$ARGUMENTS».
Лаунчер — `maind` (если не в PATH — `${CLAUDE_PLUGIN_ROOT}/bin/maind`).

## Шаги
1. **Цель.** Если в «$ARGUMENTS» нет пути/id — спроси у пользователя путь к репозиторию или id проекта. Новый путь maind зарегистрирует сам.
2. **Набор** (CLI неинтерактивен — спрашиваешь ТЫ, через AskUserQuestion):
   - **bundle**: `recommended` (дефолт) · `full` (память federation + brain core) · `minimal` · `custom`;
   - **код-граф** (Serena, граф символов проекта) — да/нет → флаг `--with-code`;
   - **brain doc-sync** — да/нет → флаг `--with-brain`.
3. **Предпросмотр** (сначала ОБЯЗАТЕЛЬНО dry-run):
   `maind onboard <проект> --bundle <B> [--with-code] [--with-brain] --dry-run --json`
   Покажи пользователю план шагов из вывода.
4. **Применение** по подтверждению (без `--dry-run`, с `--yes`):
   `maind onboard <проект> --bundle <B> [--with-code] [--with-brain] --yes --json`
5. **Отчёт.** Пройди по шагам вывода (register / skills / deploy / graph / memory / skill). Шаги `skipped` из-за отсутствия swissknifeman/brain — это нормально (каждый шаг standalone-safe).

onboard транзитивно поднимает скиллы (swissknifeman `integrate`) и MCP-серверы хаба — отдельно их ставить не нужно.
