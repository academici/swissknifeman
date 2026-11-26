# Execution integration contracts

Owners: P07.08.a (local integration), P07.08.b (intent effects and administrative reconciliation). Integration rules live in [`domain/integration.py`](../../src/skm/modules/execution/domain/integration.py) and the Git adapters in [`adapters/git/`](../../src/skm/adapters/git/). The G26–G34 and G48–G51 command notes name the same local Git effects.

| File | Owner responsibility |
|---|---|
| `src/skm/modules/execution/domain/integration.py` | Pure commit plan, mode constraint, canonical trailers and path exclusions |
| `src/skm/modules/execution/application/commands/acquire_integration_slot.py` | Fenced bus acquisition, attempt mount binding, durable target/run host pins |
| `src/skm/modules/execution/application/commands/release_integration_slot.py` | Fenced release, stale-holder diagnostic without releasing a successor |
| `src/skm/modules/execution/host/stages/integrate.py` | Ordered per-target StageClient protocol, immutable accepted inputs, partial receipt vector |
| `src/skm/modules/execution/host/stages/run_checks.py` | Exact-SHA recheck, owner retry tip guard, no reuse, proof-gated finally cleanup |
| `src/skm/modules/execution/ports.py` | Vcs candidate preparation/publication/reconciliation and environment recheck gateway |
| `src/skm/adapters/git/integration.py` | Detached candidate projection, FileLock, epoch, prepared journal, one-use admission, canonical CAS and protected receipts |
| `src/skm/adapters/git/integration_process.py` | Full object/ref fsync; gated helpers with durable ownership/identity before IO; admin inspection registration and explicit cleanup status across lookup errors |
| `src/skm/modules/execution/host/stage_client.py` | Assignment-bound slot release forwards the actual slot fencing token |
| `src/skm/adapters/git/environments/worktree.py` | Owned detached recheck paths and durable bindings/cleanup proof |
| `src/skm/adapters/git/environments/existing_checkout.py` | Recheck delegation with user HEAD/index/dirty bytes preserved |
| `src/skm/adapters/git/environments/managed_clone.py` | Detached local target, remote/local/pushed tips and fetch without local reset |

Before `seal_output`, the host Git writer creates the output ref and its binding in one Git transaction.
The binding records the attempt, step, output number, mount, pinned Git directory, ref, expected old OID
(all zeroes for create-only refs), assignment fence and snapshot SHA. An exact replay verifies both refs.
After the server validates the manifest and assigns an output ID, the host records the ID and returned
manifest digest against the same binding. Candidate preparation and publication verify these refs against
the server's accepted output chain before effect admission and target-branch CAS.

`git_integration_vcs()` binds the writer gateway. The writer requires trusted Begin integration targets,
accepted output identities and artifact digests, a live StageClient admission and a precreated Git-effect
ProcessOwnership. It never obtains a UnitOfWork. Execution's existing `record_integration()` verifies complete
receipts and emits IntegrationCompleted; the workflow engine controls the later TaskAccepted transition.
Begin persists a stable `integrate` packet with the acceptance decision, output chain, byte-ordered targets
and runtime artifact digests. Local `git_commit` phases require that packet, a current assignment and a
locked current slot; every fresh executing guard gets a new admission bounded by lease, slot and five seconds.
P07.08.b adds exact intent-backed effects and an immutable assignment binding for read-only reconciliation.
Host factories use the registered wire DTO identities. The writer accepts the host's pinned canonical
repository map and precreated ownership callback; it imports accepted objects from the attempt clone.
Every writer Git command enables `core.fsync=all`, including candidate, epoch and receipt object writes.
The trusted ref helper supports the declared `pgroup_best_effort` ownership through the platform's
pidfd-owned process group; unavailable cgroup/container launchers are refused before admission.
Its identity/PGID is fsynced into the prepared journal before any ref transaction stdin is released.
Empty final-only task deltas retain the target SHA and produce an explicit no-op receipt with no commits.
Final-only commit trailers always use the accepted output's identity, even when its trailing projection
has an unchanged tree after earlier changed outputs; implementation-and-fixes commits retain per-output identities.
Later integration stages preserve the original accepted packet and effect IDs. A server-bound
`mode=reconcile` only inspects existing receipts, journals, remote refs or provider observations.


A returning GitRunner proves its child reaped. An interrupted ref helper leaves an unresolved durable
ownership journal and blocks successor activation after restart. Recovery's `quiescent` callback must prove
that exact containment empty; a PID lookup, lease expiry or supervisor restart cannot provide that proof.
Partial refs retain unknown status. Journals and candidate inputs are retained for reconciliation.
Runtime/check containment must protect Git metadata and writer storage; these files add no isolation backend.

Executor validation and independent review are separate. Review: **changes_requested**
(`01a1e4b3-9b7e-7fe1-87a0-dd455986df70`); the six findings are addressed by this correction.

Additional owner rows:

| File | Responsibility | Leaf |
|---|---|---|
| `src/skm/modules/execution/application/_integration_inputs.py` | Stable accepted Begin inputs, artifacts and receipt binding | P07.08.a |
| `src/skm/modules/execution/application/commands/record_external_effect.py` | Local git_commit guards and exact one-use intent admission/outcome | P07.08.a / P07.08.b |
| `src/skm/adapters/git/integration_candidate.py` | Detached task projection and independent candidate validation | P07.08.a |

The owning generator partitions execution documents into bounded `_documents_*` modules and preserves
`generated.documents` as the import facade. The full generated-file ownership rows live in
[the contract inventory](contracts.md#p0708a--local-integration-additions).
The unrelated advance-table split and A6 waiver change are reverted to the pre-P07.08.a test file;
the original test names, helpers and assertions are unchanged. The implementation's Python files stay
below S3's 600-line limit; the restored pre-existing advance-table file is outside that implementation.

Executor validation: **implemented**. The final single combined invocation, with mandatory PostgreSQL,
completed 171 tests across the seven task suites and contract imports, including four accepted-no-op
trailer regressions, 24 root guardrails, Ruff and Pyright (zero errors/warnings). `MAX_LINES=517` for the
accepted-no-op correction and `596` across the P07.08.a Python implementation delta, including generated
shards. The restored pre-existing advance-table file has 2351 lines and is byte-identical to
the task baseline, not a new split or fixture change. Frozen execution/spec inputs, `.codex/state` and
`.swissknifeman/context-pack` are excluded from the implementation commit. These executor checks do not
constitute a new independent review verdict.


## P07.08.b — external effects and reconciliation

| File | Responsibility | Leaf |
|---|---|---|
| `src/skm/modules/execution/domain/external_effect.py` | Immutable requests, identity-bound observations, absence proof validation and pure Git/admission values | P07.08.b |
| `src/skm/modules/execution/application/commands/reconcile_external_effect.py` | Authorized run-scoped reconciliation, pinned bound assignments, read-only claim/begin/renew/result/revoke and bounded reissue | P07.08.b |
| `src/skm/modules/execution/application/commands/record_external_effect.py` | Exact policy intent proposal/one-use approval consumption, durable executing and atomic outcomes; complete target vector | P07.08.b |
| `src/skm/modules/execution/host/stages/integrate.py` | External effect orchestration and narrow injected provider execute/lookup contract; admin observation never publishes | P07.08.b |
| `src/skm/adapters/git/integration.py` | Exact SHA remote push with expected-old guard, endpoint/locator checks, durable gated helper identity, conservative read-only push/commit lookup | P07.08.b |

An interrupted executing effect and its policy intent become outcome_unknown in the same UoW.
An intended effect never consumed authority and becomes failed without inventing a policy execution.
New IO requires a normal active integration stage and a fresh single-use approval. Transport errors,
missing lookups or missing receipts never prove absence. A succeeded target is retained through a
partial vector; acceptance requires every selected target to have a successful receipt.

Administrative work derives solely from Assignment.reconcile_effect_id, with a fresh DB lease, worker
credential, current read authority and the exact pinned active host. Paused, cancelled, failed, archived
and emergency scopes remain stopped. No attempt cursor, task, runtime token, reservation or writer slot
is advanced by an administrative observation, release, failure or expiry. Results close the read and
replay without duplicate outcomes/events; interrupted reads receive new fenced rows with backoff.
Host activation/registration and current checkout binding remain required; no restore authority is inferred.
Provider execute adapters must durably journal and consume admission before IO; unavailable adapters
produce unknown/operator observations. Tests use a narrow fake provider and temporary file:// remotes.

Initial P07.08.b executor validation: **76 task tests passed**, with mandatory PostgreSQL, memory,
temporary file:// remotes and no skipped tests. All root source guardrails passed. The combined
architecture run has **81 passed, 2 failed**: the implemented-command tuple in
`tests/architecture/contract_registrations.py` and the owner inventory in
`docs/architecture/contracts-02.md` still lack the new reconciliation command. Both files are outside
this leaf's write set; the exact two-line synchronization patch is prepared at
`/tmp/p0708b-scope.patch` and awaits owner authorization. The checks remain unchanged.
Ruff passed; Pyright reported zero errors and warnings. Changed Python files have `MAX_LINES=597`.
Independent review: **changes_requested** (`01a1e55b-4044-70f2-870d-622d0e5e2bc3`).
This correction addresses all four reproduced Major findings: failed required effects block completion;
cached heartbeats revalidate current ownership/fencing; restart diagnostics remain in the policy outcome
rather than occupying an immutable unknown-effect receipt; and every administrative Git read helper
persists its ownership/identity and registers it through the current admin claim before releasing Git.
Read helpers use distinct units derived as UUID5(effect_id, owner_nonce), preserving immutable stage
process identities while proving their relation to the assignment's effect server-side. Prepared host
markers cover a crash before server registration. An unresolved inspection journal blocks later reads
until the exact containment has an empty proof; a missing PID never supplies that proof. Normal writer
journals remain unchanged by inspection. Regression coverage includes memory, mandatory PostgreSQL and
temporary file:// Git remotes. Executor verification does not constitute a new independent acceptance.

Correction executor validation: **85 task tests passed** (mandatory PostgreSQL, memory and local
file:// Git remotes; no skips). The requested combined pytest/Ruff/Pyright command was run; after
non-behavioral lint/type corrections, the same scoped Ruff and Pyright checks both passed, with
zero type errors/warnings. Changed Python files have `MAX_LINES=595`. No unrelated tests or
`make check` were run. Frozen inputs and coordinator/session state are excluded from the commit.

Follow-up review (`01a1e55b`) confirmed closure of those four findings and requested a correction
to the worker cleanup gate. Reconciliation now carries cleanup status independently of effect state:
a completed or unavailable lookup can report outcome_unknown and still record its result, close the
admin assignment/lease and escalate to the operator. Explicit `reaped=False` or `CleanupUnconfirmed`
continues to block result recording. Memory/PostgreSQL regressions exercise the actual worker `_record`
gate and command bus, including the unconfirmed-cleanup case and unchanged workflow/budgets.
This correction's single requested combined invocation passed **91 tests**, scoped Ruff and Pyright
(zero errors/warnings), with `MAX_LINES=483` for changed Python files. Independent acceptance of this
correction is separate from executor validation.

The next review (`01a1e55b`) confirmed clean unknown recording but found that real Git lookup error
handlers discarded unconfirmed cleanup. Scoped Git inspection now retains `reaped=False` across
unresolved helper journals and swallowed lookup errors, and confirms cleanup only after helper reap,
durable journal update and marker removal. Commit/push inspection explicitly returns that status;
the host requires it after invoking Git inspection. Effect outcome never supplies cleanup evidence.
Real file:// push regressions on memory and PostgreSQL inject failure after actual `RenewLease`
registration and verify the worker gate retains the admin lease/stage without escalation. A completed
unknown Git read still closes/escalates. Commit/push restart tests also verify explicit cleanup flags.
The cached PG fixture removes each case's binding so separate Git scenarios remain independent.
Executor validation: the final single combined invocation passed **95 tests**, scoped Ruff and
Pyright (zero errors/warnings), including the changed inspection helper module. Changed Python files
have `MAX_LINES=595`; frozen inputs and session state are excluded. Independent acceptance remains
separate from these executor checks.
