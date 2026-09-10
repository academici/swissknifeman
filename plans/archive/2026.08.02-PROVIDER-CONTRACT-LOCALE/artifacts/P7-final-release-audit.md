# P7.4 final design and release audit

**Audit snapshot:** 2026-08-17T06:21:00Z
**Repository anchor:** `519af66def68027738a0158142cf7a19050d3983`
**Route:** `gpt-5.6-sol/frontier/xhigh`, session `01a00e4f-af6d-7a33-b636-7d22b423145b`
**Owner disposition:** D89 accepts only a truthful non-releasable candidate and requires a
non-GREEN P7.4 disposition while required blockers remain.

**Вердикт: RED**

The package-contract candidate may remain a documented non-published artifact under D88/D89, but
it is not a releasable tree. P7.4 does not authorize tag, push, publication, fleet rollout,
provider repair, or a claim of live provider efficacy.

## Severity-ranked findings

### Blocker F1 — release gates are objectively non-green

`artifacts/P6.3/evidence/fleet-health-verdict.json` reports `aggregate=non-green`,
`p7_release_authorized=false`, 23 sealed projects, 22 bindings, two providers, one unavailable
required project, 24 required-project blockers, and the global
`P5_ROLLOUT_NOT_AUTHORIZED` blocker: 25 release blockers in total. The two P6 observations have
equal semantics, so this is stable negative evidence rather than a transient comparison failure.
`artifacts/P7.1/evidence/release-blockers.json` faithfully carries the 24 project blockers plus
deferred P5 rollout, non-live-verified Claude Code, and diagnostic-only Codex replay. D89 explicitly
forbids a GREEN release verdict for this state.

### Blocker F2 — the frozen P7.4 verifier interface is not implemented

The exact acceptance `check` command exits 2 because the committed script does not accept
`--p6-evidence`, `--p5-journal`, `--contracts-dir`, or `--capabilities`. The exact crosswalk command
also exits 2 because `--require-exact-set` is absent. The script's current release-tree subcommand
expects `--protected-paths`, not the frozen release/acceptance/worktree manifest interface. Thus the
item's required public commands cannot prove the frozen inputs, dynamic Decision Log set, or clean
release-tree predicate. P7.4 is read-only and cannot repair this P7.1-owned implementation.

### Blocker F3 — there is no clean committed release candidate

`artifacts/P7-release-candidate-manifest.md` records only HEAD
`519af66def68027738a0158142cf7a19050d3983`, states that P7.3 changes are deliberately uncommitted,
and derives `releasable=false`. The audit began in a shared dirty worktree containing predecessor
P7 changes and unrelated owner changes. `artifacts/P7-final-worktree-status.json` is the bounded
porcelain snapshot; audit-created files and the separately requested Task roadmap record are
classified independently. A dirty observation is not a committed candidate anchor.

### Major F4 — the validation carrier is red

Core, skiller, harness, maind, analyst, provider-doc generation, provider-doc tests, and the P7.1
bundle verifier are green. `packages/task/scripts/validate.sh` is red because plan lint finds two
errors: P7.3's closed item lacks the parsed write-site line and P7.4's estimated read weight exceeds
100000 (`112743` observed in the package run). The frozen acceptance and crosswalk commands are also
red as described by F2. Final citation/lint and release-tree command outcomes are recorded in the
validation table below after the audit artifacts are sealed.

### Major F5 — live efficacy and ablation are not release evidence

P7.1 contains 54 replay rows across two providers, nine workflows, and the `no-skill`,
`minimum-core`, and `provider-tuned` variants. Its verifier returns 0 and package blockers are empty.
However, `skill-ablation-results.json` is `deferred-owner-decision`, with the reason that live
efficacy is outside package acceptance; the replay is classified `diagnostic-not-release-gate`.
D88 permits that package boundary, but it cannot satisfy P7.4's release-efficacy condition.

### Major F6 — plan cold-start carriers drift from the terminal evidence

`decisions/_current.md` stops at D88 while the dynamically enumerated log contains D1–D89;
`roadmap.md` still resumes at P6.3 although P7.1–P7.3 are terminal; P2/P3 phase handoffs describe
stale phase progress. The dynamic crosswalk avoids hiding D89, but these human entry points can
misroute a fresh executor and must be regenerated or reconciled by their owners.

### Process deviation F7 — Task's five-file read has a two-layer output-budget footgun

The mandated five files were physically read once, but the outer orchestration result truncated
the combined output even when the nested command requested a larger budget. Bounded rereads were
needed to recover the hidden P7.4 section. The reproduction and proposed snapshot/cursor contract
are recorded separately in `roadmap/2026.08.17-task-five-file-read-output-budget.md`; this does not
alter the P7.4 release decision.

## Exact-set and identity checks

- Decision Log snapshot: 89 files, exact IDs D1–D89. The crosswalk has 89 rows;
  `missing=[]`, `extra=[]`, `duplicates=[]`, `post_snapshot=[]`. Its aggregate digest is
  `sha256:a4f5e460b5eab9df46cbba570b9c654d198577d7f6f8652a2b4ef781bbae29f3`.
  D87–D89 have blob identities but are not tracked at the HEAD anchor, which itself prevents a
  committed-tree claim.
- P0/P6/P7 project sets are equal at 23; provider sets are equal at `claude-code,codex`; P7 carries
  35 shared capability expectations. P6's 24 required-project blockers equal P7.1's deferred
  project-blocker projection.
- P5's transaction journal is empty while `project-set.json` reports zero transactions,
  `rollout_authorized=false`, `migration_readiness=held-unresolved`, and 13421 unresolved rows.
  This is consistent negative evidence under D83/D88, not terminal rollout/rollback evidence for a
  release.
- The inspected contracts retain the frozen provider-control, locale-resolution,
  English-authoring-overlay, locale-authoring-review, and provider-health identities. No contract
  was edited in this audit.

## Validation

| Carrier | Exit | Result |
|---|---:|---|
| P7 acceptance `check` (exact P7.4 argv) | 2 | RED: four required arguments unsupported |
| P7.1 evidence `verify.py` | 0 | GREEN |
| `verify-decision-crosswalk --require-exact-set` | 2 | RED: flag unsupported |
| `verify-release-tree` (exact P7.4 argv) | 2 | RED: implementation requires a different `--protected-paths` interface |
| `python3 -m unittest discover -s core/tests` | 0 | GREEN, 275 tests |
| `packages/skiller/scripts/validate.sh` | 0 | GREEN, 645 tests; warnings retained |
| `packages/task/scripts/validate.sh` | 1 | RED, 934 tests pass but plan lint has 2 errors |
| `packages/harness/scripts/validate.sh` | 0 | GREEN, 652 tests |
| `packages/maind/scripts/validate.sh` | 0 | GREEN, 557 tests |
| `packages/analyst/scripts/validate.sh` | 0 | GREEN, 256 tests |
| `scripts/provider-docs.py --check` | 0 | GREEN |
| `scripts/test-provider-docs.py` | 0 | GREEN, 5 tests |
| strict plan citations | 0 | GREEN, 34 citations, 0 findings |
| plan lint against HEAD | 1 | RED: 2 errors, both new relative to HEAD |

No failed or skipped release gate is treated as green. No package, docs, generated source,
contract, fleet, provider, tag, push, or publication mutation was performed by P7.4.

## Full scope payload for RED

| Finding | Owning locus | Exact repair/authority needed | Consequence while open |
|---|---|---|---|
| F1 | P5/P6 + repository owner | authorize and execute a separately scoped rollout/health measurement, or record a new exact owner disposition; produce zero required release blockers | release forbidden |
| F2 | P7.1 acceptance producer / frozen P7.4 contract owner | implement the declared CLI and machine exact-set/release-tree checks, or explicitly revise and re-freeze the validation contract | P7.4 validation cannot pass |
| F3 | release integrator | commit a reviewed candidate with all referenced evidence/decisions, separate foreign changes, then capture a clean tree | no reproducible release anchor |
| F4 | P7.3/P7.4 plan bookkeeping owners | repair the parsed P7.3 write-site carrier and reduce/split the P7.4 read budget without weakening required evidence | Task validation and plan lint remain red |
| F5 | provider-efficacy owner | open a new scoped item with working provider access and explicit efficacy acceptance | no live-provider release claim |
| F6 | plan projection/phase owners | regenerate/reconcile `_current.md`, plan roadmap, and stale handoffs from authoritative decisions/journal | cold-start drift remains |
| F7 | Task command owner | adopt a snapshot-once/cursor read contract and surface the outer output budget; see the roadmap candidate | future executors may miss hidden plan sections |

## Owner decision and continuation

D89 is the applicable Owner decision: reject GREEN/release authorization while blockers remain.
No new exception is inferred and no waiver is requested by the audit.

Provider-neutral Semantic Next:

```text
$ task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE P7
```

The design session must route F1–F6 forward through their owning items, preserve this RED evidence,
and must not reopen release execution without explicit rollout/provider authority.

Native Codex launch:

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman \
  -m gpt-5.6-sol -c model_reasoning_effort=high \
  -a never -s danger-full-access \
  '$ task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE P7'
```

## P7.7 bounded F2–F6 delta audit

**Delta snapshot:** `2026-08-17T10:32:29Z`
**Repository HEAD:** `eaf5cc0e043e31a3e9edd562e98113010958976f`
**P7.6 scope anchor/tree:** `072f806507c0b2672fb393c6fb15812bbb3cddd6` / `356fab8290bc578604371ec499d05cb93114f9ef`
**Route:** `gpt-5.6-sol/frontier/xhigh`, session `01a00f2e-4e55-74b2-a141-8778962bc110`

**Package-candidate verdict: RED — local recovery incomplete.**

**Release verdict: RED — unchanged D89 blockers; `release_authorized=false`.**

This is the single D90 successor delta audit. It does not rerun fleet/provider efficacy, rewrite
the P7.4 baseline, or authorize tag, push, publish, rollout, provider repair, or release.

### Delta findings

| Surface | Result | Independent evidence |
|:--|:--|:--|
| F2 verifier interface | RED | `check` and `verify-decision-crosswalk --require-exact-set` now return 0, and the verifier self-test is GREEN. The exact frozen `verify-release-tree` command still returns 2 because it passes Markdown `P7-release-candidate-manifest.md` to a JSON-only `p7-candidate-paths/v1` interface. Substituting the actual `P7-candidate-paths.json` reaches the next predicate and returns 2 for unclassified `bundles/P7.7.json`. |
| F3 committed candidate and partition | RED | The P7.6 scope commit and tree equal the integration receipt. Candidate/foreign and protected/foreign intersections are empty, and the sealed foreign-list digest still equals `61a1fd0ce056bd5699417cad152f0cc6b276303b66f6ce2b8073832e62c9bddd`. However, the required current-D# crosswalk differs from the P7.6 anchor, the generated P7.7 bundle is outside both sets, and six current foreign bytes differ from the sealed preimages. The verifier checks the manifest-list digest but does not compare current foreign bytes to those preimages. |
| F4 validation/bookkeeping | RED | Targeted provider/crosswalk/self-test, remediation manifest, integration receipt, decision views, state views, bundle freshness, provider-doc check and strict citations are GREEN. Status projection was stale and was regenerated successfully. Plan lint remains RED with 11 diagnostics: P7.5/P7.6 terminal notes omit write-site codes, three downstream records are absent, and the committed handoff is schema-invalid. |
| F5 live efficacy/blockers | unchanged RED | No live retry was performed. The blocker payload is byte-equal to the P7.3 manifest payload (`sha256:f23721271c91c236c0e256842fa5fbe92b4868fb948719978863381f423c12fa`), and D89 remains byte-identical (`sha256:9a456ddcb8d9bd5ee6434528a66c45e1f3fff5f0b5d03f6cf7f7b3cdc91508cb`). |
| F6 cold-start carriers | RED | Decision views, all item-state views, P7.7 bundle and citations are fresh; status was repaired. The invalid handoff plus missing downstream records still make the cold-start entry point non-conformant. |

The known F7 outer-output truncation reproduced while reading the declared bundle set. Only the
hidden release-candidate carrier was reread; this remains a process deviation and does not change
the F2–F6 verdict.

### Receipt disposition

No P7.4 GREEN command is claimed as reused because P7.4 did not record a command-level input hash.
P7.7 reran only the declared F2–F6 commands. The current exact Decision Log has D1–D90 with
`missing=[]`, `extra=[]`, `duplicates=[]`, and `post_snapshot=[]`; its generated carrier is
`sha256:b8a6c4fc34a97fb7acb81d25ff8ea2b575f552d58e396eaac79bc98672ee3263`.

### Fix recommendations required before phase close

1. Bind the frozen release-tree validation to `artifacts/P7-candidate-paths.json`, or teach the
   verifier to resolve the Markdown carrier to that schema explicitly; add one exact-argv
   regression for the declared P7.7 command.
2. Seal candidate/foreign membership after terminal bookkeeping, or define a deterministic
   runtime-carrier class for journal/state/status/bundle/handoff outputs. The verifier must hash
   current foreign bytes against their recorded preimages, with explicit generated-runtime
   exemptions, instead of hashing only the static manifest list.
3. Repair P7.5/P7.6 terminal write-site evidence and record downstream results for P7.6/P7.7
   through the owning journal/downstream tools; regenerate status/index/handoff and rerun plan lint.
4. Add command-level input hashes to future reusable audit receipts. Until then, mark prior
   receipts unqualifiable rather than self-attesting reuse.
5. Keep D89's external blocker and live-efficacy state unchanged. They need separately authorized
   external execution and are not prerequisites for closing P7 as a truthful non-releasable phase.

After recommendations 1–4, rerun only the three exact P7.7 commands, generated-view checks and
plan lint, then execute `task:plan-close 2026.08.02-PROVIDER-CONTRACT-LOCALE P7`. Recommendation 5
continues outside this phase and release remains forbidden.
