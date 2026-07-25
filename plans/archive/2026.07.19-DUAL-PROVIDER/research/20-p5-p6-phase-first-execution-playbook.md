# P5–P6 phase-first execution playbook

**Status:** design-only operational aid; it does not change item scope, frozen
contracts, routing, owner gates, or the roadmap.  It is a recovery control for
execution after D80/D81, not a second implementation plan.

## Purpose and governing anchors

This playbook turns D80/D81 into an executable operating rhythm for the two
largest remaining phases.  It prevents the P3 failure mode: treating an
independent conformance item as the first time the owning implementation seam
is exercised, then repairing one symptom per re-open.

- **D80**: use targeted regression/static checks while the same phase is being
  built; run full package validation, docs/release assessment, phase close and
  independent audit once at the terminal phase boundary (`plan.md` D80;
  `findings/P3-throughput-retrospective-2026-07-21.md` §Corrective controls).
- **D81**: after the first owning-phase blocker, stop the dependent item,
  identify all *confirmed same-seam* causes in one bounded scan, and report the
  dependency as `🔴 Blocked` rather than `🟡 In progress` (`plan.md` D81).
- **Plan protocol** still governs item status, journal, explicit-path commits,
  handoff, and escalation.  D80 reduces duplicated phase-wide validation; it
  does not waive an item’s contract, fail-closed acceptance, or a frozen/public
  contract gate.
- All tests and render/apply probes use disposable temporary roots.  P5/P6
  retain their explicit no-live-apply, no-FOREMAN and no-fleet boundaries
  (`phases/P5.md` Phase Context; `phases/P6.md` Phase Context).

### Non-negotiable sequencing

There is no safe code parallelism inside either chain:

```text
P5.1 → P5.2 → P5.3 → P5.4 → P5.5 → P5.6 → P5.7 → P5 terminal gate
P6.1 → P6.2 → P6.3 → P6.4 → P6.5 → NEW SESSION → P6.6 → P6 terminal gate
```

P5.2–P5.4 mutate the same catalog/render/managed-boundary seam; P5.6→P5.7 is
a frozen instruction contract followed by its renderer.  P6.2 consumes the
P6.1 provider result, P6.4 consumes the P6.3 schema, and P6.5→P6.6 is an
intentional cold-start boundary.  These dependencies are explicit in
`research/09-p5-harness-provider-surfaces-design.md` §Item sequence,
`research/10-p6-maind-analytics-bootstrap-design.md` §Item sequence and
session boundary, and `roadmap.md` §Карта исполнения.

Do not use a development workflow merely to run these dependent items in
parallel.  The roadmap’s `solo` decision remains correct.  A fresh execution
subagent per item is useful for context isolation; it is not evidence that
multiple writers may edit a shared seam concurrently.

## Universal execution cadence

### 1. One bounded phase-entry pack

Immediately after the predecessor phase is terminal and before the first item:

1. Read the phase, current frozen input contracts, predecessor conformance
   report, package guide(s), and the current package test inventory.
2. Record a protected-path snapshot and the exact temporary-root convention.
3. Build a one-page **expected-inventory ledger** from contracts and source
   catalogs, never from render output.  The ledger lists each provider,
   semantic ID, required capability, ownership state and expected diagnostic.
4. Identify the smallest targeted test command(s) for each upcoming writer
   seam.  This is a test map, not a test run and not a new artifact contract.

The phase-entry pack may use at most two parallel, read-only helpers:

| Helper | Output | Prohibited work |
|:--|:--|:--|
| Inventory scout | exact source/catalog IDs, compatibility fixtures, protected paths | code, fixtures, expected-output regeneration |
| Failure-mode scout | existing negative cases and missing same-seam probes | design changes, package edits, full audit verdict |

The item executor reconciles those findings once before writing.  This creates
one early shared picture without creating competing designs or a standing
review bureaucracy.

### 2. Per-item fast path

For an executable item, run only:

1. contract/entry-gate check and scope check;
2. contract-authored focused tests for the changed seam;
3. static/import/compile check for changed Python or deterministic renderer
   check for changed artifacts;
4. temporary-root no-write/ownership assertion where the item has a writer;
5. explicit-path item commit and plan bookkeeping commit.

Do **not** run every package `validate.sh`, generated-doc check, release check,
or an independent audit after every item.  Those are deferred to the terminal
phase gate below.  The one exception is a real item deliverable that another
item consumes: its focused conformance must run before the consumer starts,
but it must not be mislabeled as terminal phase validation.

### 3. First blocker circuit breaker

If a focused probe finds a defect in an earlier item’s seam:

1. Mark the dependent item `🔴 Blocked` and name the owning item/seam in
   handoff/status.
2. Run **one** bounded read-only scan: same writer/lock/renderer/result layer,
   only already-contractual invariants, only reproducible temporary-root cases.
3. Bundle every confirmed cause into one minimal repair.  Do not speculate about
   adjacent packages or change frozen contract semantics.
4. Run targeted regressions for the bundle once, resume the blocked item once.
5. A second blocker in a different seam is a design/escalation question, not a
   license for an unbounded repair bundle.

This is the direct application of D80/D81; it forbids both per-symptom
re-open loops and concealment of a blocked successor.

### 4. Terminal phase gate (once)

After the final implementation/conformance item is green, run exactly one
phase-wide pass on the final anchored tree:

1. all package validators named by the phase;
2. full independent expected-inventory/conformance report;
3. generated docs/release/CHANGELOG assessment where the phase creates them;
4. protected-path delta and plan-lint comparison;
5. phase close; then a fresh independent Sol/xhigh audit.

If that audit finds an implementation defect, return to the *owning* item with
the circuit breaker above.  Do not open a chain of audit-only rechecks.  A
passing audit is the phase’s only release-quality verdict.

## P5 execution lanes

### P5-A — contract and security boundary: P5.1

**Dependency:** terminal P4.5 and six frozen predecessor contracts
(`phases/P5.md` Entry gate; P5.1 Inputs).

**Route:** Sol/high manual design.  This is not implementation work.  It
freezes `provider-harness-contract` only after its required inventory,
alternatives and explicit Approval Owner D# (`phases/P5.md` P5.1
Implementation Rules; `roadmap.md` P5.1).

**Early probes before approval:** exact one-to-one surface mapping; all three
security axes remain independent; default/project/fleet inheritance cannot
select full access; missing capability/trust/mapping/secret is diagnostic
before write.  These are contract examples and static checks, not harness
package validation.

**Stop boundary:** an unresolved security semantic, contract expansion, or
full-access default is an owner-level fork.  D79 authorizes routine
contract-preserving decisions, not an unapproved frozen security contract.

### P5-B — shared harness implementation seam: P5.2 → P5.4

**Bundle boundary:** these three sequential commits form one implementation
lane over profiles/render plans/managed ownership.  They are not a single
item: each produces the API and focused evidence required by the next.

| Item | Required focused probe before successor | Defer to P5 terminal gate |
|:--|:--|:--|
| P5.2 profiles/security | both provider plans; explicit trust; rejection of implicit full access/unknown mapping; Claude golden and managed-only repair in temp root | package-wide validate, release/docs sweep |
| P5.3 hooks/context | intent × provider support/activation/diagnostic; untrusted/unsupported/missing matcher; kill switch and ownership; first-turn budget verdict for each new always-on carrier | package-wide validate and complete inventory report |
| P5.4 MCP/agents/packs | semantic ID exact-set, cache-contained bundle, secret-reference-only output, user-owned conflict and managed drift repair | package-wide validate, generated operator docs, full harness report |

**Cross-seam probe after P5.4 (required before P5.5):** on one disposable
project, render both providers from the same semantic profile and assert:

- every required surface has one provider-tagged outcome;
- a missing capability/trust/secret or one provider conflict is visible and
  cannot be aggregated as success;
- no secret literal appears in output/lock/report;
- `check → apply → check` is empty and repair changes managed bytes only;
- current Claude compatibility fixtures remain independent expected inputs.

This is deliberately narrower than the P5.5 inventory/doctor deliverable.  It
finds an integration break at the handoff between writers, before the
independent conformance item is asked to discover basic wiring defects.

### P5-C — independent harness conformance: P5.5

**Route:** Terra/medium.  P5.5 authors an independent expected reader from the
frozen contract and source inventory; it never imports expected data from
render output (`phases/P5.md` P5.5 Implementation Rules).

Run its semantic report, two-run determinism and its positive/negative
security matrix now because P5.6 consumes the conformance handoff.  Treat
that report as a *component handoff*, not a declaration that P5 as a whole is
closed: P5.6/P5.7 still add the instruction contract and renderer.

### P5-D — instruction contract and projection: P5.6 → P5.7

P5.6 is a second, intentionally separate public-contract gate.  Route it to
Sol/xhigh and obtain the listed approval before P5.7 writes harness code
(`phases/P5.md` P5.6; `roadmap.md` P5.6).  It is not safe to merge it into P5.1:
the instruction source/marker/provenance boundary depends on P5.5 evidence.

P5.7 then uses Terra/high and must perform only focused instruction tests:

- exact root plus five-package scope set;
- common semantic IDs equal in the independent Claude/Codex projections;
- allowed extension delta only; no extension overrides a common rule;
- corrupt/missing/newer lock, stale source, local managed drift and unmanaged
  target all fail before write;
- repair preserves bytes outside matching markers and all work is in a temp
  root.

### P5 terminal gate and review checkpoint

Run once after P5.7: the full harness validator, P5.5 independent inventory
report against the final tree, P5.7 instruction parity report, generated
operator references, protected snapshot and plan-lint.  Then close P5 and run
a fresh Sol/xhigh independent audit.

**PR checkpoint:** after that GREEN audit, prepare one review PR checkpoint
whose base is the already-reviewed P1–P3 delivery and whose head contains the
complete terminal P4–P5 commits.  Do not open a PR from a partial P5 lane or
from a failed audit.  The checkpoint description must group commits by
P4/P5 item, state temp-only/no-live-apply evidence, list frozen contract D#s,
and include the terminal audit link.  This playbook does not itself create a
PR or alter the plan’s existing PR authority.

## P6 execution lanes

### P6-A — mAInd provider operation seam: P6.1 → P6.2

P6.1 uses Terra/high to build the single provider loop and provider-tagged
result.  Before P6.2, its focused temporary-root probe must show both provider
rows, exact semantic server inventory, no write on disabled/unknown/missing
projection, user-owned preservation, and a non-green aggregate for a one-row
failure (`phases/P6.md` P6.1 Implementation Rules/Validation).

P6.2 consumes that result rather than resolving the provider again.  Its
focused probe combines one P5 instruction render with `onboard/sync/health`
intents and proves: required-provider partial failure remains non-green absent
the pre-existing explicit partial flag; safe autonomy cannot imply full
access; root plus five package instruction IDs are exact; repair remains
managed-block-only.  This is the earliest cross-package/fail-closed probe for
P6, and it is still temp-only.

### P6-B — analytics contract and multi-package implementation: P6.3 → P6.4

P6.3 is Sol/xhigh manual design with an owner approval: freeze the neutral
schema only after P6.2, ≥3 alternatives, P5 fixture evidence and privacy/
migration review (`phases/P6.md` P6.3 Implementation Rules).  It must reject
unverified provider raw shapes rather than invent a reader schema.

P6.4 is Terra/high after the existing shared-core/analyst contribution gate.
The writer boundary is one `core` primitive plus analyst-owned readers/store;
maind and harness remain consumers/adapters.  The focused integration matrix
before P6.5 must prove:

- same semantic fixture normalizes deterministically for Claude and Codex,
  while provider provenance stays distinct;
- unknown/corrupt/additive raw shape, missing provenance, prompt/secret leak,
  path traversal and mixed provider/session collision refuse safely;
- migration is dry-run/check/apply on a temp root, copy+verify/idempotent, and
  leaves legacy bytes in place;
- no new normalized write enters `.claude`, no raw transcript is stored, and
  human promotion/audit semantics remain append-only.

This is the only appropriate multi-package integration test before P6.5.  Do
not repeatedly run all package validators during P6.4; preserve them for the
phase-wide conformance/checkpoint gate.

### P6-C — terminal conformance/checkpoint: P6.5

P6.5 is the single full terminal pre-restart gate (Terra/medium).  It is
evidence-only: a failure reopens P5.6/P5.7/P6.1–P6.4 rather than being patched
inside P6.5 (`phases/P6.md` P6.5 Code Guidance).

Run once on the final anchored tree:

1. full isolated two-provider deploy/sync/instruction/analytics matrix;
2. all four package validators, current Claude compatibility and protected
   delta checks;
3. exactly one compact mAInd checkpoint write in `project:swissknifeman`;
4. read-only memory isolation, graph, Serena and fixed cited Perplexity probe;
5. disk checkpoint containing plan/item commits, contract/config/catalog/
   render hashes, provider IDs, timestamps and exact P6.6 reads.

The expected inventory must derive from frozen contracts plus semantic source
catalogs, never P6 output.  A skipped provider/tool, tool failure, hash
mismatch or non-zero protected delta blocks P6.5; it is not an xfail.

### P6-D — mandatory cold boundary: P6.6

P6.6 is Terra/medium in a genuinely new session.  It is not a continuation,
a subagent handoff, or an opportunity to repair code.  The new session must:

1. read the committed disk checkpoint first;
2. then recall the named mAInd checkpoint under `project:swissknifeman`;
3. compare plan/commit/contract/instruction source+render hashes;
4. run only the listed public read-only provider/analytics/graph/Serena/
   Perplexity probes and update the same compact checkpoint with the verdict.

Any absence or mismatch is RED/blocked and returns to the owning item with a
D#; remembered chat context, a different web query, or direct filesystem
guessing may not substitute for the checkpoint.  This follows `phases/P6.md`
P6.6 Implementation Rules and `research/10-p6-maind-analytics-bootstrap-design.md`
§Item sequence and session boundary.

### P6 terminal gate and review checkpoint

Once P6.6 is GREEN, perform phase close and one fresh Sol/xhigh independent
audit.  The audit reads disk evidence and checkpoint records from scratch; it
does not rerun P6.5 as a second implementation test.  Its review checklist is
the exact P6.5/P6.6 evidence set plus contract boundaries and protected delta.

**PR checkpoint:** only after this audit, prepare the P6 review PR checkpoint
on top of the P4–P5 checkpoint (or update that review series if it has not
merged).  It must separate: (a) temp-only deployment/provision code,
(b) analytics schema/readers/migration, and (c) read-only checkpoint evidence.
It must state explicitly that self-host apply/release is still P7 and that no
FOREMAN/fleet/live bootstrap mutation is included.

## Routing and context economy

Use the existing `roadmap.md` routing exactly:

| Work | Model/effort | Why |
|:--|:--|:--|
| P5.1, P6.3 contract design | Sol/high or Sol/xhigh as routed | frozen/public/security or privacy schema |
| P5.2–P5.4, P5.7, P6.1–P6.2, P6.4 | Terra/high | bounded implementation against frozen inputs |
| P5.5, P6.5, P6.6 | Terra/medium | independent/evidence conformance; P6.6 in new session |
| terminal audits | fresh Sol/xhigh | independent adversarial phase verdict |

Fresh subagents receive a compact committed launch block: phase/item, immutable
inputs, exact files, test tier, protected boundary, and predecessor commit.
They do not receive a growing transcript.  Root orchestration retains only
phase state, D80/D81 circuit-breaker state and the next launch block.

## Completion criteria for this playbook

- P5/P6 implementation items run once in dependency order with targeted seam
  checks, not repeated package-wide validation.
- The first blocker creates one truthful blocked status and one bounded
  same-seam remediation scan.
- P5 gets one terminal full validation/close/audit after P5.7; P6 gets one
  terminal integrated checkpoint gate plus the distinct cold-session proof and
  audit.
- No proposed optimization weakens a frozen contract, an explicit owner gate,
  fail-closed behavior, temp-only boundary, or the P6 cold-start boundary.

## Verification basis

Repo-grounded only: `plan.md` D79–D81 and Contracts; `roadmap.md` routing and
solo rationale; `phases/P5.md` P5.1–P5.7; `phases/P6.md` P6.1–P6.6;
`findings/P3-throughput-retrospective-2026-07-21.md`;
`research/09-p5-harness-provider-surfaces-design.md`;
`research/10-p6-maind-analytics-bootstrap-design.md`; and
`research/13-instruction-contract-remediation.md`.  No external capability
claim is introduced, and no package, contract, roadmap, handoff, live target,
FOREMAN or fleet file was changed.
