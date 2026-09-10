# Locale authoring and review contract

**Version:** v1.0.0
**Status:** frozen
**Approval Owner:** repository owner
**Approval:** D77 · 2026-08-14

## Purpose

English is the sole semantic source. Russian is a sparse rendered overlay governed by
`english-authoring-overlay-v1.md`; admitted legacy `SKILL.ru.md` files are removed by P4 after
equivalence and rollback evidence is recorded. This contract adds the minimum authoring and review
rules needed for that migration. It performs no content, runtime, provider, project, fleet, or
publication write.

## Compact English

Canonical prose MUST be direct, task-specific, and free of repeated repository rules, tutorials,
universal Gotchas, speculative provider advice, and examples that do not protect a known failure.
Compactness never removes an invariant, safety boundary, validation command, trigger, negative
case, code, URL, ID, path, schema key, placeholder, parser literal, or diagnostic/action code.

For skills, `SKILL.md` SHOULD remain below 500 lines and its instruction body SHOULD remain below
about 5,000 tokens. These are review signals, not deletion targets. An over-budget unit is accepted
when its evidence record names the retained invariant or observed failure mode; estimated counts
near a limit are not treated as exact provider counts.

## Prose and machine literals

Comments, internal docstrings, development documentation, test names, and test descriptions are
compact English canonical prose. They explain intent, boundaries, or a regression; they do not
repeat code. API names, commands, paths, IDs, schema keys, placeholders, parser literals, URLs,
diagnostic codes, and test data are machine literals and remain byte-identical.

Diagnostics contain stable English `code`, `action`, and `context` fields plus one locale-rendered
`message`. Rendering preserves every interpolation and immutable literal and records resolved
locale and fallback. A changed interpolation or unsupported fallback refuses the render.

## Review evidence

Each migrated unit records:

- canonical unit ID, English source digest, immutable tokens, invariants, and projection digest;
- author and renderer identities;
- an English semantic reviewer and a Russian-render reviewer, both different from the author and
  renderer, with explicit `pass` outcomes;
- Russian render or a declared English fallback only where the overlay contract permits it;
- exact batch, rollback, provider/model/date, and validation identities when execution reaches P4
  or P7.

Structural validation can prove shape, source freshness, literal preservation, and reviewer
separation. It cannot prove fluency or model efficacy. If an independent review is unavailable,
the unit remains unadmitted; no extra review loop is created inside P2.

## Migration and rollback

P4 processes bounded manifests in dependency order. Each row binds owner, source and target
preimages, English postimage, overlay digest, generated owner, independent review, and rollback ID.
The batch stops on a changed preimage, missing review, stale projection, literal drift, failed
generation, or rollback mismatch. Rollback restores only declared owned preimages.

P4 carries the migration batches; P7 carries real-project/provider replay and release acceptance.
P2 freezes contracts and deterministic shape checks only. A deterministic fixture or fluent text
alone MUST NOT be cited as proof that a skill improves current model behavior.

## Diagnostics

| Code | Meaning |
|:--|:--|
| `AUTHORING_SOURCE_NOT_ENGLISH` | Canonical source locale is not `en`. |
| `AUTHORING_REVIEW_MISSING` | Required independent review or pass outcome is absent. |
| `AUTHORING_SELF_REVIEW` | Author or renderer approves its own work. |
| `AUTHORING_LITERAL_CHANGED` | An immutable token or interpolation changed. |
| `AUTHORING_RUSSIAN_RENDER_MISSING` | A required Russian render is absent. |
| `AUTHORING_FALLBACK_UNSUPPORTED` | The unit declares fallback outside the overlay contract. |
| `AUTHORING_INVARIANT_DELETED` | A required semantic/safety invariant is absent. |
| `AUTHORING_PROJECTION_STALE` | Projection digest differs from canonical source. |
| `AUTHORING_SCHEMA_INVALID` | Fixture or evidence shape is invalid. |

## Versioning

A v1.0 reader accepts only `1.0.x`. A major version is required to change source ownership,
review independence, literal preservation, diagnostics, migration admission, or rollback. A patch
may clarify prose or add a regression fixture without changing accepted/refused outcomes.

## Frozen decisions

D77 freezes:

- **C1:** English-only semantic source and Russian sparse overlay;
- **C2:** compactness protects invariants and uses an exception record instead of blind deletion;
- **C3:** English prose versus immutable machine literals;
- **C4:** stable diagnostic fields plus locale-rendered message and interpolation parity;
- **C5:** independent English semantic and Russian-render review;
- **C6:** bounded P4 migration/rollback with real-project/provider acceptance deferred to P7.

