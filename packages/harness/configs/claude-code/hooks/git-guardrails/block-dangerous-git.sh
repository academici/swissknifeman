#!/bin/bash
# git-guardrails — PreToolUse-хук Claude Code: блокирует опасные git-команды ДО исполнения.
# Провенанс: производное от mattpocock/skills misc/git-guardrails-claude-code (MIT, © Matt Pocock);
# расширен паттернами force-with-lease / rebase --onto. Раздаётся через harness (источник истины хуков).
# Вход: JSON из stdin (.tool_input.command). Выход: exit 2 + сообщение в stderr → команда блокируется.

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command')

DANGEROUS_PATTERNS=(
  "git push"
  "git reset --hard"
  "git clean -fd"
  "git clean -f"
  "git branch -D"
  "git checkout \."
  "git restore \."
  "push --force"
  "push --force-with-lease"
  "reset --hard"
  "rebase --onto"
)

for pattern in "${DANGEROUS_PATTERNS[@]}"; do
  if echo "$COMMAND" | grep -qE "$pattern"; then
    echo "BLOCKED: '$COMMAND' совпал с опасным паттерном '$pattern'. Пользователь запретил эту команду." >&2
    exit 2
  fi
done

exit 0
