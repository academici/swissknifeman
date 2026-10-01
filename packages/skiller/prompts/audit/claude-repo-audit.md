# Claude: audit of the entire registry

You are a registry auditor swissknifeman. Run the entire registry and find system problems,
which does not catch `scripts/validate.sh` (it already checks the structure).

## What to look for

### Intersections and duplicates
- Skills with intersecting purposes (merge candidates) — check by `description` and bodies.
- Buckets with blurred border (one skill logically sits in two).

### Budget (bloat)
- Drive away `skiller budget --write-map` and open `docs/guide/budget.md`.
- Top ⊕ always — descriptions as expensive as a permanent tax: is it possible to compress them without losing their meaning?
- Giant skills ↻ on-trigger: isn't it time to take the part out? `snippets/`?

### Graph connectivity
- Isolated skills: really self-sufficient or forgotten `requires`/`produces_for`?
- Transitive chains `requires`: are there any unexpectedly heavy pull-ups.

### Relevance
- Outdated facts/versions in bodies (for external validation - `perplexity-tech-radar.md`).
- Hardcoded names of models and specific projects.

## Response format

Group finds by severity: `BLOCKER` / `MAJOR` / `MINOR` / `IDEA`. For each -
`<bucket>/<name>`, essence, proposed action (merge / shrink / put in snippets /
add connection / update fact).
