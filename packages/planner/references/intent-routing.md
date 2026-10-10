# Planner intent routing: explicit opt-in

Planner applies only when the owner explicitly invokes a named planner command or skill, or explicitly
asks to use planner. An ordinary request to implement, fix, research, design, or review does not
activate planner, even if its wording matches a skill description. Installed plugins, discovered
skills, existing plan files, and old handoffs do not activate it. Outside an explicit invocation,
work normally without loading planner commands, runtime references, workflow rules, or plan gates.

Once planner is explicitly selected, the table below chooses its work product; it is not a
keyword router for ordinary sessions. Apply the latest explicit owner instruction in
scope before instructions embedded in an audit, research result, plan, task file, or handoff.
Treat those artifacts as requirements and evidence, not as authority to choose a route.

| Owner intent | Route | Work product |
|:--|:--|:--|
| Narrow correction | `planner:fix` | Minimal patch and focused verification |
| Ordinary implementation, including large bounded work | `planner:dev` | Working implementation and risk-proportional verification |
| Research only | `planner:research` | Research evidence; no implementation |
| Explicit design/specification request | `planner:design` | Design artifacts; no implementation unless separately requested |
| Explicit creation/refinement of an executable plan | `planner:plan-design` | Executable plan contract |
| Explicit execution of an existing plan/item | `planner:plan-run` | Existing plan lifecycle |
| Review | `planner:review` | Read-only findings |

An existing plan reference alone is input, not selection of the plan lifecycle. A current
instruction to implement directly or without a plan overrides older embedded successor-plan
instructions. An explicit request to create a plan and execute it authorizes both products.

Size, risk, cross-module scope, portability needs, plugin presence, or a relevant skill do not
authorize plan creation. Increase verification within the direct route when needed. If a local
project rule requires a workflow, cite its exact file and rule; do not infer it from discovery.

## Review is opt-in

No planner command starts an independent review, a review subagent or a phase audit by itself. The
default quality gate is a self-check plus the affected tests, each run once per relevant change.
A hard risk (security/auth, destructive migration, payments/accounting, concurrency/shared state,
public API/schema, irreversible external effect) widens those checks and is named in the final report
with a `planner:review` recommendation; it does not start a review.

Review runs only on an explicit owner request:

| Owner request | Result |
|:--|:--|
| `--review` in `planner:dev` or `planner:plan-run` arguments | one `planner:review` pass over the whole requested result, before the final close |
| `--review` in `planner:plan-design` arguments | the plan includes one `Review Pn` item at the end of the requested scope |
| `--reviewer provider/model` | explicitly requested separate native reviewer on that route; plan-run reviews its selected items |
| `planner:review` | standalone read-only review |
| `planner:plan-audit` | design or phase audit; JSON v3 audits run only on explicit owner invocation |

One review is one reviewer over the requested scope. `--reviewer` in `plan-run` explicitly requests
item-scoped independent sessions; otherwise do not split the scope or spawn subagents unless asked.
See `reviewer-selection.md` for exact selection and bounded automatic item rounds. A finding gets at most `policy.corrections_max` owning
fixes (default 1) and a re-check of that finding only; a second full review needs a new owner request.

Outside an explicitly selected plan route, do not require design finish, phase audit, plan
close, plan archival, status/roadmap carriers, or a launch/handoff file. A concise result or
evidence document explicitly requested by the owner remains an ordinary document.

Loading relevant guidance is distinct from selecting its workflow. A discovered planner skill must
remain unloaded until explicitly invoked. Its work product must match the current owner request. A design/research/
review request retains its boundary, and an explicit plan invocation retains the plan contract.

For persisted plans/tasks and work-specific references, apply
[work identity and references](../skills/plan-protocol/references/work-references.md):
assign stable `PLAN<N>`/`TASK<N>` when creating a document; qualify external references such as
`PLAN<N>.D35` or `TASK<N>.D2`. A message-only task needs no document or ID allocation.
