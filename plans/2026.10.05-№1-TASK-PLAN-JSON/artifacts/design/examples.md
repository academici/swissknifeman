# PLAN1 worked examples

Concrete, copyable shapes for `research/00-design.md`. Values are illustrative; field order is canonical.

## E1. `plan.json`

```json
{
  "$schema": "urn:swissknifeman:task:plan:plan:v1",
  "id": "2026.10.05-№1-DEMO",
  "short_id": "PLAN7",
  "title": "Plan №1 — Demo",
  "status": "active",
  "created": "2026-10-05",
  "updated_at": "2026-10-05T10:00:00Z",
  "repository": "demo",
  "owner": "repository owner",
  "authoring": {"provider": "claude-code", "model": "claude-opus-5-5", "effort": "high"},
  "goal": "Config errors are reported at load time with all problems at once.",
  "context": "The loader crashes deep in runtime with KeyError …",
  "non_goals": ["Config format changes"],
  "rules": ["stdlib only", "English diagnostics"],
  "phases": ["P1"],
  "settings": {"design_audit": "none", "scout": "off"}
}
```

## E2. `phases/P1/phase.json`

```json
{
  "$schema": "urn:swissknifeman:task:plan:phase:v1",
  "id": "P1",
  "title": "Config validation",
  "design": "detailed",
  "goal": "load_config() rejects invalid configs with one aggregated error.",
  "context": "Loader lives in lib/pkg/config.py; tests in tests/test_config.py.",
  "scope": {"include": ["load_config validation"], "exclude": ["CLI flags"]},
  "pitfalls": ["Do not change behaviour for valid configs"],
  "validation": [{"id": "V1", "cmd": "bash scripts/test.sh", "expect": "exit 0", "kind": "acceptance"}],
  "deliverables": ["validated loader"],
  "items": ["P1.1", "P1.2"],
  "batches": [
    {"id": "B1", "items": ["P1.1", "P1.2"], "mode": "recommended", "note": "shared files and tests"}
  ],
  "closed": null
}
```

## E3. `phases/P1/P1.1.json` (detailed, after finish)

```json
{
  "$schema": "urn:swissknifeman:task:plan:item:v1",
  "id": "P1.1",
  "title": "Validate required keys",
  "status": "done",
  "summary": "load_config() checks required keys and types before first use.",
  "why": "Broken configs crash later with unclear KeyError.",
  "scope": {"include": ["load_config() and its tests"], "exclude": ["config file format"]},
  "depends_on": [],
  "related": [{"ref": "P1.2", "relation": "informs", "note": "P1.2 reuses the error collector"}],
  "decisions": ["D1"],
  "reads": [
    {"path": "lib/pkg/config.py", "why": "function to change", "required": true},
    {"path": "@plan/research/00-design.md", "section": "§2 Validation", "why": "error format", "required": true}
  ],
  "task_files": [
    {"path": "lib/pkg/config.py", "change": "modify"},
    {"path": "tests/test_config.py", "change": "modify"}
  ],
  "artifacts": [{"path": "@plan/artifacts/P1/error-catalog.md", "role": "output"}],
  "rules": ["Collect all errors, raise once"],
  "guidance": "Iterate REQUIRED_KEYS; append `ConfigIssue(key, problem)`; raise `ConfigError(issues)`.",
  "examples": [{"path": "@plan/artifacts/design/examples.md", "section": "E3"}],
  "validation": [
    {"id": "V1", "cmd": "python3 -m unittest tests/test_config.py", "expect": "OK", "kind": "acceptance"}
  ],
  "deliverables": ["validation in config.py", "3 new tests"],
  "route": {"class": "implementation", "effort": "medium"},
  "review": {"mode": "none"},
  "authority": {"kind": "routine"},
  "rag": {"need": "none", "status": "not_needed"},
  "units": [],
  "result": {
    "started_at": "2026-10-05T10:05:00Z",
    "finished_at": "2026-10-05T10:40:00Z",
    "executor": {"provider": "codex", "model": "gpt-6-sol", "effort": "high"},
    "notes": "3 tests added; aggregated error message.",
    "deviations": [],
    "pending": [],
    "escalation": null,
    "checks": [{"id": "V1", "exit": 0, "at": "2026-10-05T10:38:00Z", "summary": "Ran 14 tests OK"}],
    "commits": ["a1b2c3d"]
  },
  "updated_at": "2026-10-05T10:40:00Z"
}
```

Skeleton item (phase `design: skeleton`) — only required fields:

```json
{"$schema": "urn:swissknifeman:task:plan:item:v1", "id": "P2.1", "title": "TBD by phase design",
 "status": "todo", "summary": "Outcome placeholder", "why": "From plan goal",
 "scope": {"include": ["to be designed"], "exclude": []},
 "route": {"class": "implementation", "effort": "high"}, "review": {"mode": "none"},
 "authority": {"kind": "routine"}, "rag": {"need": "none", "status": "not_needed"},
 "result": null, "updated_at": "2026-10-05T10:00:00Z"}
```

## E3a. Item with units (orchestration, owner M3/M4)

Item `phases/P1/P1.1.json` has `"units": ["U1", "U2", "U3"]`; the workspace is `phases/P1/P1.1/`:

```text
phases/P1/P1.1/U1.json        phases/P1/P1.1/U1/brief.md   (generated at dispatch)  U1/report.md (worker)
phases/P1/P1.1/U2.json        phases/P1/P1.1/U2/brief.md
phases/P1/P1.1/U3.json
```

`phases/P1/P1.1/U1.json`:
```json
{"$schema": "urn:swissknifeman:task:plan:unit:v1", "id": "U1", "item": "P1.1", "title": "Error collector",
 "goal": "ConfigIssue/ConfigError types with tests",
 "files": ["lib/pkg/config_errors.py", "tests/test_config_errors.py"], "depends_on": [],
 "checks": [{"id": "V9", "cmd": "python3 -m unittest tests/test_config_errors.py", "expect": "OK", "kind": "acceptance"}],
 "route": {"class": "economy", "effort": "medium"}, "mode": "delegate",
 "instructions": "Pure dataclasses; message format from D1.", "status": "todo", "outcome": null,
 "updated_at": "2026-10-05T10:00:00Z"}
```
U2 (`docs/config.md`, mode `either`) has no dependency path to U1 and disjoint files → U1 and U2 may run in parallel;
U3 (`lib/pkg/config.py`, `depends_on: ["U1"]`, mode `self`) waits for U1 and stays with the executor.

```bash
python3 $T unit PLAN7 P1.1 add --title "Error collector" --json @u1.json
python3 $T unit PLAN7 P1.1 U1 dispatch --agent claude-code/haiku   # writes phases/P1/P1.1/U1/brief.md
python3 $T unit PLAN7 P1.1 U1 return --notes "2 files, tests green" --changed lib/pkg/config_errors.py
python3 $T unit PLAN7 P1.1 U1 accept --notes "reviewed diff, V9 rerun OK" --minutes 6
```

## E4. `decisions/D2.json` — open question, then accepted

```json
{
  "$schema": "urn:swissknifeman:task:plan:decision:v1",
  "id": "D2", "title": "Error language", "date": "2026-10-05", "status": "open",
  "question": "Diagnostics in English or Russian?",
  "options": [{"id": "A", "text": "English"}, {"id": "B", "text": "Russian"}],
  "applies_to": ["P1"],
  "actor": {"provider": "claude-code", "model": "claude-opus-5-5"}
}
```
`plan.py decide <plan> D2 --accept A --rationale "repo convention" --by owner` →
`status: accepted`, `decision: "A — English"`, `rationale`, `answered_by: owner`.

## E5. `log.jsonl` lines

```json
{"v":1,"ts":"2026-10-05T10:05:00Z","type":"start","item":"P1.1","phase":"P1","actor":{"provider":"codex","model":"gpt-6-sol","effort":"high"},"summary":"start P1.1 (batch B1)","data":{"requested":["P1.1","P1.2"],"route":"ok"}}
{"v":1,"ts":"2026-10-05T10:20:00Z","type":"difficulty","item":"P1.1","actor":{"provider":"codex","model":"gpt-6-sol"},"summary":"tests import config at module load; patched via fixture","impact":"P1.2 tests need the same fixture","next":"reuse tests/conftest fixture"}
{"v":1,"ts":"2026-10-05T10:40:00Z","type":"finish","item":"P1.1","phase":"P1","actor":{"provider":"codex","model":"gpt-6-sol"},"summary":"P1.1 done","data":{"status":"done"}}
```

## E6. CLI session (executor)

```bash
T=packages/task/scripts/plan.py
python3 $T next PLAN7
# run-items: task:plan-run 2026.10.05-№1-DEMO P1.1 P1.2  (implementation/medium)
python3 $T start PLAN7 P1.1 P1.2 --actor codex/gpt-6-sol/high
# Context packs: plans/2026.10.05-№1-DEMO/context/P1.1.md, …/P1.2.md — read P1.1 first.
python3 $T log PLAN7 P1.1 --type difficulty --summary "tests import config at module load" --next "reuse fixture"
python3 $T finish PLAN7 P1.1 --status done --check V1=0 --notes "3 tests added" --commit a1b2c3d
# P1.1 done. Next in batch: P1.2
```

Designer:
```bash
python3 $T add-phase PLAN7 --title "Config validation" --json '{"goal":"…"}'
python3 $T add-item PLAN7 P1 --title "Validate required keys" --json @item.json   # or --file item.json
python3 $T push PLAN7 P1.1 reads --json '{"path":"lib/pkg/config.py","why":"target","required":true}'
python3 $T batches PLAN7 P1 --json '[{"id":"B1","items":["P1.1","P1.2"],"mode":"recommended"}]'
python3 $T check PLAN7 && python3 $T design-done PLAN7 P1
```

## E7. Template + partial

`templates/plan/status.md`:
```text
<!-- generated by task plan.py render — edit JSON through plan.py -->
# Status — {{short_id}} {{title}}

**Plan status:** {{status_label}} · **Items:** {{done}}/{{total}} · **Updated:** {{updated}}

{{#phases}}
## {{id}} — {{title}} · {{status_label}}

| Item | Title | Status | Route | Updated |
|:--|:--|:--|:--|:--|
{{#items}}
{{>item-row}}
{{/items}}
{{#closed}}

Closed {{at}}: {{summary}}
{{/closed}}

{{/phases}}
```
`templates/plan/_item-row.md`:
```text
| {{id}} | {{title}} | {{status_label}} | {{route}} | {{updated}} |
```
Rendering rule check: the `{{#items}}`/`{{/items}}` and `{{>item-row}}` lines are standalone → no blank
lines between table rows.

## E8. Context pack excerpt (`context/P1.2.md`)

```markdown
# PLAN7.P1.2 — Validate types
Plan: Plan №1 — Demo · Phase P1 · Batch B1 (P1.1 ✓, P1.2) · Route implementation/medium
Finish: `plan.py finish PLAN7 P1.2 --status done --check V1=0 --notes "…"` · Friction: `plan.py log PLAN7 P1.2 --type difficulty --summary "…"`

## Goal
load_config() rejects wrong types … Why: …

## Scope
Include: … · Exclude: …

## Context
Phase P1: … Pitfalls: Do not change behaviour for valid configs. Rules: stdlib only; English diagnostics.

## Decisions
- D1 (accepted): collect all errors, raise once. Consequences: …

## Upstream results
- P1.1 🟢 Done — 3 tests added; aggregated error message. Outputs: @plan/artifacts/P1/error-catalog.md

## Reads
1. lib/pkg/config.py — function to change (required)
2. @plan/research/00-design.md §2 Validation — error format (required)
   > (inlined section text …)

## Files to change (hint)
- lib/pkg/config.py (modify, exists) · tests/test_config.py (modify, exists)

## Lessons
- 10:20 P1.1 difficulty: tests import config at module load → reuse tests/conftest fixture

## Done when
- V1 `python3 -m unittest tests/test_config.py` → OK (acceptance)
- Deliverables: type validation; tests
```

## E9. Migration mapping (v2 → v3) used by `docs/migration/v2-to-v3.md`

| v2 carrier / field | v3 target |
|:--|:--|
| `plan.md` Meta `Plan ID`, `Short ID`, `Title`, `Repository`, `Approval Owner`, `Authoring Model` | `plan.json` `id`, `short_id`, `title`, `repository`, `owner`, `authoring` (written by hand per the migration doc) |
| `plan.md` §1 Context | `plan.json.context` (first paragraph → `goal`) |
| `plan.md` §2 Execution Rules | `plan.json.rules[]` — one bullet per rule, keep ≤ 12, long rules → `@plan/_v2/plan.md` reference |
| `plan.md` §3 Routing row | item `route` (`class/effort`); `Batch` → `phase.batches`; `Review full|light` → `review.mode: none` unless owner asked |
| `brief/*.md` owner message | `brief.json.messages[]` verbatim; requirement table → `requirements[]` |
| `phases/Pn/Pn.md` Phase Context / Scope / Dependencies / Pitfalls / Validation / Deliverables / Assurance | `phase.json` `context` / `scope` / `depends_on` / `pitfalls` / `validation` / `deliverables` / `assurance` |
| `> SKELETON` marker | `design: skeleton`; otherwise `detailed` (set by `design-done` after `check`) |
| item `Intent`, `Why`, `Scope Included/Excluded` | `summary`, `why`, `scope.include/exclude` |
| item `Inputs` + `Required Reads` | `reads[]` (Required Reads `required: true` in their order, then Inputs not already listed `required: false`) |
| item `Files` | `task_files[]` (`change: any` unless the text says create/delete) |
| item `Implementation Rules`, `Code Guidance`, `Validation`, `Deliverables` | `rules[]`, `guidance`, `validation[]` (`V1…` per command, `kind: acceptance`), `deliverables[]` |
| item `Authority` `[OWNER-GATE:X] … scope=…` | `authority: {kind: owner_gate, gate: X, scope}` |
| state `Status` emoji | `status` enum (table in §4 of dossier) |
| state `Completion Notes`, `Known Deviations`, `Pending Work`, `Escalation Needed` | `result.notes`, `result.deviations[]`, `result.pending[]`, `result.escalation` |
| `decisions/D*.md` (frontmatter + `## Solution`/`Decision`, `Rationale`/`Why`) | `decisions/D*.json` (`status`, `decision`, `rationale`, `applies_to` = `items`, `supersedes`, `superseded_by`) |
| `journal.jsonl`, `bundles/`, `*.state.md`, `.plan-cache/`, `session-routing.md`, `decisions/_*.md`, `closure/` | moved to `_v2/` unchanged; one `migrated` log event |
| `research/`, `artifacts/`, `findings/`, `backlog/` | stay in place; referenced by `@plan/...` paths |
