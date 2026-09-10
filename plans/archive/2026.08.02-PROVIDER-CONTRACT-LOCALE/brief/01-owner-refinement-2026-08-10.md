# Owner refinement — 2026-08-10

This refinement is additive to `brief/00-brief.md`. It integrates
`audits/2026.08.10-skills-audit.md` into the existing skills/control-plane plan; it does not
create a third master plan and does not absorb the separate Artifex supervisor implementation.

The resulting package must be lightweight for current frontier models. A skill should add only
knowledge, boundaries or repeatable workflow that the model cannot reliably infer from the task,
repository and tools. Generic reminders, duplicated examples, repeated platform behavior and
legacy guardrails are removed when real evaluations show that they no longer improve outcomes.
High-stakes and destructive boundaries remain explicit.

Development is evidence-led in this order:

1. current official provider/specification documentation defines expected behavior;
2. real Claude Code and Codex sessions on representative repository tasks demonstrate actual
   discovery, invocation and outcome behavior;
3. with-skill / without-skill and minimal-core / provider-tuned comparisons justify each retained
   instruction;
4. deterministic unit, schema, golden and generator tests prevent implementation regressions but
   do not stand in for provider behavior.

Every claim in the audit must receive a recorded verdict: confirmed, partially confirmed,
rejected/stale, or unverified. Counts and thresholds are remeasured from the current tree. No skill
is merged, removed, split or made resident merely because a lexical heuristic or synthetic fixture
says so.

The package is multi-provider by construction:

- one minimal provider-neutral Skill Core expresses the job, trigger boundary, inputs, outputs,
  safety/risk semantics, required capabilities and on-demand resources;
- Claude Code and Codex render additive adapters and may tune their own discovery metadata,
  invocation controls, file layout, measurement and replay fixtures without replacing shared
  meaning;
- a third provider can join by declaring capabilities and implementing the same adapter seams,
  without editing existing provider adapters or forking canonical skill bodies;
- provider parity means shared observable semantics plus explicit native/degraded/unsupported
  states, never byte-identical output or one universal numeric budget.

The desired end state is an easy-to-install, easy-to-extend package whose default context is small,
whose routing is clear, whose generated projections cannot drift, and whose quality verdicts remain
honest about uncertainty and provider differences.
