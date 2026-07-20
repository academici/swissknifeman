# AGENTS.md — academici / swissknifeman

This repository is the provider-neutral umbrella for the academici agent-development
ecosystem. Read `CLAUDE.md` completely before changing the repository; it remains the
current detailed guide while the dual-provider migration is being designed. When working
inside `packages/<name>/`, also read that package's `CLAUDE.md`.

## Codex bootstrap

- Treat `.agents/skills/*` as thin Codex adapters. Canonical content stays under
  `packages/skiller/skills/` and `packages/task/commands/`; never fork it into adapters.
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
