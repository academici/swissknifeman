# auto-approve — sources

This hook is adapted and combined from three projects. The logic has been rewritten and
expanded (config management, modes strict/permissive/bypass, tiered-deny, log
solutions), but the basic ideas come from:

| Project | What's taken |
|---|---|
| [oryband/claude-code-auto-approve](https://github.com/oryband/claude-code-auto-approve) | Parsing compound commands via AST `shfmt`, read allow/deny, active `deny`. |
| [yigitkonur/auto-approve-claude-plan](https://github.com/yigitkonur/auto-approve-claude-plan) | Auto-confirm plan dialog (`ExitPlanMode`), link with `defaultMode: bypassPermissions`. |
| [froggeric/claude-smart-approval](https://github.com/froggeric/claude-smart-approval) | Decomposition of compound commands into segments, the idea of two-stage evaluation (Stage-2 AI — NOT enabled, deterministic mode left). |

## What's done differently here

- Constructions (allow / deny_hard / deny_block / read-subcommands) moved to
  `config.json` — only logic in the code; yes per-project override.
- Three modes in one switch (`auto-approve.sh` + `env.ini`): strict,
  permissive, bypass (+ off).
- Tiered-deny: catastrophic → active `deny`, mutations → prompt.
- Log of all decisions in `~/.claude/logs/auto-approve-decisions.jsonl`.
- `shfmt` optional: if available - AST-parsing as union-gain; otherwise regex.
- Stage-2 AI and auto-learning from froggeric are intentionally NOT included (determinism).
