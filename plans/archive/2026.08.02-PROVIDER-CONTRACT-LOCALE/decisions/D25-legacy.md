---
id: D25
date: 2026-08-02
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P4 pre-mortem: likely failures are cosmetic source-direction reversal, translated literals/placeholders, one-provider-only Russian render, half-migrated generated output, incomplete corpus inventory/self-review, and foreign dirty-tree capture. RAG:— (repo-grounded: P4 recon/research, current dirty tree and predecessor generated/ownership gates).

## Почему

Mitigations are assigned respectively to P4.2/P4.3 writer gates, P4.1/P4.2 token fixtures, P4.1/P4.4 provider-pair tests, P4.6 terminal regeneration, ledger+independent review, and explicit preimage/Files staging.
