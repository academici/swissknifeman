---
disable-model-invocation: true
description: "Execute ready Task plan items with plan.py under the current session route."
argument-hint: "<PLAN> [Pn.m ...] [--review]"
---
Invocation payload: `$ARGUMENTS`. `plan.py` is `python3 <Task package root>/scripts/plan.py`.

**Goal:** finish the requested items (or the ready batch from `next`) with green acceptance checks,
one commit per item, inside the item's scope.

**Steps**
1. `plan.py next <plan>` — without item ids, run the batch it names; with ids, run those.
   `--review` is a flag, never an item id.
2. `plan.py start <plan> <items…> --actor <provider>/<model>/<effort> --session auto`.
   A route refusal (`ROUTE_UNDERSHOOT`) stops before any product write; a stronger route is fine.
3. Read only `context/<item>.md` and the files its Reads section lists; get more state with
   `plan.py show <plan> <ref>`. Never read or edit the generated Markdown views.
4. Implement Scope include only. Use the item's rules, guidance and decisions.
5. When reality changes the plan, an assumption or a blocker appears:
   `plan.py log <plan> <item> --type deviation|blocker|difficulty|assumption|note --summary "…"`.
6. Run each Validation check once per relevant change; keep long output in a file.
7. `plan.py finish <plan> <item> --status done --check V1=0 … --notes "…"`
   (`done_with_deviations` with `--deviation`, `blocked` with `--escalation`). The last item closes its phase.
8. One scoped commit (plan JSON + product files), then the next item of the batch.

**Rules**
- Run under the session route; never switch the model. The item route is the minimum.
- Change plan state only through `plan.py`; JSON is the source of truth.
- Owner gates: `plan.py grant` only with the owner's explicit message quoted in `--note`.
- Hard risk (security, schema/public API, data, concurrency, publishing) widens checks and is named in the
  final report with a `task:review` recommendation; no review runs by default.
- `--review`: after the last green item, one `task:review` pass over the scope diff; fix a confirmed
  finding in its open item, report findings of closed items as recommendations.
- Stop only at an owner gate, a missing decision, an external wait or exhausted context; existing dirty
  changes belong to the owner.

**Done when** every requested item is finished with recorded checks, committed, and the final report
states the result and the exact `plan.py next <plan>` line.
