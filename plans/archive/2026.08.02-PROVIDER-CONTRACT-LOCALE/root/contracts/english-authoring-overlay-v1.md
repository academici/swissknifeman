# English authoring and localized overlay contract

**Version:** v1.0.0
**Status:** frozen
**Approval Owner:** repository owner
**Approval:** D77 · 2026-08-14

## Purpose

This contract makes compact English the sole semantic source for Swissknifeman skills, commands,
plugin metadata, comments, development documentation, plans, diagnostics, and provider-rendered
human text. Localized prose is a sparse key-addressed rendering overlay. It never becomes another
semantic tree, capability declaration, provider input, generated target, or migration authority.

The v1 source locale is exactly `en`; the only rendered overlay locale is `ru`. Locale selection,
normalization, and fallback are owned by `locale-resolution-v1.md`. This contract consumes the
resolved locale and never reads a carrier, environment variable, provider state, or user setting.

Normative words `MUST`, `MUST NOT`, `SHOULD`, and `MAY` are literal.

## One canonical source

Every authorable carrier belongs to exactly one row in
`artifacts/P2-authoring-carrier-matrix.json`. A row declares its stable carrier identity, pattern,
semantic owner, localization mode, generated owner, migration admission, and rollback boundary.
The JSON matrix is the machine source; its Markdown file is a deterministic review projection.

A semantic carrier has exactly one English canonical artifact. English bytes determine source
identity and remain authoritative when an overlay is absent, incomplete, stale, or refused.
Localized text MUST NOT add, remove, reorder, or reinterpret requirements, triggers, negative
boundaries, capabilities, validation steps, safety clauses, commands, or machine identities.

Existing `SKILL.ru.md` files are migration inputs only. They remain untouched until P4 records an
owner, English preimage, semantic-equivalence evidence, generated owner, target preimage, action,
and rollback identity for the exact matrix row. A local override or unowned source always refuses
automatic admission. Absence, basename equality, timestamp, or byte equality never proves
ownership or equivalence.

## Carrier classes

The matrix closes these classes:

- `semantic-source`: English skill and command prose plus plugin semantic metadata;
- `render-resource`: provider/user-facing messages, plan prose, and diagnostic `message` text;
- `english-only`: code comments, internal docstrings, and development documentation;
- `machine-identity`: IDs, paths, commands, schema keys, placeholders, parser literals,
  diagnostic/action codes, URLs, and provenance fields;
- `generated-target`: provider projections, registries, marketplaces, locks, and generated docs;
- `legacy-input`: pre-admission Russian sources and local overrides.

Comments and development documentation are English canonical prose and have no localized overlay
in v1. Machine identities are never translated. Generated targets are written only by their
declared generator from canonical source plus a validated overlay result.

## Overlay envelope

An overlay is UTF-8 JSON with exactly:

```json
{
  "$schema": "urn:swissknifeman:localized-overlay:v1",
  "contract_version": "1.0.0",
  "locale": "ru",
  "source_catalog_sha256": "sha256:...",
  "units": {
    "skill.core.verify-claims.body.purpose": {
      "source_sha256": "sha256:...",
      "immutable_tokens": ["context7", "WebSearch"],
      "text": "... context7 ... WebSearch ..."
    }
  }
}
```

No other top-level or unit fields are allowed. `source_catalog_sha256` is the SHA-256 of canonical
JSON for the ordered English unit inventory: object keys sorted, separators `,` and `:`, Unicode
unescaped. Each `source_sha256` is the digest of the exact UTF-8 English source unit. A mismatch
refuses the overlay; the renderer does not guess which revision was intended.

Translation keys match
`^[a-z][a-z0-9]*(?:[.-][a-z0-9][a-z0-9_-]*)+$`, are globally unique, and remain stable across
provider projections. Keys are semantic resource identities, not file positions or translated
labels. One canonical unit may have at most one key. A key never selects a provider target.

`units` is sparse. A missing Russian key resolves to the exact English unit and records
`fallback=true`; it is not copied into the overlay. An unknown key, duplicate source identity,
empty text, invalid digest, unsupported locale/version, or absent deterministic English fallback
refuses the complete overlay result.

## Immutable tokens

The canonical owner supplies the complete ordered `immutable_tokens` list for each localizable
unit. It includes every machine-significant ID, path, command, schema key, placeholder, parser
literal, diagnostic/action code, URL, and code fragment in the unit. The localized text MUST
contain every declared token byte-for-byte, in the same order and multiplicity. It MUST NOT invent
a translated alias for a token or use a localized token as a lookup key.

Code fences and surrounding prose may localize only when the code bytes and declared tokens remain
unchanged. When a renderer cannot prove token parity, it refuses the localized unit and emits the
stable diagnostic `OVERLAY_IMMUTABLE_TOKEN_MISMATCH`; it never publishes best-effort text.

## Renderer and provider boundary

The provider-neutral resolver returns one complete ordered unit result with exactly `key`,
`source_sha256`, `resolved_locale`, `text`, `fallback`, and `overlay_sha256`. English fallback uses
`overlay_sha256=null`. The resolver performs no filesystem, environment, provider, or target I/O.

Each provider adapter receives the same resolved semantic message request. It may add native
layout or invocation mechanics and may write only targets owned by its descriptor. It MUST NOT:

- read another provider's rendered target, lock, status, or evidence as source;
- convert Claude output into Codex output, or the reverse;
- alter canonical English, overlay bytes, capability/lock provenance, or another adapter's files;
- translate machine identities, source keys, or stable diagnostic fields;
- claim semantic equivalence from byte equality or one successful generated target.

Every generated projection records the canonical source digest, overlay digest or English
fallback marker, resolved locale, adapter identity/version, and rendered digest. A target without
that provenance is unowned and cannot be adopted automatically.

## Migration admission and rollback

P4 may migrate only a matrix row whose action record has exactly: `carrier_id`, `owner`,
`source_path`, `source_preimage_sha256`, `english_postimage_sha256`, `overlay_path`,
`overlay_sha256`, `generated_owner`, `target_preimages`, `semantic_review_evidence`, and
`rollback_id`. All paths and target sets are exact and provider-qualified.

Admission refuses `owner-missing`, `preimage-changed`, `semantic-review-missing`,
`generated-owner-missing`, `local-override`, `cross-provider-target`, and `rollback-incomplete`
before any write. A generated artifact is regenerated through its owner; it is never edited in
place. Rollback restores only the declared canonical, overlay, and generated target preimages. It
never deletes or overwrites an unowned file, local override, another provider target, or newer
post-admission change.

Coexistence is explicit: admitted English source and sparse overlay may coexist with a preserved
legacy `SKILL.ru.md` until the action's verification and rollback checkpoint are committed. The
legacy file then remains evidence or is removed only by the exact authorized P4 action. This
contract itself performs no migration, deletion, publication, or provider/fleet write.

## Diagnostics

Diagnostics have exactly `severity`, `code`, `carrier_id`, `key`, and `message`. Only `message`
may localize. Severity, code, carrier identity, key, ordering, and provenance remain stable English
machine fields. Errors return no partial localized result.

| Code | Closed meaning |
|:--|:--|
| `OVERLAY_VERSION_UNSUPPORTED` | Contract or overlay version is unsupported. |
| `OVERLAY_SCHEMA_INVALID` | Required shape/type/value is invalid. |
| `OVERLAY_UNKNOWN_FIELD` | An unknown structural field is present. |
| `OVERLAY_KEY_INVALID` | A key is malformed, duplicated, or not in the English inventory. |
| `OVERLAY_SOURCE_DUPLICATE` | More than one semantic source claims one resource identity. |
| `OVERLAY_SOURCE_DIGEST_MISMATCH` | Catalog or unit digest does not match canonical English. |
| `OVERLAY_LOCALIZED_SEMANTIC_SOURCE` | Localized bytes are presented as canonical meaning. |
| `OVERLAY_IMMUTABLE_TOKEN_MISMATCH` | Token bytes, order, or multiplicity changed. |
| `OVERLAY_GENERATED_EDIT_FORBIDDEN` | A generated target was supplied as an editable source. |
| `OVERLAY_FALLBACK_MISSING` | A sparse key has no deterministic English fallback. |
| `OVERLAY_CROSS_PROVIDER_TARGET` | One provider target is used by or written for another. |
| `OVERLAY_OVERRIDE_ADOPTION_FORBIDDEN` | A local/unowned override is proposed for automatic adoption. |
| `OVERLAY_ROLLBACK_INCOMPLETE` | Exact preimage/rollback identity is incomplete. |

Diagnostics order by `carrier_id`, then `key`, then `code`.

## Versioning

A v1.0 reader accepts only `1.0.x`. A major version is required to change source language,
overlay locale set, key/digest identity, fallback, immutable-token semantics, carrier ownership,
provider isolation, or migration/rollback authority. A minor may add an optional understood field
that older readers safely refuse. A patch may clarify prose or add fixtures without changing an
accepted or refused outcome.

## Normative fixtures and checker

`overlay-positive.json` carries a complete English inventory, sparse Russian overlay, English
fallback, immutable tokens, and provider-qualified render provenance.
`overlay-negative.json` changes one invariant per case and declares the exact refusal code for:
duplicate source, invalid key, localized semantic source, generated edit, missing fallback,
immutable-token drift, cross-provider target, and override adoption.

`artifacts/p2-locale-authoring-check.py --stage overlay` validates this contract, the frozen locale
contract, the matrix, both fixtures, every closed refusal, and deterministic matrix Markdown. It
uses only the Python standard library, performs no network/environment/provider read, and writes
nothing.

## Exact Owner freeze gate

The Owner decision atomically freezes:

- **E1 — source identity:** English-only semantic canon and exact carrier classes;
- **E2 — overlay:** v1 envelope, stable key grammar, sparse Russian resource and English fallback;
- **E3 — immutable tokens:** byte/order/multiplicity preservation and fail-closed diagnostics;
- **E4 — renderer isolation:** same resolved semantic request, provider-owned targets and provenance;
- **E5 — migration:** owner/preimage/equivalence/generated-owner/rollback admission and legacy coexistence;
- **E6 — matrix/checker:** JSON source, deterministic Markdown, normative fixtures and no-write checker;
- **E7 — authority:** no content, runtime, provider, project, fleet, publication, adoption, deletion, or translation write.

Exact approval reply:

```text
APPROVE P2.2 ENGLISH-OVERLAY E1-E7 AS WRITTEN
```

Any E1–E7 change is a revision request. Only an accepted immutable Owner decision may set
`Version` to `v1.0.0`, `Status` to `frozen`, and `Approval` to its D-number.
