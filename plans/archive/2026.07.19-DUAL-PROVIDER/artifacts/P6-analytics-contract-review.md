# P6.3 analytics contract review

Status: accepted and frozen for P6.4 consumption.

## Repo-grounded P5 inventory

The Claude reader source is `configs/claude-code/hooks/run-report` (`SCHEMA=2`). It parses a line-streamed transcript and produces the observed normalized candidates `tools`, `files`, `workflows`, `retrieval`, `devloop`, `maind`, `usage`, `reads`, and `errors`. Those names are inventory evidence, not permission to carry provider payload shapes into the neutral contract.

Codex evidence is the committed P5 hook/context support matrix. P6.3 treats that matrix as capability and context evidence only and does not invent Codex raw keys, event names, or payload shapes.

Evidence sources:

- `packages/harness/configs/claude-code/hooks/run-report` — sha256 `72703a62558653ff2a7413641ceb32767e764357e4b43076bf69463342276e3c` (`run-report.py`)
- `plans/2026.07.19-DUAL-PROVIDER/artifacts/P5-hook-context-matrix.md` — sha256 `7695eec299a57e5086be193267965ce1245366938425025e865f907b5be1706a`

The recorded hashes were computed from the named P5 evidence sources after both P6.3 files existed.

## Alternatives

### A — Claude-shaped common store — REJECT

A shared store modeled on Claude's current report would make one provider's transcript conventions, schema number, and categories the ecosystem contract. Codex would either impersonate Claude or require implicit lossy mappings. This violates provider neutrality and leaks raw-provider evolution into consumers.

### B — Per-provider normalized stores — REJECT

Separate Claude and Codex normalized homes would preserve provider distinctions but force every consumer to branch, duplicate retention and migration logic, and reconcile incompatible identities. “Normalized” would cease to mean a stable shared semantic boundary.

### C — Neutral `.swissknife` store + explicit named readers + legacy fallback — ACCEPT

Use `.swissknife/analytics` for normalized append-only analytics and `.swissknife/analyst` for human-curated analyst state. Provider-specific acquisition and interpretation live only in explicit named readers. A bounded legacy Claude `SCHEMA=2` fallback dual-reads existing data while all new writes target the neutral store.

## Consequences

- Producers map allowlisted semantics into one versioned envelope; provider-specific raw paths, event names, and shapes remain reader-local.
- Consumers depend on the neutral contract rather than provider files and can reject unknown providers or schemas deterministically.
- Privacy improves because transcripts, prompts, raw bodies, and resolved secrets never enter normalized storage.
- Provenance remains locally auditable through opaque references and hashes without copying raw evidence.
- Migration requires explicit plan, dry-run, check, and apply phases; it costs operational work but preserves source bytes.
- Legacy reads are temporary compatibility behavior, not a second write contract.

## Producer-to-P6.4-consumer matrix

| Producer | Reader boundary | Neutral output | P6.4 consumer behavior |
|---|---|---|---|
| Claude `SCHEMA=2` run report | named Claude legacy reader | semantic envelope, run report, opaque provenance | dual-read legacy input; consume neutral records; never write legacy |
| Codex P5-supported hook/context evidence | named Codex reader | semantic envelope, run report, opaque provenance | consume only capabilities actually supported by the committed P5 matrix; reject unknown schema/provider |
| Migration tool | migration reader with conflict checks | copied and verified neutral events plus audit records | plan/dry-run/check/apply; surface collisions; preserve all source bytes |
| Human analyst promotion | provider-neutral promotion path | append-only audit plus curated analyst state | keep human promotion semantics unchanged |

## Delegated verdict

D79 authority accepts Alternative C. This acceptance freezes D90: P6.4 MUST consume the neutral store through explicit named readers and the bounded legacy fallback defined by `provider-analytics-contract v1.0.0`; changing that boundary requires a new versioned decision.
