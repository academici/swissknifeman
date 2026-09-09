# Design-audit F1–F4 remediation — 2026-09-09

**Mode:** bounded design-only repair of finding 12 ATTENTION.
**Product execution:** unopened.
**External/release actions:** not authorized.

## F1 — promoted Laravel carrier

`artifacts/source-roadmap/2026.08.14-laravel-parallel-isolation-lifecycle.md` now maps exactly to
P5.3, a dedicated Skiller-owned vertical item. D1's 23 promoted carriers remain the governing
decision; its affected-item index now includes P5.3 without changing the accepted disposition.
`findings/00-roadmap-disposition.md`, the brief refinement, P5 phase contract and
execution roadmap all carry the same disposition. The source bytes are unchanged.

## F2 — truthful design/audit provenance

No historical event was backfilled. The pre-existing journal evidence is interpreted as follows:

- Design pass 1/3: original P0 `plan-design` event at journal line 1, supported by the owner brief
  and initial disposition carriers.
- Design pass 2/3: original P1–P6 phase-detail `plan-design` events at lines 2–7, each with its own
  provider session ID.
- Design pass 3/3: original `finish` event at line 8.

New `Design pass 1/3`–`3/3` journal rows are present-tense provenance-reconciliation records that
cite these old rows; they are not retroactive authoring events and do not change timestamps or
attempt counts. The bounded F1–F4 repair has its own current finish row.

Finding 09's phrase "prior read-only audit" referred to an ephemeral review whose report/event was
not persisted. It therefore has no durable audit identity and is not counted. Finding 12 and
journal line 10 are the first durable `plan-audit design` attempt. No missing report, verdict,
fingerprint or event has been invented.

## F3 — P6 manifests

P6.3 and P6.4 use exact plan artifact/test/docs paths plus two bounded owners:

- Harness instruction sources are only `scopes[].sections[].sources[].path` in
  `packages/harness/configs/common/instructions/catalog.json`; Codex outputs are only
  `targets[].target_path` from the read-only `harness instructions plan --provider codex --json`
  manifest.
- Skiller bootstrap canon/outputs are only the identities, class-B canonical records, providers,
  targets and lock path declared by `repository-bootstrap-skills.json` and
  `publication-lock.json`; `skiller registry` remains the sole writer.

The executor must freeze the selected manifest subset and digests in `candidate-spec.json` before
the first canonical mutation. Wildcard directories and prose such as "relevant files" no longer
grant write authority.

## F4 — docs gates

Every docs-touching item now names concrete commands. Task/root docs use the umbrella build
`npm --prefix packages/skiller run docs:build`; Skiller docs also use
`docs:standalone:build`; Harness docs use `npm --prefix packages/harness run docs:build`; Analyst
docs use `npm --prefix packages/analyst run docs:build`. Failed or skipped builds remain non-green
evidence at that item's close boundary.

## Integrity boundary

The remediation changes plan/disposition/index carriers and generated plan views only. It does not
change product runtime implementation, existing item statuses, immutable source-roadmap bytes,
consumer projects, release state, tags, remotes or deployment state.

## Deterministic verification

- Exact source-name scan: 23/23 `artifacts/source-roadmap/*.md` carriers occur in item specs;
  Laravel parallel isolation resolves only to P5.3.
- Journal reconciliation: `Design pass 1/3`, `2/3`, `3/3` are current `not retroactive` rows
  pointing to original lines 1, 2–7 and 8; the only durable `plan-audit design` remains line 10,
  attempt 1.
- Generated carriers: state 19/19, status 1/1, decisions 4/4 and first runnable P1.1 bundle 1/1
  regenerated and byte-fresh in check mode.
- `python3 packages/task/scripts/plan-lint.py plans/2026.09.09-№1-LEAN-EXECUTION` →
  0 errors / 0 warnings; `python3 packages/task/scripts/plan-lint.py --conflicts` →
  0 discrepancies / 0 warnings.
- The same scoped lint with baseline `49909ef37e973e5e45d9c8e9646b72b6e03da839` →
  0 errors / 1 honest warning because this new plan path is absent from that HEAD.
- Docs-gate matrix scan covers all twelve docs-touching specs (including P6.4) with zero missing
  applicable standalone/aggregate commands.
- Frozen source aggregate remains
  `1b7134cfe6b18c2dbe130d4112e95fa95681be0dbe36387909a3002d7f3a2aa5`.
- `bash packages/task/scripts/validate.sh` → exit 1 after 936 tests green (1 skipped): fleet lint
  still reports 12 errors / 17 warnings outside this plan, with all errors owned by the known
  `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE` baseline. This aggregate check is not reported green;
  the scoped and conflict checks above remain independently valid.
