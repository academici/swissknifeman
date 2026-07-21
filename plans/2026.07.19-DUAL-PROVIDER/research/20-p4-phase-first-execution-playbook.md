# P4 phase-first execution playbook

**Purpose:** a bounded execution playbook for P4 after terminal P3.  It changes no
product contract, item scope, routing row, or authority boundary.  Its purpose is to
apply D80/D81 before code starts, so P4 discovers command/publication/routing seam
defects at their owning item rather than during P4.5 parity.

**Plan anchors:** `phases/P4.md` §Phase Context, P4.1–P4.5; `plan.md` D24–D27,
D79–D81 and §3 Routing; `roadmap.md` rows P4.1–P4.5 and gates G03/G04;
`root/contracts/provider-{capability,config,artifact,migration-gates,skill-publication}-contract.md`;
`research/08-p4-task-command-routing-design.md`; and
`findings/P3-throughput-retrospective-2026-07-21.md`.

## 1. Non-negotiable entry and ownership boundary

P4 begins only after G03 has committed evidence: terminal P3.5, its conformance
artifact, a literal independent P3 audit `GREEN`, and a prepared P1–P3 review PR.
The executor verifies those facts from committed files; an in-progress handoff,
untracked `.agents/skills`, or a passing narrow P3 test is not a substitute.  This is
the P4 entry gate in `phases/P4.md` and G03 in
`root/contracts/provider-migration-gates.md`.

Before P4.1, record one read-only baseline in the P4 work report (not a new product
artifact):

1. enumerate canonical `packages/task/commands/*.md`, their IDs, source hashes and
   plugin registrations with an independent reader;
2. snapshot protected paths named by P4.2/P4.5: root `.agents/skills`, root
   `.claude-plugin` outside declared targets, `plans/2026.07.18-FOREMAN/**`,
   `plans/ACTIVE.md`, and fleet sentinels;
3. verify that P3's committed API can render/check a *task adapter descriptor* in a
   temporary root, including cache containment and a qualified failure before any
   write; and
4. verify the five frozen input-contract versions and the exact provider IDs/capability
   vocabulary which P4.1 is allowed to consume.

This preflight is deliberately small and read-only.  It catches the P3 pattern
"downstream parity is the first real integration check" without prematurely running a
phase-wide validation suite.  A missing P3 descriptor capability is a G03/P3 defect,
not a reason for P4.2 to copy or bypass the publication pipeline.

P4.1 is the sole new frozen-contract decision.  It retains its public-contract
approval boundary.  Once its exact v1.0.0 contract is frozen, D79 permits evidence-
backed, contract-preserving implementation decisions without new owner pauses.
Accordingly P4.2/P4.4 contribution records are prepared at the beginning of their
items and immediately implemented when they prove Rule of Three, minimal API,
dependency direction and SemVer compatibility.  Escalate only if they require a new
contract meaning, authority expansion, or a genuine owner fork; do not manufacture a
second approval pause for a prescribed implementation.

## 2. Dependency map and bundle boundaries

```text
G03 / terminal P3 + frozen P0–P3 contracts + P1–P3 review PR
                         |
                       P4.1  freeze command/routing contract
                         |
                       P4.2  catalog + Codex adapter + P3 descriptor probe
                         |
                       P4.3  named Claude projection + pre-change golden
                         |
                       P4.4  neutral plan-routing canon and both invocations
                         |
                       P4.5  independent parity + docs + one phase validation
                         |
              close P4 -> independent P4 audit -> G04 -> P5
```

There is no parallel code branch inside P4: every item consumes a preceding artifact
and all touch the command/catalog/routing seam (`phases/P4.md` DoR and D27).  The only
parallelism allowed is read-only and bounded: one independent inventory/protected-path
snapshot may run while the P4.1 contract candidate is being authored, and an independent
P4 audit starts only after phase closure.  It never writes package or plan carriers.

The correct repair unit is one confirmed *same-item/same-seam* bundle.  On the first
owning-item blocker, mark the dependent item `🔴 Blocked`, run the targeted invariant
matrix below, and repair all confirmed causes in one minimal change.  Run only the
affected tests, then resume.  Do not reopen/validate once per symptom.  This is D80/D81,
not a weakening of a fail-closed condition.

## 3. Early invariant probes by item

| Before or during item | Probe that must pass before downstream work | Owning result if it fails |
|:--|:--|:--|
| P4.1 | Every current command maps exactly once to a stable semantic ID; semantic records contain no provider model name, UI prefix, or provider path; each required provider mapping has evidence, both ordered axes and a diagnostic for unknown/ambiguous/undershoot. | Contract candidate remains unsealed; resolve the contract, never add P4.2-local metadata. |
| P4.2 | Canonical command reader reports `missing=extra=duplicates=∅`; source hash changes invalidate the adapter; a representative intent and plan command render through P3 into an isolated cache and are readable without a checkout; unsupported/missing mapping refuses before a write. | P4.2 bundle in catalog/render/P3 descriptor seam; no hand-written adapter body or copytree workaround. |
| P4.3 | Capture the committed Claude command files and plugin registration *before* P4.3 wiring; compare all IDs, frontmatter and bytes after a two-run render/check. | P4.3 bundle in Claude projection/golden seam; fixtures are evidence and are never updated from actual output. |
| P4.4 | For every plan command and every Next form, exercise semantic ID -> provider invocation -> cold-start payload with exact, overshoot, undershoot, missing and ambiguous mapping cases; assert six statuses, 16 fields, journal and commit topology unchanged. | P4.4 bundle around the single routing-vocabulary/invocation-renderer hotspot; no blind model-name replacement or local lint shim. |
| P4.5 | Independent canonical reader, not either renderer, reaches every command and each provider outcome; protected-path before/after snapshot and two ordered reports are byte-identical. | Return the defect to P4.1–P4.4 by its owning seam; P4.5 does not soften a fixture, skip a case, or regenerate expected output. |

The P4.2 preflight uses P2's observation/action discipline: `managed-drift`,
`provenance-invalid`, ownership conflict, missing capability and uncontained output are
refusals/no-write states, not warnings that the next renderer may repair implicitly
(`artifacts/P2-provider-artifact-conformance.md` C3, C5–C8).  The P3 publication
contract additionally forbids a provider-manifest-to-provider-manifest conversion and
requires independent projections; P4 must keep that boundary.

## 4. Test tiers and validation cadence

| Tier | When | Commands/evidence class | What is deliberately not repeated |
|:--|:--|:--|:--|
| E — entry | once before P4.1 | G03/contract/version/PR checks; independent command inventory; temporary P3 task-descriptor probe; protected snapshot | package-wide validators, registry regeneration, audit |
| T — targeted | once per implementation item and once per same-seam repair bundle | P4.1 normative contract scan; P4.2 catalog/Codex adapter/temp-cache tests; P4.3 Claude golden/two-run tests; P4.4 focused routing, linter fixture and RU→EN drift tests | full `packages/task`/`packages/skiller` validation and release/docs sweep after each item |
| I — integration | at the end of P4.4, before P4.5 authors its independent report | all early invariant probes together, both projections against the same frozen catalog, representative legacy-plan lint delta | independent P4.5 parity close/audit |
| F — phase terminal | P4.5 only | two independent ordered P4.5 parity runs; `bash packages/task/scripts/validate.sh`; `bash packages/skiller/scripts/validate.sh`; required generated docs/registry checks; plan-lint; protected snapshot; docs/release assessment | no second full validation merely because an earlier targeted check was green |
| A — independent | after P4 close, fresh Sol/xhigh context | adversarial P4 audit and G04 verdict | implementation/review by the same agent context |

T and I are acceptance gates, not informal smoke tests.  A red targeted test is fixed
inside the active item/bundle before its code commit.  F and A happen exactly once at
the terminal phase boundary, matching D80.  This preserves the P4 item validations
while avoiding the P3 failure mode of repeatedly running package-wide checks without
new phase-level evidence.

## 5. Execution and context routing

The root orchestrator keeps only the phase ledger, gates and protected-path status.
Each item gets a fresh sequential subagent grounded from committed plan/handoff and
this playbook; no background agent edits P4 code concurrently.

| Step | Route from `plan.md` §3 / `roadmap.md` | Fresh-context rule |
|:--|:--|:--|
| P4.1 | `gpt-5.6-sol/xhigh`, manual, full | New session; contract candidate, review and freeze only. |
| P4.2 | `gpt-5.6-terra/high`, manual, full | Fresh subagent after P4.1 commit; contribution record then prescribed code. |
| P4.3 | `gpt-5.6-terra/medium`, plan-exec, full | Fresh subagent; no design authority or golden rewrite. |
| P4.4 | `gpt-5.6-sol/high`, manual, full | Fresh subagent; contribution record then one routing/invocation coupling batch. |
| P4.5 | `gpt-5.6-terra/medium`, plan-exec, full | Fresh subagent; independent reader/report; no implementation changes except an evidence-backed owning repair route. |
| close/audit | close mechanically, then `gpt-5.6-sol/xhigh` audit | Each is a new session; audit has no executor chat context. |

The P4 launch is a new session because P3 audit/PR is a phase boundary, not because a
manual item demands a restart.  Cold-start reads are: `AGENTS.md`, `CLAUDE.md`,
`packages/task/CLAUDE.md`, `packages/task/commands/plan-exec.md`, `plan.md`,
`roadmap.md`, `handoff.md`, `phases/P4.md`, this playbook, P4.1 Required Reads, and
the committed G03/P3 audit evidence.  The actual current model/effort, approval policy,
sandbox and worktree root are confirmed by the normal AGENTS preflight; they are not
inferred from a launch command.

## 6. Close, audit and PR readiness

Each item keeps the existing two-commit close topology and explicit-path staging.  The
phase deliberately defers only *phase-wide* work, never commits or bookkeeping.  At P4.5
terminal validation, require all of the following before P4 close:

- frozen P4.1 contract and accepted P4.2/P4.4 contribution records match the committed
  public surface;
- the independent P4.5 report has no missing, extra or duplicate semantic command or
  provider projection; every routing/diagnostic/Next form has positive and negative
  coverage;
- Claude compatibility is byte/literal green, Codex adapters are cache-contained, and
  both projections are deterministic/no-write on the second run;
- package validation, generated docs/registry checks, plan-lint and protected-path delta
  are green; any existing unrelated warning is named with its baseline, never called green;
- `docs-maintenance` is assessed once at this phase boundary: generated
  `packages/task/docs/reference/provider-commands.md` is the operator documentation
  deliverable, so no duplicate manual documentation sweep is added; and
- phase close, fresh independent audit `GREEN`, and G04 pass occur before P5.1.

Open or update the P4 PR only after the P4 audit evidence is committed.  Its description
links the P4.1 contract/approval, P4.2 and P4.4 contribution records, P4.5 conformance,
the audit verdict, the exact package validators and the protected-path no-write result.
It does not bundle P5 work, live installation, FOREMAN or fleet changes.

## 7. Stop rules

Stop and disclose immediately when any condition changes a frozen contract, requires a
new public semantic command ID, cannot prove P3 publication containment, would alter a
protected path, or exposes a routing/linter compatibility change outside P4.4's declared
compatibility path.  Record the actual blocked item and the owning seam; after the first
blocker, collect the complete same-seam matrix before proposing one remediation.  That is
the D81 schedule-control point, not a request to repeat P3's per-symptom reopen loop.

**Verification:** repo-grounded only.  No external provider/API claim is introduced.
