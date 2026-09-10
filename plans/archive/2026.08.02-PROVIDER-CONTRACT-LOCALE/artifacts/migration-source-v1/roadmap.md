# Roadmap исполнения — 2026.08.02-PROVIDER-CONTRACT-LOCALE

**Обновлён:** 2026-08-03 · **Соответствует plan.md:** v1.0.5 · **Статус:** design-audit remediation F1–F25 applied; execution remains closed until repeated independent `task:plan-audit 2026.08.02-PROVIDER-CONTRACT-LOCALE design` is GREEN.

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
| P4.2 | root slice `configs/locale-corpus-v1.json`, `core/locale/corpus.py`, `core/tests/locale/test_corpus.py`, `scripts/{check-locale-corpus.py,test-check-locale-corpus.py}`, fixtures, `artifacts/execution/P4.2/**`, integration/close | `packages/skiller`: `scripts/check-translations.sh`, `scripts/validate.sh` integration call and `tests/test_translation_direction.py` only |
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
Read ../../AGENTS.md, AGENTS.md, ../../plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/phases/<Pn>.md,
and ../../plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/roadmap.md section "Per-cwd execution and evidence carrier".
Do not edit item status/shared ledger/other packages. Return exact files, commit SHA, validation
commands with exit codes, readback and foreign-diff comparison to the root coordinator.
```

### P4.2/P4.3 exact slice acceptance

The generic carrier above is specialized without executor interpretation. For P4.2 the root
coordinator runs `PYTHONPATH=. python3 -m unittest core.tests.locale.test_corpus`,
`python3 scripts/test-check-locale-corpus.py`,
`python3 scripts/check-locale-corpus.py --inventory --check --ledger configs/locale-corpus-v1.json`,
`bash packages/skiller/scripts/check-translations.sh --strict`,
`bash packages/skiller/scripts/test.sh` and `bash packages/skiller/scripts/validate.sh`; the
Skiller cwd record must independently contain zero exits for
`bash scripts/check-translations.sh --strict`, `bash scripts/test.sh` (which owns its
monorepo/core import path and discovers `tests/test_translation_direction.py`) and
`bash scripts/validate.sh`. For P4.3 every Skiller batch runs `bash scripts/test.sh` (covering
the five test modules named in P4.3 Validation) and
`bash scripts/check-translations.sh --strict --direction en-source`,
`bash scripts/validate.sh` from `packages/skiller`; only checkpoint-enumerated P4.6 derived drift
may remain non-zero. The root coordinator then runs the P4.3 ledger/checkpoint/review verifier
from `phases/P4.md` and is the only writer of `configs/locale-corpus-v1.json`,
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
first column; root integration commands remain in `phases/P4.md` Validation and are never
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
in `phases/P4.md` P4.4 Validation. P4.6 terminal integration runs the four exact
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
| P4.3 `<checkpoint-id>` | `artifacts/execution/P4.3/checkpoints/<checkpoint-id>.json`; diff `<base_sha>..<candidate_sha>` limited to manifest paths; `configs/locale-corpus-v1.json`; frozen `root/contracts/{english-authoring-overlay-v1,locale-authoring-review-v1}.md`; `phases/P4.md` P4.3; `packages/skiller/AGENTS.md` and exact changed skill/canon sources | `artifacts/execution/P4.3/reviews/<checkpoint-id>.round-<round>.json` |
| P4.4 `<checkpoint-id>` | `artifacts/execution/P4.4/checkpoints/<checkpoint-id>.json`; same manifest-limited committed diff; ledger; the two frozen authoring/review contracts plus frozen P3 diagnostic contract; `phases/P4.md` P4.4; root and changed package `AGENTS.md`; exact changed canonical/catalog sources | `artifacts/execution/P4.4/reviews/<checkpoint-id>.round-<round>.json` |
| P4.5 `<checkpoint-id>` | `artifacts/execution/P4.5/checkpoints/<checkpoint-id>.json`; same manifest-limited committed diff; ledger; frozen compactness/review contract; `phases/P4.md` P4.5; root/current package `AGENTS.md`; exact changed files, AST/command-byte result and owning-runner result | `artifacts/execution/P4.5/reviews/<checkpoint-id>.round-<round>.json` |
| P4.6 `<checkpoint-id>` | `artifacts/execution/P4.6/checkpoints/<checkpoint-id>.json`; same manifest-limited committed diff; ledger; frozen authoring/review contracts; `phases/P4.md` P4.6; root/current package `AGENTS.md`; exact changed docs, link/build result; for `terminal-regeneration`, generated exact-set and second-run/readback results | `artifacts/execution/P4.6/reviews/<checkpoint-id>.round-<round>.json` |

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
| P1.1 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P1.1` | frontier/high | schema freeze | desired/status public contract |
| P1.2 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P1.2` | frontier/high | ownership/capability freeze | consumes P1.1 and freezes ecosystem semantics |
| P1.3 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P1.3` | frontier/high | C1–C6 Owner approval | migration/rollback freeze after P0/P1 evidence |
| P2.1 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P2.1` | frontier/high | locale contract/registry identity approval | freezes independent surfaces/precedence plus exact IANA bytes/provenance |
| P2.2 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P2.2` | frontier/high | source/overlay approval | consumes P2.1, freezes canonical direction |
| P2.3 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P2.3` | frontier/high | review/policy approval | closes compactness and translation-review contract |
| P3.1 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P3.1` | implementation/high | — | public resolver against frozen P1/P2 contracts |
| P3.2 | solo/per-cwd | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P3.2` | implementation/high | — | root coordinator + four required package-cwd slices; owns relative-target public hook CLI fix and consumes P3.1 |
| P3.3 | solo/per-cwd | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P3.3` | implementation/high | — | root coordinator + four required package-cwd slices; status/diagnostic contract feeds rollout/health |
| P4.1 | solo/per-cwd | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.1` | implementation/high | — | root coordinator owns stdlib runtime + pinned-registry reader/update producer; Harness/Task cwd slices consume the shared locale boundary |
| P4.2 | solo/per-cwd | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.2` | implementation/high | admission ledger approval | root coordinator owns tooling/ledger/evidence/closure; exact fresh Skiller cwd slice and validation paths are mandatory |
| P4.3 | solo/per-cwd-ledger | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.3` | implementation/high | admitted skill rows | root coordinator + exact Skiller cwd slice; ≤12 units and executable independent reviewer carrier per checkpoint |
| P4.4 | solo/per-cwd-ledger | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.4` | implementation/high | admitted command/plugin rows | ≤10 rows, one package cwd per checkpoint; parser literals release-sensitive |
| P4.5 | solo/per-cwd-ledger | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.5` | implementation/high | admitted code-prose rows | ≤12 files/≤40 prose spans, one package cwd; concrete runners + independent review |
| P4.6 | solo/per-cwd-ledger | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.6` | implementation/high | terminal ledger | ≤10 docs files per checkpoint; terminal regeneration is a separate final integration stage |
| P5.1 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P5.1` | frontier/high | exact fleet action D# | freezes target/action/rollback set and initializes the D47 durable hash-chained journal before any consumer write |
| P5.2 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P5.2` | implementation/high | approved override actions | live project-owned override preservation through exact apply/resume/verify carrier |
| P5.3 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P5.3` | implementation/high | approved managed actions | exact managed repair with write-ahead project rollback and deterministic resume |
| P5.4 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P5.4` | implementation/high | exact quarantine D# | destructive boundary plus journal reconciliation and two-run convergence |
| P6.1 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P6.1` | implementation/high | exact Brain action D# | protected external transaction with D52 WAL/resume/reconcile; P0.4 owns credentials |
| P6.2 | solo/per-cwd | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P6.2` | frontier/high | provider-health freeze | root coordinator + Skiller/Harness/mAInd cwd slices |
| P6.3 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P6.3` | implementation/high | — | exact-set two-run evidence; may complete non-green |
| P7.1 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P7.1` | implementation/high | — | deterministic gate: non-empty `release-blockers.json` stops P7.2/P7.3 release-green progression |
| P7.2 | solo/per-cwd | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P7.2` | implementation/high | — | root coordinator + five package-cwd regression slices; includes pinned-registry and public relative/absolute hook CLI zero-write smoke |
| P7.3 | solo/per-cwd | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P7.3` | implementation/high | — | owns exact external `docs/reference.md` entries and registry identity in the release manifest; blocker set must be empty; no publish |
| P7.4 | solo | `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P7.4` | frontier/xhigh | Owner GREEN/ATTENTION/RED D# | cold read-only adversarial audit; dynamic exact-set decision crosswalk; no self-fix |

## Deterministic Validation/Note (not owner gates)

| Где | Predicate/evidence | Результат |
|:--|:--|:--|
| P0.4 evidenced no-op | The frozen P0.3 no-op predicate evaluates pass over committed P0.1 manifest/classification plus a fresh independent P0.4 redacted detector and provider/trust checks; the evidence record has `action_set=[]`, plaintext-secret findings 0 and protected-target delta 0. | Close P0.4 through its ordinary Validation with committed no-op evidence; no D# authorizes an empty mutation. If the predicate is false, mutation remains waiting until an exact containment D# exists. |
| P4.3–P4.6 source checkpoint | The checkpoint verifier recomputes either `clean` or the exact ordered `deferred-derived-only` rows and proves zero other errors. | Accept/resume the source checkpoint; this is technical deferred state, not owner authority. P4.6 closure still requires terminal all-green. |
| P4.6 terminal regeneration | Complete terminal source ledger + exact cumulative deferred set + frozen helper-plan hash; Harness writable targets are passed in its exact alphabetic order through `--authorize`. | Ordinary item-scoped generated write; no P0 contract/containment D# applies. Any plan-hash/target/order drift refuses before write. |

## Гейты владельца (сводно)

| Где | Что утверждает | Блокирует |
|:--|:--|:--|
| P0.3 contract freeze | exact recovery-gate semantics and checker evidence | P1–P7 contract consumption; never authorizes a write |
| P0.4 mutation branch | exact security/trust targets, preimages, backup and rollback | any containment mutation; the deterministic no-op row above is outside owner authority |
| P1.1–P1.3 | provider-control-plane schema, ownership/capability map and C1–C6 migration/rollback freeze | P3–P7 |
| P2.1–P2.3 | locale/source/overlay/review contracts | P4–P7 |
| P4.2–P4.6 | admitted corpus rows and terminal independent review | each next migration batch and P5 |
| P5.1–P5.4 | exact consumer action and quarantine sets | every live fleet write and P6 |
| P6.1/P6.2 | Brain transaction and provider-health contract | P6.3/P7 |
| P7.4 | final release verdict; exceptions name exact rows and consequences | any later tag/push/publish operation |

Execution starts from this map only after a GREEN independent
`task:plan-audit 2026.08.02-PROVIDER-CONTRACT-LOCALE design`. `handoff.md` is the sole current
Next carrier; after that audit it must point to P0.1 under the route and Owner gates above.
