# Audit-9 resolver-valid authority reconciliation

## Inputs

- `plan.md` → last `## Audit design — 2026-08-05` (pass 9).
- `brief/16-audit8-owner-carriers-and-execution.md` — original finite owner-approved scopes.
- `brief/17-audit9-resolver-valid-owner-carriers.md` — explicit append-forward owner directive
  and exact Layer-0 successor messages.
- `findings/P3-P6-audit9-authority-resolver-recon-2026-08-05.md` — exact resolver grammar,
  ambiguity rule and journal observation.

## Active carrier topology

| Boundary | Historical carrier | Active successor | Consumers |
|:--|:--|:--|:--|
| Artifex package instruction generation | D91, retained as malformed audit history | D95 / `G-OWNER-P3.8-HARNESS-INSTRUCTIONS-R2` | P3.8 only |
| Root instruction generation | D92, retained as malformed audit history | D96 / `G-OWNER-P6.2-HARNESS-ROOT-INSTRUCTIONS-R2` | P6.1 freeze, then P6.2 |
| Reconciliation | D93/D94 retain audit-8 generator/isolation decisions | D97 supersedes D91/D92 only as active machine authority | P3.8, P6.1, P6.2, P6.4 audit |

The two R2 grants copy their predecessor branch and finite scope exactly. New gate identities are
required because the resolver treats a malformed row carrying the same marker as an ambiguity;
they are not additional authority. D86/D87 remain separate package/root-output grants. D93 stays
the sole plan→apply→check order and D94 stays the P3.7 temp-isolation rule. RAG:—
(repo-grounded: audit-9 findings; `findings/P3-P6-audit9-authority-resolver-recon-2026-08-05.md`).

## Verification contract

1. Build all 39 ordinary Task Contracts at their exact routed model/effort and require
   `pre_mutation=allow`, `pre_final=allow`.
2. Build protected P3.8 with D95's gate/branch/scope; require `allow/allow`.
3. Build protected P6.1 and P6.2 with D96's gate/branch/scope; require `allow/allow` for both.
4. Re-run plan-lint, conflict lint, strict citations, complete Required Reads producer checks,
   56/56 phase DoR, 39-item Routing/roadmap coverage, D1–D97 continuity and G1→G5 lineage.
5. Append one journal event for this finish that explicitly records the forward provenance repair
   for the missing audit-8 D91–D94 plan-design carrier.

No execution, generated output, hook repair, status mutation or historical-row edit is part of
this reconciliation. RAG:— (owner/repo-grounded: `brief/17-audit9-resolver-valid-owner-carriers.md`).

## Observed finish verification — 2026-08-05

- Worktree-local `plan-lint.py`: 0 errors / 0 warnings; `--conflicts`: 0 mismatches /
  0 warnings.
- `packages/task/scripts/verify-plan-citations.py --strict`: 23 citations checked / 0 findings.
- All 39 ordinary Task Contracts on their exact routed model/effort: `allow/allow`.
- Protected Task Contracts: P3.8 through D95 and P6.1/P6.2 through D96 each resolve
  `granted=true`, `pre_mutation=allow`, `pre_final=allow`.
- Structural sweep: 39 items, 624/624 fields, 39 Routing rows, 39 roadmap rows, 56/56 DoR
  checks, D1–D97 continuous, 9 historical design-audit blocks, G1→G5 complete.
- Root Harness instruction `plan` and `check` are GREEN/noop for both providers. Effective Codex
  hook dry-run remains honestly non-green with exactly two `stale-source → update` actions; P4.6
  owns the later repair and this finish did not mutate hooks.
- Journal line 112 is the sole new event and names the missing audit-8 D91–D94 authoring
  provenance plus current D95–D97 finish.

Environment caveat: `codex doctor --json` reports the shell config default model as
`gpt-5.6-terra`, while semantic `task:plan-design` routes `gpt-5.6-sol/high`; the doctor output
does not independently prove the already-running session selector. The journal actor therefore
records the prescribed semantic route, not a separately observed provider selector. The cold
design audit must report this caveat rather than cite doctor as proof of the current session
model. RAG:— (repo/environment-grounded: observed 2026-08-05 preflight output).

Verification status: no external queries were needed; every verdict-bearing fact is
repo/environment-grounded. Unverified future facts remain actual P3.8/P6 execution and G1–G5
runtime outcomes. No workaround was accepted.
