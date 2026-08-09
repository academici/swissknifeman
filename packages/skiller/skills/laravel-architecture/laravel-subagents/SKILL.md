---
name: laravel-subagents
bucket: laravel-architecture
version: 0.1.0
description: "Subagent orchestration on large Laravel tasks: activation threshold, delegating research to Explore agents, review via laravel-reviewer, tests via laravel-test-writer, worktree isolation of parallel edits. Do not apply to small/medium tasks."
risk: write
persona: oss-dev
tags: [workflow, orchestration, agents, laravel]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude]
sha256: ""
---

# Laravel Subagents

Orchestrator (main Claude Code session) protocol with subagents on large Laravel tasks. Subagents give context isolation + fresh view, not parallelism per se. Plugin ships two agents: `laravel-reviewer` (read-only review + PHPStan/Pint/Pest), `laravel-test-writer` (Pest tests for finished code).

## Activate only if at least one holds

- Task spans **three or more domains/layers** (e.g. migrations + models + actions + HTTP + Filament).
- Spec describes a whole feature: migrations, models, business logic, routes, tests in one task.
- Before implementation a wide investigation of a large codebase is needed (dozens of files just to understand).

**Anti-trigger (outweighs triggers):** small/medium tasks — editing one or two domains, bugfix, adding a field, refactoring one layer — do directly, no decomposition, no subagents. Exception: `laravel-reviewer` may be called on medium tasks too if the change is risky (authorization, money, data migrations).

## Algorithm

1. **Decompose.** Split spec into subtasks by layer/domain; fix expected artifact for each. If skill `complex-task-orchestrator` is available, use its template; else minimum:

   ```text
   Цель:
   Инварианты (что нельзя сломать):
   Подзадачи: 1) ... → артефакт
   Зависимости между подзадачами:
   ```

2. **Research → subagents.** Understanding existing structure, finding integration points, inventorying affected files — delegate to Explore agents (read-only). Return conclusions to main context, not contents of dozens of files.
3. **Write architectural code yourself.** Contracts, models, key actions/services — orchestrator's work in main context. Do not pin cheap models on architectural pieces.
4. **Parallel only for independent.** Subtasks with no shared files (different domains, independent console commands, seeders) may go to parallel subagents. If edits may collide on files (shared models, routes, service providers, composer.json) — run sequentially or isolate each agent in a git worktree. If unsure about independence, treat as dependent.
5. **Review after each unit.** Finished an implementation unit (domain, layer, feature) — call agent `laravel-reviewer`, passing the diff or file list. Do not defer review.
6. **Tests → for finished code.** After review call `laravel-test-writer` with paths + brief description of expected behavior. Resolve discrepancies in its report: either code bug or spec inaccuracy.
7. **Fix findings pointwise.** Apply review notes directly in existing code — do not regenerate the unit from scratch, do not hand the fix to a new agent without the finding's context.

## Anti-patterns

- Decomposition/subagents on small/medium task (see anti-trigger).
- Role-agent pipeline (planner → generator → reviewer → ...) where one context suffices: each break loses spec knowledge.
- Pinning a cheap model on architectural code.
- Parallel agents over dependent files without worktree isolation.
- Reviewing own code instead of calling `laravel-reviewer`.

## Output

Implemented feature + `laravel-reviewer` reports (per-unit verdicts) and `laravel-test-writer` report (coverage, run) in orchestrator's final answer.

## Quality checklist

- [ ] Activation threshold checked: task truly large (≥3 layers/domains or whole feature), else skill not applied.
- [ ] Wide research done by Explore agents, not main context.
- [ ] Architectural code written by orchestrator, not delegated.
- [ ] Parallel ran only subtasks with no shared files (or in worktree).
- [ ] Each finished unit passed `laravel-reviewer`; verdicts in report.
- [ ] `laravel-test-writer` called for finished code; discrepancies resolved.
- [ ] Review findings fixed pointwise, no from-scratch regeneration.

## Links

- `agents/laravel-reviewer.md`, `agents/laravel-test-writer.md` — plugin agents (available only in Claude Code plugin channel).
- `general/complex-task-orchestrator` — general decomposition template, if connected in project.
- `laravel-testing/laravel-testing` — tests written by `laravel-test-writer`; `php/static-analysis` — checks run by `laravel-reviewer`.
- `oss-dev/gh-review` — review and handoff via `gh` with context economy.
- `general/context-economy`, `general/session-handoff` — main session context management when delegating.
