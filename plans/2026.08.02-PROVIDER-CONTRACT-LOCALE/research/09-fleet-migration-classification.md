# P0.2 — fleet migration classification

This is a deterministic, no-write reduction of the sealed P0.1 evidence. A row is only
given a non-ambiguous class where the snapshot itself proves it; all other rows remain
no-op until a later P5 item supplies the missing ownership or semantic proof.

## Summary

| Classification | Rows | Disposition |
|:--|--:|:--|
| `ambiguous` | 13319 | no-op |
| `broken-link` | 102 | report to P5.1 |

## Brief-known cases

| Case | Traced rows | Classes | Disposition |
|:--|--:|:--|:--|
| FlexCRM | 12 | ambiguous: 12 | no-op pending P5 proof |
| Vintera | 0 | none | not observed in redacted path catalog |
| Insiders | 15 | ambiguous: 15 | no-op pending P5 proof |
| Azguard | 80 | ambiguous: 80 | no-op pending P5 proof |
| Dterema | 43 | ambiguous: 43 | no-op pending P5 proof |

## Safety boundary

No provider or fleet path was modified. `canonical-equivalent`, `local-override`, and
`stale-managed-copy` require evidence excluded from this privacy-minimized snapshot; they
are deliberately not inferred from a filename, a managed flag, or content similarity.

Machine source: `artifacts/P0-provider-fleet-classification.json`.
