---
disable-model-invocation: true
description: "Deprecated alias of /planner:design. Explicit design request: produce a plan or ADR; implementation is separate."
argument-hint: "[what to design] [--reviewer <provider/model>]"
model: opus
effort: high
---
> `/task:design` is deprecated and will be removed in the next minor release: use `/planner:design`. Say this to the user once, then follow the instructions below; `<Planner package root>` is the root of the enabled planner plugin.

Owner rules: run `python3 <Planner package root>/scripts/plan.py overlays planner:design` first and follow any rules it prints as additions to this command; they never override the plan, its checks or safety rules.
This is a DESIGN task: produce durable artifacts, not implementation. User input: `$ARGUMENTS`.
Apply the shared opt-in contract in `references/intent-routing.md` from the installed planner package.
Activate this workflow only for an explicit design request. Scale, risk, or an existing plan does not
turn ordinary implementation or repair into design. The route is pinned to Opus/high; do not switch it.

Profile `design`:

1. Delegate only an independent research track while continuing useful work. Match research depth to
   unresolved decisions and risk; small designs need no orchestration.
2. Produce a durable file sufficient for implementation after session loss: objective, decisions,
   boundaries, affected paths, acceptance criteria, and verification. Include exact text or schemas only
   where the contract depends on them. Put disputed choices and the recommendation under `## Discussion`.
   The handoff names the artifact, executor, and concrete next step; implementation starts only on owner request.
3. Verify changing external facts before recording them through `decision-verification`/`verify-claims`
   (context7, then Perplexity, then WebSearch). Keep retrieval on a worker that has the required tools.
4. Record material external sources in provenance (`docs/reference.md` when present).
5. Ask only for a missing product choice or authority boundary. Make authorized reversible design decisions
   directly; do not request repeated approval of the method or plan.

For concurrency, transactions, auth or data integrity, model affected operations/resources/drivers
and name invariant enforcement and bypass paths; lock work checks interfering pairs and implicit
locks. Implementation and read-only review are separate roles. `--reviewer provider/model` is an
explicit review request; use `references/reviewer-selection.md`, never implement reviewer findings
inside a design-only boundary.
