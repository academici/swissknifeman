#!/usr/bin/env bash
# managed by maind — SessionStart healthcheck связи с хабом (НЕ блокирует работу).
# Тихий при здоровой связи (--strict rc=0 → exit 0, без контекст-нагрузки); печатает статус
# подключения (память + maind MCP) в контекст сессии ТОЛЬКО когда что-то нездорово.
# Источник: <maind>/templates/health/session-start-hook.sh — правьте там и `maind sync
# --only health-hook --all --mode update`, а не в копии проекта.
# Лаунчер maind: env MAIND_BIN → PATH (command -v). Без машинно-специфичного пути
# в артефакте — генерируемый хук одинаков на любой машине. Не нашли → тихий no-op.
MAIND="${MAIND_BIN:-}"
[ -n "$MAIND" ] || MAIND="$(command -v maind 2>/dev/null)"
[ -n "$MAIND" ] && [ -x "$MAIND" ] || exit 0
out="$("$MAIND" health --cwd --strict 2>/dev/null)"
rc=$?
[ "$rc" -eq 0 ] && exit 0
[ -n "$out" ] && printf '%s\n' "$out"
exit 0
