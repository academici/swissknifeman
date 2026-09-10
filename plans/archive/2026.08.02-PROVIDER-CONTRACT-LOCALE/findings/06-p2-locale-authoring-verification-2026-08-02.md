# P2 verification — locale and authoring boundaries

**Date:** 2026-08-02

## External verification

- [RFC 5646 / BCP 47](https://www.rfc-editor.org/info/rfc5646/) defines language tags,
  their syntax and canonicalization considerations. Tags are case-insensitive and
  locale-sensitive casing is a stated hazard. **Verdict:** accept BCP 47 at the boundary,
  normalize with locale-neutral rules, and never use tag case as semantic state.
- [Unicode TR35 / LDML](https://www.unicode.org/reports/tr35/) is Unicode's locale-data
  specification. **Verdict:** locale data can be treated as structured input; P2 selects no
  locale library and adds no runtime dependency.
- The i18next fallback page cited by the earlier finding was not retrievable in this
  environment. It is not treated as independent verification in this pass.

The standards establish tag form and safe canonicalization, not SKM carrier ownership or
precedence. Command/session → environment → project → user → built-in `en`, independent
surfaces, and sparse fallback are therefore explicit product decisions traced to the brief
and `research/01-target-architecture.md`, not claims of standard-mandated behavior.

## Repository verification

- `core/provider/config.py` is a pure resolver over already-read layers and has no
  filesystem/environment I/O. It is a reusable ownership pattern, not a locale implementation.
- `packages/skiller/scripts/check-translations.sh` identifies `SKILL.ru.md` as local source
  and `SKILL.md` as derived EN. This is opposite to the requested English source target and
  requires P4 admission, not hand-editing a generated artifact.
- No dedicated locale resolver, locale carrier, message catalog or provider-neutral localized
  diagnostic layer exists in the inspected core/package code.

## Confidence and Проверка

High for BCP 47 tag/casing claims; medium for the fallback architecture because it is an SKM
design inference. RAG: Web fallback — RFC 5646 and Unicode TR35 opened 2026-08-02.
Непроверено → ПОВТОРНЫЙ ПРОХОД: re-check any runtime API/tooling immediately before P4.
Обходки/[POSSIBLE-DEFECT]: no library is selected and P2 must not claim CLDR coverage.

## 2026-08-03 design-audit remediation: three locale stages

Primary-source recheck: [RFC 5646 §2.1, §2.2.7, §4.5 and §4.6](https://www.rfc-editor.org/rfc/rfc5646.html)
was reopened on 2026-08-03. Its ABNF makes a complete `x-*` tag and a trailing `-x-*`
sequence well-formed language-tag syntax; private-use content is opaque outside a private
agreement. RFC canonical form is a separate registry-backed operation (including
`Preferred-Value` mappings and extension ordering); case regularization is optional and must
not be confused with catalog selection. RFC 5646 also does not define an application's
supported catalog or suitable fallback language.

**Verdict:** P2 must expose three independent results: `syntax` (well-formed/refused),
`canonical` (RFC/IANA canonical tag), and `catalog` (SKM `en`/`ru` resolution). In v1,
`ru-RU` is not canonicalized to `ru`; its canonical tag remains `ru-RU` and the product
catalog resolves it to `ru`. A syntactically valid registered tag unsupported by the catalog
may resolve to `en` under SKM policy. A tag containing private-use is accepted by syntax and
canonicalized without interpreting or reordering the opaque private portion, but catalog
resolution fails closed with `unsupported-private-use` because v1 defines no private
agreement or catalog mapping. It is never classified as `malformed`.

**Confidence and Проверка:** high for syntax/private-use/canonicalization
boundaries from the RFC; high for the stated v1 outcome as an explicit internal product
decision, not an external claim. RAG: Web fallback, official RFC Editor, query/reopen date
2026-08-03. Непроверено → ПОВТОРНЫЙ ПРОХОД: the execution item must pin the
IANA Language Subtag Registry snapshot/version used for registry-backed canonicalization.
Обходки/[POSSIBLE-DEFECT]: none.
