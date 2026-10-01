# Phase closure report template — `plans/<PLAN-ID>/closure/<Pn>.json` (schema v1)

Machine-readable phase evidence stored beside, not instead of, the generated layout-v2
`phases/<Pn>/<Pn>.closed.md`. Enable it with `Closure Protocol | v1` in `## 0. Meta`.
Plans without this field are unaffected, and existing closed records are never rewritten.

Writes phase-closing lifecycle of the current `plan-run` or explicitly called standalone
`plan-close <ID> Pn` from the items/state fields (retelling is prohibited).
Read: `plan_lint` (scheme + reconciliation with `## Phase Status` and Status Board) and `plan-audit <ID> Pn`
(checking the relevance of evidence bindings; repeating only invalid/changed delta and live boundary,
detection of editing phase specifications after closing by `inputs_sha256`).

## Entire file

```json
{
  "schema_version": 1,
  "plan": "",
  "phase": "P8",
  "closed_at": "2026-07-30",
  "closed_by": {"command": "plan-run", "actor": "implementation/medium"},
  "phase_status": "🟢 Done",
  "git": {"head_sha": "<40 hex>", "branch": "<branch>", "dirty": false},
  "inputs_sha256": {"plan.md": "<64 hex>", "phases/P8.md": "<64 hex>"},
  "items": [
    {"id": "P8.7", "status": "🟢 Done", "evidence_class": "real",
     "evidence": "PYTHONPATH=. python3 -m unittest core.tests.test_io -v - 9 passed (on <sha>)"},
    {"id": "P8.9", "status": "🟠 Done with deviations", "evidence_class": "synthetic",
     "evidence": "one fixture run: tests/fixtures/eval-one-case.json — 1 case, not a corpus"}
  ],
  "gates": [
    {"id": "validate.sh:task", "status": "PASS", "evidence_class": "real",
     "evidence": "bash packages/task/scripts/validate.sh - exit 0 (on <sha>)"},
    {"id": "fleet-adoption", "status": "PENDING", "evidence_class": "baseline_pending",
     "evidence": "no live plan except ECO-OPT enabled Closure Protocol v1"}
  ],
  "metrics": [
    {"name": "lint_new_from_closure", "value": "0", "label": "real"},
    {"name": "docs_impact_blocked_changes", "value": "—", "label": "baseline_pending"}
  ],
  "limitations": ["capability matrix tested on 2 of 9 surfaces"],
  "external_side_effects": []
}
```

## Filling rules

| Field | Rule |
|:--|:--|
| `schema_version` | exactly `1` (number). There are no other versions of the scheme |
| `plan` / `phase` | match the actual PLAN-ID and `Pn` - otherwise ERROR linter |
| `closed_at` | Phase closing ISO date (same as `Last Updated` in Meta) |
| `closed_by` | `command` - actual phase-closing lifecycle (`plan-run` or standalone `plan-close`; legacy `plan-exec` stays readable); `actor` — its neutral route `<model class>/<effort>` |
| `phase_status` | Exact phase status from `## 4. Phase Index & Status Board` |
| `git` | `head_sha` (40 hex, number anchor §8), `branch`, `dirty` (bool - whether the tree was dirty) |
| `inputs_sha256` | sha256 `plan.md` and `phases/<Pn>.md` at the time of closing; consumer - `plan-audit` |
| `items[]` | One entry per phase item; `id` and `status` must match `## Phase Status` |
| `gates[]` | submission gates (`validate.sh:<package>`, CI-job, field run): `id`/`status`/class/proof |
| `metrics[]` | change numbers: `name`/`value` (STRING - not float)/`label` (same enum classes) |
| `limitations[]` | fair surrender limits; nothing to say - an empty list, not the absence of a key |
| `external_side_effects[]` | what is touched OUTSIDE the repository (foreign trees, machine state, fleet) |

**Missing key = schema error, not "no data".** "No number" is expressed by VALUE:
record with `baseline_pending` and a reason - this is why the technique was taken.

## Evidence class (`evidence_class`, for metrics - `label`)

| Meaning | When |
|:--|:--|
| `real` | run on a COMMITTED tree; `evidence` carries the command and its output/number (empty evidence when `real` = ERROR) |
| `synthetic` | fixture / one case / simulation - `evidence` MUST call it words |
| `baseline_pending` | no number; `evidence` names the REASON (no baseline, nothing to run the gate on, we are waiting for a field run) |

This is the axis “on what DATA the result was obtained.” It does NOT replace a closed list of classes
EVIDENCE `recomputed` / `cross-checked` / `pinned-not-recomputable` / `unknown`
(`source-evidence-verification-v1.md`, SKILL §13 - “is the statement deducible from the commercial
bundle"): both dictionaries act simultaneously, neither one overrides the other.
