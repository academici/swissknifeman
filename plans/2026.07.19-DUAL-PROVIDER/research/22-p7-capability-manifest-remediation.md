# P7.1 remediation design — capability manifest → gates → docs

**Date:** 2026-07-22
**Inputs:** `findings/P7.1-capability-manifest-gap-2026-07-22.md`, frozen
`root/contracts/provider-capability-contract.md`, accepted
`root/adr/0001-provider-adapter-architecture.md`, terminal P3–P6 conformance artifacts.

## Problem boundary

P7.1 cannot generate a trustworthy support matrix because the normative manifest promised
by D3/D55 was never materialized. Existing package catalogs remain legitimate semantic
sources for their own skills/commands/harness/instruction/analytics records, but they cannot
independently own provider Support Level, native binding, evidence or diagnostic. Those
cross-package fields belong to the single manifest. RAG:— (repo-grounded:
`findings/P7.1-capability-manifest-gap-2026-07-22.md`, capability contract Derived consumers)

The remediation is one coupling-hotspot bundle. It does not reopen provider semantics or
translate one provider output into another; it materializes and wires the already-frozen
contract before deriving docs.

## Alternatives

| Alternative | Result | Verdict |
|:--|:--|:--|
| Hand-author README/docs from the plan or current files | fastest, but creates a second support canon and has no no-write drift gate | reject |
| Aggregate P3–P6 rendered outputs/conformance reports into a matrix | deterministic but self-confirms the implementation being checked; cannot supply pre-render adapter gates | reject |
| Root-owned manifest + pure shared validator/projection + explicit production consumers + root docs render/check | one support/evidence source, fail-closed pre-render gates and reproducible docs | choose |
| Re-design frozen schema/support vocabulary | unnecessary authority expansion; no evidence that D55 schema is insufficient | reject |

## Chosen design

1. `configs/provider-capabilities.json` is the umbrella-owned carrier. It implements the
   exact v1.0.0 envelope and is the only author-owned source for support level, binding,
   limitations, evidence, diagnostic and native extensions.
2. `core/provider_manifest.py` parses and validates the full contract without filesystem
   discovery; an explicit path loader is a thin boundary. It projects the rich manifest to
   the existing `ProviderConfigCatalog` used by resolution/registry gates, preserving the
   frozen P1 API while adding the missing contract data model.
3. Production adapters keep package-owned semantic requirements but receive their support
   projection from the root manifest. Ad-hoc production `ProviderConfigCatalog(...)` and
   free-form `capability_support` maps are removed; tests may construct synthetic invalid
   catalogs explicitly.
4. `scripts/provider-docs.py --write|--check` is the named repo operation. It consumes the
   validated manifest plus package semantic catalogs/conformance inputs, renders only marked
   README bytes and the complete `docs/provider-support.md`, and carries contract/catalog
   version plus source SHA-256. `--check` is strictly no-write.
5. Candidate catalog bytes, exact capability/native-extension sets, evidence freshness and
   shared-core contribution review are approved by an explicit Owner D# before production
   consumers switch to the carrier. This is a catalog-content/public-API freeze, so
   `gpt-5.6-sol/xhigh` and `Exec=manual` are required.

RAG:— (repo-grounded: D2/D3/D14/D17/D55,
`root/contracts/provider-capability-contract.md`,
`root/adr/0001-provider-adapter-architecture.md`)

## Compatibility and anti-scope

- Claude/Codex rendered bytes and package semantic catalog IDs do not change merely to fit
  the new manifest. A mismatch is a blocker and names the owning package/contract.
- No package output is parsed back into support truth. Actual render hashes remain
  conformance evidence, never manifest input.
- No live install/apply/repair, bootstrap cleanup, FOREMAN mutation, fleet write, tag, push
  or provider-contract schema change is part of P7.1.
- Root manifest discovery is explicit from repository root; linked worktree/user-home/fleet
  discovery and implicit fallback are forbidden.

## Acceptance shape

The item is ready only when one anchored run proves:

- full manifest schema/provider-matrix validation and stable canonical hash;
- every production adapter requirement resolves to exactly one manifest capability and an
  allowed support level before render;
- no production hard-coded support catalog/free-form support map remains;
- package conformance and Claude compatibility stay green;
- docs second write is empty and `--check` is byte-identical/no-write;
- README/docs exact-set has no missing/extra/duplicate common capability or native extension;
- protected FOREMAN/fleet/live paths have delta zero.

## Verification status

- External facts: none introduced; current provider claims remain pinned to the existing
  first-party evidence records carried by the frozen plan findings.
- Repo-grounding: complete for the missing carrier/call-path verdict; commands and results
  are captured in `findings/P7.1-capability-manifest-gap-2026-07-22.md`.
- Open design choice: none after D98; exact catalog content is an explicit in-item Owner D#
  gate, not an assumption in this design session.
