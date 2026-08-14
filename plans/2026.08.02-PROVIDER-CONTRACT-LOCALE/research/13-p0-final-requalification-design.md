# P0 final requalification design

Sources: `brief/04-final-p0-requalification-2026-08-14.md`, `phases/P0/P0.md` audit attempt 2,
`artifacts/p0-provider-fleet-classify.py`, `artifacts/p0-recovery-gates-check.py`,
`artifacts/p0-security-trust-evidence.py`, `artifacts/p0-execution-provenance.py`, D67–D69 and
`root/contracts/provider-recovery-gates-v1.md`.

## 1. Closed defect set

The 2026-08-13 audit leaves two unresolved findings. First, the classification producer rebuilds
the same 13,421 artifact IDs, class sequence, counts and dispositions from the refreshed P0.5
manifest but changes evidence-source digests; the stored output and every downstream pin therefore
form one stale graph. Second, P0.7 treats a persisted observation as globally invalid ten minutes
after capture even though design, close and independent audit are separate roots. Both are
repository-observed acceptance defects; no external factual verdict is introduced. RAG:—
(repo-grounded: `phases/P0/P0.md` audit attempt 2 F1–F2)

## 2. Digest rebind without reclassification

P0.9 regenerates the classification through its existing owner and proves semantic identity by a
closed projection that excludes only volatile evidence-source digests: exact artifact-ID order,
classification, owner, action, rollback, destination, known-case mapping, policy and class counts
must remain equal. It records old/new source and manifest hashes plus every downstream pin, then
regenerates the P0.6 compact projection, recovery evidence and provenance checks from the new
source. A class/disposition/set difference is an acceptance failure, never an allowed refresh.
The old P0.8 literal remains historical evidence at its item commit; D70 and P0.9 become the current
forward acceptance carrier without rewriting that commit or any journal row. RAG:—
(repo-grounded: audit F1, D69, `artifacts/p0-provider-fleet-classify.py:check`)

## 3. Freshness at the use site

P0.10 separates two meanings that the current script conflates:

- persisted evidence is a provenance-bound observation record and can be checked for byte/input/
  privacy/no-op integrity without claiming it is live now;
- `admit` performs the real provider/trust/detector/protected-delta observations in the current
  invocation, validates them immediately and emits a redacted stdout receipt without persisting a
  reusable time-window token.

The final P0 audit runs `admit` as its last live acceptance command. P1 reruns the same command
immediately before its first product mutation, so an old P0 artifact never authorizes a current
transition. Unavailable/red provider rows, non-empty action sets, input drift or privacy findings
still fail closed. The frozen v1.0.1 contract remains byte-identical: its “fresh executable
producer” is the live `admit` path, while its sealed evidence requirement is met by the integrity-
checked observation and audit record. RAG:— (repo-grounded: audit F2,
`root/contracts/provider-recovery-gates-v1.md` P0.7 admission, D67–D68)

## 4. Final audit contract

P0.10 produces one committed static fan-in over the new digest graph, the live-admission command,
all P0 validators, generated views and plan lint. Phase close then hands off to one final
independent P0 audit invocation. Under the repository continue-first protocol, any deterministic,
reversible and in-scope defect found there is repaired and revalidated within that audit root; it
does not open another design cycle. Only a reproduced owner/frozen-contract boundary may return a
new design recommendation. A GREEN audit opens P1 subject to a new live `admit` pass at P1 entry.
RAG:— (repo-grounded: plan-protocol continue-first gate and owner refinement 2026-08-14)

## 5. Pre-mortem

| Failure after 6–12 months | Early signal | Mitigation / owner |
|:--|:--|:--|
| Digest refresh silently changes dispositions | semantic projection differs while row count stays equal | P0.9 rejects any exact-field delta; P0.2 remains classification owner |
| A stale file is mistaken for current security health | caller invokes integrity check but not `admit` | P0.10/P1 gate require live `admit` exit and stdout receipt; persisted record never grants admission |
| Final audit repeats the prior loop for bookkeeping drift | same non-material fingerprint produces another design handoff | audit root regenerates once and continues; only authority/frozen semantics can cross the boundary |
| Live admission leaks host paths or secret material | stdout contains disallowed absolute/secret patterns | allowlisted redaction/privacy scan fails before receipt; no raw stdout/stderr persists |
| Contract v1.0.1 changes accidentally during repair | D67 exact SHA no longer matches | P0.9/P0.10 assert byte-identical contract and D67 binding before every write/final gate |

RAG:— (repo-grounded: P0 audit attempts 1–2, root security/evidence/generated-artifact rules)
