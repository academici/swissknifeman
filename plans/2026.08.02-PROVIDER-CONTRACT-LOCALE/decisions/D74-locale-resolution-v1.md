---
id: D74
date: 2026-08-14
status: accepted
type: contract_freeze_decision
item: P2.1
items: [P2.1]
contract_version: v1.0.0
supersedes: []
superseded_by: null
---
## Решение

The repository owner delegated the P2.1 choice to the executing agent and directed it to choose
the optimal solution and finish the item. Under that authority, DecisionRequest
`P2.1-locale-resolution-freeze`, action digest
`7518114159f02fdce57b8951acbedfeae3788bed7d8b55636c3928cb349181f2`, was resolved
`approve` with reason `P5_DECISION_OWNER_APPROVED`.

D74 accepts the L1–L6 set in `root/contracts/locale-resolution-v1.md` v1.0.0, final SHA-256
`365214ea0c98c7c9224c994158be7f80eafb6def83123159fd1026aedb74a8e2`. The approved
candidate SHA-256 before approval metadata was
`07c0ffd8b0598105e49f23c09d1a9e6275bf2e02f3e0a176e997a6233daee2d8`; its normative registry
input is `File-Date: 2026-06-14`, SHA-256
`be1fad86a99e3a932d07b80c9b3c271ec2381a5909ce22420144e5077ab0a43a`, 731605 bytes.

## Почему

The candidate satisfies the exact P2.1 acceptance inventory: independent locale surfaces,
single-owner precedence, separate syntax/canonicalization/catalog stages, deterministic `en`/`ru`
catalog behavior, private-use refusal, redacted provenance, and P1 no-write boundaries. Its
fixtures and checker validate those invariants against the pinned registry bytes.

## Consequences

D74 freezes the locale-resolution contract and its L1–L6 decision set for P3–P7 consumers. It
authorizes no runtime, configuration, provider, user, project, environment, fleet, or rendered
content mutation. Later semantic or byte changes require a typed decision and version verdict.
