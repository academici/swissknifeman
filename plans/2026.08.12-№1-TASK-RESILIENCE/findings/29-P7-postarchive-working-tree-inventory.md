# P7 postarchive working-tree inventory — 2026-08-13

## Observation boundary

Read-only inventory was taken at `HEAD=7472ace86bc227639de430d8cff576d9d6d7fd02`
on branch `main`. The exact pre-design digests and path grouping are stored in
`artifacts/P7/working-tree-baseline-v1.json`. No Task/Skiller/product validation was run during
this design pass; current code remains a candidate, not a green result. RAG:— (repo-grounded:
Git index/worktree at the recorded HEAD and the artifact digest record).

## Staged owner-prepared state

- 249 staged paths move `plans/archive/2026.08.12-№1-TASK-RESILIENCE/**` back to
  `plans/2026.08.12-№1-TASK-RESILIENCE/**` and stage the intended closed-roadmap removals.
- The staged binary diff digest is
  `94ceb5091b59063a84b2997da71ac19cbef206259b1b9bccd61a760e0dd43193`.
- `plans/ACTIVE.md` was still `Active: —` before this design pass, so reactivation was incomplete
  at the owner-facing carrier boundary. RAG:— (repo-grounded: `plans/ACTIVE.md`, recorded staged
  diff).

## Unstaged product candidate

The 54-path candidate has five coherent surfaces:

1. route/run and terminal-state primitives (`command_catalog`, `route_evidence`, `journal`,
   `plan_item_state`, `task_contract` plus focused tests);
2. terminal delivery and lint enforcement (`plan_delivery`, three lint modules plus tests);
3. audit/block safety (`block-candidate` schema, rubric, `plan_blocking`, `review_policy`,
   `plan_gates` plus tests);
4. canonical commands, plan-protocol, provider/docs/runtime projections and their locks;
5. root CHANGELOG and roadmap disposition edits.

The grouping is based on actual changed paths and function/test seams, not on the number of
files. P7 items preserve these boundaries so a fresh session can validate and commit one surface
without staging the rest. RAG:— (repo-grounded: `git diff --name-status`,
`artifacts/P7/working-tree-baseline-v1.json`).

## Roadmap snapshot disposition

All 22 Markdown snapshot bytes match the hashes recorded in
`artifacts/roadmap-snapshots/README.md`; `catalog-at-follow-up.md` matches its recorded digest.
The snapshot set is historical evidence, not a second active queue. RAG:— (repo-grounded:
`sha256sum artifacts/roadmap-snapshots/*.md`).

- Fully implemented/superseded records are removed from root `roadmap/` and retained here.
- Four partial records remain at root with narrowed residue: evidence-anchor graph, local-repair
  all-five/Files+metrics, terminal-final transport lifecycle, terminal-handoff transcript gate.
- Two Task records remain active and explicitly outside P7 implementation: authoritative batch
  admission and `plan-views history` CLI alignment.
- `roadmap/2026.08.11-plan-views-history-cli-contract.md` exists, but its catalog row is absent
  from the current `roadmap/README.md`; P7.5 must restore the row without implementing the feature.

## Safety classification

The existing staged/unstaged tree is authorized input, not noise to reset. Each executor must
compare its scoped diff against the recorded baseline, stage only declared paths, and leave all
other paths byte-preserved. Any need to change P0–P6 evidence, existing tag objects, release/rollout
state, the two active roadmap features or a public/frozen contract outside P7 is an authority/design
boundary, not an implicit extension. RAG:— (repo-grounded: owner request in
`brief/01-refinements.md`, D32).
