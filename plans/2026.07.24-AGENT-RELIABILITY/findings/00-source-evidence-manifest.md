# Finding 00 — committed source-evidence bundle

**Зафиксировано:** 2026-07-24. По owner decision D25 все execution-required
inputs материализованы под
`plans/2026.07.24-AGENT-RELIABILITY/artifacts/source-evidence/`.
Host paths ниже являются optional provenance и никогда не участвуют в
execution gate.

## Canonical bundle

| Evidence class | Canonical path |
|:--|:--|
| Full external audit snapshot | `artifacts/source-evidence/perplexity-audit.md` |
| Seven lossless plan journals | `artifacts/source-evidence/journals/` |
| Sanitized selected incidents | `artifacts/source-evidence/sessions/selected-incident-events.jsonl` |
| Bundle hashes/sizes | `artifacts/source-evidence/manifests/bundle-manifest.json` |
| Journal snapshot selection/provenance | `artifacts/source-evidence/manifests/journal-snapshots.json` |
| Session selection/redaction/provenance | `artifacts/source-evidence/manifests/selected-session-evidence.json` |
| Precomputed incident corpus | `artifacts/source-evidence/precomputed/corpus.json` |
| Precomputed baseline | `artifacts/source-evidence/precomputed/baseline.json` |
| Sanitized runtime before-state | `artifacts/source-evidence/runtime/` |
| Deterministic stdlib verifier | `artifacts/source-evidence/verify_source_bundle.py` |
| Format, privacy and verification contract | `artifacts/source-evidence/README.md` |

The bundle manifest is the only hash/size SSOT; this finding deliberately
does not duplicate values that could drift. `verify_source_bundle.py verify`
recomputes the manifest and semantic invariants from committed bytes only.
Missing optional origins are ignored; a missing or mismatched committed file
fails closed.

Design-time verification on 2026-07-24 passed all four modes: 20 manifest
entries, seven journal snapshots, five sanitized cases, corrected telemetry
denominators with the clean control, and eight claim ranges within the
2993-line audit. This proves bundle integrity before audit-design; it is not
P0.1 execution or its future verification report.

## External audit claim inventory

The full snapshot is retained, but its proposals remain hypotheses:

| Snapshot lines | Claim class | Planned use |
|:--|:--|:--|
| 21–169 | architecture map/target/roadmap hypotheses | P4.1 falsification only |
| 312–463 | provider/manifest/registry/lock hypotheses | P1 inventory; not fact before code proof |
| 625–766 | hook observations/hypotheses | P0.4/P3.1 |
| 767–912 | agent/orchestration duplication hypotheses | P1/P2 |
| 1049–1194 | telemetry/quality observations | P3 |
| 1363–1529 | proposed tests/gates | P0.3/P3.3; thresholds not adopted verbatim |
| 1538–1939 | roadmap/PR proposals | non-binding |
| 2903–2993 | executive summary/completeness | hypothesis summary, not acceptance evidence |

Addressed reads use the committed snapshot, for example:

```bash
sed -n '625,766p' plans/2026.07.24-AGENT-RELIABILITY/artifacts/source-evidence/perplexity-audit.md
```

## Provenance and privacy boundary

Original sources were the user-owned repository audit, seven journals in this
and foreign repositories, and selected Codex session records. Their exact
origins and source hashes live in the committed manifests. They may assist a
future forensic refresh but are not required to execute this plan.

The bundle contains lossless journal snapshots and only sanitized,
selection-manifested session events. Raw rollout files are intentionally
excluded because they may be hundreds of megabytes and contain secrets,
reasoning or unrelated bodies. Sanitization preserves only original hashes,
exact record selectors, timestamps, concise observable summaries and
confidence needed by the frozen corpus; raw event/tool/action payloads are
not retained. P0.1 verifies this boundary and never rescans profiles, mAInd,
`tmp/` or foreign repositories.
