# P7 design preflight — 2026-09-10

## Environment

- Exact Codex route capture: `gpt-5.6-sol/high`, class `frontier`, cwd repository root, approval
  `never`, sandbox `danger-full-access`; source `provider-thread-state`, green.
- `packages/maind/bin/maind health --cwd --json`: `connected`, memory round-trip and Codex provider
  trust green.
- `packages/harness/bin/harness hooks --target . --provider codex --observer --trusted --dry-run`:
  one `context.observer` surface, registration and handler both `clean -> noop`, green.
- Baseline plan lint: `plan-lint: OK (1 plan, 0 errors, 0 warnings)`.
- `codex doctor --json`: overall warning because the Responses WebSocket handshake returned HTTP
  503; HTTPS fallback remained available. This transport warning is not treated as a green
  WebSocket check and does not alter repository evidence or the verified current route.

## Repository measurements

The five canonical `packages/task/commands/plan-*.md` files contain 150,605 bytes; canonical
`packages/skiller/skills/general/plan-protocol/SKILL.md` contains 25,720 bytes; total 176,325 bytes.
The exact P7 budget is therefore at most 105,795 bytes after a 40% reduction. DecisionRequest and
Continue-first algorithm blocks are copied into four canonical commands, while route, delivery,
projection and cold-start policy are repeated across command/canon carriers.

Current executable owners already exist in `task_contract.py`, `route_evidence.py`,
`plan_repair.py`, `plan_blocking.py`, `review_policy.py`, `plan_gates.py`, `plan_projection.py`,
`plan_continuity.py` and `plan_delivery.py`. P7 should make command Markdown call those owners and
delete duplicated algorithms; it should not replace them with another persisted policy carrier.

RAG:— (repo-grounded: exact commands above and source paths measured in this worktree).
