# Incident: repeated executor restarts during P1 — 2026-08-12

## Impact

The P1 execution was prolonged by seven avoidable executor restarts. Eight P1.5
execution processes were started in total; a separate `plan-design P1.5` process
was also started and is not included in that restart count. The owner waited for
more than an hour, received repeated nonterminal progress instead of the requested
P1 result, and paid the context/token cost of re-reading the same plan and test
surface. This was an orchestration failure, not a product-code requirement.
For the actual bounded retirement change, seven restarts are grossly
disproportionate: they indicate poor execution control, not inherent task size or
complexity.

RAG:— (direct session and repository evidence: `journal.jsonl`, shell executor
session `12107`, owner messages in the active Codex thread).

## Exact count and chronology

The count reported to the owner is **7 restarts**: the initial P1.5 execution plus
seven replacement launches, i.e. **8 P1.5 execution launches total**. Six
replacement launches have durable journal identities; the final replacement was
terminated from shell session `12107` before it wrote an attempt event, so its
absence from `journal.jsonl` must not be interpreted as absence of the launch.

| Sequence | Kind | Durable identity / evidence | Observed outcome |
|---|---|---|---|
| 1 | initial P1.5 executor | run `a9766dbc…`, session `019ff66a…`, 14:43Z | stopped after fixture failures and a route-freshness rejection |
| 2 | restart 1 | run `42c4523e…`, session `019ff676…`, 15:08Z | emitted another local-repair handoff |
| — | separate design detour, excluded from restart count | session `019ff688…`, 15:29Z | expanded P1.5 DoR/D17 but interrupted delivery flow |
| 3 | restart 2 | run `a9de8bbd…`, session `019ff69c…`, 15:38Z | full suite still 61 failures / 69 errors |
| 4 | restart 3 | run `59b4badc…`, session `019ff6a1…`, 15:42Z | D17 repaired; suite remained nonterminal |
| 5 | restart 4 | run `f5a1546f…`, session `019ff6aa…`, 15:57Z | partial fixture conversion; 54 failures / 67 errors remained |
| 6 | restart 5 | run `af62c676…`, session `019ff6b4…`, 16:03Z | 53 failures / 67 errors remained |
| 7 | restart 6 | run `09f54314…`, session `019ff6ba…`, 16:10Z | inventory regeneration; no terminal result |
| 8 | restart 7 | shell executor session `12107`; stopped in the active owner turn | terminated on owner escalation; no durable attempt event |

Earlier P1.1–P1.4 launches and their retries are outside this exact P1.5 count.
They still contributed to total elapsed time and are visible in `journal.jsonl`.

## What happened

1. The original request was treated as permission to keep re-entering the plan
   protocol instead of as a terminal instruction to finish the requested batch in
   the current session.
2. A route-provenance mismatch was elevated into a fresh-process requirement.
   The protocol evidence requirement was allowed to override the owner's explicit
   instruction and the fact that repair could continue safely in the same session.
3. `local-repair` results were handled like handoff boundaries. Each replacement
   paid setup, plan-read, repository-read and validation costs again without
   changing the dominant failure class.
4. The broad v1-fixture migration was discovered through repeated full-suite runs
   instead of first building a file/failure matrix and exhausting one failure class
   in a single process.
5. The P1.5 design gap was repaired through a separate design launch mid-execution.
   The design artifacts were useful, but the process boundary was unnecessary and
   increased delay and context duplication.
6. There was no enforced restart budget, elapsed-time circuit breaker or rule that
   required owner approval before replacing a still-capable executor.
7. One launch was not journaled before termination, so the canonical journal alone
   under-counted the operational incident.
8. Status messages described internal retries but did not give the owner a hard
   end condition. This made the task appear unbounded because it effectively was.
9. Repeated partial edits by fresh contexts created a credible code-quality risk:
   duplicate helpers, test-only compatibility shims, inconsistent fixture
   conversions, weakened assertions and dead branches could accumulate even when
   each isolated change looked locally reasonable.

## Root cause

The primary root cause was orchestration policy inversion: route/protocol hygiene
was treated as the goal, while delivery of the owner-requested batch became
secondary. The technical test failures were ordinary repair work; they did not
require process replacement. Contributing causes were missing restart accounting,
no single-session repair invariant, repeated broad validation before focused
triage, and failure to pin the requested item boundary before expanding work.

## Mandatory prevention controls

These controls apply to the remainder of this plan and are acceptance evidence for
P1.5:

1. **Zero automatic restarts in the active owner session.** A route mismatch is
   recorded as a deviation and repaired forward in the current process. It cannot
   trigger another Codex/executor launch.
2. **One executor per item by default.** Replacing a capable executor requires an
   explicit owner decision. `local-repair`, test red, stale generated output and
   context compaction are not restart authority.
3. **Every launch is journaled before work.** If startup fails before the canonical
   writer is available, record the launch immediately in this incident carrier and
   reconcile it into the journal before closure.
4. **Scope pin before execution.** The literal requested range is recorded. Any
   expansion to additional items/phases requires an explicit owner instruction or
   a separately stated hard dependency; it must never happen silently.
5. **Failure-class circuit breaker.** After two validations with the same dominant
   failure class, stop broad reruns, create a focused failure matrix, and run only
   the affected modules until that class is exhausted.
6. **Elapsed-time circuit breaker.** At 15 minutes without a terminal result, report
   exact completed/remaining gates once and continue in the same session. A time
   checkpoint never creates restart authority.
7. **Design repair stays in-process.** A newly discovered stable-spec gap is written
   directly in the active worktree and validated there; it does not cause a design
   subprocess unless the owner explicitly requests one.
8. **Terminal communication invariant.** Progress notes cannot substitute for a
   terminal result. Final handoff must state completed scope, red/skipped gates,
   commits, preserved unrelated changes and whether external effects occurred.
9. **Restart-accumulation diff audit in a fresh session.** Before terminal phase
   closure, a separate fresh-context `task:plan-audit` must inspect the complete P1
   product diff for duplicate helpers, compatibility branches reintroduced only to
   satisfy tests, dead code, weakened assertions/gates, generated files edited
   outside their owner, and unrelated scope. The current exhausted execution
   context must not self-certify that review. Green tests alone are insufficient.

## Verification for this incident

- No executor process is relaunched after this finding is written.
- P1.5 is repaired and validated directly in the active session.
- P1.5 reaches an audit candidate with real validation evidence; the complete P1
  diff then passes the mandatory fresh-session restart-accumulation audit before
  terminal phase closure.
- Closure evidence cites this finding and the count `7 restarts / 8 P1.5 execution
  launches`, including the unjournaled final launch.
- Any remaining red validation is reported as red; it is never converted into a
  new handoff/restart loop.
