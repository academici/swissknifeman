# P0 pre-mortem

Assume the programme failed after 6–12 months. The recovery gates assign the
following mitigations before any later transition is opened.

| Failure mode | Early signal | Mitigation | Owner gate |
|:--|:--|:--|:--|
| One provider is treated as proof for both | missing provider row | independent Claude/Codex rows | R01–R07 |
| User-owned content is overwritten | absent provenance/preimage | preserve and require P5 ownership proof | R06 |
| Credential exposure is hidden by prose | detector unavailable or nonzero | no-op branch fails; separate mutation authority | P0.4 |
| Dirty observation becomes release proof | working-tree-only evidence | committed digest-qualified evidence | R01 |
| Recovery is claimed after partial failure | one postcondition fails | rollback and keep dependent gate closed | R01, R06 |
