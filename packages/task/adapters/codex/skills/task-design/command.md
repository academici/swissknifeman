<!-- Generated Codex runtime projection; do not edit as source.
Canonical source: packages/task/commands/design.md
Canonical SHA-256: sha256:60cf239254634feac393137d4d9f02dfcc6a0dc0077266554d4cab8c8e81a4e0
Adapter: task.codex-command/1.0.18
-->
This is a DESIGN task: produce durable artifacts, not implementation. User input: `$ARGUMENTS`.
Apply the shared opt-in contract in `references/intent-routing.md` from the installed Task package.
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
together and name invariant enforcement points; lock work checks interfering pairs and implicit
locks. Handoff implementation and read-only review as separate invocations. A requested review
may select a reviewer with optional `--reviewer provider/model`; review does not implement its findings.
