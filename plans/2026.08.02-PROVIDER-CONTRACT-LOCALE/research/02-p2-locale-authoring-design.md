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

P2.1 binds canonicalization to the faithfully vendored `File-Date: 2026-06-14` registry
snapshot, SHA-256 `be1fad86a99e3a932d07b80c9b3c271ec2381a5909ce22420144e5077ab0a43a`,
731605 bytes. The canonical source identity remains the official IANA URL. During execution on
2026-08-14 that live URL had advanced to `File-Date: 2026-08-08`; the approved historical bytes
were therefore recovered from immutable mirror commit `9c61d166a353390977a21155796b4092bb796e50`
and independently matched against all three frozen identity fields. `upstream.json` records both
the canonical URL and actual retrieval URL so provenance does not imply that the current IANA
response still has the approved bytes.

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
Execution verification on 2026-08-14: Perplexity Web failed before retrieval because its Chromium
profile was locked; WebSearch found the IANA/FTP carrier and GitHub code search found the exact
historical digest. The immutable mirror download was verified locally by `sha256sum`, first-line
read and byte count. Confidence is high for byte identity and medium for mirror provenance; the
original official retrieval remains documented in `findings/12-design-audit-remediation-2026-08-03.md`.
Непроверено → ПОВТОРНЫЙ ПРОХОД: Perplexity synthesis of historical archive availability did not run;
the byte-level acceptance fact is nevertheless closed by the pre-approved digest and independent
immutable download. Обходки/[POSSIBLE-DEFECT]: the historical recovery uses an immutable third-party
mirror because IANA's live/FTP endpoints no longer serve the approved snapshot; some
legacy long-form skills may need complete localized rendering resources; record those as
overlays in the matrix, never as a second semantic source.

## Execution protocol observation

The durable P2.1 DecisionRequest completed as `approve`, but the Task queue helper also emitted
derived journal transition rows with null `session_id`/`run_id` and independently counted
attempts. The explicit P2.1 execution events retain the original verified route receipt and
run identity. The helper defect is recorded as a process deviation for repair in Task; it does
not change the locale contract, its evidence, or the terminal item binding.
