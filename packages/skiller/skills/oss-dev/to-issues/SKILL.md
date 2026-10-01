---
name: to-issues
bucket: oss-dev
version: 0.1.1
description: "Explicit publishing request only: turn a plan/spec into vertical GitHub issues with dependencies."
risk: write
persona: oss-dev
tags: [issues, github, vertical-slices, decomposition, planning]
requires: [github-flow]
produces_for: [implement]
outputs: []
snippets: []
adapters: [claude, cursor, fable]
disable-model-invocation: true
sha256: ""
when_to_use: "Use when the owner explicitly requests publishing a plan as GitHub issues."
---

# To Issues

Break a plan into independently-grabbable issues using vertical slices (tracer bullets).

> **Tracker config.** Before publishing you need: a repository tracker and a dictionary triage-labels. We have
> this `gh` + repo specific labels (and not `/setup-matt-pocock-skills`). If the set of labels is unclear -
> check with the maintainer or get it from `oss-dev/github-flow`.

## Process

### 1. Gather context

Work from whatever is already in the conversation context. If the user passes an issue reference (issue number, URL, or path) as an argument, fetch it from the issue tracker and read its full body and comments.

### 2. Explore the codebase (optional)

If you have not already explored the codebase, do so to understand the current state of the code. Issue titles and descriptions should use the project's domain glossary vocabulary (`CONTEXT.md`), and respect ADRs in the area you're touching.

Look for opportunities to prefactor the code to make the implementation easier. "Make the change easy, then make the easy change."

### 3. Draft vertical slices

Break the plan into **tracer bullet** issues. Each issue is a thin vertical slice that cuts through ALL integration layers end-to-end, NOT a horizontal slice of one layer.

<vertical-slice-rules>

- Each slice delivers a narrow but COMPLETE path through every layer (schema, API, UI, tests)
- A completed slice is demoable or verifiable on its own
- Any prefactoring should be done first

</vertical-slice-rules>

### 4. Quiz the user

Present the proposed breakdown as a numbered list. For each slice, show:

- **Title**: short descriptive name
- **Blocked by**: which other slices (if any) must complete first
- **User stories covered**: which user stories this addresses (if the source material has them)

Ask the user:

- Does the granularity feel right? (too coarse / too fine)
- Are the dependency relationships correct?
- Should any slices be merged or split further?

Iterate until the user approves the breakdown.

### 5. Publish the issues to the issue tracker

For each approved slice, publish a new issue to the issue tracker (via `gh issue create`). Use the issue body template below. These issues are considered ready for AFK agents, so publish them with the correct triage label unless instructed otherwise.

Publish issues in dependency order (blockers first) so you can reference real issue identifiers in the "Blocked by" field.

<issue-template>
## Parent

A reference to the parent issue on the issue tracker (if the source was an existing issue, otherwise omit this section).

## What to build

A concise description of this vertical slice. Describe the end-to-end behavior, not layer-by-layer implementation.

Avoid specific file paths or code snippets — they go stale fast. Exception: if a prototype produced a snippet that encodes a decision more precisely than prose can (state machine, reducer, schema, type shape), inline it here and note briefly that it came from a prototype. Trim to the decision-rich parts — not a working demo, just the important bits.

## Acceptance criteria

- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3

## Affected projects

List of affected repositories if the slice affects multiple ecosystem projects (otherwise omit the section).

## Environment

Where it appears/is checked: production / staging / specific device (POS, fiscal officer). Omit if not applicable.

## Blocked by

- A reference to the blocking ticket (if any)

Or "None - can start immediately" if no blockers.

</issue-template>

Do NOT close or modify any parent issue.

## Related skills

- `oss-dev/github-flow` — general thread Issue→PR→Release (required dependency).
- `general/spec-interview` / `general/grill-with-docs` — where does the plan come from/Terms of reference for partitioning.
- `general/implement` — next step: implementation according to published issue (this skill `produces_for` him).
- `oss-dev/issue-triage` — state machine for processing existing issue/PR.
