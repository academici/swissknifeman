---
name: spec-review
description: "Review a change independently against repository standards and the approved specification."
---

# Spec Review

Identify the exact diff, the approved specification or ticket, and the applicable
repository instructions. Use the same revision and scope for both reviewers.
If the specification is missing, record which acceptance criteria could not be
verified and review the available requirements.

Start two independent read-only subagents, one for each axis below. Give each
the diff range, scope, and relevant sources. Tell both reviewers to inspect
evidence without editing files, changing repository state, or spawning further
agents. Have each report findings with severity, a file and line, the impact,
and the evidence supporting the claim. If subagents are unavailable, conduct two
separate passes and describe how the review was performed.

## Standards

Review repository rules, module boundaries, code clarity, error handling, and
test coverage. Identify regressions and cite the rule or existing behavior that
establishes the expected outcome. Treat preferences as optional suggestions.

## Spec

Trace each acceptance criterion to the implementation and its verification.
Check missing behavior, out-of-scope changes, and cases where the implementation
or tests disagree with the approved requirements. Cite the criterion for each
finding.

Cross-check the evidence, merge duplicate findings, and keep the two sections in
the final report. State any gaps in coverage and which checks were observed.
Explicitly report each axis that has no findings.
