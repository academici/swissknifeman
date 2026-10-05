# Plan.md template - copy to plans/<PLAN-ID>/plan.md

Skeleton of the master plan according to the `plan-protocol` protocol. PLAN-ID of the new plan -
`<YYYY>.<MM>.<DD>-№<N>-<CODE-NAME>` (e.g.),
where `N` is a positive number, unique within the date; Title starts with
`Plan No. N -...`. Old date and `[A-Z][A-Z0-9-]+` IDs are saved only for
back-compat. New Plan Gets Meta`Short ID | PLAN<N>`: permanent number for the repository,
including archive, regardless of day No. N. External links: `PLAN<N>.D35`, `PLAN<N>.P2.3`;
assignment rule and legacy fallback - `references/work-references.md`.
Do not invent numbers or count them manually: `python3 packages/task/scripts/plan-id.py --codename <CODE-NAME>`
(scans `plans/` and `plans/archive/`) gives ready-made `plan_id`, `title_prefix` and `short_id` - substitute as is.
Stored format - only Markdown with hard markers; JSON - derived
parser artifact, not the source of truth.

The design fork lives in the `## Discussion` section (provenance: options + required
status - `Exploration` / `Decision pending` / `Resolved → D#`); everything that is NOT `Resolved`,
is additionally maintained in `plans/<PLAN-ID>/open-questions.md` (unclosed tracker);
protocol - SKILL section 3.
Ambiguity in the text - marker `[NEEDS CLARIFICATION: <question>]` (section 7).

```markdown
# <PLAN-ID> - Plan No. N - <Title>

## 0. Meta

| Field | Meaning |
|:--|:--|
| Plan ID | <PLAN-ID> |
| Short ID | PLAN<next available repository number> |
| Title | Plan #N - <short name of plan> |
| Layout | v2 |
| Version | 0.1.0 |
| Document Type | Executable Master Plan |
| Authoring Model | frontier |
| Repository | <repo> |
| Related Packages | <pkg1, pkg2> |
| Execution Mode | phase-first |
| Target Operator Classes | implementation (exec) · economy (LOW) · frontier (design/audit) |
| Approval Owner | <person approving the plan> |
| Home | repo:<repository> |
| visibility | <optional: private OR public, default private; public → in git there is only public extraction, SKILL section 4> |
| supersedes | <optional: old PLAN-ID whose track wave the plan is replacing; predecessor in plans/archive/> |
| Paused By | <optional: PLAN-ID of interceptor ACTIVE + date; fills in plan-design new; no — “—”> |

## 1. Context

<5–15 lines: what we do and why. Self-sufficient - the performer does NOT see
discussion in which the plan was born.>

## 2. Execution Rules

<Squeeze ≤20 lines + plan-specific deviations. Full protocol - skill
plan-protocol; do not copy it entirely. Minimum:>
- One item at a time; the status is updated IN PLAN until the work is completed.
- Statuses - 6 canonical byte-to-byte lines (see plan-protocol §5).
- Plan diverges from code → do not improvise, escalate (§8).
- After closing the item/phase, overwrite plans/<PLAN-ID>/handoff.md.

## 3. Routing

<LINE BY LINE coverage of all items. Batch/Review are required: `solo` only with a specific
cause; connected adjacent items of the same phase should be grouped if the general context saves
re-read/setup/validation. The group does not cross audit/close and does not mix Exec.
Exec: `run` (execution under the session route) or `plan-design`; legacy `plan-exec`/`manual`/`plan-run` are read as `run`.
Review is opt-in: Review=`none` unless the owner asked for review of the scope (`--review` or an explicit
request); hard risk widens validation and is reported, it does not raise Review. Requested independent
review - one separate item `Review Pn` (read-only, verdict file) at the end of the requested scope.
Do not write `Independent review` in the Validation item.
Only semantic classes `economy|implementation|frontier`, not provider selectors.
Design finish raises the batch to maximum class/effort/review and fixes
exact admission in `roadmap.md` execution sheet.>

| Batch | Items | Model class/effort | Exec | Review | Why |
|:--|:--|:--|:--|:--|:--|
| B1 | <Pn.m> | <implementation/high> | run | none | recommended: <low-risk; self-check + affected tests; general reads/setup> |
| B1 | <Pn.(m+1)> | <implementation/high> | run | none | recommended: <bounded integration seam; add the package/integration check to Validation> |
| solo | <Pn.k> | <frontier/high> | run | full | <only when the owner requested review of this item> |

## 5. Decision Log

Solutions catalog: `decisions/`; collect:
`python3 packages/task/scripts/plan-views.py decisions`.

## 6. Update Log

| Date | Who (role/model) | What |
|:--|:--|:--|
| <YYYY-MM-DD> | issue-planner/frontier/high | Plan created |

## 7. Contracts

<OPTIONAL: Only for plans that export/consume frozen contracts.
If you do not export or consume, the section is REMOVED (its absence is not a defect).>

### Exported

| Contract | Version | Status | Consumers | Notified |
|:--|:--|:--|:--|:--|
| <root/contracts/<name>.md> | v1.0.0 | frozen | <PLAN-ID (Pn.m)> | <YYYY-MM-DD> |

### Consumed

| Contract | Donor plan | Pinned | Spotted | Reaction |
|:--|:--|:--|:--|:--|
| <DONOR/root/contracts/<name>.md> | <DONOR-ID> | v1.0.0 | — | — |

## Discussion

<OPTIONAL, WITHOUT number, last section. There are no forks - DELETE section.>

### 1 — <fork in one line>

- **(recommended) Option A.** Pros... Cons...
- **Option B.** Pros... Cons...

**Status:** Resolved → D# | Decision pending (owner needed) | Exploration
```
