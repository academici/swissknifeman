<!-- Generated Codex runtime projection; do not edit as source.
Canonical source: packages/planner/commands/plan-audit.md
Canonical SHA-256: sha256:00787d0d0207672b8669544ece39360c45d2ea73b87b1e6bd601c6d6682a440b
Adapter: planner.codex-command/1.0.18
-->
## Native Codex launch-block — required only at a real user-facing boundary

This generated runtime is the Codex provider projection. `$ planner:…` runs inside the **current**
Codex session; never copy Claude Code slash syntax. Continue ready work of the requested scope in
this session: an item, a phase or a failed test is not a session boundary.

Only when the owner asks for a new session, print `**Native Codex command:**` and one fenced `bash`
line that pins the repository cwd, the model and effort mapped from the next item's route, approval
policy and sandbox (never put the command in a table cell):

```bash
codex -C <repo-cwd> -m <model-selector> -c 'model_reasoning_effort="<effort-selector>"' -a never -s danger-full-access '$ planner:<command> <arguments>'
```

Current Codex mapping: economy=gpt-6-luna, implementation=gpt-6-sol, frontier=gpt-6-astra; low=low, medium=medium, high=high, xhigh=xhigh.

## Codex planner CLI — provider-specific

`plan.py` means `python3 -I .swissknifeman/launcher.py planner`, run from the project root; the launcher binds the
project and hands over to the installed `swissknifeman`. Declare the route with
`--actor codex/<model>/<reasoning effort>` from this session's settings.

Project CLI: `plan.py` means `python3 -I .swissknifeman/launcher.py planner`, run from the project root (the launcher binds the project; without one, run `swissknifeman project init` once). Never locate or run a Swiss Knife Man package script.
Owner rules: run `plan.py overlays planner:plan-audit` first and follow any rules it prints as additions to this command; they never override the plan, its checks or safety rules.
Invocation payload: `$ARGUMENTS`.

Read `references/reviewer-selection.md` for optional `--reviewer` and effort selection.
Without a selector, select an active model entry tagged `audit` in the `model_inventory`
of `configs/command-routing.json`; prefer a provider different from `plan.authoring.provider`
when an eligible route is available. Record the observed route, never an inferred model. A session that executed this candidate
must hand the review to a fresh read-only session; never review its own work as independent evidence.

**Goal:** one independent verdict (GREEN / ATTENTION / RED) on a plan design or a finished phase.

**Steps**
0. `plan.py readiness status <plan> <Pn> --json` for a phase target (omit `<Pn>` for
   `design`). Read the current digest, certificate and changed components. A pending detailed
   phase is a design-check target; a finished phase is a product audit.
1. `plan.py check <plan>` and `plan.py show <plan>`; read the target phase and items with
   `plan.py show <plan> <ref>`.
2. `design`: judge whether each detailed item is executable from its context pack
   (`plan.py context <plan> <item> --stdout`): scope, reads, exact checks, decisions, dependencies.
   Apply this design check also to a pending detailed `Pn`. Execution economy is a required
   readiness dimension, with the same Major+ blocking severity as executability:
   - Measure item size: count scope kinds/modules and prompt bytes (rules, guidance and reads
     as whole files). Split an item that cannot fit one or two executor rounds.
   - Check write-set carriers for every changed contract: tests, fixtures, golden/digests,
     schema mirrors and generated provider projections must have an owner in the item.
   - Keep checks proportional: a cheap negative example per new rule in its own item; cheap
     schema/tag/golden checks stay local; remove duplicate hub jobs; place one group V20 under M4.
   - Keep D24 instructions coherent: one self-check line; flag “only targeted tests”, per-step
     commits and stale line-number instructions. Mechanical `plan.py check` warnings are leads
     to verify, not automatic audit findings.
   - Defer schemas, migrations and other volume with no downstream consumer. Record the
     measured cost and owning item for each economy finding.
3. `Pn`: compare the phase's product diff with item scope, recorded checks and deliverables; rerun
   only checks whose inputs changed.
4. Add a knowledge JSON document using `plan.py add-document <plan> --file <input.json>`:
   lowercase `id: audit-<scope>-<YYYY-MM-DD>`, title, `applies_to`, and `sections` for the verdict,
   findings (severity, evidence `path:line`, owning item) and recommendations. The API generates
   its human view; report the source `@plan/knowledge/<id>.json`.
5. For a phase-scoped design check, record its certificate after adding the audit document:
   `plan.py readiness record <plan> <Pn> --verdict <ready|ready_with_advisories|not_ready> --audit knowledge/<id> --actor <observed-provider/model[/effort]>`.
   Map GREEN → `ready`, ATTENTION → `ready_with_advisories`, RED → `not_ready`.
   Pass every finding as `--finding '{"id":"F1","severity":"major","blocking":true,"ref":"Pn.m","text":"evidence and impact"}'`.
   Any Major+ finding in executability or execution economy makes the phase `not_ready`;
   advisories contain only nonblocking minor findings. Structural or external errors forbid
   either ready verdict. A whole-plan audit records no whole-plan certificate.
6. `plan.py log <plan> <Pn> --type note --summary "audit <verdict>: <file>"` (`design`: the first target phase).

**Rules**
- Runs only on explicit owner invocation; one reviewer, one pass, no subagents unless asked.
- Read-only over product code and execution state; only the verdict document, phase readiness certificate and note are added through the API.
- A finding names its owning item; fixing it is `plan-run` work (`plan.py reopen` by the owner).
- Severity follows demonstrated impact; uncertainty is reported as a question, not a defect.

**Done when** the verdict file exists, the phase design-check certificate is recorded when applicable,
the note is logged, and the report gives the verdict and
`plan.py next <plan>`.
