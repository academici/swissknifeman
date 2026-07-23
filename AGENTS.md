# AGENTS.md — academici / swissknifeman

This repository is the provider-neutral umbrella for the academici agent-development
ecosystem. Read `CLAUDE.md` completely before changing the repository; it remains the
current detailed guide while the dual-provider migration is being designed. When working
inside `packages/<name>/`, also read that package's `CLAUDE.md`.

## Codex bootstrap

- Treat `.agents/skills/*` as thin Codex adapters. Canonical content stays under
  `packages/skiller/skills/` and `packages/task/commands/`; never fork it into adapters.
- In an isolated worktree, never invoke a bare/global write-capable package CLI. Use the
  worktree-local `./packages/<name>/bin/<cli>` and verify its real repo root before writes.
- Use the `maind` MCP server for project memory and ecosystem/code-graph queries when
  available. Its scope for this repository is `project:swissknifeman`.
- Preserve Claude Code compatibility. Provider-specific files are adapters over a shared
  contract, not replacements for `.claude*`, `CLAUDE.md`, or existing commands.
- Do not execute `plans/2026.07.18-FOREMAN` beyond its current checkpoint until the
  dual-provider bootstrap and migration plan are approved.
- Python packages remain stdlib-only. Preserve unrelated user changes.

## Codex launch and hook integrity

- This repository is an explicitly trusted self-host target. When asking the owner to
  start or restart Codex, never give a bare launch command: include repository cwd,
  routed model/effort and the native full-access knobs. Canonical xhigh form:
  `codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="xhigh"' -a never -s danger-full-access`
  (append `resume --last` when resuming the current thread). These privileges are local
  to this trusted repository; never propagate them implicitly to FOREMAN or fleet projects.
- Every completed task and terminal handoff must end with a Codex new-session launch
  block, including `AUDIT-CAP`, Owner Approval and other non-executable boundaries. Give
  a table with the exact native model, reasoning effort, approval policy, sandbox, cwd and
  context (`NEW SESSION`), followed by one copy-paste shell command containing `codex -C`,
  `-m`, `model_reasoning_effort`, `-a never`, `-s danger-full-access` and a self-contained
  cold-start prompt. If there is no executable next item, the prompt must carry the exact
  owner decision or verification boundary; never omit the command. A provider-neutral
  `plan-protocol` launch-block may accompany this table but does not replace it. Treat
  completion as a `session-handoff` activation; for plan work, apply `plan-protocol` too.
- Cold-start preflight is `pwd` → `git status --short` → effective `codex doctor --json`
  → hook-command integrity → `maind health --cwd` → applicable plan-lint. Confirm the
  effective model/effort, approval policy and sandbox instead of inferring them from files.
- A hook failure is never noise. Exit `127` means an unresolved command/path: find the
  effective registration, verify that every command exists and is executable, remove
  dangling/duplicate entries, and run a synthetic hook probe. Codex native approval and
  sandbox settings own access; do not register a Claude auto-approve hook as their substitute.
- A running Codex process may retain its startup hook registry. After changing registrations,
  restart it or keep a minimal executable compatibility shim at any cached path until restart;
  verify both the cold-start registry and the live-session call path.
- Capture each observed launch/hook defect in the active plan's `brief/` + `findings/` and
  fix the owning source/generator when it exists. Keep only stable recurring invariants here.
- Disclose environment defects as soon as they can affect model/effort, filesystem access,
  MCP/evidence, hooks, sandbox/approval, context budget or validation fidelity. Pause dependent
  work and repair safe in-scope defects immediately; otherwise record the evidence and route an
  explicit follow-up. Never treat a failed or skipped check as green.
- For an active executable master plan, the root agent automatically delegates each next
  executable item to a fresh subagent grounded from the committed plan/handoff; a launch block
  is a recovery carrier, not a request for the owner to relay routine work. Run sequentially
  dependent items one agent at a time and continue automatically after green close/audit. Yield
  only at an explicit Owner Approval, new-authority boundary or genuinely unresolved blocker.
- Treat audit regressions as an automatic fix-forward loop: return to the owning item/phase,
  follow the plan-protocol reopen rules when needed, commit the repair separately, repeat
  validation and independent audit, then resume the roadmap. Ask the owner only when repair
  changes a frozen contract, expands authority or presents a genuine owner-level fork.
