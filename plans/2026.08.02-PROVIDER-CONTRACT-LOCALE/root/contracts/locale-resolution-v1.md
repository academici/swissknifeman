# Locale resolution contract

**Version:** v1.0.0
**Status:** frozen
**Approval Owner:** repository owner
**Approval:** D74 · 2026-08-14
**Registry:** `core/locale/data/language-subtag-registry.txt` · `File-Date: 2026-06-14` · SHA-256 `be1fad86a99e3a932d07b80c9b3c271ec2381a5909ce22420144e5077ab0a43a` · 731605 bytes

## Purpose

This contract defines a provider-neutral, deterministic locale preference and catalog resolution
model for Swissknifeman. It owns only already-read locale descriptors, validation,
canonicalization, catalog fallback, redacted provenance, and stable diagnostics. It authorizes no
carrier, environment, provider, user, project, fleet, or rendered-content write.

The three locale surfaces are exactly `response`, `plan`, and `diagnostics`. Each surface resolves
independently. English is the complete v1 default; Russian is an independently selected rendered
locale. A locale tag is not a provider, model, region-routing, trust, approval, or sandbox value.

Normative words `MUST`, `MUST NOT`, `SHOULD`, and `MAY` are literal.

## Result envelope

Every operation returns exactly:

```json
{
  "contract_version": "1.0.0",
  "result": null,
  "diagnostics": []
}
```

On any input/schema failure, `result` is `null` and diagnostics contain at least one `error`. A
partial surface map is forbidden. On success, `result` contains exactly `surfaces`, and each of the
three required surface rows is complete. Unknown fields, surfaces, carrier kinds, ranks, diagnostic
codes, or contract major/minor versions fail closed.

## Preference carriers and precedence

The pure resolver receives already-read layers and never reads a file, process environment, OS
locale, provider output, or host state itself. Exact precedence, strongest first, is:

| Rank | Kind | Carrier | Owner | Presence and write rule |
|:--|:--|:--|:--|:--|
| 1 | `command-session` | in-memory command or session descriptor | calling command/session | Optional and invocation-local; never persisted by the resolver. |
| 2 | `environment` | already-read `SWISSKNIFEMAN_LOCALE_*` descriptor | process launcher | Optional and read-only; raw environment names/values never enter result or provenance. |
| 3 | `project` | `.swissknife.json#/locale` | project / skiller schema | Optional project intent; provider adapters and fleet state cannot rewrite or outrank it. |
| 4 | `user` | `~/.swissknifeman/locale.json#/locale` | user | Optional user intent; the resolver never creates or updates it. |
| 5 | `built-in` | in-memory `en` defaults | this contract | Required lowest layer; exactly one `en` value per surface and never persisted. |

Exactly zero or one layer may exist at ranks 1–4 and exactly one layer exists at rank 5. Two
candidates at one rank produce `LOCALE_DUPLICATE_RANK`; order, mtime, provider, and adapter identity
never select a winner. An adapter observation/status/projection is not a preference carrier and
produces `LOCALE_ADAPTER_INPUT_FORBIDDEN`. A layer asking the resolver to persist an environment or
other value produces `LOCALE_PERSISTENCE_FORBIDDEN`.

A layer has exactly `contract_version`, `rank`, `kind`, and `locale`. `locale` is a non-empty map
containing only the three surface IDs, each mapped to one non-empty locale-tag string. Missing
surfaces inherit independently; `null`, deletion markers, generic object merge, cross-surface copy,
and a layer-wide locale alias are forbidden. The highest-ranked defined value wins for each surface.

The project and user carriers are future inputs. This contract and P2.1 do not create either file or
key. OS locale inference is excluded in v1.

## Three-stage resolution

Each winning surface value passes through the following stages in order. Syntax,
canonicalization, and catalog support are distinct facts and MUST NOT be collapsed.

### Stage 1 — RFC 5646 syntax

Input is validated as a complete RFC 5646 language tag. Matching is ASCII case-insensitive.
Subtags are separated only by `-`; empty subtags, invalid lengths/characters, duplicate variants,
and duplicate extension singletons are malformed. A complete private-use tag such as `x-acme` and
a language tag with a trailing private-use sequence such as `en-x-acme` are well-formed.

Malformed input stops with `LOCALE_MALFORMED`, `canonical=null`, `resolved=null`, and no catalog
fallback. Syntax acceptance alone does not establish registry membership or catalog support.

### Stage 2 — registry-backed canonicalization

Canonicalization uses only the faithfully vendored snapshot:

| Field | Frozen value |
|:--|:--|
| Official URL | `https://www.iana.org/assignments/language-subtag-registry/language-subtag-registry` |
| File-Date | `2026-06-14` |
| SHA-256 | `be1fad86a99e3a932d07b80c9b3c271ec2381a5909ce22420144e5077ab0a43a` |
| Bytes | `731605` |
| Provenance | `core/locale/data/upstream.json` |

Any byte, header, URL, hash, length, or provenance mismatch produces
`LOCALE_REGISTRY_IDENTITY_MISMATCH` before a result. The registry is a generated-owner boundary:
the file is never hand-edited. P4.1 owns the sole explicit future update producer; replacing the
snapshot requires new contract authority and updated provenance.

Canonicalization applies complete-tag and subtag `Preferred-Value` records from this exact
snapshot and locale-neutral ASCII casing: language/extlang/variant/extension/private-use lower
case, script title case, region upper case. It preserves the opaque private-use subtag sequence in
the same order and never interprets its content. Extension reordering is outside v1; input order is
preserved. `ru-ru` canonicalizes to `ru-RU`; `ru-RU` remains `ru-RU`.

A syntactically valid primary language, extlang, script, region, or variant that is absent from the
pinned registry produces `LOCALE_UNREGISTERED`. Grandfathered/redundant complete tags are admitted
only when present in the pinned registry. Registry membership does not imply rendered support.

### Stage 3 — Swissknifeman catalog

The rendered catalog set is exactly `en` and `ru`.

1. A canonical tag containing private-use always refuses with `LOCALE_UNSUPPORTED_PRIVATE_USE`,
   `resolved=null`, and `fallback=false`. It is never `LOCALE_MALFORMED`.
2. Exact `en` or `ru` resolves to itself with `fallback=false`.
3. A registered canonical tag whose parent chain reaches `en` or `ru` resolves to that first parent
   with `fallback=true`; therefore canonical `ru-RU` resolves to `ru`.
4. Any other syntactically valid, registered canonical tag resolves to `en` with `fallback=true`
   and diagnostic `LOCALE_UNSUPPORTED_CATALOG`.

There is no provider-specific fallback, OS fallback, translation lookup, region inference, or
best-effort use of an unregistered tag.

## Surface result and provenance

Each successful surface row has exactly:

```json
{
  "surface": "response",
  "rank": 1,
  "kind": "command-session",
  "requested": "ru-ru",
  "canonical": "ru-RU",
  "resolved": "ru",
  "fallback": true,
  "diagnostic": null
}
```

The fields are exactly `surface`, `rank`, `kind`, `requested`, `canonical`, `resolved`,
`fallback`, and `diagnostic`. `diagnostic` is `null` or one stable code from this contract.
Rows are ordered `response`, `plan`, `diagnostics`.

Provenance intentionally contains no raw environment value, variable name, absolute path, user
home, provider payload, target bytes, credential, token, timestamp, or adapter state. A request for
one surface MUST NOT alter the winner, requested tag, canonical tag, result, fallback, or diagnostic
of another surface; a mismatch produces `LOCALE_CROSS_SURFACE_LEAKAGE`.

## Diagnostics

Every diagnostic has exactly `severity`, `code`, `surface`, and `message`. Only `message` may be
localized. Severity, code, surface, ordering, and all result/provenance fields remain stable English
machine literals. Diagnostics order by surface order, then severity (`error`, `warning`, `info`),
then code.

| Code | Severity | Closed meaning |
|:--|:--|:--|
| `LOCALE_VERSION_UNSUPPORTED` | error | A layer or result version is malformed or unsupported. |
| `LOCALE_SCHEMA_INVALID` | error | Required shape/type is missing or invalid. |
| `LOCALE_UNKNOWN_FIELD` | error | An unknown structural field is present. |
| `LOCALE_UNSUPPORTED_SURFACE` | error | A locale map names anything outside the exact surface set. |
| `LOCALE_DUPLICATE_RANK` | error | More than one candidate occupies a precedence rank. |
| `LOCALE_CARRIER_MISMATCH` | error | Rank, kind, or carrier ownership does not match the closed table. |
| `LOCALE_ADAPTER_INPUT_FORBIDDEN` | error | Provider adapter output/status was supplied as preference input. |
| `LOCALE_PERSISTENCE_FORBIDDEN` | error | A resolver input asks to persist a carrier value. |
| `LOCALE_CROSS_SURFACE_LEAKAGE` | error | One surface's selection changes another surface. |
| `LOCALE_MALFORMED` | error | The requested tag fails RFC 5646 syntax. |
| `LOCALE_UNREGISTERED` | error | A syntactically valid tag uses a subtag absent from the pinned registry. |
| `LOCALE_REGISTRY_IDENTITY_MISMATCH` | error | Registry bytes or adjacent provenance differ from the frozen identity. |
| `LOCALE_UNSUPPORTED_PRIVATE_USE` | error | A syntax-valid tag contains private-use and v1 has no private catalog agreement. |
| `LOCALE_UNSUPPORTED_CATALOG` | info | A registered canonical tag is unsupported and deterministically falls back to `en`. |

Errors return no partial result. The informational catalog fallback stays on its surface row and
does not authorize a carrier or content write.

## P1 provider-configuration crosswalk

| P1 boundary | Locale v1 composition |
|:--|:--|
| Pure resolver over already-read layers | Preserved; locale resolution performs no filesystem/environment I/O. |
| Operation/project/fleet/legacy provider ownership | Independent; locale adds no provider selection field and no fleet rank. |
| `.swissknife.json` project ownership | Preserved; future `#/locale` is additive and independent of `#/providers`. |
| Leaf-granular provenance | Preserved as one locale winner per surface, with the stricter redaction fields above. |
| Explicit false/missing provider semantics | Unchanged; locale tags cannot enable, disable, or select a provider. |
| Stable diagnostic structure | Composed; only human message may localize, never code/path/source/provider identity. |
| No read/check write authority | Preserved; locale resolve/check is strictly no-write. |

## Versioning and compatibility

A v1.0 reader accepts only `1.0.x`. Unknown minor/major versions, fields, ranks, kinds, surfaces,
and codes fail closed. Patch changes may add explanatory examples without changing accepted or
rejected behavior. A minor may add an optional understood field that old readers can safely reject.
A major is required for precedence, carrier ownership, surface set, stage boundaries, catalog set,
fallback, provenance, or diagnostic meaning changes.

Absent explicit carriers resolves all surfaces from the built-in `en` layer. Existing provider
configuration remains byte-identical. No locale carrier or environment value is created,
normalized in place, migrated, or written by compatibility behavior.

## Normative fixtures and checker

`artifacts/P2-locale-resolution-fixtures/positive.json` contains syntax, canonicalization,
catalog, independent-surface, precedence, and redacted-provenance vectors.
`negative.json` changes one invariant per case and declares the exact refusal code. The stdlib-only
`artifacts/p2-locale-authoring-check.py` reads only this contract, those fixtures, the pinned
registry, and adjacent provenance; it has no environment or network access and performs no writes.

The checker validates exact registry identity, contract literals, complete surface ordering,
one-rank ownership, RFC syntax/private-use separation, registry `Preferred-Value` mapping,
catalog exact/parent/English fallback, diagnostics, and provenance redaction. Its self-test mutates
copied in-memory evidence and must separately observe syntax, canonicalization, catalog, and
provenance failures.

## Exact Owner freeze gate

The Owner decision is atomic and freezes all of:

- **L1 — surfaces/carriers:** exact independent surfaces and five-rank ownership/precedence;
- **L2 — stages:** distinct RFC syntax, pinned-registry canonicalization, and SKM catalog results;
- **L3 — registry:** D41 exact URL, File-Date, SHA-256, bytes, adjacent provenance, and P4.1-only update ownership;
- **L4 — catalog/private use:** exact `en`/`ru`, parent/English fallback, and private-use refusal;
- **L5 — provenance/diagnostics:** exact redacted fields, stable codes, no partial result, and cross-surface isolation;
- **L6 — compatibility/authority:** P1 additive crosswalk, no runtime/provider/fleet/carrier write, and no locale-as-provider semantics.

Exact approval reply:

```text
APPROVE P2.1 LOCALE-RESOLUTION L1-L6 AS WRITTEN
```

Any L1–L6 change is a revision request, not partial approval. Only an accepted immutable Owner
decision may change `Version` to `v1.0.0`, `Status` to `frozen`, and `Approval` to its D-number.
