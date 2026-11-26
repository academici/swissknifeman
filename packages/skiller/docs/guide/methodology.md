# Methodology: against code bloat

How to simultaneously develop a product and the common packages on which it depends, **not
inflating** packages with speculative abstractions and technical debt. Document
formulates the principles and shows what skills and registry configs they
supported.

Generalized terminology: **dependent package** — any generic package
(composer/npm/…), **consumer project** — any project that depends on it.
The principles apply to any ecosystem «product ↔ package».

## Diagnosis: Why shared code is bloated

**Speculative Generality.** Having received the task «render general», agent (or person)
designs «for growth The»: interface where there is one implementation; abstract
`BaseService`; parameter «in case you need it». YAGNI requires
the opposite - implement only what is needed now.

**Premature generalization.** Transfer logic to package before pattern
repeated in two **independent** places. Rule of Three (Fowler): generalize to
third repetition, and not on the second, and especially not on the imaginary future.

**Silent package modification.** Agent working on a product without approval
adds a method/extends a contract in a dependent package, «because it's convenient».
Each product task quietly expands the package - this is the source
bloat.

**Specifics of the AI ​​agent.** The agent is prone to escalation of complexity: for each task
build «correct architecture» from scratch, without knowing the boundaries of what already exists.
Without explicit checks, this results in duplicate abstractions and growth of interfaces.

## Dual-mode model

**Mode 1 - task in the product.** Dependent package = **read-only dependency**, like
any external. Lack of functionality → **issue to the package** + temporary
implementation on the consumer side. Not a line in the package without an explicit ticket.

**Mode 2 - package development.** Package **doesn't know** about consumers: none
inverse product dependencies (Dependency Inversion). Expansion - via
contracts/events, not monkey-patching; public contracts - under ADR.

## Central Principle: Stop and Ask

Default - **ask rather than expand**. Before introducing a new
class/provider/interface/abstraction:

1. **Structure Overview** — is there no extension point already? (contract, event, config,
   trait). Often new is not needed.
2. **When in doubt, a small task or subagent go/no-go**: survey (that already
   solves the problem) → court by YAGNI/Rule of Three → one-line verdict
   justification. Intelligence is separated from implementation - this is control through
   small steps.
3. `no-go` → sell to the consumer; `go` → two-stage gate.

## Governance-gate

**Step 1 - Proposal issue** in the package repository: which consumer initiates,
source problem, why it cannot be solved locally, draft contract, ≥2
alternatives considered (event vs method, trait vs base class, config vs
parameter).

**Step 2 - Review + ADR** (after approval proposal): thread → ADR → minimum
contract → PR with mandatory manual review by the package maintainer.

### What is NOT included in the package

| Antipattern | Symptom | Right place |
|---|---|---|
| «General BaseService» | class without invariant, only convenience | trait/helper in consumer |
| Consumer configuration | parameters are specific to one project | config consumer |
| Proxy method | wraps one package method without logic | call directly |
| Temporary storage | code «until we figure out where» | issue + refactor backlog |
| God-interface | >5–7 methods without cohesion | split into contracts |

### SemVer contracts

`patch` — bugfix; `minor` — new API without breaking; `major` — breaking,
consumers adapt the code. Any deletion/renaming/change signature
public API, data format or config key → major + ADR + entry
«Breaking:» in CHANGELOG + migration guide.

## How this is supported in the registry

The methodology does not produce new entities for the sake of entities - it relies on
existing skills and adds exactly one new gate.

| Principle | Skill / config | Distribution |
|---|---|---|
| Reflex «ask before expanding», YAGNI, surgical edits | [`general/anti-drift`](https://github.com/academici/swissknifeman/blob/main/skills/general/anti-drift/SKILL.md) | CORE — to all projects |
| Deep Gate: proposal → ADR → SemVer, boundaries, direction of dependencies | [`architect/package-contribution-protocol`](https://github.com/academici/swissknifeman/blob/main/skills/architect/package-contribution-protocol/SKILL.md) | opt-in |
| Checklist speculative-generality on fresh diff | [`quality/code-simplifier`](https://github.com/academici/swissknifeman/blob/main/skills/quality/code-simplifier/SKILL.md) | CORE-bucket |
| ADR and comparison ≥2 options | [`architect/architecture`](https://github.com/academici/swissknifeman/blob/main/skills/architect/architecture/SKILL.md) | opt-in |
| Evolution of the public contract (SemVer, breaking, migration) | [`architect/api-design`](https://github.com/academici/swissknifeman/blob/main/skills/architect/api-design/SKILL.md) | opt-in |
| Hardware packet write boundary | preset `product-boundary` ([permissions](/harness/configs/claude-permissions)) | opt-in |
| Scope/out-of-scope/DoD before start | [`general/task-brief-template`](https://github.com/academici/swissknifeman/blob/main/skills/general/task-brief-template/SKILL.md) | CORE-bucket |
| Search for candidate duplicates in a common package | [`system/cross-project-coordinator`](https://github.com/academici/swissknifeman/blob/main/skills/system/cross-project-coordinator/SKILL.md) | opt-in |

## Hybrid distribution

Two layers, so that the discipline is both universal and targeted:

1. **Basic reflex - in all projects.** «Ask before expanding» and read-only
   packet boundary is hardened into `anti-drift` — CORE-skill that goes to every
   project via `connect`. Does not require separate installation.
2. **Deep protocol - selective.** `package-contribution-protocol`
   connects via marketplace only to projects that are finalizing their
   packages. There are also two manual boosts:
   - **First priority in root `CLAUDE.md`** consumer - ready
     generic-block in snippet `claude-md-priority.md` skill (inserted by hand).
   - **Preset `product-boundary`** — `bash scripts/apply-permissions.sh --target <project> --preset product-boundary`
     blocks writing to `vendor/**`; option
     for path-repo (`packages/**`) — in the snippet `permissions-deny.md`.

## Plan → Clear → Execute for cross-repo tasks

The task affecting both the package and the consumer is divided into separate sessions (see
[`general/context-economy`](https://github.com/academici/swissknifeman/blob/main/skills/general/context-economy/SKILL.md)):
planning and proposal in a consumer context → `/clear` → implementation
minimum contract in the package → `/clear` → use of new API in the product.

## The discipline of the registry itself

Same anti-bloat applies to skills: a new skill is created only if there is no
intersections with existing (otherwise the existing one is expanded), without specific names
projects/packets in the body. Acceptance standard - internal skill `skill-authoring`
and [`CONTRIBUTING.md`](https://github.com/academici/swissknifeman/blob/main/CONTRIBUTING.md).

## Criteria: always-on vs retrieval-only (registry skills)

Same anti-bloat principle also applies to the distribution of the skills themselves: not every skill
registry must be loaded resident into the project (⊕ always) or trigger
in full on-trigger (↻ on-trigger) — keep some of the content honest
**retrieval-only** (⌥ on-demand, body opens on a specific issue, not
according to description). Three tiers - `budget.py` (`skiller budget`).

Skill - **always-on** (candidate for CORE/`keep`-distribution), if at least true
one of:

- **procedural gate** — part of the required process gate (example - CORE
  `anti-drift`/`context-economy`: are distributed to each project by policy, not by
  usage-signal);
- **was loading in the window** — is fixed explicitly Skill-tool call after usage-window
  audit (verdict `keep`);
- **`level: core|foundation`** — explicit self-declaration of the base layer in
  frontmatter ([skills-architecture.md §2](./skills-architecture.md)).

Skill - **retrieval-only**, if in fact a reference book: a noticeable body with
rare/zero direct use - it is more economical to load it for a specific
question than the whole on-trigger.

**Exclusion from profiles** — only by verdict `dead` (0 downloads) **two
usage-windows in a row**; the first step is always `exclude` in profile (reversible), not
removing a skill from the registry.

**Criteria Validation Tool** — `skiller bucket-audit` (size · overlap ·
usage → verdicts `keep`/`thin`/`retrieval-only`/`merge`/`dead`,
`lib/skiller/audit.py`). Testing on a live registry with full numbers and analysis
controversial cases (incl. blind spot of the detector on auto-trigger/CORE-skills —
important to read before literally reading `dead`) — solution document
[bucket-audit-2026-07.md](./bucket-audit-2026-07.md).

## Summary: Question before adding code to package

> Is this used in **two or more independent consumers right now**, and
> **can't everyone** do it yourself?

«No» for at least one part → code remains in the consumer with `TODO` and a link to
issue.

### Five healthy packet markers

1. Each public method is used in 2+ consumers.
2. Everyone breaking change has ADR and major-bump.
3. The package does not import anything from consumers.
4. All extensions are via contracts/events, not monkey-patching.
5. `git log` package - only explicitly matched PR.

## Sources

- Martin Fowler, «Refactoring» (2nd ed.) — Rule of Three, Speculative Generality.
- Robert C. Martin, «Clean Architecture» — SOLID/YAGNI, Dependency Inversion.
- [GNOME API Stability](https://developer.gnome.org/documentation/guidelines/maintainer/api-stability.html) — SemVer and stability guarantees API.
- [KDAB: API Stability](https://www.kdab.com/api-stability-to-change-or-not-to-change/) — when and how to change API.
