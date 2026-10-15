<!-- Generated Codex runtime projection; do not edit as source.
Canonical source: packages/planner/commands/design.md
Canonical SHA-256: sha256:1ea50aa97adbde27580b0c04913c0ed7afd0dba929a8188d3939abba3cac3b6d
Adapter: planner.codex-command/1.0.18
-->
Project CLI: `plan.py` means `python3 -I .swissknifeman/launcher.py planner`, run from the project root (the launcher binds the project; without one, run `swissknifeman project init` once). Never locate or run a Swiss Knife Man package script.
Owner rules: run `plan.py overlays planner:design` first and follow any rules it prints as additions to this command; they never override the plan, its checks or safety rules.
This is a DESIGN task: produce durable artifacts, not implementation. User input: `$ARGUMENTS`.
Apply the shared opt-in contract in `references/intent-routing.md` from the installed planner package.
Activate this workflow only for an explicit design request. Scale, risk, or an existing plan does not
turn ordinary implementation or repair into design. The route is pinned to frontier/high; do not switch it.

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
