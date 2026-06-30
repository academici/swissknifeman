#!/bin/bash
# daemon-safety — PreToolUse-хук Claude Code: блокирует деструктивные операции над
# ОБЩИМИ долгоживущими демонами (perplexity-web-mcp и т.п.) ДО исполнения.
# Зачем: демон обслуживает несколько живых агентов; pkill/rm его профиля/сокета/
# Singleton-локов рушит чужие сессии. Корректный путь — переиспользовать живой
# браузер или дождаться простоя, а не kill+restart вслепую.
# Раздаётся через harness (источник истины хуков). Снять разово: PERPLEXITY_DAEMON_GUARD=off.
# Вход: JSON из stdin (.tool_input.command). Выход: exit 2 + stderr → команда блокируется.

[ "$PERPLEXITY_DAEMON_GUARD" = "off" ] && exit 0

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')
[ -z "$COMMAND" ] && exit 0

# Деструктив над процессами браузерных демонов.
KILL_PATTERNS=(
  "pkill.*(perplexity|playwright|chromium|chrome)"
  "killall.*(perplexity|playwright|chromium|chrome)"
  "kill +-9.*(perplexity|playwright|chromium)"
)
# Удаление профиля / сокета / локов демона.
RM_PATTERNS=(
  "rm .*Singleton"
  "rm .*\.playwright/(profile|profiles)"
  "rm .*perplexity-web-mcp"
  "rm .*profile\.lock"
  "rm .*perplexity.*\.sock"
)

block() {
  echo "BLOCKED (daemon-safety): '$COMMAND' совпал с '$1'." >&2
  echo "Это рушит общий демон, обслуживающий других агентов. Сначала убедись, что демон простаивает," >&2
  echo "переиспользуй живой браузер или дождись очереди. Разовый обход: PERPLEXITY_DAEMON_GUARD=off." >&2
  exit 2
}

for p in "${KILL_PATTERNS[@]}" "${RM_PATTERNS[@]}"; do
  if echo "$COMMAND" | grep -qE "$p"; then
    block "$p"
  fi
done

exit 0
