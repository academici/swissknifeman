## Project Plans - Convention plan-protocol

Master plans live in `plans/<PLAN-ID>/` (`plan.md` + `phases/` + `handoff.md`) by protocol
plan-protocol; flat `.md` in `plans/` (except `ACTIVE.md`/`README.md`) — draft plan mode,
expand it: `/task:plan-design from-draft <file>`. Active plan - `plans/ACTIVE.md`
(no file - only plan 🟡). Statuses are updated IN plan FILES, not in chat - work
is not completed without updating. Cycle: item/phase closed → `handoff.md` overwritten →
recommended `/clear`. Commands: `/task:plan-{design,exec,close,audit}`.
