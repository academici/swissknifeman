---
name: axioma-stack
bucket: axioma
version: 0.1.0
description: "Binds the universal reuse-gate to the live Ecosystem_Tech_Radar.md of the Axioma ecosystem: canon path, its 4-section structure, delegation to ecosystem-reuse-gate's algorithm, a concrete reuse report per unit. Read when designing any new Axioma-ecosystem project/feature — right after axioma-doctrine, before new-project/tech-stack-selection."
risk: read
persona: architect
tags: [axioma, ecosystem, reuse, tech-radar]
level: ""
requires: [ecosystem-reuse-gate]
produces_for: []
outputs: [chat]
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Axioma Stack

## Context

`ecosystem-reuse-gate` is a universal, data-free mechanism: it receives the
registry path as a parameter. This skill is the Axioma-specific binding: it
points to WHERE the live canon lives, explains its structure, and runs the
mechanism against it. Read it right after `axioma-doctrine` (the "reuse by
default" principle) and before `new-project`/`tech-stack-selection` — the
doctrine explains WHY, this skill produces the CONCRETE verdict for the unit
being designed.

The single source of data is the live file
`02-Knowledge/00-Strategy/Ecosystem_Tech_Radar.md` in the Brain vault. This
skill does NOT hold a copy of its contents — an embedded copy drifts from the
canon on the first radar edit. Only the path, structure, and reading
algorithm live here.

## Inputs

- The functional unit being designed (what the feature/package does).
- The consumer's language cluster (PHP/Laravel on `CoreX`, Dart/Flutter on
  `AxiomaErpSdk`, Node/Scraping, Frontend/Design System — radar §1).
- Canon path: `02-Knowledge/00-Strategy/Ecosystem_Tech_Radar.md` **relative to the Brain vault root** (not the current project's CWD). Designing OUTSIDE Brain — first resolve the Brain vault root (ecosystem maind hub / known path), then open the radar there; a CWD-relative path silently collapses the gate into a no-op.

## Canon structure (4 sections)

1. **§1 Language clusters** — "task → recommended / forbidden" tables per
   cluster (PHP/Laravel, Dart/Flutter, Node/Scraping, Frontend). Read your
   cluster's table first.
2. **§2 Map: functional unit → package/vendor** — a flat list of every
   tracked unit with its state (`package` / `vendor` / `use-vendor` /
   `build-new` / `keep-per-project`). Fast exact-match lookup.
3. **§3 Gap-roadmap** — units with confirmed duplication not yet closed by a
   package/vendor, prioritized by consumer count. If the unit being designed
   is here, the ecosystem has already flagged the duplication.
4. **§4 Decision precedents** — the same 7 generalized if-then rules that
   `ecosystem-reuse-gate` runs directly (identical rules; the radar section
   is the source, not a copy).

## Algorithm

1. Read `axioma-doctrine` first if not already read in this design session
   (sets the principle; this skill executes it).
2. Open `02-Knowledge/00-Strategy/Ecosystem_Tech_Radar.md`.
3. Call `ecosystem-reuse-gate` with the path parameter set to this file and
   the unit being designed — the gate's mechanism is not reimplemented here,
   only invoked (see `requires`).
4. Inside the call: look up the unit in §2 first (exact/close match), refine
   against your cluster's §1 table if needed; if the unit already appears in
   §3, that is an extra signal — "duplication already confirmed by the
   ecosystem" — not a separate branch of the algorithm.
5. Receive the verdict from the gate (`use-vendor` / `use-package` /
   `build-new` / `keep-per-project`) with the rule from §4 that fired.
6. Produce the reuse report (see "Outputs") with a direct quote of the radar
   line justifying the verdict — a quote, not a paraphrase.
7. Multiple units in one design task → repeat steps 3–6 per unit, one report
   line per unit.

## Outputs

A reuse report in chat, one line per unit:

`<unit> → <verdict> (rule N) — "<radar line quote>"`

Not a standalone file — the decision is embedded into the design dialogue
(`new-project` / `tech-stack-selection`), same as `ecosystem-reuse-gate`.

## Quality checklist

- [ ] Radar read via the path
      `02-Knowledge/00-Strategy/Ecosystem_Tech_Radar.md` as a live file, not
      an embedded copy.
- [ ] The full unit table (map §2) is NOT duplicated in the skill body — only
      section structure and a navigation algorithm.
- [ ] Verdict obtained by invoking `ecosystem-reuse-gate` (`requires`), not
      by rephrasing the §4 if-then rules in this skill's own words.
- [ ] The reuse report contains a quote of a specific radar line, not a
      generic phrase.
- [ ] Cross-links to `axioma-doctrine` (principle) and `ecosystem-reuse-gate`
      (mechanism) are present.

## Links

- `architect/ecosystem-reuse-gate` — universal registry-check algorithm and
  the 7 if-then rules (invoked by this skill, not duplicated).
- `axioma/axioma-doctrine` — the "vendor-vs-build reuse by default"
  principle, read before this skill.
- `02-Knowledge/00-Strategy/Ecosystem_Tech_Radar.md` — the single source of
  data (canon, live file in the Brain vault).
