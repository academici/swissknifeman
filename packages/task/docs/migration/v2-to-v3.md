# Migrating a Task plan from layout v2 (Markdown) to v3 (JSON)

Manual procedure for one plan. Written so a model with no Task background can follow it step by step.
There is no migration code: you write the JSON files yourself and `plan.py check` tells you what is
wrong. Delete this file once every owner plan is migrated.

Placeholders: `<PLAN>` = plan directory id (`2026.10.05-№1-TASK-PLAN-JSON`), `<DIR>` = `plans/<PLAN>`,
`<SHORT>` = Short ID (`PLAN1`), `<T>` = `python3 <Task package root>/scripts/plan.py`,
`<NOW>` = current UTC time `YYYY-MM-DDTHH:MM:SSZ`, `<ME>` = your `provider`/`model`, for example
`{"provider": "claude-code", "model": "claude-sonnet-5-5"}`. Run every command from the repository root.

## 0. Preconditions — stop if any fails

1. `test -f <DIR>/plan.md && test ! -f <DIR>/plan.json && echo OK` prints `OK`.
2. `git status --short <DIR>` prints nothing (commit or ask the owner first). If `git check-ignore <DIR>/plan.md`
   prints a path, the plan is not tracked (for example `plans/` is gitignored): note it — use `mv`/`rm -r`
   instead of `git mv`/`git rm` below, keep a copy `cp -a <DIR> <backup outside the repo>` first, and skip the commit in step 6.
3. `<T> --help` prints the verb list.
4. Nothing in `<DIR>` is `🔄 In progress`: `grep -rl "In progress" <DIR>/phases` prints nothing. If it does,
   ask the owner whether to finish that item first.

## 1. Move the v2 carriers away

```bash
mkdir <DIR>/_v2
cd <DIR> && git mv plan.md index.md roadmap.md status.md handoff.md open-questions.md phases decisions _v2/ && cd -
cd <DIR> && for f in journal.jsonl bundles session-routing.md closure .plan-cache; do [ -e "$f" ] && git mv "$f" _v2/; done; cd -
```

For an untracked plan replace every `git mv` with `mv`. Expected: `ls <DIR>` shows `_v2` plus `research/`, `artifacts/`, `brief/`, `findings/`, `backlog/` if they
existed. Those stay in place; refer to them as `@plan/research/...` etc. `_v2/` is temporary and is never referenced from JSON. A `git mv` error for a missing file
is fine; any other error → stop and ask. From now on read v2 text only from `<DIR>/_v2/`.

## 2. Write the plan skeleton (4 files)

Read `_v2/plan.md` Meta table and §1–§2, and `brief/*.md` (the owner's first message). Write:

`<DIR>/plan.json`
```json
{
  "$schema": "urn:swissknifeman:task:plan:plan:v1",
  "id": "<PLAN>", "short_id": "<SHORT>", "title": "<Meta Title, prefix 'Plan №N —'>",
  "status": "active", "created": "<YYYY-MM-DD from the plan id>", "updated_at": "<NOW>",
  "repository": "<Meta Repository>", "owner": "<Meta Approval Owner or 'repository owner'>",
  "authoring": {"provider": "<from Meta Authoring Model>", "model": "<model id>"},
  "goal": "<first paragraph of §1 Context>", "context": "<rest of §1, max ~15 lines>",
  "rules": ["<one string per §2 Execution Rules bullet, at most 12>"],
  "phases": ["P1", "P2"],
  "settings": {"design_audit": "none", "scout": "off"}
}
```
`<DIR>/brief.json`
```json
{"$schema": "urn:swissknifeman:task:plan:brief:v1",
 "messages": [{"id": "M1", "date": "<YYYY-MM-DD>", "text": "<owner message, verbatim>"}],
 "requirements": []}
```
One `messages[]` entry per owner message in `brief/*.md` (`M1`, `M2`…; keep the text verbatim without the `>`
quote marks). Each row of a requirements table (`B1 | text | owner`) becomes `requirements[]`:
`{"id": "B1", "text": "…", "source": "M1", "owners": ["D1", "P1.1"]}`; an `Environment` list becomes `environment[]`.
`<DIR>/.gitignore` — exactly two lines: `context/` and `.lock`.

`<DIR>/log.jsonl` — exactly one line:
```json
{"v":1,"ts":"<NOW>","type":"migrated","summary":"migrated from layout v2; old carriers in _v2/","actor":<ME>}
```

## 3. Per phase: write `phases/<Pn>/phase.json`

Source: `_v2/phases/<Pn>/<Pn>.md`. Rules: a `> SKELETON` marker → `"design": "skeleton"`, otherwise
`"detailed"`. A `<Pn>.closed.md` file (or every item terminal) → fill `closed`, else `"closed": null`.
A `Phase Contract` block (Consumes / Produces / Boundaries) → `contract: {"consumes": [...], "produces": [...], "boundaries": [...]}`;
a `Phase Assurance` block → `assurance: {"impact": "…", "seams": [...], "live": false, "note": "<Rationale and Audit Intent>"}`.

```json
{
  "$schema": "urn:swissknifeman:task:plan:phase:v1",
  "id": "<Pn>", "title": "<phase title>", "design": "detailed",
  "goal": "<first sentence of Phase Context>", "context": "<Phase Context>",
  "scope": {"include": ["<Scope Included lines>"], "exclude": ["<Scope Excluded lines>"]},
  "depends_on": ["<Pn-1>"], "pitfalls": ["<one per Pitfalls bullet>"],
  "validation": [{"id": "V1", "cmd": "<exact command>", "expect": "<expected>", "kind": "acceptance"}],
  "deliverables": ["<Deliverables>"],
  "items": ["<Pn>.1", "<Pn>.2"],
  "batches": [{"id": "B1", "items": ["<Pn>.1", "<Pn>.2"], "mode": "recommended"}],
  "closed": {"at": "<NOW>", "result": "done", "summary": "<N> item(s): <N> done"}
}
```
Batches: take the `Batch` column of `_v2/plan.md` §3 Routing (or `_v2/roadmap.md` execution sheet); items
with the same batch go in one batch; an item without a batch (including `solo`) gets its own `B<Pn>-<m>`, for
example `BP3-1`, so batch ids stay unique across phases. `closed.result` is the
worst item result in this order: `skipped` < `done` < `done_with_deviations` < `blocked`.

## 4. Per item: write `phases/<Pn>/<Pn.m>.json`

Sources: `_v2/phases/<Pn>/<Pn.m>.md` (spec) and `_v2/phases/<Pn>/<Pn.m>.state.md` (state).

| v2 | v3 field |
|:--|:--|
| `### Pn.m — <title>` | `title` |
| Intent / Why | `summary` / `why` |
| Scope Included / Scope Excluded | `scope.include[]` / `scope.exclude[]` (one string per bullet) |
| Required Reads (numbered) | `reads[]` in order, `required: true`; `section` = the `§…` part; a decision becomes `@plan/decisions/<D#>.json` |
| Inputs not already in Required Reads | `reads[]`, `required: false`; plan files as `@plan/<path>` |
| Files | `task_files[]`, `change: "any"` unless the text says create/delete; one entry per path (no `{a,b}` brace lists: `check` warns `modify_missing`) |
| Implementation Rules / Code Guidance | `rules[]` / `guidance` (one string) |
| Validation (one bullet per command) | `validation[]`: `V1`, `V2`… with `cmd`, `expect`, `kind: "acceptance"`; a bullet that is a prose control (negative test, `ls` expectation) still gets the command that proves it, with the prose in `expect`; a manual live check gets `kind: "live"` |
| Deliverables | `deliverables[]` |
| Routing row class/effort | `route` (`economy`, `implementation` or `frontier`; effort `low`…`xhigh`) |
| `Authority [OWNER-GATE:X] … scope=S` | `authority: {"kind": "owner_gate", "gate": "X", "scope": "S"}`; else `{"kind": "routine"}` |
| Dependencies on other items | `depends_on[]` (from the phase `Dependencies` section, e.g. `P1.1 → P1.2` makes `P1.2` depend on `P1.1`; the phase itself carries `depends_on`) |
| state Status | `status` (table below) |
| state Completion Notes / Known Deviations / Pending Work / Escalation | `result.notes` / `result.deviations[]` / `result.pending[]` / `result.escalation` |

| v2 Status | `status` | `result` must contain |
|:--|:--|:--|
| ⬜ Not started | `todo` | `"result": null` |
| 🔄 In progress | `in_progress` | `started_at` |
| 🟢 Done | `done` | `finished_at` |
| 🟡 / 🟠 Done with deviations | `done_with_deviations` | `finished_at`, `deviations` (split `Known Deviations` on `;` into strings) |
| 🔴 Blocked | `blocked` | `escalation` |
| ⚪ Skipped | `skipped` | `decision` (`D#` that skipped it) |

Timestamps: take the item's dates from the state file or `_v2/journal.jsonl`; if only a date is known use
`<date>T00:00:00Z`. Always add `"review": {"mode": "none"}`, `"rag": {"need": "none", "status": "not_needed"}`,
`"updated_at": "<NOW>"`. Do not invent `result.checks` or `result.commits`; copy commit SHAs only when the
state file names them.

## 5. Decisions: write `decisions/<D#>.json`

Source: `_v2/decisions/D*.md` (skip `_index.md`, `_current.md`, `_archive.md`).
```json
{"$schema": "urn:swissknifeman:task:plan:decision:v1", "id": "D1", "title": "<title>", "date": "<frontmatter date>",
 "status": "accepted", "decision": "<## Solution text>", "rationale": "<## Why text>",
 "consequences": ["<one string per ## Consequences bullet>"], "applies_to": ["<frontmatter items>"],
 "supersedes": [], "superseded_by": null, "actor": <ME or the record's Actor>}
```
The frontmatter `Actor:` line becomes `actor` (`claude-code` + the model id); `Evidence:` lines become `evidence[]`
(`{"kind": "repo|rag|owner", "ref": "<path>", "note": "…"}`). `status: open` needs `question` instead of `decision`/`rationale`. Copy texts in full; `_v2/` is deleted in step 6.

## 6. Check, render, verify

1. `<T> check <PLAN>` — repeat after every phase. Fix each reported `CODE: path: message` in the named file;
   never delete a field just to silence an error you do not understand.
2. `<T> render <PLAN>` — writes the Markdown views, `AGENTS.md`, `CLAUDE.md`.
3. `<T> check <PLAN>` → `0 error(s)`; `<T> show <PLAN>` lists every phase and item with the v2 statuses;
   `<T> next <PLAN>` names the step the v2 handoff named.
4. Remove the old carriers (git history keeps them): `git rm -r -q <DIR>/_v2`; for an untracked plan `rm -r <DIR>/_v2`
   (your backup from step 0 is then the only copy).
5. Commit: `git add <DIR> && git commit -m "chore(plan): migrate <SHORT> to layout v3"`. Skip this for an untracked plan.

## Worked example — one item

v2 `_v2/phases/P1/P1.2.md` + state `🟢 Done`, notes "store and ops done":
```text
### P1.2 — Store and authoring API
**Intent:** plan JSON is written only through ops.  **Why:** B2.
**Scope Included:** - store.py - ops.py     **Scope Excluded:** CLI
**Required Reads:** 1) research/00-design.md §4
**Files:** packages/task/lib/task/plan/store.py; packages/task/lib/task/plan/ops.py
**Validation:** - `python3 -m unittest discover -s packages/task/tests/engine` → OK
**Deliverables:** store and ops modules
```
v3 `phases/P1/P1.2.json`:
```json
{"$schema": "urn:swissknifeman:task:plan:item:v1", "id": "P1.2", "title": "Store and authoring API",
 "status": "done", "summary": "plan JSON is written only through ops.", "why": "B2.",
 "scope": {"include": ["store.py", "ops.py"], "exclude": ["CLI"]},
 "reads": [{"path": "@plan/research/00-design.md", "section": "§4", "why": "store design", "required": true}],
 "task_files": [{"path": "packages/task/lib/task/plan/store.py", "change": "any"},
                {"path": "packages/task/lib/task/plan/ops.py", "change": "any"}],
 "validation": [{"id": "V1", "cmd": "python3 -m unittest discover -s packages/task/tests/engine", "expect": "OK", "kind": "acceptance"}],
 "deliverables": ["store and ops modules"],
 "route": {"class": "frontier", "effort": "high"}, "review": {"mode": "none"}, "authority": {"kind": "routine"},
 "rag": {"need": "none", "status": "not_needed"},
 "result": {"finished_at": "2026-10-05T00:00:00Z", "notes": "store and ops done"},
 "updated_at": "<NOW>"}
```

## Stop and ask the owner when

- a status is ambiguous (state file and journal disagree, or an item is half done);
- a decision has no Solution/Decision text, or two decisions contradict;
- an item has no Validation command (v3 needs one acceptance check for a detailed phase);
- `plan.py check` reports an error you cannot map to a field in this document;
- the plan directory holds files not named here that look like plan state.
