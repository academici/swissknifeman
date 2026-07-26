# Provider/core hypotheses — code-grounded adjudication and bounded future proposals (P4.1)

RAG:— (repo-grounded: `core/provider*.py`, `core/tests/test_provider*.py`,
`packages/skiller/lib/skiller/{publication,registry,config,lock}.py`,
`packages/harness/lib/harness/{provider_render,provider_audit,agentpacks}.py`,
`packages/harness/configs/claude-code/hooks/{run-report/_lib.py,pack-guard/pack-guard.py}`,
`packages/harness/scripts/{validate.sh,sync-usage.sh}`, `core/pathology.py`,
`packages/analyst/lib/analyst/trace.py`; plan-grounded: D14, D23, D25, D89, D92).

## What this file is

The external audit committed at `artifacts/source-evidence/perplexity-audit.md`
(sha256 `dd686f91…a4a0d37b`, 2993 lines, hash-pinned by
`manifests/bundle-manifest.json`) was retained so that its architectural proposals could be
**decided against code**, not carried forward as ambient claims (`findings/00`, § External
audit claim inventory: lines 21–169 / 312–463 / 625–766 / 767–912 are marked "P4.1
falsification only" / "not fact before code proof").

This file is the durable record of that decision: **16 load-bearing hypotheses**, each with a
verdict, the exact functions/callers/tests that decide it, and — for accepted ones — one
bounded future proposal. The machine-readable form is
`artifacts/P4.1/hypothesis-verdicts.json`, checked by
`artifacts/P4.1/verify_claim_verdicts.py`.

**Nothing here is implemented by P4.1.** Every accepted hypothesis is a *proposal for a future
plan* with a named owner, contract, tests and observable user outcome. This item mutated no
byte of `packages/**` or `core/**`.

**Adjudication axis.** These verdicts do not depend on, and are not argued from, the plan's
acceptance state (D89): whether the acceptance floors are met is a different measurement from
whether an architectural claim is true of the code. The verifier enforces this mechanically —
an `observable_relevance` field that argues from acceptance completion fails the check.

## Verdict semantics

| Verdict | Means |
|:--|:--|
| `accept` | the audit's proposed change is adopted as ONE bounded FUTURE proposal (owner/contract/tests/outcome); this item implements nothing |
| `reject` | the proposed change is not adopted. `observation_upheld` names whatever part of the observation IS true — reject is never a claim that the author saw nothing |
| `unknown` | the committed tree cannot decide it in either direction; the MISSING evidence is named by name, not as "unclear" |

## Verdicts

| # | Hypothesis (audit lines) | Verdict | Decided by |
|:--|:--|:--|:--|
| H01 | split `core/` into domain/application/infra/adapters (45–169) | **reject** | `core/` imports zero packages (one-way rule already holds); `core/provider.py`/`provider_config.py` declare and hold the pure boundary; `core/cli.py` is a 111-line argv primitive, not a dispatcher; no measured incident points at core layout |
| H02 | `core/` is a coordination catch-all; provider invariants are implicit author knowledge (171–311) | **reject** | 77 green tests over seven `core/tests/test_provider*.py` modules pin the invariants; `test_exports_match_the_approved_public_surface` pins the public surface |
| H03 | mixed truth model config/manifest/lock (312–463) | **reject** | the assumed pipeline does not exist: `provider_config_catalog` projects manifest → config; the lock records rendered-artifact provenance; drift is a closed `DriftObservation` enum with one action per state |
| H04 | duplicated normalization + identity scattering (362–378) | **reject** | one `ArtifactAdapterIdentity` propagated registry → render → lock and regression-tested; no rename/alias path exists for `ProviderId` at all |
| H05 | artifact layer is a hidden second lock (372–374) | **reject** | `plan_artifact_render` is pure; preview and apply share one plan and preview provably writes nothing; apply re-checks preconditions |
| H06 | seven mandatory contract tests are missing (442–452) | **reject** | 6/7 map one-to-one onto existing tests; the 7th (identity rename back-compat) has no subject in the code |
| H07 | P0 CLI backlog `status/validate/doctor/explain/trace` + dry-run (568–576) | **reject** | status/doctor/registry/lock exist per package, 41 `--dry-run` declarations, `artifact_dry_run` + `ArtifactActionKind.REPAIR` shipped; the `explain` half is carried separately as H08 |
| H08 | the CLI cannot explain which config layers produced the decision (532–542) | **accept → FP-1** | `ConfigProvenance` is computed per effective leaf and rendered by nobody |
| H09 | distinct exit codes per error class (544–554) | **reject** | error class is machine-readable in the payload (`PCFG_*`, `REGISTRY_*`, `HARNESS_*`, `DriftObservation`); widening the exit-code contract is a public compatibility change with no measured incident behind it |
| H10 | run-report is fail-open without quality flags → silent signal loss (659–662) | **accept → FP-2** | the returned payload has no completeness/skipped-line field at all; `analyst.trace` already owns the honest vocabulary |
| H11 | vendored `_usage.py` drifts from `core/usage.py` (671–673) | **reject** | `validate.sh` step [2/7] is a byte `cmp` gate that fails the build with the exact fix command |
| H12 | the hook layer holds operational ownership policy (696–705) | **accept → FP-3** | the `managed AND NOT user_owned` predicate is implemented three times (owner, reporter, blocker) with no parity gate; the third copy documents the duplication itself |
| H13 | cross-surface intent drift; need semantic core + generated variants + drift detection (767–912) | **reject** | already the implemented architecture: generated thin projections with `canonical`/`canonical_sha256`/`generator`, byte-identical across providers, `registry --check` green, P1.4 measured 0 collisions |
| H14 | hooks need an observation/advisory/enforcement taxonomy (686–694) | **reject** | per-hook policy is declared at each hook's own site and differs by construction; the missing single table is a docs gap, not a structural one |
| H15 | heuristic drift degrades the classifiers (663–665) | **unknown** | needs a labelled run corpus that does not exist; `core/pathology.py` states its own thresholds are uncalibrated |
| H16 | semantic duplication across agents/skills/docs/workflows (834–836) | **unknown** | the effective identity map covers publication units only; agent-pack roles, workflow scripts and doc sections are outside it |

**Totals: 3 accept · 11 reject · 2 unknown.**

The audit's own "top-5 critical actions" (2941–2949) map onto these rows: (1) provider truth
model as a canonical contract → H03 reject, already frozen in
`root/contracts/semantic-identity-ownership-v1.md` plus `configs/provider-capabilities.json`;
(2) centralize ownership/policy vocabulary → **H12 accept (FP-3)**; (3) invariant tests /
replay / golden gates → H06 reject for the provider domain, and the replay half exists for the
layer-2 harness (`artifacts/P3.9` `--replay`); (4) quality-aware telemetry with explicit
degraded modes → **H10 accept (FP-2)**; (5) agent/runtime surface with a semantic core and
drift checks → H13 reject (delivered), with the untested residue held honestly at H16
(`unknown`).

## Bounded future proposals

None of the three is executed by this plan. Each names one owner, one contract it must respect,
its tests and the user-visible outcome that makes it worth doing.

### FP-1 — render the already-computed provider-config provenance to the operator

- **Source:** H08 (audit 532–542).
- **Owner:** a future plan (new item). P4.2's read-only doctor may print a *subset* of this
  data inside its own frozen scope, but it does not own this proposal and must not grow a new
  public surface for it (D92).
- **Contract:** `root/contracts/semantic-identity-ownership-v1.md` (active owner / source /
  evidence vocabulary). Rendering only — `resolve_provider_config` semantics do not change.
- **Tests:** per-leaf rendering names layer kind, carrier, RFC6901 pointer and explicit-vs-default;
  the legacy-default path renders as *defaulted*, never as an explicit choice; a precedence case
  (operation ▸ project ▸ fleet-project ▸ fleet-defaults) names the winning layer.
- **Observable user outcome:** "why is this provider/capability active here" is answered by one
  read-only command instead of by reading `resolve_provider_config` by hand.
- **Rule of Three:** two committed occurrences (`findings/04-runtime-preflight.md`,
  `findings/P1.4-effective-runtime-proof.md` both reconstructed effective state manually).
  Deferred rather than done because a new public surface needs recorded
  consumers/alternatives/SemVer first (D23/D92).

### FP-2 — make run-report degradation observable

- **Source:** H10 (audit 659–662, 729–734).
- **Owner:** a future plan — the *same* producer-instrumentation debt D88 п. 6а already names
  (`contract_ref`/`finding_refs` unfilled by the P3.4/P3.9 harnesses). One owner for both: both
  are "the producer does not declare what it failed to produce".
- **Contract:** `root/contracts/unified-agent-trace-v1.md` § quality
  (`completeness`/`missing`/`degraded`). The hook payload adopts it **additively** as
  `SCHEMA = 3`; `SCHEMA = 2` readers keep working.
- **Tests:** a golden transcript with N malformed lines and M unknown event types asserts the
  reported counters equal N and M; a fixture without `_usage.py` asserts the usage slice is
  declared degraded rather than only set to `None`; `core/pathology.py::detect` must not report a
  clean run over a payload that declares itself partial.
- **Observable user outcome:** a report built from a partially unparsable transcript says so, so
  `maind analyze` and the pathology detectors stop reporting clean runs over missing telemetry.
- **Rule of Three:** three recorded occurrences of the same seam — F1 = 0.96 (declared fields
  unfilled), F10 = `unknown` (a channel that does not exist), and this hook (dropped lines never
  counted). Confirmed class, not a predicted one.

### FP-3 — one ownership predicate for managed/user-owned paths, with a parity gate

- **Source:** H12 (audit 696–705, 2933).
- **Owner:** a future plan (new item). The surface spans `packages/harness/lib/**` and two hook
  directories, so it cannot be a side effect of any item in this phase.
- **Contract:** `root/contracts/semantic-identity-ownership-v1.md` (ownership / managed /
  user-owned vocabulary). Lock formats (`skills-lock.json`, `.claude/agent-pack.lock.json`)
  are unchanged — this is one *reading* of them, not a new format.
- **Tests:** a parity test over one shared fixture lock asserting `agentpacks`,
  `_protected_sets` and `pack-guard._managed_files` return the same protected set (including the
  `user_owned` exclusion and the directory-prefix rule); a negative fixture (missing lock,
  malformed JSON, `user_owned` entry) asserting all three degrade identically; a build gate
  mirroring the existing `validate.sh` [2/7] `cmp` step so a hook-local copy cannot drift
  unnoticed.
- **Observable user outcome:** `pack-guard` can no longer block a file that `run-report` does not
  consider protected (or the reverse) — one consistent answer to "is this file mine or the
  pack's".
- **Rule of Three:** met on the tree — owner, reporter and blocker each implement the predicate,
  and the blocker's own docstring calls the duplication deliberate. The repo already has the fix
  pattern (`sync-usage.sh` + `cmp` gate) to reuse.

## What stays undecided, and why that is the honest answer

`H15` (heuristic drift) and `H16` (semantic duplication across agents/skills/docs/workflows) are
`unknown`. Both are decidable — but only by producing a measurement that does not exist on the
committed tree (a labelled run corpus for H15; an intent→artifact map covering non-publication
surfaces for H16). Recording them as "accept, probably true" would manufacture agreement;
recording them as "reject, speculative" would extend measured results past their declared scope.
Both carry their missing evidence by name in `hypothesis-verdicts.json` and belong in the P4.3
packet as named residue, not as findings.
