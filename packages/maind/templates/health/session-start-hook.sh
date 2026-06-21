#!/usr/bin/env bash
# managed by maind — SessionStart healthcheck связи с хабом (НЕ блокирует работу).
# Печатает статус подключения (память + maind MCP) в контекст сессии Claude Code.
# Источник: <maind>/templates/health/session-start-hook.sh — правьте там и `maind sync
# --only health-hook --all --mode update`, а не в копии проекта.
MAIND="{{MAIND_BIN}}"
[ -x "$MAIND" ] || exit 0
"$MAIND" health --cwd 2>/dev/null || true
exit 0
