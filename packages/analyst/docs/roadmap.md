# Roadmap

Implemented circuit: **P1 (MVP)** — `digest` + lessons-store + human `review`/`promote`;
**P2** — cross-project `scan` + reconcile; **P3** — confidence-arithmetic (Beta/decay) + numeric
state-machine `recompute`; **P4** — [`suggest`](./guide/suggest) → draft skill.

## Postponed for P5 (by design, no debt)

| Direction | What | Why delayed |
|:--|:--|:--|
| Skill `analyst-capture` | prompt discipline layer-2: how to catch lessons in the gray run | requires field signal calibration; separate from layer-1 |
| `observe.sh` (PostToolUse-thread) | streaming capture of observations during the run (not only post-mortem by run-report) | current on-demand `digest` covers MVP; flow - only based on friction |

Ecosystem principle: **do not implement speculatively** — feature is enabled based on a measured problem,
not «for growth The». Deviations caught in field work are routed by the skill `field-feedback-loop`.

## Related

- Numeric gates `suggest` (`--min-tier`) will become cheap when P3 will start stamping
  unit-confidence to pattern index (now confidence — per-lesson).

## Moved from root roadmap (2026-08-02)

### `analyst digest` reads Known Deviations/Pending Work closed plans as a source of lessons

**Status:** ⬜ deferred (idea Owner 2026-07-12, post-release).
**Implementation criterion:** will accumulate ≥2-3 plan with content Known Deviations/Escalation
Needed after this is a specific signal that manual review plan.md stops scaling.

#### Idea

`analyst digest` currently draws candidate lessons ONLY from run-report (`--project|--cwd
--session`) — line-by-line parsing of the session transcript (tests/lint/files/tool-failures). Plan-protocol
already OBLIGES everyone item on closing to fix in a structured way: `Known Deviations`,
`Pending Work`, `Escalation Needed` (`plan-run.md`), plus plan end date (`Last
Updated`/`Update Log` in `plan.md`). This is a ready-made, machine-parsable source of problems/finds,
which **not currently used anywhere** analyst-loop.

#### Why not implement it right now

- Second free log file «plan problems» would DUPLICATE the fact that the plan-protocol is already
  requires writing in a structured manner `phases/Pn.md` — produces two sources of truth that
  will disperse over time (anti-pattern repo: «Single Source of Truth > copies»).
- Not much data yet: the repo has been closed for the entire history ~5 plans; value cross-plan scanning
  will appear when more material accumulates for real pattern mining (`analyst scan`
  and so it works for cross-project patterns, not isolated facts).
- No clear criterion yet «what exactly from Known Deviations deserves to be a lesson» — without it
  this will either be a noisy dump, or another manual filter on top of a manual filter.

#### Implementation Sketch (when returning to the idea)

Not a new format - a new SOURCE for an existing pipeline `digest → review/promote →
curated`:

1. Function (analogue `run_report.load`) — scans `plans/*/plan.md` + `phases/*.md`,
   finds items with non-empty `Known Deviations`/`Escalation Needed`/`Pending Work`,
   closed (`Status` terminal) AFTER the last date `analyst digest`-run through plans
   (cursor - how `events.ndjson`, do not revise what has already been processed).
2. Every find → candidate lesson with provenance `plan:<ID>#<item>` (analogue of the current one
   `session:<uuid>` provenance run-report-lessons) — pipeline `review`/`promote` does not change,
   the person is still in the gate.
3. Archived plans (`plans/archive/`) — also a source (there are already closed finds that
   may not have been included in the analysis during the life of the plan).

#### Alternative (if the criterion still fails)

Do nothing - Update Log + Known Deviations and so human readable
`/planner:plan-design`/review of the new plan (Required Reads are already referred to Completion Notes
previous items). Automation is justified only with real volume, not «for growth The».

#### Source

Dialogue Owner 2026-07-12 (after closing, release v0.9.0) ·
`packages/analyst/lib/analyst/digest.py` (current single source - run-report) ·
`packages/skiller/skills/general/plan-protocol/SKILL.ru.md` (structure Known
Deviations/Pending Work/Escalation Needed, required at closing item'a).


### Coating analyst-cycle on a fleet of onboarded projects

**Status:** deferred (data available, no solution). **Implementation criterion:** conscious decision
by umbrella-policy of hooks on other people's projects - not one-sided inclusion.

#### Context

`analyst` (run-report → digest → lessons → token-report) gives value only where
hook `run-report` is actually turned on and is accumulating history. Fleet check (SKM-AUDIT-004,
P3.1/P3.2) showed: from ~20 of onboarded projects, only a small part writes run-report
in general, and accumulated even less analyst-state/token-trend. No signal is not a bug
`digest` (rechecked read-only on three projects, see. R3 in
: `--dry-run` resolves correctly
binary and legitimately returns `candidates: []`), a data-coverage gap: hook `run-report`
per-project setting (harness-hooks), is not a global daemon.

#### Metering (SKM-AUDIT-004, 2026-07-07)

- Run-report: **5/20** projects have accumulated a history (agelto 30, azguard 10, vaulter 9,
  chatom 6, swissknifeman 4).
- Analyst-state (`~/.swissknifeman/analyst` per-project): **2/20** (agelto, vaulter).
- Token-trend (`analyst token-report`): **2/20** (agelto 42 records, swissknifeman 4).
- Where the hook is enabled and has accumulated history (agelto), signal is useful -
  rolling-baseline is already considered normal.

#### Why is it not being implemented now? (D6, SKM-AUDIT-004)

Bulk enable hook `run-report` on 15 other people's projects at once - cross-package change
configurations of multiple repositories, wider «safe reversible on one project». Requires
solutions for umbrella-policy, not «safe quick-win».

#### Options (without obligation)

1. Enable `run-report` default hook for new onboardings (`maind onboard`/
   `harness hooks`) — does not touch already onboarded projects, closes gap on new ones.
2. Don't change anything - the data will appear organically as projects are used.
3. Add `analyst`-slice in `maind projects status`/`maind fleet` for visibility
   coverage without a separate team for the project (observability without behavior change).

#### Source

 (table. 2) ·
 (R6).

