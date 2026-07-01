---
name: anti-drift
bucket: general
version: 0.2.1
description: "Discipline against agent rabbit-holing: think before coding, simplicity first, surgical edits, circuit-breaker on dragging iterations."
risk: read
persona: oss-dev
tags: [workflow, discipline, orchestration, context]
requires: []
produces_for: [session-handoff]
outputs: []
snippets: ["claude-md-anti-drift.md"]
adapters: [claude, cursor, fable]
sha256: ""
---

# Anti-Drift

## When to activate

Any code-writing/editing session, especially when:
- task already took >2–3 "try another way" iterations;
- solution accretes new layers/flags/dependencies;
- session is long, early decisions risk being forgotten.

## Four principles (Karpathy)

1. **Think Before Coding** — before editing state: what changes, why, which assumptions. On ambiguity ask ONE clarifying question, don't guess. Check: can you explain the plan in one paragraph? If not, plan isn't ready.
2. **Simplicity First** — minimal code for the current task; not one line "for the future" (YAGNI). Check: "could I write this simpler?" If yes, rewrite before committing.
3. **Surgical Changes** — touch only files named in the task; don't improve neighboring code unrequested. Check: `git diff` — any out-of-scope change? Revert it.
4. **Goal-Driven Execution** — success criterion (test/check) first, then code. Check: is there a check that fails BEFORE and passes AFTER?

## Circuit Breaker — stop thresholds

Catches three degradation patterns: layered edits (new layer atop old instead of removing it), symptomatic fixes (treat the log not the cause), context saturation (conflict with early session decisions).

- **Soft (warning):** codebase investigation >~10 tool-calls without a conclusion → stop, formulate a decision from current data; ask for what's missing.
- **Hard stop:** after ~20 iterations with no working result → stop, describe what you tried and why it failed. Then `session-handoff` + new session with clean context, or ask the user.
- **Complexity-escalation ban:**
  - Needs a new package or abstraction layer → ASK first.
  - Touches >5 files → describe plan first, then edit.
  - Second fix of the same symptom → stop, find root cause (reproduction → root cause → fix → verification), not a third patch.
- **Dependent-package boundary — ask before extending.** A dependent package (`vendor/**`, path-repo `packages/**`, shared package) is **read-only** by default. Before adding a class/provider/interface/abstraction:
  - Survey package structure first for an existing extension point (contract, event, config, trait) — often nothing new is needed.
  - When in doubt, hand the go/no-go to a **separate small task/subagent** (survey reuse → judge by YAGNI/Rule of Three → verdict); don't mix recon with implementation.
  - Missing package functionality → **issue against the package**, temporary impl on consumer side (`app/`/`Modules/`) + `TODO`; don't edit the package "along the way".
  - Deep protocol (proposal → ADR → SemVer) → `package-contribution-protocol`.

## Shared resources & flaky tools

Long-lived daemons/servers (browser pools like perplexity-web-mcp, dev servers, LSP) serve OTHER agents concurrently.

- **No unneeded/destructive ops.** Never `pkill`/`kill -9`/`rm` a daemon's profile, socket, or Singleton lock. Prefer the gentlest path: reuse the live process, wait for it to free up. Rebuild/restart a shared service ONLY after confirming it's idle (no live agents) — else you crash others' sessions.
- **Respect concurrency.** Several tasks may hit one tool in parallel; that's expected — let them queue (or one tab/context per task), don't force-clear the resource.
- **Flaky tool → retry, don't panic.** An external tool (web search, network) can blip. Retry with backoff before giving up or changing the plan; a solid plan shouldn't collapse on one transient error. Configure retries/log/notify on the tool side, don't route around it.

## Related skills

- `task-brief-template` — scope and acceptance criteria fixed before start.
- `session-handoff` — exit session after the hard threshold.
- `complex-task-orchestrator` — decomposition and DoD for complex tasks; this skill = iteration discipline within them.
- `context-economy` — context economy on a dragging session (`/compact`, `/clear`, Plan→Clear→Execute).
- `package-contribution-protocol` — deep gate against dependent-package bloat (proposal → ADR → SemVer), when editing the package is agreed.

## Snippet

`snippets/claude-md-anti-drift.md` — ready-made rules block for the target project's CLAUDE.md (agent applies thresholds without an explicit skill call).

<!-- ru-source-sha256: 7ebaee24e5cac6c4e6ead03b0c8ac9447682ca0e8fea575d1724ad4efa0a0b3f -->
