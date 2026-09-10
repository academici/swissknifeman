---
id: D17
date: 2026-08-02
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

Locale v1 separates three stages: RFC 5646 well-formed syntax (including `x-*` private-use), RFC/IANA canonicalization, and SKM catalog resolution. `ru-RU` remains canonical `ru-RU` but the v1 `en`/`ru` catalog resolves it to `ru`; other valid unsupported registered tags fall back to `en`. Any tag containing a private-use sequence is syntax-valid and canonicalized without interpreting or reordering its opaque private portion, but v1 has no private agreement/catalog mapping and therefore refuses catalog resolution with `unsupported-private-use`, never `malformed`. RFC facts: RAG:✅ 2026-08-03 RFC 5646 §2.1/§2.2.7/§4.5/§4.6 verification in `findings/06-p2-locale-authoring-verification-2026-08-02.md`; precedence, catalog and refusal policy: RAG:— (internal product rule in `research/02-p2-locale-authoring-design.md`).

## Почему

Preserves BCP 47 syntax truth while making the bounded v1 catalog deterministic; requested/canonical/resolved/fallback provenance remains separate and contains no environment values.
