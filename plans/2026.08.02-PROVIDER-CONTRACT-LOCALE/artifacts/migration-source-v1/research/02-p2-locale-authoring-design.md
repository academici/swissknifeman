# P2 locale and authoring design synthesis

## Traceability

| Requirement or fact | Destination |
|:--|:--|
| English default; Russian response, plan and diagnostics may differ | P2.1 surfaces/precedence and P2.3 review vectors |
| Russian plan and provider-rendered text | P2.1 `ru` resolution; P2.2 overlay; P2.3 Russian-render review |
| Canonical skills/plugins/comments/development docs become compact English | P2.2 source matrix and P2.3 authoring policy |
| No parallel source or generated-file edits | P2.2 owner/preimage/rollback matrix |
| Independent providers | P2.1 canonical intent and P2.2 owned renderer boundary |

Sources: `brief/00-brief.md`, `findings/01-rag-locale-2026-08-02.md`,
`findings/06-p2-locale-authoring-verification-2026-08-02.md`,
`research/01-target-architecture.md`, and P1 contracts named by P2.

## Resolution model

Each surface independently selects one preference by precedence, then passes it through three
separate stages. First, RFC 5646 syntax validation accepts every well-formed tag, including a
complete `x-*` tag or a tag with a trailing private-use sequence; malformed input stops here.
Second, registry-backed RFC canonicalization produces a canonical tag using a contract-pinned
IANA registry snapshot. It may regularize case with locale-neutral rules, but it does not
interpret or reorder opaque private-use subtags. Third, SKM catalog resolution applies the
bounded v1 product policy over `en` and `ru`.

`ru-RU` therefore stays canonical `ru-RU` and resolves to catalog `ru`; this is catalog
resolution, not RFC normalization. Other valid registered tags unsupported by v1 resolve to
`en` with `unsupported-catalog` fallback provenance. Any tag containing private-use is
syntax-valid and canonicalizable, but v1 has no private agreement or catalog mapping, so the
catalog stage refuses with `unsupported-private-use` and no fallback; it is never reported as
`malformed`. Trace carries selected rank/kind plus distinct `requested`, `canonical`,
`resolved`, `fallback` and diagnostic fields, never environment values, paths or provider
output. The proposed user carrier is `~/.swissknifeman/locale.json` and project intent is
additive at `.swissknife.json#/locale`; neither is created by design.

## Authoring and review model

English is the semantic source. Localized prose is a resource/key overlay and missing keys
fallback through the locale contract. IDs, code/action identifiers, paths, commands, schema
keys, placeholders, URLs and parser literals retain source bytes. Existing `SKILL.ru.md`
files are migration inputs until a matrix row proves English source, owner, semantic
equivalence and rollback. Provider-rendered text and plans are localizable; comments and
development docs are English canonical prose.

Each admitted unit needs structural checks plus independent English semantic and Russian-render
review. The author/renderer cannot self-approve. Safety/contract/validation text and opaque
tokens outrank compactness budgets. P4 implements only approved matrix batches after the P0,
P1 and P2 gates; P2 itself mutates no content.

## Проверка

RAG: the P2 finding validates external syntax, private-use and canonicalization boundaries
against RFC 5646, last rechecked 2026-08-03; repo claims were read from
`core/provider/config.py` and `packages/skiller/scripts/check-translations.sh`.
Непроверено → ПОВТОРНЫЙ ПРОХОД: no runtime library/API is selected; P2.1 must pin
the IANA registry snapshot used by canonicalization. Обходки/[POSSIBLE-DEFECT]: some
legacy long-form skills may need complete localized rendering resources; record those as
overlays in the matrix, never as a second semantic source.
