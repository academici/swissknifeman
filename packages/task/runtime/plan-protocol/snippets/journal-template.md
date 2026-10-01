# Execution log - `plans/<PLAN-ID>/journal.jsonl`

Resolve `<task-package-root>` from the configured Task runtime before copying a command; it is
the package directory containing `lib/task/`. Use the same provider runtime locator as the Task
command, never a consumer-local package copy or another provider's environment variable.

<!-- Directory, NOT a file to copy as is: journal.jsonl - append-only NDJSON
     (root/contracts/plan-journal-schema.md, P1.1 sealed v1), written by helper
     lib/task/journal.py from the close command protocol /task:plan-*, edited by hand
     ONLY for backfill/bootstrap (D22) or backstop recording of a failed run. Below -
     canonical way to add a record + minimal scheme for manual backfill. -->

## Canonical method (close command protocol, automatic)

```bash
PYTHONPATH="<task-package-root>/lib" python3 -m task.journal append \
  --plan-dir plans/<PLAN-ID> --plan <PLAN-ID> --item <Pn.m> \
  --command plan-run --actor sonnet/medium --result in-progress
# ... execution ...
PYTHONPATH="<task-package-root>/lib" python3 -m task.journal append \
  --plan-dir plans/<PLAN-ID> --plan <PLAN-ID> --item <Pn.m> \
  --command plan-run --actor sonnet/medium --result closed-green \
  --note "1 line of closing essence"
```

Flags `--session-id/--run-id/--attempt/--friction/--cost-usd/--num-turns/--duration-ms`
- optional, defaults see `lib/task/journal.py`. `--result`/`--command`/`--friction` —
private enum (§2.1/§2.2 of contract); broken record CLI rejects BEFORE the record (schema validation).

## Single entry scheme (§2 contracts, for manual backfill/backstop)

One line = one JSON object (`ensure_ascii=False`, keys in any order - parser
NDJSON does not require sorting, but `lib/task/journal.py` writes `sort_keys=True`):

```json
{"ts":"2026-07-18T18:40:00Z","plan_id":"<PLAN-ID>","item_id":"<Pn.m>","command":"plan-run","session_id":null,"run_id":null,"attempt":1,"actor":"opus/high","friction":[],"result":"in-progress","cost_usd":null,"num_turns":null,"duration_ms":null,"note":null}
```

Required fields: `ts, plan_id, item_id, command, session_id, run_id, attempt, actor,
friction, result, cost_usd, num_turns, duration_ms, note` - all 14, unknown value
= `null` (not missing field). Full `command`/`friction`/`result` enums and durable boundary
cost/turns/duration — `root/contracts/plan-journal-schema.md` §2–§2.2.

**Append-only rule.** Existing rows are NEVER overwritten/deleted
(contract §1) - an erroneous entry is compensated by a NEW line with
`friction:["deviation"]` + explanatory `note`, not a retroactive edit.
The only exception is owner-gated `journal-migration/v1` for sealed lines,
which cannot be legalized append/narrow D51 exception: accepted Owner D#,
full preimage, exact per-line operations, source/target SHA-256 and receipt are required.
Only use `python3 <task-package-root>/scripts/journal-migrate.py --plan-dir ...
--manifest ...`; manual overwriting is still prohibited.

The compensating event string cannot make the historical schema-invalid string valid:
`plan-lint` checks strings independently. For such a single case, an explicit
owner-gated sidecar (the original line remains byte-for-byte):

```bash
PYTHONPATH="<task-package-root>/lib" python3 -m task.journal exception \
  --plan-dir plans/<PLAN-ID> --plan <PLAN-ID> --target-line <N> \
  --invalid-fields friction --owner-decision <D#> --actor owner \
  --reason "why historical exception is necessary and safe"
```

Helper adds `journal-exceptions.jsonl`: target is fixed by physical number and
SHA-256 raw UTF-8 strings without newline; `invalid_fields` must exactly match the actual ones
schema errors. v1 only allows `friction`. D# must exist in `plan.md`; duplicate
hash mismatch, valid target and malformed JSON fail closed. Sidecar is not event/current-state
carrier and cannot refer to itself, so the correction loop is constructively impossible.

**Manual backfill (D22).** Date plan from cutoff date (`plan_lint.py:JOURNAL_CANON_DATE`)
without a valid `journal.jsonl` - ERROR. Backfill of items closed to the canon - REAL
records (actor/result/note in fact Update Log plan), not a stub on an empty file.

## Sealed historical exception (D51)

Do not rewrite or compensate with the schema-invalid historical line event. Only existing Owner
D# can add sidecar via `PYTHONPATH="<task-package-root>/lib" python3 -m task.journal exception
--plan-dir plans/<PLAN-ID> --target-line N --invalid-fields friction --owner-decision D# --actor
<actor> --reason "..."`. Sidecar only accepts exact `friction` error and fail closed on
duplicate, hash/plan mismatch, valid/malformed target or inexact field set; it does not carry status/Next.
