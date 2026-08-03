# Artifex threat model, operating envelope, and pre-mortem

## Verdict

Artifex may automate only a narrow local-repository control loop whose authority, inputs,
side-effect boundary, validation, recovery classes, and budget are frozen before dispatch. The
worker, repository text, MCP/memory observations, provider output, snapshot, and worker-reported
success are untrusted evidence inputs. None may grant authority or mark a slice accepted.

The prototype is unsafe to continue whenever it cannot prove one of a finite set of states from
durable evidence. In particular, unknown postimage, invalid journal chain, missing rollback
preimage, ambiguous process identity, ambiguous authority, provider-schema drift, or foreign
worktree ownership reaches `incident` or `owner_attention` before another write. Sandbox success,
model confidence, a valid signature on a widening mandate, and a worker statement that tests passed
are deliberately insufficient.

This is a plan-local threat freeze, not evidence that the future implementation satisfies it.
Executable proof belongs to the owner items named in `threat-cases-v1.json` and to the independent
P4/P5 runs.

## System and trust boundaries

```text
repository canons + frozen plan + narrowing-only mandate
                         |
                [B1 compiler boundary]
                         |
               immutable slice manifest
                         |
                [B2 scheduler/WAL]
                         |
        intent durable ----+---- owner queue
                         |
                [B3 provider adapter]
                         |
               untrusted fresh worker
                         |
                [B4 public side effect]
                         |
             observed repository/provider state
                         |
                [B5 validation/arbiter]
                         |
        accepted | rollback | OWNER | incident
                         |
                [B6 reporting boundary]
```

| Boundary | Trusted input | Untrusted input | Mandatory decision |
|:--|:--|:--|:--|
| B1 compiler | pinned repository root, plan/contracts and source hashes | repository prose, dynamic path text | exact paths, capabilities and authority compile or refuse |
| B2 scheduler/WAL | verified immutable run identity and valid chain prefix | snapshot, stale process state, replay request | one writer; append intent before public effect; chain failure is incident |
| B3 provider adapter | frozen provider-neutral envelope and explicit installed capability record | provider events, stderr, exit mapping and session claims | closed mapping or `provider_unavailable`; no guessed parity |
| B4 public side effect | verified intent, preimage, idempotency key and authority result | worker recommendation and confidence | perform one named effect only; permissions cannot widen authority |
| B5 validator/arbiter | frozen schema, scope, hashes and validation argv | worker output, “tests passed”, sandbox exit, postimage | independently prove acceptance or choose a closed refusal/recovery state |
| B6 reporter | verified terminal journal state and minimized evidence | raw transcripts, prompts, environment and private reasoning | typed redacted summaries only; no secret or raw prompt persistence |

The repository and host are trusted only as named, hashed objects at a boundary. A file becoming a
symlink, an input hash changing, another contributor modifying the worktree, or a second writer
acquiring the run turns the formerly trusted preimage into an observed mismatch.

## Protected assets

| Asset | Failure consequence | Protection invariant |
|:--|:--|:--|
| authority stack and owner gates | protected action runs unattended | mandate can only narrow; conflict/unknown is OWNER before intent |
| repository and foreign dirty work | data loss or misattributed commit | exact file ownership, pre/postimages, one writer, isolated worktree when required |
| journal and run identity | replay accepts a false history or repeats an effect | append-only hash chain, stable identities, reopen verification, snapshot never authoritative |
| rollback preimages | partial write cannot be recovered | backup existence and hash proven before risky effect; absent backup is incident |
| provider/session/process identity | duplicate/orphan work or wrong-process termination | durable exact identity and explicit stop authority |
| validation and acceptance | worker self-certifies a bad change | deterministic external validation bound to source/postimage hashes |
| token, cost, attempts and time budget | runaway spend or false economy | journal-derived counters; unknown is not zero; check before intent |
| credentials, prompts and private reasoning | secret disclosure in journal, Git or memory | allowlist minimization and redaction before durable append |
| provider-neutral contract | one provider silently becomes semantic SSOT | additive adapters, closed capability/failure taxonomy, unsupported stays explicit |
| reliability/economic verdict | biased pilot productizes an unsafe candidate | frozen case bank, matched inclusion and independent adjudication |

## Operating envelope

### Allowed v1 envelope

- One trusted local Git repository and one plan-local run directory on a filesystem that reports
  the durability operations used by the implementation.
- A frozen executable plan, exact repository/package instructions, immutable slice manifest,
  unsigned or signed narrowing-only mandate, provider record, budgets, acceptance commands and
  hashes available before dispatch.
- One sequential writer by default. At most two workers only for proven independent read-only
  slices or separate linked worktrees; integration remains serialized.
- Fresh provider process/context per bounded slice, with exact argv, timeout, byte caps and a
  provider-neutral return envelope.
- Local reversible repository changes inside declared files, or read-only provider/repository
  observations. Each public effect has a durable intent and a finite pre/postimage reconcile rule.
- Redacted typed evidence sufficient for replay, validation, budget and terminal reporting without
  raw transcripts, prompts, environment dumps or credentials.

### Outside the envelope

- Remote hosts, messenger/desktop UI, arbitrary services, production credentials, unattended
  destructive operations, credential rotation, public release/publish, or irreversible external
  actions.
- Ambient filesystem, network, provider, child-agent or Git authority; provider fallback not named
  by the frozen route; permission or sandbox widening after a refusal.
- Concurrent writes in one worktree, best-effort journal repair, guessing an unknown third state,
  reconstructing a missing backup, or continuing through plan/source/mandate drift.
- Provider-specific output as the shared semantic contract, raw chain-of-thought as evidence, LLM
  judgement as an acceptance override, or worker-written expected verdicts.
- Any GO claim from synthetic-only waves, unmatched model/scope/validation, omitted failures,
  missing denominators, or unknown token/cost/intervention fields treated as zero.

Crossing this boundary is not an automatic extension. It is an OWNER decision and, where it changes
public contract, dependency, package topology, security, or rollback semantics, a plan redesign.

## Adversary and error assumptions

- The worker is competent but fallible and may follow prompt injection, hallucinate success, exceed
  scope, conceal an error in prose, request a retry, or emit a malformed/oversized envelope.
- Repository text, MCP/memory output, provider events and stderr may be malicious, stale,
  contradictory, truncated, duplicated or schema-drifted. Their origin does not make them authority.
- A valid signature proves origin, not legality. A lower-precedence mandate can be authentic and
  still illegally widen files, tools, provider, model, budget, validation or action class.
- The supervisor, provider child or host may die between any two durable/public operations. Delivery
  may be at least once; process and session observations may be stale or ambiguous.
- The filesystem may expose symlinks, partial writes, missing backups, disk/fsync failures and
  changed inodes. Snapshot state may lag or disagree with the journal.
- Another trusted contributor may modify the shared worktree. Their delta remains foreign even when
  it is valid code and must not be stashed, reverted, overwritten or attributed to the slice.
- Provider quota, approval, authentication, timeout, usage fields and structured-output behavior may
  differ by installed version. Missing values remain unknown and cannot satisfy a floor.
- The candidate, scheduler and validator can share a systematic bug. Hence expected cases are data,
  validation is independent, and P4/P5 require fault injection and candidate-blind adjudication.

## Six-to-twelve-month pre-mortem: raw causes before clustering

Assume that after six to twelve months the supervisor was abandoned after corrupting work,
interrupting the owner too often, and costing more than manual execution. Before assigning themes,
the independent cause list is:

1. A required repository file instructed a worker to edit outside the slice, and its wording was
   treated as authority.
2. MCP or recalled memory content smuggled an instruction or credential request into a fresh worker.
3. A symlink or parent traversal made an apparently in-scope path target another repository or host
   file.
4. A signed mandate widened permissions, budget or files, and signature validity was mistaken for an
   owner grant.
5. Model confidence or a provider sandbox exit replaced deterministic authority and acceptance.
6. A worker's “tests passed” summary was accepted although the frozen command was not independently
   executed on the accepted postimage.
7. The process died after an external effect but before its observation; resume repeated the effect.
8. Duplicate delivery created two workers or counted one result and its usage twice.
9. An orphan process kept writing while resume started a replacement.
10. A truncated, reordered or manually altered journal was silently repaired from a stale snapshot.
11. A partial postimage had no verified backup, and reconstruction destroyed the only recoverable
    evidence.
12. Plan, mandate, validation or source drift produced a slice whose inputs never existed together.
13. Provider timeout, quota or approval denial was mapped to success, zero cost, or an undeclared
    fallback.
14. Provider schema drift dropped a severe state or inflated the coordinator context with raw output.
15. Missing usage/accounting was treated as zero and defeated the attempt, token or cost breaker.
16. A worker recursively spawned children or retries outside the durable budget.
17. A foreign dirty delta was committed as current work or lost during automatic cleanup.
18. Concurrent writers produced valid individual records in an invalid global order.
19. Auto-resolution of an out-of-scope merge conflict changed a public or security boundary.
20. Raw provider diagnostics persisted a credential, prompt or private reasoning into Git history.
21. The owner queue became noisy because routine evidence failures were misclassified as authority
    decisions, while real irreversible cases were delayed in the batch.
22. Pilots sampled only happy paths or synthetic faults, omitted failed attempts, and declared GO
    against an unmatched baseline.
23. Candidate and validator shared one implementation table, so a wrong expectation certified
    itself.
24. Recovery worked for process crashes but not disk-full/fsync/lock failures, which were never in
    the trial bank.

The order above is the recorded ideation order. Clusters below are derived afterward and must not be
used to erase an individual cause or its evidence owner.

## Cause clusters and control ownership

| Cluster | Raw causes | Primary bank cases | Detection and fail-closed rule | Later owners |
|:--|:--|:--|:--|:--|
| authority and untrusted input | 1–6, 21 | THR-001–THR-008 | exact provenance/scope/action-class gates; incomplete evidence stays `validating`, conflict/widening goes `owner_attention` | P1.2–P1.3, P4.4–P4.5 |
| durable boundary and replay | 7–12, 18, 24 | THR-009–THR-012, THR-016–THR-018, THR-023–THR-024 | verified intent/chain/preimage; unknown postimage, bad chain or absent backup is `incident` and never retried | P1.1, P4.1–P4.2 |
| provider and budget | 9, 13–16 | THR-012–THR-015, THR-019–THR-020 | closed exit/schema mapping and journal counters; unavailable/unknown is not success or zero | P1.4–P1.5, P4.2, P5.3–P5.4 |
| worktree and integration | 3, 17–19 | THR-003–THR-004, THR-021–THR-022, THR-024 | normalized path identity, foreign-delta snapshot and exact ownership; out-of-scope conflict is OWNER | P1.2, P4.3–P4.4 |
| privacy and evidence | 2, 14, 20 | THR-002, THR-020, THR-025 | allowlist-minimize before append; prohibited raw payload does not become durable evidence | P1.4–P1.5, P4.4–P4.5 |
| biased acceptance and economics | 5–6, 15, 22–23 | THR-007–THR-008, THR-019, THR-026 | independently recompute frozen validation, eligibility and denominators; missing/mismatched evidence makes the branch ineligible | P4.1, P5.1–P5.4 |

## Finite reconcile and refusal policy

For any durable intent lacking accepted terminal evidence, only these transitions are legal:

1. Exact approved postimage: re-run independent validation and accept only if every frozen gate
   passes.
2. Exact preimage/no effect: append a no-effect observation and retry only within the unchanged
   budget and idempotency identity.
3. Contract-recognized partial plus verified backup: roll back the whole slice, verify the preimage,
   then retry or escalate according to the frozen budget.
4. Any other postimage, missing/invalid backup, ambiguous process, invalid chain, or changed frozen
   input: `incident` or `owner_attention`; no retry and no further write.

The same policy applies to provider effects, Git integration and plan bookkeeping, not just file
writes. `dispatched`, provider exit zero, `worker_success`, sandbox success, and worker-reported test
success remain observations rather than acceptance states.

## Machine bank and independent validation

`artifacts/P0/threat-cases-v1.json` freezes stable `THR-001`…`THR-026` cases. Every case names its
boundary, protected assets, precondition, attempted action, expected fail-closed state, independent
detection, rollback/reconcile rule, durable evidence, mitigation and one P1/P4/P5 owner item.

`artifacts/P0/validate-threat-cases.py` does not compute expectations from a candidate rule table. It
checks the authored bank against a separate fixed schema and coverage vocabulary: every D22 class;
injection; path and symlink escape; journal tamper; orphan worker; budget evasion; provider-schema
drift; foreign dirty delta; and four explicit insufficient-evidence negatives. It rejects unknown
third-state outcomes other than `incident`, any accepting outcome, non-P1/P4/P5 owner, missing
evidence field, unstable/duplicate ID, or coverage gap.

The validator proves completeness of the freeze's shape, not runtime safety. P4.1/P4.2/P4.4 must
turn the bank into crash, tamper, authority, privacy and recovery execution; P5 must preserve all
failures and unknown quantities in the candidate-blind terminal verdict.

## Provenance and non-claims

The system boundary and failure classes synthesize repository canons, D10–D13/D18/D22, the P0.1–P0.3
terminal artifacts, `research/01-target-architecture.md`, `research/02-authority-and-conflict-policy.md`,
`research/03-durable-state-and-recovery.md`, and the donor reliability-acceptance contract. RAG:— for
the internal threat decisions. The already recorded reference-product observation about at-least-once
delivery remains RAG:✅ in `findings/02-reference-products-2026-08-03.md`; this item performs no new
external retrieval and makes no new provider/product claim.

No package implementation, provider permission, credential, live penetration test, threshold,
dependency, package home, or acceptance verdict is created here.
