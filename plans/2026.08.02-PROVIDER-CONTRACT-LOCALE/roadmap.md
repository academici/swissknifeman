# Roadmap исполнения — 2026.08.02-PROVIDER-CONTRACT-LOCALE

**Обновлён:** 2026-08-15 · **Соответствует plan.md:** v1.1.4, flat/fast routing · **Статус:** P0–P3 terminal; P4.1 nonterminal attempt reconciled for a solo resume under D79.

## Fast execution carrier

Sequence: `P1 close → P2.1–P2.3 → P3.1–P3.3 → P4.1 → P4.2 → P4.3 → P4.4 → P4.5 → P4.6 → P5.1–P5.4 → P6.1–P6.3 → P7.1–P7.3 → P7.4`. D79 makes every P4 item a separate routed root because each closes a producer, rollback, package-cwd or terminal-regeneration boundary; no P4 future bundle is required before its producer becomes terminal. Other stable ranges keep one root coordinator where Routing still groups them. Item commits and owner/security gates remain exact; common bookkeeping and lint are amortized only inside an actual Routing batch. P7.4 is the only planned independent whole-plan review and permits at most one targeted repair/recheck; frozen P4 content-review records remain product evidence, not Task Review.

Every remaining item has the same hard circuit-breaker: one initial candidate, one declared Validation pass, at most one grouped repair and one targeted recheck; a second RED returns the exact failing gate without a third loop. Green receipts whose inputs did not change are reused. Extra fixtures/checkers/reviewers/fuzz/mutation/adversarial probes are forbidden unless they are an explicit Deliverable or the minimum regression for an observed acceptance failure.

Real provider/project evidence runs as soon as prerequisites exist and once per candidate. Synthetic checks lock reproduced behavior but do not create extra fixture/reviewer loops. The historical red P1.2→P1.3 probe is provenance, not an admission gate: P1.3 owns production and acceptance of `--stage final`.

## Evidence-led skill modernization carrier

The audit does not create a second plan or pre-authorize its proposed rewrites. Its verified work
flows through the existing sequence:

`P0.5 corrected baseline → P0.6 semantic recovery gates → P0.7 executable security evidence → P0.8 provenance/fan-in → P0.9 semantic digest rebind → P0.10 live admission/final fan-in → final P0 audit → P1.2 Skill Core/adapters → P2.3 authoring/evidence → P3.2 adapter runtime → P3.3 multi-label audit → P4.2 template → P4.3 corpus → P6.2 health → P7.1 real replay/ablation → P7.2 regression locks → P7.4 cold audit`.

Official current provider documentation defines the intended interface. P7.1 proves behavior with
real Claude Code and Codex no-skill/minimum/provider-tuned workflows and instruction ablation;
P7.2 preserves demonstrated failures with deterministic tests. The minimum shared Skill Core stays
provider-neutral, while additive adapter descriptors carry discovery, invocation, projection and
provider-only tuning. A synthetic third-provider descriptor is a mandatory extensibility test, not
a claim of live efficacy. No audit heuristic, lexical overlap, token estimate or green synthetic
suite can authorize a merge, retirement or release by itself.

Все items последовательны по данным и/или несут contract/release/security риск. Каждый
item имеет одного root coordinator и запускается через `task:plan-run` под route из
`plan.md §3`. Multi-package item не выдаёт этот root-запуск за одну сессию: он
обязан пройти per-cwd protocol ниже. P4.3–P4.6 дополнительно используют внутренние
bounded ledger batches; это checkpoint'ы одного item'а, а не новые item IDs и не
параллельный Workflow script.

## Per-cwd execution and evidence carrier

Root coordinator is the sole owner of the item status, cumulative shared ledger, integration
validation and final close. Before any mutation it creates
`artifacts/execution/<item>/manifest.json` with the exact slice set, frozen input commits,
foreign-diff snapshot and deterministic next slice. Root/core/plan paths are its own slice.
Every package mutation is a fresh Codex launch from that package cwd; the package session reads
root → package instructions, edits only its declared package paths, commits only those paths,
and returns commands/exit codes plus the commit SHA. The coordinator verifies that report and
writes `artifacts/execution/<item>/cwd/<scope>.json`; package sessions never update plan status,
the shared corpus ledger or another package's evidence.

Evidence records have the closed fields `item`, `slice`, `cwd`, `route`, `input_commits`,
`files`, `preimage_sha256`, `commits`, `validation`, `readback`, `foreign_diff`, `result`, and
`next`. `validation` is a closed object with `state`, ordered command results and
`deferred_derived`; outside P4.3–P4.6 its only accepted state is `clean`. A slice is accepted only
when paths stay inside its declared scope, commit hashes resolve, validation satisfies the exact
state contract below, readback is green and the foreign-diff set is unchanged.
On interruption, the coordinator recomputes hashes and resumes from the lexicographically first
non-accepted slice; a partial/uncommitted slice is rolled back only from its named recoverable
preimage, never skipped. The item closes only after manifest exact-set equality and integration
validation; no package session may self-close the item.

| Multi-package item | Root/integration slice | Required package cwd slices (sequential) |
|:--|:--|:--|
| P3.2 | `core/provider`, core tests, manifest/close | `packages/harness` → `packages/maind` → `packages/skiller` → `packages/task` |
| P3.3 | `core/provider`, core tests, manifest/close | `packages/harness` → `packages/maind` → `packages/skiller` → `packages/task` |
| P4.1 | `core/locale`, pinned registry data/update producer, core/provider tests, fixtures, manifest/close | `packages/harness` → `packages/task` |
| P4.2 | root slice `configs/locale-corpus-v1.json`, `core/locale/corpus.py`, `core/tests/locale/test_corpus.py`, `scripts/{check-locale-corpus.py,test-check-locale-corpus.py}`, fixtures, `artifacts/execution/P4.2/**`, integration/close | `packages/skiller`: canonical `SKILL_TEMPLATE.md`, generated `generate-skill/generate-skill/snippets/SKILL_TEMPLATE.md` through its owner, template/generator checks, `scripts/check-translations.sh`, `scripts/validate.sh` integration call and corresponding tests only |
| P4.3 | root slice `configs/locale-corpus-v1.json`, `artifacts/execution/P4.3/{manifest.json,checkpoints/**,reviews/**,cwd/**}`, integration/close | `packages/skiller`: admitted `skills/**`, three named repository-bootstrap canons, source-direction `scripts/check-translations.sh`, named `lib/skiller/**` modules and corresponding `tests/**` only |
| P4.4 | core catalogs/diagnostics and shared ledger | `packages/harness` → `packages/maind` → `packages/skiller` → `packages/task` |
| P4.5 | admitted `core/**`/`scripts/**`, shared ledger | `packages/analyst` → `packages/harness` → `packages/maind` → `packages/skiller` → `packages/task` |
| P4.6 | root docs/config, shared ledger, terminal integration | `packages/analyst` → `packages/harness` → `packages/maind` → `packages/skiller` → `packages/task` |
| P6.2 | health contract, `core/provider`, core tests | `packages/skiller` → `packages/harness` → `packages/maind` |
| P7.2 | root/core regressions and integration matrix | `packages/analyst` → `packages/harness` → `packages/maind` → `packages/skiller` → `packages/task` |
| P7.3 | root docs/scripts/CHANGELOG and release manifest | `packages/harness` → `packages/skiller` |

Package-slice launch is a bare subtask of the open item, not a second `task:plan-run` and not
an authority to close it. Substitute the exact package/item/scope and use the item route:

```text
codex -C /home/vostrikov/projects/packages/swissknifeman/packages/<name> -m <gpt-5.6-terra for implementation | gpt-5.6-sol for frontier> -c model_reasoning_effort="high" -a never -s danger-full-access

Execute only package slice <scope> of 2026.08.02-PROVIDER-CONTRACT-LOCALE <item>.
Read ../../AGENTS.md, AGENTS.md, ../../plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/phases/<Pn>/<Pn>.md,
../../plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/phases/<Pn>/<Pn.m>.md,
../../plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/bundles/<Pn.m>.json,
../../plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/phases/<Pn>/<Pn.m>.state.md, and
../../plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/roadmap.md section "Per-cwd execution and evidence carrier".
Do not edit item status/shared ledger/other packages. Return exact files, commit SHA, validation
commands with exit codes, readback and foreign-diff comparison to the root coordinator.
```

### P4.2/P4.3 exact slice acceptance

The generic carrier above is specialized without executor interpretation. For P4.2 the root
coordinator runs `PYTHONPATH=. python3 -m unittest core.tests.locale.test_corpus`,
`python3 scripts/test-check-locale-corpus.py`,
`python3 scripts/check-locale-corpus.py --inventory --check --ledger configs/locale-corpus-v1.json`,
`python3 packages/skiller/scripts/generate-skill-template.py --check`,
`bash packages/skiller/scripts/check-translations.sh --strict`,
`bash packages/skiller/scripts/test.sh` and `bash packages/skiller/scripts/validate.sh`; the
Skiller cwd record must independently contain zero exits for
`python3 scripts/generate-skill-template.py --check`, `bash scripts/check-translations.sh --strict`,
`bash scripts/test.sh` (which owns its monorepo/core import path and discovers
`tests/test_skill_template.py` plus `tests/test_translation_direction.py`) and
`bash scripts/validate.sh`. For P4.3 every Skiller batch runs `bash scripts/test.sh` (covering
the five test modules named in P4.3 Validation) and
`bash scripts/check-translations.sh --strict --direction en-source`,
`bash scripts/validate.sh` from `packages/skiller`; only checkpoint-enumerated P4.6 derived drift
may remain non-zero. The root coordinator then runs the P4.3 ledger/checkpoint/review verifier
from `phases/P4/P4.3.md` and is the only writer of `configs/locale-corpus-v1.json`,
`artifacts/execution/P4.2/**`, `artifacts/execution/P4.3/**`, plan evidence, integration results,
status and item closure. A package commit cannot advance the ledger or close either item.

### P4.3–P4.6 `deferred-derived-only` state

Source checkpoints may use exactly one of two `validation.state` values. `clean` requires every
named command exit 0 and an empty `deferred_derived` array. `deferred-derived-only` is legal only
for P4.3–P4.6 before the P4.6 terminal-regeneration checkpoint: every nonzero command result must
normalize to one ordered row with fields `cwd`, stable `command_id`, `diagnostic_code` exactly
`DERIVED_TARGET_STALE`, root-relative `target_path`, `owner_generator` and observed preimage hash;
the array is sorted by `(cwd, command_id, target_path)`, is nonempty and equals the set recomputed
from the cumulative ledger plus owning generator dry-runs. Any test, parser, semantic, link,
review, ownership, command-launch or other non-freshness error makes the checkpoint non-accepted.

`python3 scripts/check-locale-corpus.py --verify-checkpoint ...` owns this classification: it
recomputes the exact row set, rejects missing/extra/reordered/duplicate rows, and persists the
cumulative union in the accepted checkpoint/resume chain. Resume still advances from the first
non-accepted source row; an accepted `deferred-derived-only` checkpoint is not retried merely
because its derived targets remain stale. P4.6 terminal-regeneration plan must consume exactly
that union as its generated writable-target set. After its apply/readback, all commands in the
P4.4/P4.6 matrix and all affected package validations return 0, every checkpoint state is
`clean`, the cumulative deferred set is empty, and a byte-stable second owner run is required;
otherwise P4.6 cannot close.

### P4.4/P4.6 closed cwd→command matrix

The cwd key is an exact closed set. A checkpoint whose `cwd` is absent, or whose evidence omits
one command listed for that item/cwd, is non-accepted. Commands are executed from the cwd in the
first column; root integration commands remain in `phases/P4/P4.4.md` and `phases/P4/P4.6.md`
Validation and are never
substituted by a package runner.

| Item | cwd | Exact command(s); source-checkpoint exit contract |
|:--|:--|:--|
| P4.4 | repository root | `PYTHONPATH=. python3 -m unittest core.tests.locale.test_catalog core.tests.locale.test_render core.tests.provider.test_status core.tests.provider.test_diagnostics` |
| P4.4 | `packages/harness` | `bash scripts/test.sh` · `bash scripts/validate.sh` |
| P4.4 | `packages/maind` | `bash scripts/test.sh` · `bash scripts/validate.sh` |
| P4.4 | `packages/skiller` | `bash scripts/test.sh` · `bash scripts/validate.sh` |
| P4.4 | `packages/task` | `bash scripts/validate.sh` |
| P4.6 | repository root | `python3 scripts/test-provider-docs.py` · `python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/test-p4-terminal-regeneration.py` |
| P4.6 | `packages/analyst` | `npm run docs:build` · `bash scripts/validate.sh` |
| P4.6 | `packages/harness` | `npm run docs:build` · `bash scripts/validate.sh` |
| P4.6 | `packages/maind` | `npm run docs:build` · `bash scripts/validate.sh` |
| P4.6 | `packages/skiller` | `npm run docs:standalone:build` · `npm run docs:build` · `bash scripts/validate.sh` |
| P4.6 | `packages/task` | `bash scripts/validate.sh` |

P4.4 terminal integration additionally runs the one fully expanded cross-package unittest command
in `phases/P4/P4.4.md` Validation. P4.6 terminal integration runs the four exact
`p4-terminal-regeneration.py` invocations there, including the frozen plan hash and the exact
alphabetically ordered Harness `--authorize` target set. In both items the root coordinator finally runs
`python3 packages/task/scripts/plan-lint.py plans/2026.08.02-PROVIDER-CONTRACT-LOCALE --baseline HEAD`;
package sessions do not replace or invoke that root-owned close gate.

For every matrix row, `clean` means exit 0. Before terminal regeneration, a real nonzero exit is
legal only when the checkpoint verifier maps it exactly to `deferred-derived-only` under the
preceding section; the prose “command listed in this matrix” never converts a failure by itself.
At P4.6 terminal close every row is `clean`/0 without exception.

## P4.3–P4.6 read-only checkpoint reviewer carrier

Every committed P4.3–P4.6 checkpoint is reviewed by a fresh identity that is distinct from all
checkpoint `author_id`/`renderer_id` values. The reviewer performs zero mutation: it does not edit,
write the review file, stage, commit, update the ledger or status, or run an apply/generator command.
The trusted-repository launch remains `-a never -s danger-full-access`; read-only behavior is a
task contract verified by equal before/after `git status --porcelain=v1` bytes and HEAD SHA. The
root coordinator owns the review record: it stores the reviewer's stdout byte-for-byte at the
exact path below, then runs the P4.2 checkpoint verifier before accepting it.

| Item/checkpoint | Exact committed inputs | Reviewer stdout stored by root coordinator |
|:--|:--|:--|
| P4.3 `<checkpoint-id>` | `artifacts/execution/P4.3/checkpoints/<checkpoint-id>.json`; diff `<base_sha>..<candidate_sha>` limited to manifest paths; `configs/locale-corpus-v1.json`; frozen `root/contracts/{english-authoring-overlay-v1,locale-authoring-review-v1}.md`; `phases/P4/P4.3.md`; `packages/skiller/AGENTS.md` and exact changed skill/canon sources | `artifacts/execution/P4.3/reviews/<checkpoint-id>.round-<round>.json` |
| P4.4 `<checkpoint-id>` | `artifacts/execution/P4.4/checkpoints/<checkpoint-id>.json`; same manifest-limited committed diff; ledger; the two frozen authoring/review contracts plus frozen P3 diagnostic contract; `phases/P4/P4.4.md`; root and changed package `AGENTS.md`; exact changed canonical/catalog sources | `artifacts/execution/P4.4/reviews/<checkpoint-id>.round-<round>.json` |
| P4.5 `<checkpoint-id>` | `artifacts/execution/P4.5/checkpoints/<checkpoint-id>.json`; same manifest-limited committed diff; ledger; frozen compactness/review contract; `phases/P4/P4.5.md`; root/current package `AGENTS.md`; exact changed files, AST/command-byte result and owning-runner result | `artifacts/execution/P4.5/reviews/<checkpoint-id>.round-<round>.json` |
| P4.6 `<checkpoint-id>` | `artifacts/execution/P4.6/checkpoints/<checkpoint-id>.json`; same manifest-limited committed diff; ledger; frozen authoring/review contracts; `phases/P4/P4.6.md`; root/current package `AGENTS.md`; exact changed docs, link/build result; for `terminal-regeneration`, generated exact-set and second-run/readback results | `artifacts/execution/P4.6/reviews/<checkpoint-id>.round-<round>.json` |

Substitute one item/checkpoint/round (`round` is exactly `1` or `2`) and its committed hashes from the checkpoint, then launch a
new reviewer process with this complete carrier:

```text
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c model_reasoning_effort="high" -a never -s danger-full-access

READ-ONLY checkpoint review for 2026.08.02-PROVIDER-CONTRACT-LOCALE <P4.3|P4.4|P4.5|P4.6> <checkpoint-id>, round <1|2>.
Reviewer identity: <item>/<checkpoint-id>/review-<round>/<fresh-session-id>; it MUST differ from every author_id and renderer_id in the checkpoint and prior rounds.
Read only the item-specific committed inputs in roadmap.md section "P4.3–P4.6 read-only checkpoint reviewer carrier". Recompute the manifest hashes; inspect `git diff --no-ext-diff <base_sha>..<candidate_sha> -- <exact manifest paths>`; verify the frozen contracts, semantic/literal/link obligations, validation evidence, rollback and contiguous next pointer. Do not edit/write/stage/commit, do not run apply/generators, and do not update the ledger/status/evidence. Capture HEAD and `git status --porcelain=v1` before and after; they must be byte-identical.
Output ONLY one JSON object on stdout with fields: item, checkpoint_id, round, reviewer_id, author_ids, renderer_ids, base_sha, candidate_sha, input_sha256, verdict, findings, required_fixes, head_before, head_after, status_before_sha256, status_after_sha256, zero_mutation. verdict is exactly APPROVE or FIX_REQUIRED; APPROVE requires empty findings/required_fixes, distinct identities, equal HEAD/status hashes and zero_mutation=true.
```

`FIX_REQUIRED` round 1 leaves the resume pointer unchanged: the author produces a separate fix
commit (never amend), the coordinator commits a revised checkpoint, and a fresh reviewer identity
runs round 2 against the new candidate SHA. `FIX_REQUIRED` round 2 stops the item, preserves both
records and escalates with `task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE <P4.x>` plus the
checkpoint paths; no third round, next batch, ledger acceptance or item closure is permitted.

## Карта исполнения

| Item | Batch | Запуск | Model class/Effort | Гейт владельца | Примечание |
|:--|:--|:--|:--|:--|:--|
| P0.1 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.1` | implementation/high | — | большой fleet/evidence capture; нельзя слить с классификацией до sealed baseline |
| P0.2 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.2` | frontier/high | — | ownership-классификация несёт открытые решения и потребляет P0.1 |
| P0.3 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.3` | frontier/high | typed `contract_freeze_decision` only | freeze recovery semantics plus executable checker/hash evidence; does not authorize mutation |
| P0.4 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.4` | implementation/high | mutation branch only: typed `containment_mutation_decision` | protected external/security transaction; evidenced no-op is the deterministic Validation/Note below, never owner authority |
| P0.5 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.5` | implementation/high | — | exact-set/privacy negative fixtures and complete provider-qualified D55–D61 baseline; consumes terminal history only |
| P0.6 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.6` | frontier/high | new typed `contract_freeze_decision` for exact successor bytes | semantic G01–G11 non-weakening and acyclic phase-local verifier topology; D63 is not reusable |
| P0.7 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.7` | implementation/high | mutation branch only: exact typed `containment_mutation_decision` | executable redacted producer replaces hand-authored green booleans; no-op remains deterministic |
| P0.8 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.8` | implementation/high | — | append-only provenance ledger/correction events and committed-tree P0 fan-in; historical bytes stay immutable |
| P0.9 | p0-final-requalification | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.9-P0.10` | implementation/high | — | first adjacent batch item: semantic-identity proof and complete current digest/pin rebind; no reclassification |
| P0.10 | p0-final-requalification | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.9-P0.10` | implementation/high | mutation branch only: exact typed `containment_mutation_decision` | remaining batch suffix: live non-persisted admission, static fan-in, close candidate and last planned P0 audit handoff |
| P1.1 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P1.1` | frontier/high | schema freeze | desired/status public contract |
| P1.2 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P1.2` | frontier/high | ownership/capability freeze | freezes minimum Skill Core, additive provider adapters and third-provider registration seam |
| P1.3 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P1.3` | frontier/high | C1–C6 Owner approval | migration/rollback freeze after P0/P1 evidence |
| P2.1 | p2-contracts | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P2.1-P2.3` | frontier/high | locale contract/registry identity approval | first batch slice; freezes independent surfaces/precedence plus exact IANA bytes/provenance |
| P2.2 | p2-contracts | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P2.1-P2.3` | frontier/high | source/overlay approval | same root consumes P2.1 and freezes canonical direction; no intermediate review |
| P2.3 | p2-contracts | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P2.1-P2.3` | frontier/high | review/policy approval | same root closes compact authoring/evidence contract; bookkeeping and lint at batch boundary |
| P3.1 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P3.1` | implementation/high | — | public resolver against frozen P1/P2 contracts |
| P3.2 | solo/per-cwd | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P3.2` | implementation/high | — | D78 compact frozen-contract/recon root bundle + four required package-cwd slices; owns relative-target public hook CLI fix and consumes P3.1 |
| P3.3 | solo/per-cwd | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P3.3` | implementation/high | — | compact sealed P0 policy input, never raw fleet rows; multi-label audit evidence, typed batch failures, provider-qualified measurements and deduplicated diagnostics |
| P4.1 | solo/per-cwd | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.1` | implementation/high | — | root coordinator owns stdlib runtime + pinned-registry reader/update producer; Harness/Task cwd slices consume the shared locale boundary |
| P4.2 | solo/per-cwd | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.2` | implementation/high | admission ledger approval | one canonical minimum-core template generates its distributed copy; cross-field risk/invocation and trigger boundaries are checked |
| P4.3 | solo/per-cwd-ledger | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.3` | implementation/high | admitted skill rows | evidence-admitted lean corpus changes only; no pre-approved Vue merge, universal Gotchas or heuristic-only retirement |
| P4.4 | solo/per-cwd-ledger | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.4` | implementation/high | admitted command/plugin rows | ≤10 rows, one package cwd per checkpoint; parser literals release-sensitive |
| P4.5 | solo/per-cwd-ledger | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.5` | implementation/high | admitted code-prose rows | ≤12 files/≤40 prose spans, one package cwd; concrete runners + independent review |
| P4.6 | solo/per-cwd-ledger | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.6` | implementation/high | terminal ledger | ≤10 docs files per checkpoint; terminal regeneration is a separate final integration stage |
| P5.1 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P5.1` | frontier/high | exact fleet action D# | freezes target/action/rollback set and initializes the D47 durable hash-chained journal before any consumer write |
| P5.2 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P5.2` | implementation/high | approved override actions | live project-owned override preservation through exact apply/resume/verify carrier |
| P5.3 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P5.3` | implementation/high | approved managed actions | exact managed repair with write-ahead project rollback and deterministic resume |
| P5.4 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P5.4` | implementation/high | exact quarantine D# | destructive boundary plus journal reconciliation and two-run convergence |
| P6.1 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P6.1` | implementation/high | exact Brain action D# | protected external transaction with D52 WAL/resume/reconcile; P0.4 owns credentials |
| P6.2 | solo/per-cwd | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P6.2` | frontier/high | provider-health freeze | provider/model/surface/unit/method/uncertainty/freshness remain typed and independently visible |
| P6.3 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P6.3` | implementation/high | — | exact-set two-run evidence; may complete non-green |
| P7.1 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P7.1` | implementation/high | — | real Claude/Codex no-skill/minimum/provider-tuned replay and ablation precede exact-set release blockers |
| P7.2 | solo/per-cwd | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P7.2` | implementation/high | — | supplementary deterministic regressions lock behaviors demonstrated by P7.1; they never replace live evidence |
| P7.3 | solo/per-cwd | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P7.3` | implementation/high | — | owns exact external `docs/reference.md` entries and registry identity in the release manifest; blocker set must be empty; no publish |
| P7.4 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P7.4` | frontier/xhigh | Owner GREEN/ATTENTION/RED D# | cold read-only adversarial audit; dynamic exact-set decision crosswalk; no self-fix |

## Deterministic Validation/Note (not owner gates)

| Где | Predicate/evidence | Результат |
|:--|:--|:--|
| P0.7 evidenced no-op | The P0.7 executable producer recomputes the owner-frozen P0.6 predicate over committed P0.5 manifest/classification plus fresh redacted detector, provider/trust and protected pre/post evidence; the evidence record has `action_set=[]`, plaintext-secret findings 0 and protected-target delta 0. | Close P0.7 through ordinary Validation; no D# authorizes an empty mutation. If the predicate is false, mutation remains waiting until an exact containment D# exists. |
| P0.10 live admission | Stored observation proves only integrity. The non-persisted `admit` command recomputes provider/trust/detector/protected-delta facts at use time and emits one redacted stdout receipt. | Final P0 audit runs it last; after GREEN, P1 reruns it immediately before mutation. No persisted TTL or old receipt grants admission. |
| P4.3–P4.6 source checkpoint | The checkpoint verifier recomputes either `clean` or the exact ordered `deferred-derived-only` rows and proves zero other errors. | Accept/resume the source checkpoint; this is technical deferred state, not owner authority. P4.6 closure still requires terminal all-green. |
| P4.6 terminal regeneration | Complete terminal source ledger + exact cumulative deferred set + frozen helper-plan hash; Harness writable targets are passed in its exact alphabetic order through `--authorize`. | Ordinary item-scoped generated write; no P0 contract/containment D# applies. Any plan-hash/target/order drift refuses before write. |

## Гейты владельца (сводно)

| Где | Что утверждает | Блокирует |
|:--|:--|:--|
| P0.6 contract successor freeze | exact corrective recovery-gate bytes, version and checker evidence | P0.7 and P1–P7 consumption; D63 is historical and never authorizes new bytes or a write |
| P0.7 mutation branch | exact security/trust targets, preimages, backup and rollback | any containment mutation; the deterministic no-op row above is outside owner authority |
| P1.1–P1.3 | provider-control-plane schema, ownership/capability map and C1–C6 migration/rollback freeze | P3–P7 |
| P2.1–P2.3 | locale/source/overlay/review contracts | P4–P7 |
| P4.2–P4.6 | admitted corpus rows and terminal independent review | each next migration batch and P5 |
| P5.1–P5.4 | exact consumer action and quarantine sets | every live fleet write and P6 |
| P6.1/P6.2 | Brain transaction and provider-health contract | P6.3/P7 |
| P7.4 | final release verdict; exceptions name exact rows and consequences | any later tag/push/publish operation |

Execution resumes with solo P4.1. Its historical attempt/block-candidate and pending manifest remain
evidence; the fresh root reconciles them and starts product mutation only after the compact bundle and
route gates pass. D79 changes no P1/P2/P3 frozen semantics, P4 content admission, external no-write gate
or consumer/fleet authority. `handoff.md` is the sole current Next carrier; P4.2 is generated only after
P4.1 terminal evidence names its runtime fixtures.
