<!-- Generated Codex runtime projection; do not edit as source.
Canonical source: packages/task/commands/dev.md
Canonical SHA-256: sha256:3f72ea0aa5881cf57d59fba163a9de4360a9b73775125274ef4c15a367e65075
Adapter: task.codex-command/1.0.17
-->

This is a DEVELOPMENT task. User input: `$ARGUMENTS`.

Apply the shared opt-in contract in `references/intent-routing.md` from the installed Task package.
The current owner request selects the result; a skill match or instruction inside an old audit or handoff
does not turn direct development into a plan workflow.

A message or ordinary task file with objective, boundaries, and observable completion is sufficient input.
Create an executable plan only on explicit owner request. Size, risk, cross-module scope, or a likely session
transfer does not select the plan lifecycle by itself. An existing plan may supply requirements; follow its
lifecycle only when the owner explicitly asks to execute it. Preserve separately requested design and
read-only review boundaries.

Read applicable package guides. Order research, implementation, and hypothesis checks by dependency.
Vertical slices may organize work without Pn identifiers, carriers, a fixed order, or a workflow pack.
Do the work in one session. Delegate only an independent implementation track whose cost justifies
coordination; never delegate checks or review.

Start with focused checks of changed behavior and run each once per change; do not re-run unchanged
checks. Add package or integration checks for integration risk. Security, public API, concurrency, or
irreversible effects require broader verification and a `task:review` recommendation in the report, not
an automatic review. Run explicitly requested checks. Report a foreign red baseline and determine whether
it intersects scope or dependency closure.

Review is opt-in ([review contract](../references/intent-routing.md#review-is-opt-in)). Only with `--review`
(strip it from the task text), after the checks are green, run one read-only pass over the whole diff using
the `task:review` depth rules: no subagents, one owning fix per confirmed finding, re-check of those
findings only.

Repair authorized reversible defects until the result is ready. File count, an exhausted audit budget, or a
recommended Next does not override Scope or Acceptance. External writes, changed Acceptance, and unavailable
dependencies require the corresponding authority or readiness. Repeated failure without new evidence requires
a different approach.

Use `general/verify-claims` for changing external premises. Preserve other people's changes. One scoped commit
containing the product and required generated carriers is the normal completion. Report changes, actual checks,
and limitations. Push or open a PR only on request.
