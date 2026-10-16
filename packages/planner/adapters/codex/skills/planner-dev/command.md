<!-- Generated Codex runtime projection; do not edit as source.
Canonical source: packages/planner/commands/dev.md
Canonical SHA-256: sha256:00c494b9ee2ceee2f8b1832303e99b3f1c5ff84db5d6ea6175b71fb685bc58a7
Adapter: planner.codex-command/1.0.18
-->
Project CLI: `plan.py` means `python3 -I .swissknifeman/launcher.py planner`, run from the project root (the launcher binds the project; without one, run `swissknifeman project init` once). Never locate or run a Swiss Knife Man package script.
Owner rules: run `plan.py overlays planner:dev` first and follow any rules it prints as additions to this command; they never override the plan, its checks or safety rules.
This is a DEVELOPMENT task. User input: `$ARGUMENTS`.

Apply the shared opt-in contract in `references/intent-routing.md` from the installed planner package.
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
coordination. Requested independent review uses a fresh read-only native session.

Start with focused checks of changed behavior and run each once per change; do not re-run unchanged
checks. Add package or integration checks for integration risk. Security, public API, concurrency, or
irreversible effects require broader verification and a `planner:review` recommendation in the report, not
an automatic review. Run explicitly requested checks. Report a foreign red baseline and determine whether
it intersects scope or dependency closure.

For a requested selector, read `references/reviewer-selection.md`: use a fresh read-only session
on that exact route, then at most `policy.corrections_max` owning corrections (context pack `policy`, or
`plan.py config show`; default 1) and affected checks. The reviewer never repairs.

Review is opt-in ([review contract](../references/intent-routing.md#review-is-opt-in)). Only with
`--review`, `--reviewer` or an explicit owner request, strip review options from the task text and,
after GREEN checks, launch one fresh read-only pass over the whole diff using `planner:review` depth.
Use the selected or current native route. One owning correction and affected checks may follow;
the reviewer never repairs or launches a recursive review. Extra completed rounds follow the bounded
explicit-review policy in `references/reviewer-selection.md`.

Repair authorized reversible defects until the result is ready. File count, an exhausted audit budget, or a
recommended Next does not override Scope or Acceptance. External writes, changed Acceptance, and unavailable
dependencies require the corresponding authority or readiness. Repeated failure without new evidence requires
a different approach.

Use a claim-verification skill, when installed, for changing external premises. Preserve other people's changes. One scoped commit
containing the product and required generated carriers is the normal completion. Report changes, actual checks,
and limitations. Push or open a PR only on request.
