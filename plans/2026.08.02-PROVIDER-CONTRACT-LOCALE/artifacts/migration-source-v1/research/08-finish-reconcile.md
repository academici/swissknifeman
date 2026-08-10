# Design pass 3/3 — cross-phase finish reconcile

## Method and boundary

The finish pass read the brief, all current findings/research, `plan.md`, P0–P7 item specs,
roadmap, journal and handoff. It compared each phase contract's produced outputs with every
later Inputs/Required Reads reference, checked all 30 items against Routing and roadmap, and
reran the DoR criteria. Future deliverables are declarations backed by an earlier producer;
they are not reported as files that already exist.

## Producer/consumer graph

| Producer | Frozen or committed output | Consumers | Reconcile verdict |
|:--|:--|:--|:--|
| P0.1–P0.4 | sealed fleet baseline/classification, `provider-recovery-gates-v1`, containment/no-op evidence | P1–P7 | complete exact-set/security gate; no later phase reclassifies live bytes |
| P1.1–P1.3 | `provider-control-plane-v1`, ownership/capability matrix and migration/rollback conformance | P2–P7 | additive over archived provider contracts; provider outputs never become intent |
| P2.1–P2.3 | `locale-resolution-v1`, `english-authoring-overlay-v1`, `locale-authoring-review-v1` | P3–P7 | all three contracts now registered; P2 Scope/DoR/contract carrier restored |
| P3.1–P3.3 | pure desired snapshot, provider-scoped reconcile/readback and status diagnostics | P4–P7 | package owners preserved; no fleet-health claim in implementation layer |
| P4.1–P4.6 | locale runtime, cumulative corpus ledger, regenerated projections and repository acceptance | P5–P7 | sequential terminal regeneration owns all deferred derived drift |
| P5.1–P5.4 | approved fleet action set, durable append-only per-project transaction log, rollback/readback and convergence/unresolved sets | P6–P7 | live locator is identity-bound to sealed P0; no action inferred from classification; a restart reconciles the first non-terminal transaction before progressing |
| P6.1–P6.3 | Brain transaction result, `provider-health-v1`, exact-set two-run fleet bundle | P7 | complete non-green evidence may close P6 but remains a release blocker |
| P7.1–P7.4 | acceptance bundle, permanent regressions, release candidate and adversarial verdict | later explicit release operation | no tag/push/publish authority is granted by this plan |

## Coupling hotspots

- `.swissknife.json` and provider configuration are read through P1/P3 ownership; P2 locale is
  additive and P5 cannot derive intent from host state.
- Provider locks/status and package renderers are composed by P3, regenerated/read back by P4,
  observed by P5/P6 and accepted by P7; no phase creates a parallel carrier.
- Canonical skill/command/instruction sources flow through one P2 admission contract and one P4
  cumulative ledger; P4.6 is the sole terminal derived-artifact regeneration point.
- Fleet identity/evidence flows P0 → P5 → P6 → P7 by exact stable sets; absolute roots remain
  ephemeral locators and one provider/project cannot mask another. P5 aggregate JSON is derived
  from the D47 durable journal, and P7.4's D# denominator is parsed dynamically from Decision Log.

## Routing and execution map

Routing covers all 30 items. Ranges P0.2–P0.3 and P2.1–P2.3 are homogeneous contract/design
classes; every other row is per-item. All items derive `Exec = manual` because their prescribed
effort is high/xhigh or tier is frontier. Every phase is sequential by Inputs→Deliverables,
so no phase reaches the independent N≥3 trigger for a parallel Workflow script. Multi-package
items nevertheless require the D39 per-cwd session/evidence carrier, and P4.3–P4.6 require D40
bounded checkpoints with independent reviewer/resume semantics. `roadmap.md` retains the same
30 items, order, model/effort and root `task:plan-run` command per item while exposing the
package-cwd sublaunches, closed P4.4/P4.6 cwd→command matrix and sole root closure owner. F18-listed
single-cwd items now carry fully expanded helper/test/verify/lint invocations in their Validation.

## DoR gaps closed by finish

1. Added P2 phase Scope Included/Excluded, contract-first carrier and full DoR checklist.
2. Added `english-authoring-overlay-v1` and `locale-authoring-review-v1` to exported Contracts.
3. Added `research/00-user-intent.md` and indexed the brief→decision→item→evidence trace.
4. Replaced one ambiguous archived P2 Required Read with its exact archive path.
5. Reserved unique future research filenames for P0.2, P0.3 and P1.1.

## Final verdict

The design feasible set is non-empty and all known coupling hotspots reconcile after F16–F18. There are zero
clarification/skeleton markers, every item has 16 fields and non-empty Code Guidance/Validation,
all load-bearing Intent/Why/Implementation Rules carry an allowed RAG marker, all six exported
contracts have producer-first consumers, the P5 crash boundary has a durable carrier, P7 decision
coverage is exact-set, and the final roadmap covers 30/30 items. Execution
remains closed until an independent `task:plan-audit … design` returns GREEN.

## Verification

- **RAG:** no new external fact class was introduced. The finish verdict uses the existing
  same-day primary-source findings for BCP 47 and desired/observed state; all new conclusions
  are repo/plan-grounded by the files named above.
- **Unverified → repeat pass:** planned contract/API/file identities must be pinned from actual
  terminal producer commits before each consumer executes; any mismatch reopens plan-design.
- **Workarounds/[POSSIBLE-DEFECT]:** baseline attribution against HEAD is unavailable while the
  plan directory is untracked; additionally the installed Codex runtime has no
  `task@swissknifeman` plugin, so the adapter-prescribed runtime lint lookup was skipped and the
  worktree-local linter was run explicitly. Both limits are disclosed; neither result is
  mislabeled as a baseline or installed-runtime verdict.
