# Templates Task plan-protocol - reference

All skeletons of plan documents live in one set of snippets in the SSOT skill:
`packages/skiller/skills/general/plan-protocol/snippets/` (manifest - `index.json` ibid.).
This page is an index of “which template is for what”; content is NOT duplicated - single
source of truth > copies. The commands `/task:plan-*` take skeletons from there automatically.

| Template (snippet) | For what | Key in v2 |
|:--|:--|:--|
| `plan-template.md` | skeleton `plan.md`: Meta, Context, Execution Rules, Routing, Status Board, Decision/Update Log | required Batch/Items/route/Exec/Review/Why; `solo` only with reason |
| `phase-template.md` | stable phase index/item spec | v2 separates spec from generated state |
| `handoff-template.md` | skeleton rolling `handoff.md`: Next/Done/Remaining/Sources of truth/Open risks | execution Next saves Batch and remaining suffix |
| `launch-block-template.md` | fixed form “what to run next”: table Batch/Model/Thinking/Context/Essence + separate command block | provider-native copy-safe command; Batch from Routing; cold-start and hard boundary rules |
| `active-template.md` | 4-line index `plans/ACTIVE.md` | parses `plan-lint` byte-to-byte |
| `code-guidance-patterns.md` | 3 Code Guidance patterns for typical item's classes | anti-conformance/contract · anti-self-deception (gate) · if-then escalation to D# |
| `decision-record-template.md` | append-only `decisions/<D-id>.md` | YAML id/date/status/item/items/supersedes/superseded_by; literal `Solution`/`Why`, `## Consequences` on substitution |
| `item-state-template.md` | generated `<Pn.m>.state.md` | five volatile result fields; cannot be edited by hand |
| `closure-template.md` | opt-in judgment evidence `closure/<Pn>.json` | complements, does not replace generated `<Pn>.closed.md` |

## How to use it

- **New plan/phase** - do not assemble by hand: `/task:plan-design` unfolds
  `plan-template.md` and `phase-template.md` itself.
- **Handoff** — `plan-run`/`plan-close` overwrite `handoff.md` by
  `handoff-template.md`; The Next block must be launch-block'th
  (`launch-block-template.md`) - checked by `plan-lint`.
- **Code Guidance item'a** - wording is not invented: a suitable pattern is taken from
  `code-guidance-patterns.md` and is parameterized under item.

Field schemes and filling rules - skill `general/plan-protocol` and
`references/plan-layout-v2.md`. Validator: `python3 packages/task/scripts/plan-lint.py
plans/<PLAN-ID>` - new 2.0 checks (skeleton marker, field order, launch-block,
`[NEEDS CLARIFICATION]` at 🟡+, Update Log limit) are issued at the warning level.
