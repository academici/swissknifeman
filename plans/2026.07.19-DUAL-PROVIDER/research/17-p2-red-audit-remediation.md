# P2 RED audit remediation design

**Дата:** 2026-07-20

**Основание:** `phases/P2.md` `## Audit P2 — 2026-07-20`,
`root/contracts/provider-artifact-contract.md`, `core/provider_artifact.py`,
`core/provider_lock.py`, `core/tests/test_provider_{artifact,lock,artifact_e2e}.py`.

## Diagnosis

Audit establishes three connected gaps. First, the render request accepts arbitrary override
mappings while lock parse can reconstruct semantically incomplete provenance; identity matching
then checks only a subset. The frozen contract requires non-empty source provenance and stable
override ID/owner/order/provenance, so this is a fail-closed bug, not a new contract decision.

Second, clean/noop apply still serializes and atomically replaces the lock. The contract's clean
row explicitly says `noop` and `no write`; lock replacement is therefore forbidden even if its
bytes do not change.

Third, the P2 report proved whole-file cases but not the contract-required managed-block and
project Override goldens. Core must not invent package marker syntax, so the narrow seam is an
explicit caller-owned codec pair passed with the precomputed plan: `extract(file_bytes,
ordered_block_ids)` obtains exactly the contract-hashed managed bytes; `replace(file_bytes,
managed_bytes, ordered_block_ids)` produces complete target bytes. Both are verified before
write; a missing/invalid codec produces `boundary-invalid/refuse` with zero writes.

## Chosen remediation

P2.5 keeps the frozen contract and P2.1 `core.__all__` unchanged. It strengthens existing
constructors/parser/matching and extends existing P2.2 plan/apply inputs only. Each override
layer has exact canonical keys `id`, `owner`, `order`, `provenance`; IDs/owners are stable
non-empty identifiers, order is a non-negative non-boolean integer and unique, provenance is
non-empty canonical JSON data, and the caller sequence is preserved. Parsed lock records use the
same validator. Full provenance identity comparison includes sources, adapter/provider,
source/render hashes, boundary, override layers and capability requirements.

The conformance report gains named, hand-authored cases for successful whole-file and
managed-block lifecycle, project Override to stale-source/update, malformed provenance and
override refusal, boundary-invalid refusal, clean/noop zero writes, managed drift/repair and
ownership/capability refusal. Block fixtures have two blocks and assert prefix, inter-block and
suffix preservation.

## Boundaries

No package adapter, CLI, real provider path, marker grammar, discovery, mutable registry,
frozen contract/ADR edit, K1–K6/core export change, FOREMAN/fleet access or unrelated working-tree
change is authorized. A codec is supplied only by a caller that owns its format; future P3–P6
adapters provide real codecs when they own a managed file format.

RAG:— (repo-grounded: frozen contract Managed boundary/Override/Observation sections and Audit
P2 findings).
