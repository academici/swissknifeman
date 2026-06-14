# auto-approve — источники

Этот хук-комплекс адаптирован и объединён из трёх проектов. Логика переписана и
расширена (конфиг-управление, режимы strict/permissive/bypass, tiered-deny, лог
решений), но базовые идеи — оттуда:

| Проект | Что взято |
|---|---|
| [oryband/claude-code-auto-approve](https://github.com/oryband/claude-code-auto-approve) | Разбор компаунд-команд через AST `shfmt`, чтение allow/deny, активный `deny`. |
| [yigitkonur/auto-approve-claude-plan](https://github.com/yigitkonur/auto-approve-claude-plan) | Авто-подтверждение диалога плана (`ExitPlanMode`), связка с `defaultMode: bypassPermissions`. |
| [froggeric/claude-smart-approval](https://github.com/froggeric/claude-smart-approval) | Декомпозиция компаунд-команд на сегменты, идея двухстадийной оценки (Stage-2 AI — НЕ включён, оставлен детерминированный режим). |

## Что здесь сделано иначе

- Конструкции (allow / deny_hard / deny_block / read-субкоманды) вынесены в
  `config.json` — в коде только логика; есть per-project override.
- Три режима в одном переключателе (`auto-approve.sh` + `env.ini`): strict,
  permissive, bypass (+ off).
- Tiered-deny: катастрофичное → активный `deny`, мутации → промпт.
- Лог всех решений в `~/.claude/logs/auto-approve-decisions.jsonl`.
- `shfmt` опционален: при наличии — AST-разбор как union-усиление; иначе regex.
- Stage-2 AI и auto-learning из froggeric намеренно НЕ включены (детерминированность).
