# Authority and conflict policy

## Precedence

1. System, security and provider hard limits.
2. Repository root and applicable package instructions.
3. Frozen plan contracts and append-only D# decisions.
4. Signed run mandate, which may narrow but never widen 1–3.
5. Supervisor defaults.

The highest applicable rule wins. Contradictory rules at the same level are not guessed: the slice
enters OWNER with both source references and no side effect.

## Action classes

| Class | Required predicates | Examples |
|:--|:--|:--|
| `AUTO` | exact declared scope/files; reversible or no-write; no external visibility/security/public API/dependency/frozen contract; deterministic validation is available | choose existing helper, add internal test inside named files, run read-only recon |
| `AUTO-FIX` | all AUTO predicates plus same finding identity, bounded retry budget and unchanged acceptance | repair formatter/test failure caused by current slice, tighten implementation without weakening test |
| `OWNER` | any canon conflict, expansion, irreversible/destructive/external/security action, public API/SemVer/dependency/package topology change, third state, unknown capability, out-of-scope merge, exhausted budget or impossible rollback | rotate credential, add package, alter frozen schema, accept known test regression |

## Routine conflict resolver

When several alternatives satisfy AUTO predicates, order by:

1. smallest changed file/behavior set;
2. existing project primitive over a new abstraction;
3. reversible over irreversible;
4. sequential over parallel write execution;
5. fewer dependencies/provider-specific branches;
6. stronger deterministic validation;
7. lowest measured token/cost among otherwise equivalent choices.

The chosen candidate and rejected alternatives are journaled. If this ordering cannot prove one
candidate legal, the result is OWNER rather than an LLM tie-break.

## Bounded auto-fix

- Default retry budget: contract value, never open-ended.
- Same finding identity twice triggers circuit-breaker review; identity count is durable across resume.
- A retry uses a fresh worker with only the prior typed failure and changed evidence, not the full transcript.
- It cannot skip/alter tests, broaden files, increase permissions, switch provider/model beyond mandate,
  reclassify OWNER as AUTO, or mark a partial result accepted.

## Owner attention packet

Non-urgent questions are ordered by blocking dependency and batched. Every row includes exact
decision requested, controlling canons, recommendation, alternatives, blast radius, rollback,
affected pending slices and “no decision” consequence. Security/destructive/irreversible cases
interrupt immediately; all other workers that do not depend on the gate may continue within budget.

RAG:— (owner brief plus repository authority/security canons; taxonomy is an internal contract proposal).
