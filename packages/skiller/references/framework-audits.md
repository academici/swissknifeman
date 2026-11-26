# Framework Audits — ledger periodic framework audits

Audit run register agent-frame (see promt
`docs/skiller/workflows/framework-audit.md`). Complements [README](./README.md): that -
about external sources of skills, this one is about revisions of the framework itself (agents/hooks/
work flow/hub) and verified facts Claude Code.

Archive of runs: `docs/skiller/audits/`. Solutions: `docs/skiller/agent-framework/decisions-ledger.md`.

## Statuses

| Status | Meaning |
|---|---|
| `triaged` | Run disassembled, solutions in decisions-ledger |
| `partially-absorbed` | Part absorb-now implemented, part postponed |
| `absorbed` | All absorb-now items implemented |

## Runs

| Date | Topic | Archive | Status | Key decisions |
|---|---|---|---|---|
| 2026-06-23 | Universal framework | `audits/2026-06-23-universal-framework` | triaged | absorb: hub-index-fix, path-rules, spec-writer(opt), validate-agents; reject: Mustache-engine, file numbering, file-lock, complexity-scoring |
| 2026-06-23 | Agent Teams + ponytail | `audits/2026-06-23-agent-teams-ponytail` | triaged | accept: Agent Teams(v1, CC≥2.1.178), ponytail-discipline; reject: `extends:`/`@include` agents, skill-enforcement hook |
| 2026-07-01 | Workflow resilience (rate-limit incident) | `audits/2026-07-01-workflow-resilience-ratelimit` | triaged | accept: honest statuses green/deferred/infra-failed + fail-fast on null + batch default 2 + text-marker; P1 liveness external supervisor (report ~30 min + PushNotification, opt. GHA cron-watchdog); reject: in-script wall-clock/`withDeadline` (sandbox does not provide `Date.now()`/`setTimeout`/cancel) |
| 2026-07-29 | Harness-agnostic, knowledge packaging unit, token budget, spawn policy | `audits/2026-07-29-harness-agnostic` | partially-absorbed | absorb-now is executed by plan phases: P1 (short always-on root, parity `CLAUDE.md`/`AGENTS.md`), P2 (parity capability second provider, single-source + `--check`), P3 (updating framework-docs, closing the audit loop), P4 (spawn by context budget, delegation contract, policy-layer absorbed supervisor-track), P0.1 (worktree-insulation); reject: renaming `skiller`→`knowledge`, physical layer `plugins/`, `role-routing.yaml` (YAML out stdlib), `verification_strategy`/`memory_checkpoint_policy` (duplicate media); REFUTED: «Role Phase 3 not completed», «need to change the knowledge packaging unit» |

## External sources that surfaced in audits

| Source | From the audit | Solution |
|---|---|---|
| github/spec-kit | #1 | discipline opt; external toolchain (see harness/integrations/spec-kit) |
| eyaltoledano/claude-task-master | #1 | defer; do not accept format tasks.json |
| VoltAgent/awesome-claude-code-subagents | #1 | role patterns - taken into account; file numbering rejected |
| DietrichGebert/ponytail | #2 | we absorb discipline; We do not install an external plugin (conflict with boost) |
| Claude Code Agent Teams (official.) | #2 | accept v1 (Phase 6) |
