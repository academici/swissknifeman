# Post-D76 design-audit remediation — 2026-08-04

Repository owner requested a narrowly scoped `finish` remediation of the last
`## Audit design — 2026-08-04` RED report. This is plan authoring only: no plan item,
product code, provider call, hook repair, package change, generated artifact, release action or
commit is executed in this session.

Required corrections:

1. Separate the write-heavy P3.4 plan-item scope from the no-write/no-tool live readiness smoke.
   Assign an exact smoke task identity and a complete manifest → grant → replay → admission
   producer/consumer chain without weakening the frozen `slice-manifest-v1` boundary.
2. Before any P5 provider call, add owner-approved business grants and deterministic per-trial
   admissions for the P5.2–P5.4 live work. Prove that every D74/P3-only smoke grant or admission
   is invalid as a business input.
3. Give P4.4's currently non-green effective-hook prerequisite either an owning repair/recheck
   producer or an exact structural waiting gate. The design session must not repair hooks.
4. Synchronize D-records, phase specs/status counts, roadmap, phase/root handoffs and provenance;
   rerun lint, conflict and citation checks; compile and evaluate all 34+ routed Task Contracts;
   perform a complete producer → consumer reconciliation; return a fresh independent design audit.

Protected history and anti-scope:

- Do not change terminal item statuses, terminal item specifications or Completion Notes.
- Preserve the frozen bytes produced by P1.1–P1.5 and all current item implementations/commits.
- Preserve D74's live-provider objective and its forward-only successor-contract approach.
- Do not change hook state during design.
- Do not mutate package/root/fleet/Brain/docs/generated/release state or unrelated dirty worktree
  content.
