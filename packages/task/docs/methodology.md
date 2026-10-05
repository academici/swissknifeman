# Methodology Task plans v4 - full cycle

One page for the whole day-to-day process on the JSON plan engine. Structure and schemas -
[Plan structure](./plan-structure). Nothing here requires a plan for ordinary work: `/task:dev` and
`/task:fix` run without `plans/`.

## Normal path

```text
research → design (plan-design) → check → design-done → run (plan-run) → close (plan-close) → archive
                                     ↑                       │
                                     └── reopen / amend ←─────┘   audit (plan-audit) only on owner request
```

Every step is a verb of `scripts/plan.py`; the verb that names the next step is `plan.py next <plan>`.

## research

Optional. Multi-source research with verification (`/task:research`); plan reasoning goes to JSON
`sections` or `knowledge/<id>.json` through `add-document`. Raw supporting evidence stays in
`artifacts/`; execution reads refer to JSON, never to plan Markdown.

## design (`/task:plan-design`)

1. `plan.py new` creates the plan (next number, Short ID, skeleton, views).
2. `add-phase`, `add-item`, `add-decision`, `set`, `push` fill the JSON; the owner's messages go verbatim
   into `brief.json`.
3. An item is detailed when it has a summary, scope, reads, rules, acceptance `validation`, deliverables and
   a `route`; one acceptance check per detailed item is the minimum. Items are sized for one session.
4. `plan.py batches` groups items into runs (aim for few runs); `plan.py check <plan>` must show 0 errors.
5. `plan.py design-done <plan> <Pn>` marks the phase `detailed`. Later phases may stay `skeleton` until the
   previous phase closes.

Open questions are decisions with status `open`; the owner answers, then `plan.py decide` records it.

## run (`/task:plan-run`)

1. `plan.py next <plan>` (or the items the owner named) → `plan.py start <plan> <items> --actor … --session auto`.
   A route refusal stops before any product write.
2. Read JSON from `plan.py context … --stdout` and supporting files as needed; get more state with `plan.py show`.
3. Implement inside the item's scope; `task_files` are hints, not limits. Use the item's rules and decisions.
4. When reality changes the plan or an assumption/blocker appears: `plan.py log … --type deviation|blocker|difficulty|assumption|note`.
5. Run each validation check once per relevant change; long output goes to a file, only the result to context.
6. `plan.py finish <plan> <item> --status done --check V1=0 … --notes "…"` (`done_with_deviations` with
   `--deviation`, `blocked` with `--escalation`). The last item closes its phase.
7. One scoped commit per item (Russian Conventional Commit; plan bookkeeping is gitignored), then the next
   item of the batch.

Stop only at an owner gate (`plan.py grant` needs the owner's quoted message), a missing decision, an external
wait or exhausted context. Existing dirty changes belong to the owner. A hard risk (security, schema/public
API, data, concurrency, publishing) widens the checks and is named in the final report with a `/task:review`
recommendation; no review runs by default.

## review (opt-in)

`--review` on `plan-run` runs one `/task:review` pass over the scope diff after the last green item; a
confirmed finding is fixed in its still-open item, findings of closed items are reported as recommendations.
`/task:plan-audit` is a read-only audit with a verdict file and a `note` in the log; it never edits the plan.

## close and archive (`/task:plan-close`)

`finish` closes phases and the plan automatically. `plan.py archive <plan>` moves a done plan to
`plans/archive/`. A wrong finished item is reopened with `plan.py reopen <plan> <item> --reason …` (owner
amendment).

## Delegation (opt-in)

The deterministic context pack is the default. The schema already carries work units for subagents; the
`unit` verbs, an opt-in scout (weak model per provider in `configs/command-routing.json`) and `plan.py stats`
arrive with phase P4 of the JSON-engine plan. Neither becomes a default without an owner decision based on
`stats`.

## Economy rule

Do not invent bookkeeping: JSON plus the API already keep state consistent. A tool failure or a reversible
local defect is repaired in the same attempt and logged only if it changed the plan; repeated re-audits
without a material scope/risk change are not run.

Optional `--reviewer provider/model[/context][/effort]` requests a fresh read-only reviewer on that
exact native route; without an explicit review request no review runs. `plan-run` accepts
`--review-effort`; review/audit accept `--effort`. See the Task package's
`references/reviewer-selection.md` for route parsing, native session independence and the bounded
two-completed-round/one-owning-correction policy. JSON and `plan.py` remain the state API;
reviewer flags do not restore `plan-work`, launch agents from Python or execute check commands.
