# Layout template v2: `phases/<Pn>/<Pn>.md` + `<Pn.m>.md`

Layout v2 separates the stable Phase Context/item spec from the generated state. Phase Status
five result fields and Phase Handoff belong to `status.md`, `<Pn.m>.state.md` and
`handoff.md`/`<Pn>.closed.md`. The first item (P1.1) is a fully completed SAMPLE (which
level of detail required, including RAG markers on supporting facts - SKILL
section 7), the second (Pn.m) is an empty skeleton with the canonical “—”.

A phase that is intentionally NOT detailed during authoring carries in the Phase Context
fixed marker string (with it, empty items fields are legal, including
Code Guidance = "—"; without it, an empty Code Guidance is a defect in the plan):

```text
> SKELETON — not detailed, expands `design-phase: task:plan-design <ID> Pn`
```

Optional (**contract-first** mode, skill `plan-protocol` §5) the phase additionally carries
in Phase Context **contract block** - what it consumes from previous phases / produces for
does not deliberately touch the following /. Block optional (absence ≠ defect, skeleton marker
independent):

```text
> **Contract-first).** Consumes: ... Produces: ... Boundaries: ...
```

```markdown
#P1 - <Phase Title>

## Phase Context

<5–10 lines, self-sufficient: what the phase does, what it stands on, what is considered
its completion. The phase is executable without reading other phases.>

<Optional (contract-first, skill plan-protocol §5) - phase contract block:>
> **Contract-first).** Consumes: ... Produces: ... Boundaries: ...

<!-- Phase Assurance omitted = isolated/reversible/direct-close. Add the v1 block only for an
integration seam, hard risk, live/irreversible action, owner-requested audit, or ambiguous default. -->

## DoR (Definition of Ready)

<Runs plan-design before issuing “phase ready”; clearly admitted plan-audit verifies
after the fact. Fixed checklist - SKILL section 7.>

- [ ] All `[NEEDS CLARIFICATION]` are cleared (0 markers in phase).
- [ ] Scope Included / Scope Excluded phases are full (equivalent to Goals/Non-Goals).
- [ ] Alternatives for carrier solutions are recorded in the D-log.
- [ ] Open Questions are divided into `open-questions.md` statuses.
- [ ] Carrying facts carry RAG markers (`RAG:✅ ...` / `[UNVERIFIED]`).

<!-- Phase Status lives in status.md. -->

## Supporting artifacts (only for a complex handoff)

- Full implementation dossier: `research/<Pn>-design.md`.
- Retrieval synthesis and verification boundary: `research/<Pn>-design-rag.md`.
- Concrete execution examples: `artifacts/<Pn>-design/examples.md`.
- Raw capture or explicit no-search record: `artifacts/<Pn>-design-rag/capture.md` or `README.md`.

Remove this entire section for an ordinary phase. If used, affected items name the first three
carriers in `Inputs`. Raw retrieval is provenance, not a normative decision.

| ID | Title | Status | Updated |
|:--|:--|:--|:--|
| P1.1 | Validation of config upon loading | ⬜ Not started | <YYYY-MM-DD> |
| P1.2 | <title> | ⬜ Not started | <YYYY-MM-DD> |

### P1.1 — Validation of config upon loading

<!-- Status lives in item-state-template.md. -->
**Intent:** Add check to load_config() for required keys and types before first use.
**Why:** The broken config is now crashing deep in runtime with an unclear KeyError - diagnostics are expensive; ~a third of onboarding incidents are broken configs [UNVERIFIED].
**Scope Included:** load_config() function and its tests.
**Scope Excluded:** format of the config itself; migration of existing configs; CLI flags.
**Inputs:** list of required keys - in load_config() docstring; schema - schema/config.json. (Add dossier carriers only if they are created and needed by the performer.)
**Files:** lib/pkg/config.py · tests/test_config.py
**Required Reads:** 1) lib/pkg/config.py 2) tests/test_config.py 3) schema/config.json
**Implementation Rules:** stdlib-only (RAG:✅ 2026-07-02 “python json schema validation stdlib” - jsonschema requires pip, and pip is not allowed in the target environment); die() messages in Russian; Do not change the existing behavior of valid configs.
**Code Guidance:** manual check of dict keys (NOT jsonschema - pip is prohibited); collect errors in a list and crash in one die() with all of them at once; do not introduce new abstractions; mandatory test for each error class (missing key, wrong type); It is forbidden to swallow exceptions through try/except pass.
**Validation:** bash scripts/test.sh - green; manually running it with a broken config gives a clear error.
**Deliverables:** validation in config.py + ≥3 new tests. (If the item carries a RAG squeeze/recon -
declare the file here: `plans/<PLAN-ID>/findings/P1-config-validation.md`.)
**Completion Notes:** —
**Pending Work:** —
**Known Deviations:** —
**Escalation Needed:** —

### Pn.m — <Title>

**Status:** ⬜ Not started
**Intent:** —
**Why:** —
**Scope Included:** —
**Scope Excluded:** —
**Inputs:** —
**Files:** —
**Required Reads:** —
**Implementation Rules:** —
**Code Guidance:** —
**Validation:** —
**Deliverables:** —
**Completion Notes:** —
**Pending Work:** —
**Known Deviations:** —
**Escalation Needed:** —

## Phase Handoff

<To be filled in when the phase is closed: what was passed, known deviations, what’s next.>
```
