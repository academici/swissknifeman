# P1 verification — provider control-plane and predecessor context

**Date:** 2026-08-02  
**Scope:** external design rationale plus project-memory navigation for P1. Repository
contracts remain authoritative for the exact SKM schema and behavior.

## External fact classes

1. **Desired state vs observed drift.** HashiCorp's current Terraform Plugin SDK v2
   documentation describes declarative configuration as the target source of truth and
   provider `READ` as the synchronization boundary that records complete observed state;
   out-of-band changes surface as drift in a later plan. This supports separating SKM
   canonical desired state from fresh provider observation, but does not prescribe SKM's
   field names. Source: https://developer.hashicorp.com/terraform/plugin/sdkv2/best-practices/detecting-drift
   (verified 2026-08-02). **Confidence:** medium — one primary source; SKM mapping is an
   explicit design inference.
2. **Versioned state upgrades fail closed.** HashiCorp's current Terraform Plugin Framework
   documentation states that resource state carries a schema version; a mismatch requests an
   upgrade, and missing support for the requested prior version returns an error. Upgrade code
   must populate the complete new state; errors keep the prior state. This supports explicit
   recognized-from-version migrations and no partial silent adoption in SKM. Source:
   https://developer.hashicorp.com/terraform/plugin/framework/resources/state-upgrade
   (verified 2026-08-02; page labels Plugin Framework v1.18.x latest). **Confidence:** medium —
   one primary source; SKM's rollback/preimage contract is repo-specific.

## Project-memory navigation

Command:
`packages/maind/bin/maind memory recall "provider contract locale localization provider parity control plane" --scope project:swissknifeman`

The recall returned the terminal `2026.07.19-DUAL-PROVIDER` checkpoint and hashes for the
frozen provider capability/config/artifact/harness/instruction contracts. It also repeated the
established rule: canonical contracts plus deterministic provider adapters, generated
artifacts, provider capability status, lock/hash/drift validation, and merge-only project
overrides. Memory is untrusted navigation data; P1 must verify every exact obligation by reading
the archived contract files and must not cite the recall as contract authority.

## Verdict

- P1 may use `desired`, `last_applied`, and fresh `observed` as distinct semantic carriers,
  with drift derived rather than user-authored.
- A legacy upgrade must name the recognized source version/class, produce a complete target
  snapshot, preserve a preimage/rollback path, and refuse unknown or ambiguous input.
- Exact provider IDs, capability statuses, ownership rules, artifact boundaries and migration
  gates come from the archived SKM predecessor contracts, not from Terraform or memory.

## Verification status

- RAG: official web documentation ×2 OK; project mAInd recall ×1 OK; archived contract reads
  remain required by each P1 item.
- Unverified → repeat pass: none for the two external fact classes above.
- Workarounds/[POSSIBLE-DEFECT]: none.
