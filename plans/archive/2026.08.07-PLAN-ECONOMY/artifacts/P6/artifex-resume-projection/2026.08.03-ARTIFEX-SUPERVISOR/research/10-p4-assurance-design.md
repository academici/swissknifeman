# P4 assurance design: recovery, write isolation, security, and owner telemetry

## Sources and execution gate

This synthesis uses `findings/08-p4-recovery-security-recon-2026-08-03.md`,
`findings/06-p2-runtime-recon-2026-08-03.md`,
`findings/07-p3-provider-runtime-recon-2026-08-03.md`,
`research/01-target-architecture.md`, `research/02-authority-and-conflict-policy.md`,
`research/03-durable-state-and-recovery.md`, `research/08-p2-prototype-design.md`, and
`research/09-p3-provider-adapter-design.md`. P4 execution is forbidden until P0–P3 are terminal,
their validators are green, and P3's adapter manifest still binds the installed provider versions.
Planned inputs are preconditions, not evidence. RAG:— (repo-grounded plan state).

## Producer chain and independent adjudication

| Item | Candidate ownership | Independent evidence | Consumed by |
|:--|:--|:--|:--|
| P4.1 | deterministic fault IDs, cut-point controller and child-process crash harness | frozen fault matrix/cases + external validator | P4.2–P4.5 |
| P4.2 | fixes only in existing store/scheduler/worker/CLI recovery owners | recovery results + validator proving no unknown rerun | P4.3–P4.5 |
| P4.3 | linked-worktree manager and serialized integration lane | temp-repo worktree cases/results + validator | P4.4–P5 |
| P4.4 | one shared candidate security gate used by compiler/worker/report | adversarial privacy/authority evidence + Task bundle-lint cross-check | P4.5–P5 |
| P4.5 | journal-derived attention queue and terminal packet | aggregate assurance manifest/validator | P5–P6 |

The candidate never authors its own expected verdicts. JSON case banks are written before or
independently of the production fix; validators recompute exact case identity, source/contract hashes,
terminal journal state and forbidden-content classes. An exit code, row count, passing snapshot or
candidate-emitted `green` field is never sufficient.

P4 runs sequentially. P4.2 consumes P4.1's injection seam, P4.3 consumes the proven reconcile
semantics, P4.4 attacks the resulting candidate and P4.5 aggregates all prior evidence. There are not
three independent items and there is no unattended external chain, so the plan-protocol orchestration
criterion does not fire. RAG:— (repo-grounded dependency graph).

## Fault model and stop points

P4.1 freezes one exact row per declared P0/P1 transition and observable cut point:

- before and after each durable append/reopen verification;
- before and after provider/public Git/validation boundaries;
- provider process death before terminal record, after result and during TERM→KILL;
- duplicate dispatch/event/result, torn/reordered/hash-invalid journal and stale/missing snapshot;
- source/plan/mandate/adapter drift, lock contention and disk/write/fsync failures;
- exact preimage, exact approved postimage, recognized partial and third-state observations;
- worktree conflict/foreign delta/ownership mismatch and security/redaction/queue faults.

The injected crash is a separate child process terminated at a named deterministic seam. Parent tests
reopen files/process state from disk; a mocked exception or in-memory object is not crash evidence.
The matrix carries setup, trigger, expected last durable event, permitted next action, expected refusal,
postimage class, write delta and evidence class. Missing/extra/duplicate/unreachable rows fail the
validator so a reject-all implementation cannot pass by never crossing a seam.

## Reconcile and idempotency proof

P4.2 reuses the P2 state machine. On restart it first verifies run identity and journal, then observes
the declared boundary exactly once without invoking it:

- exact approved postimage → rerun deterministic validation and append acceptance;
- exact preimage/no effect → append no-effect and allow a new attempt only within the frozen budget;
- recognized partial → whole-slice rollback, verify exact preimage, then retry or OWNER;
- third state, unverified orphan, missing backup or drift → incident/OWNER, no mutation.

Each fake boundary has an external counter/canary so the validator proves an unresolved intent was not
silently re-dispatched. Idempotency keys reject duplicate dispatch/result/acceptance across fresh
processes. Faults are injected after every durable and public boundary, not merely at function entries.
Any missing frozen transition stops for a D# rather than teaching the test harness a new expected state.

## Linked-worktree write lane

A write-capable slice executes only in a candidate-owned detached linked worktree created at the exact
pinned base. Inventory is parsed from `git worktree list --porcelain -z`; the worktree is locked with
run/slice/attempt identity and no `--force`/broad prune is legal. Before dispatch the supervisor proves
the main worktree/ref and all declared paths match the frozen preimage.

After the worker exits, the candidate verifies the complete tracked/untracked/submodule/symlink delta,
rejects paths outside `Files`, runs frozen validation there and creates one attempt commit. Integration
uses one exclusive lane and `git cherry-pick <attempt-commit>` only when the controlled target is clean
and still at the pinned base. A conflict invokes the ordinary abort path and must reproduce the exact
preimage; a crash is reconciled by the same P4.2 postimage classifier. No automatic conflict resolution,
force removal, branch takeover or integration into the owner's current dirty tree is allowed. Tests use
fresh temporary repositories only. RAG:✅ official worktree sharing/CLI semantics in
`findings/08-p4-recovery-security-recon-2026-08-03.md`; policy is internal.

Linked worktrees isolate working files and indexes, not the shared Git repository, hooks, config,
credentials, process tree or network. P4.3 therefore proves write ownership and serialized integration,
not a sandbox. Provider sandbox/permission restrictions remain P3/P4.4 owners.

## Security and evidence boundary

P4.4 consolidates candidate-side allowlist/path/environment/content checks into one shared module used by
compiler, worker and reporting. It does not invent provider flags. Adversarial cases cover path traversal,
symlink/hardlink replacement, forbidden untracked/submodule changes, permission/child/tool widening,
prompt-injection-shaped worker fields, over-cap streams, secret-like canaries, raw transcript/thinking/tool
payload keys, environment-value leakage, malformed Unicode/JSON and candidate evidence that falsely
declares itself minimized.

Only synthetic canaries are used; no real credential/config dump is captured. Evidence stores class,
stable identity, hash, count and refusal reason, never the triggering bytes. The independent validator
calls the public Task `bundle_lint` over actual committed evidence bytes and separately verifies the
closed P1/P3 schemas. Both must pass. Hook readiness is an independent input: the existing effective
`stale-source` warning blocks a full security verdict; direct handler success or an exit-zero dry-run cannot
mask it. Repair requires separate authority and is not smuggled into P4.4.

## Attention queue and terminal packet

P4.5 derives, but never stores authoritatively, one queue view from strict journal replay. Stable finding
identity deduplicates repeated observations across resume. Security/destructive/irreversible classes are
immediate; routine OWNER rows are ordered by blocking dependency and emitted once in a bounded packet with
controlling sources, recommendation, alternatives, blast radius, rollback, affected slices and no-decision
consequence. An unresolved immediate row freezes dependent writes but not proven-independent read-only work.

The terminal packet is a closed redacted projection: accepted slices/commits, AUTO-FIX reasons, owner rows,
deviations/rollback/orphan state, provider/usage fields with explicit unknown reasons, validation refs and a
replay locator. It does not change plan status, publish mAInd memory or issue P5 GO. The aggregate validator
replays the journal, recomputes every summary/manifest hash and requires terminal green P0–P3 plus all P4
evidence rows; any unresolved severe/security/third-state/hook defect produces a non-green readiness code.

## Alternatives rejected

1. One monolithic chaos item would let later code changes rewrite earlier expected results and would hide
   which boundary actually failed.
2. Mock-only exceptions do not prove disk/process restart behavior; child-process cuts plus reopen are
   required.
3. Retrying every unresolved intent is at-least-once execution without idempotency proof and can duplicate
   writes.
4. Treating a linked worktree as a security sandbox ignores the shared repository/config/hook boundary.
5. Automatic three-way conflict resolution changes source under an acceptance contract; conflicts are OWNER.
6. Candidate-authored redaction totals or `green` fields are self-certification; external byte scans and
   replay are required.
7. Publishing terminal telemetry to mAInd in P4 would introduce a new external side effect before P5 proves
   reliability/economics.

## Ecosystem-core pre-mortem

| Failure after 6–12 months | Early signal | Mitigation | Owner |
|:--|:--|:--|:--|
| New boundary has no crash row | production callable absent from exact fault matrix | exact-set source/boundary manifest and missing/extra validator | P4.1 |
| Harness passes by raising before every side effect | zero positive accepted/reconciled paths | independent positive rows and reachability counters | P4.1–P4.2 |
| Resume duplicates an unknown write | boundary counter increments twice for one idempotency key | no-rerun canary, exact postimage classification and OWNER on third state | P4.2 |
| Worktree cleanup removes foreign work | inventory identity mismatch or use of `--force`/broad prune | lock reason/owned root exact match, clean-only remove, foreign refusal | P4.3 |
| Worktree is mistaken for a sandbox | secret/config/hook or shared-ref mutation appears outside delta | separate P3/P4.4 security gates; no security claim from worktree success | P4.3–P4.4 |
| Evidence leaks the canary it claims to detect | forbidden class appears in committed P4 bytes | independent Task bundle-lint plus closed evidence schema | P4.4 |
| Stale hook projection is called green | dry-run exit 0 while status remains warning | parse verdict/diagnostics and block full readiness until exact green | P4.4 |
| Owner packet drops or repeats a gate after resume | queue IDs/counts diverge from strict replay | journal-derived stable IDs, ordering and duplicate/restart cases | P4.5 |
| Terminal packet masks one provider or unknown metric | aggregate filled from candidate totals/snapshot | independent replay, per-provider rows and unknown-preservation validator | P4.5 |

## Stop condition

P4 is ready when all five items have finite reads/files, terminal-P3 gates, exact validators and
sequential manual routes; worktree semantics are bounded to controlled repositories; the security verdict
cannot ignore effective hook state; no unresolved external fact is promoted to a guarantee; and P4.5's
aggregate manifest gives P5 one candidate-independent readiness input. Actual P4 closure additionally
requires zero unresolved severe/security/third-state findings; otherwise P5 remains closed and the exact
owner/remediation gate is reported.

## Verification status

- RAG: current official Git worktree semantics were rechecked through Context7; same-day first-party
  provider, Python and long-horizon sources are carried by the cited findings; repository donors were read
  directly.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: filesystem power-loss behavior, terminal P0–P3 schemas, real fault/results,
  provider auth/readiness and hook repair remain explicit execution-time evidence.
- Обходки/[POSSIBLE-DEFECT]: none accepted. The bad `maind health --cwd .` form is corrected to the documented
  boolean selector; the effective hook `stale-source` warning remains a blocker, not a workaround.
