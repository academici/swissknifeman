# P07.10 execution fixtures

The harness runs the production App, PostgreSQL repositories, bus, authorization,
context finalization, Git adapters, check runners and worker entrypoint. Database
rows are recreated before each test; only application wiring is cached.
FakeRuntime replaces the provider and spawns real OS processes. RecordedRuntime
uses the production bounded TranscriptWriter for the provider's actual events.
Scheduler, lease sweeper, timeout enforcer and outbox relay run in production
ServiceRunner threads. Waiting uses Instance.wait_until and events.

## Product corrections

* Cancellation serializes nested immutable route snapshots through the document codec.
* Prospective run configuration preserves selected process restart values without
  supplying the provenance-only PROCESS level as an input resolver layer.
* Internal background commands use system authority; worker fencing and service
  principal guards remain enforced.
* Runtime requests use a policy transport view, worktree-rooted grants and the
  reserved capture limit. Ownership wire documents omit absent daemon identity.
  Provider transcripts are retained as bounded evidence through an injected
  bootstrap reader. Measured usage is priced from pinned catalog resources;
  review-round reservations close once.
  BindingRole includes the execution roles already accepted by the database, so
  retained raw results can be read at the next stage. Check rounds are numbered
  across the attempt, including distinct recheck stages. Work-scoped check and
  integration-slot limits travel in the server-prepared payload instead of being
  read from the host configuration chain.
  Agent roles come from the pinned workflow definition. Recheck environments are
  retained when terminal/reconciliation cleanup proof is still unavailable.
  Review completion preserves the selected round; acceptance receives the actual
  executor step/runtime IDs and the pinned item's review requirement.
  Worker completion advances with PostgreSQL time. Declared rechecks reach the
  workflow engine; history inputs are paged through the fixed cutoff.
  Confirmed bounded fixes honor the pinned correction floor; the M3 owner enables
  below-task-class admission explicitly, with fresh sessions for correction steps.
  Red required checks count as confirmed fix-brief feedback without review findings.
  Committed assignment completion stops queued renewals under the result lock,
  so a final heartbeat cannot turn successful completion into a lease-loss failure.
* A published Git journal is rechecked under the writer lock before admitting the
  next generation. Missing/partial receipt refs remain unknown and block admission.
* Scheduler material checks use pinned revision observations, set and recheck
  BLOCKED_BY_MATERIAL, and serialize run waiting with the normative event payload.
  They also revoke READY eligibility when a material disappears after StartRun,
  before any attempt or attempt-budget charge is created.

The four proposal patches were applied and removed. No patch artifacts remain.

## Adversarial self-check

Adversarial self-check after review remediation: **5/5**. The required foreground
combined command passed with PostgreSQL required: **12 passed, 0 skipped**;
Ruff: clean; Pyright on the four requested paths: **0 errors, 0 warnings**.
The changed Python files in this remediation have `MAX_LINES=402` (below 600).

The earlier full-suite baseline at `62f6d433f` had **134 passed, 0 skipped**,
**24 architecture checks passed**, clean Ruff and Pyright on 34 changed source
files; that baseline's changed Python files had `MAX_LINES=595`.

Independent review `01a1e764-fbe8-7a60-b35b-86f370a7ef04` identified four Major gaps.
The remediation uses a READY-to-material-wait domain transition; injects the faulty
BlobStore into build_app/CompositionOverrides; and restarts services around a
committed, paused terminal advance cursor. Validation results are recorded above.

1. All ten requested recovery files and M3 are collected with PostgreSQL required,
   without skips or expected-failure markers.
2. M3 includes a three-task DAG, failed check, rework on a different model, red
   review, triage confirmation, fix, green review, integration/recheck and K3 order.
   Reviews use separate provider sessions and read-only profiles within the ceiling.
   The trace kills an external worker and resumes the same attempt only after real
   OS reap. It checks a shared budget, fixed-cutoff event-only replay and metadata
   canary. Material recovery grants v1, never the later published v2.
3. K12 now starts a real selected run and kills its worker before any output is
   sealed. The resumed L2 provider observes the actual unsealed `41`; L3 providers
   observe a clean `0` in a fresh environment while old `41` bytes remain retained.
   Both L3 cases finish checks, review, integration/recheck and reach `succeeded`.
   A different host cannot borrow L2 ownership; replacement honors integration pins.
   No old-lease SealOutput or test-created recovery artifact supplies the handoff.
   Transcript and settlement assertions use the actual interrupted runtime.
   The PG trace ages the lease while keeping FrozenClock synchronized with DB
   time, so a released L2 assignment is not accidentally scheduled in the future.
   Dead leader/setsid, EPERM and unavailable containment never yield false reaped.
4. All twelve numbered PG races plus physical staged-byte cleanup contention,
   expiry between stages, checkpoint reconfiguration and future attempt refusal
   after count lowering are covered without resetting counters or deadline origin.
5. Forged provider acceptance and lost stdout/transcript/native visibility do not
   produce accepted outputs or erase measured calls. All mutations use production
   paths with provider/fault port fakes; no product monkeypatch or timing sleep.
   Blob upload faults pass through the App's uploader and production evidence
   recording boundary; failure commits neither a staged DB row nor a terminal
   stage/evidence binding, while a subsequent complete upload can be recorded.
   A terminal failed-check result committed during pause retains its advance cursor
   through two service restarts; resume creates its FixBrief/counter once, and two
   further restarts preserve the single acceptance and finished counters.

Independent review input: received (session above); independent re-review: not performed.
