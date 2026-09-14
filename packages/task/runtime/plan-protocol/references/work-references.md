# Work identity and references

When creating a persisted plan or standalone task, assign `Short ID`: `PLAN<N>` for a plan,
`TASK<N>` for a task (positive integer). Store it in plan Meta or the task document header,
alongside its title and existing directory ID. Allocate the next unused number above the
maximum in that repository and namespace, including archived work; never recycle or renumber.
Check existing assignments again before writing; concurrent allocations must be reconciled.
A plan item keeps its existing `Pn.m`; it does not receive a standalone `TASK<N>`.

Outside the owning work directory, qualify every work-specific decision, phase, item or finding:
`PLAN1.D35`, `PLAN1.P2`, `PLAN1.P2.3`, `PLAN1.F4`, `TASK1.D2`. This applies to code comments, docstrings,
PRs, reviews, docs and generated text. Inside that directory, bare local IDs are allowed.
Across repositories, prepend the repository identity: `swissknifeman:PLAN1.D35`.
`#` is optional presentation, not part of the ID. Short ID maps directly to its owning document;
keep it when archiving, renaming a directory or handing off. Do not create comments just to cite work.

Existing work without Short ID uses `<PLAN-ID> D35`, `<PLAN-ID> P2.3`, or the exact task path
plus local ID. Assign a Short ID only when needed; repair an old ambiguous reference only after
verifying its source. Full IDs and command arguments remain valid and unchanged.

These are authoring rules, not a new workflow or task schema. `plan-lint` checks declared plan
Short IDs for syntax and collisions across live/archive siblings; absence stays valid for legacy
plans. Task IDs and cross-repository references are checked when authoring or reviewing.
