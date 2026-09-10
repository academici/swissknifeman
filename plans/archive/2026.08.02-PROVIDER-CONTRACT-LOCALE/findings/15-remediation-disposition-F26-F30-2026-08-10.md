# Remediation disposition — F26–F30 — 2026-08-10

This carrier records the owner-authorized bounded disposition of
`findings/14-design-audit-2026-08-10.md`; it does not rewrite that audit or start another audit
cycle. D62 accepts the semantic design and limits this pass to execution-readiness carriers.

| Finding | Disposition | Durable evidence |
|:--|:--|:--|
| F26 | closed for P0.1; later items normalized for JIT | P0.1 Inputs/Required Reads are exact portable paths; `bundles/P0.1.json` is generated and byte-current. P0.2–P7.4 declarations name exact predecessor state/producer paths and are intentionally materialized only after terminal predecessors; `bundle --all` was not run. |
| F27 | closed | Active `roadmap.md`, `phases/P0/P0.3.md`, and `index.md` paths use Layout v2 `phases/<Pn>/<Pn>.md` / `phases/<Pn>/<Pn.m>.md` carriers. Historical audit, decision, and migration-source evidence remains untouched. |
| F28 | closed by owner threshold | `brief/02`, D62, Meta and the generated Update Log identify the 2026-08-10 integration as design pass 4/4 and state that no ninth whole-plan audit is required. |
| F29 | closed by this bookkeeping commit | The full current plan/docs slice reviewed here is committed together; unrelated worktree state is excluded from the pathspec. |
| F30 | closed | `handoff.md` uses canonical `waiting: … → run-items`, `Context = cold-start-root`, exactly one reason `owner-pause-no-resume`, a guarded provider-neutral command, and the pinned native Codex launch. |

## Targeted evidence

- `python3 packages/task/scripts/plan-views.py bundle --plan-dir plans/2026.08.02-PROVIDER-CONTRACT-LOCALE --item P0.1 --check`
- `python3 packages/task/scripts/plan-views.py decisions --plan-dir plans/2026.08.02-PROVIDER-CONTRACT-LOCALE --check`
- `python3 packages/task/scripts/plan-views.py status --plan-dir plans/2026.08.02-PROVIDER-CONTRACT-LOCALE --check`
- `python3 packages/task/scripts/plan-views.py state --plan-dir plans/2026.08.02-PROVIDER-CONTRACT-LOCALE --all --check`
- `python3 packages/task/scripts/plan-lint.py plans/2026.08.02-PROVIDER-CONTRACT-LOCALE --baseline HEAD`

## JIT debt, not a new audit loop

- P0.1 must recapture the observed Codex hook `record-provenance-mismatch`; D42/P3.2 owns any
  forward Harness repair. This pass does not alter package/provider state.
- Each later item regenerates its own bundle after predecessor terminality and repairs a missing
  declared producer path in that owning item. No future Validation or Code Guidance polish is
  authorized by this disposition.
