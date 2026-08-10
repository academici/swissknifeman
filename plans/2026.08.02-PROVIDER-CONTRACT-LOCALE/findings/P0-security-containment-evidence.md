# P0.7 — executable security containment evidence

## Branch

The executable P0.7 producer selected the frozen no-op branch. Its verifier accepted only
`action_set=[]`, zero detector findings, zero protected-target delta and independently green
Claude Code and Codex rows. No containment decision was requested and no external target changed.

## Controls

The evidence contains only literal command argv, exit class, observation/expiry, aggregate detector
result and SHA-256 provenance. Raw output, absolute paths, account identifiers and secret values or
hashes are not persisted. The producer pins the P0.1 manifest/classification, P0.6 contract/checker,
P0.3 recovery evidence and D67; it recomputes the deterministic branch verdict on every `check`.

## Boundary

D68 assigns branch verification to the plan-local P0.7 producer. The frozen P0.6 recovery checker
remains a pinned input and is not changed. A future nonempty action set remains refused without an
exact accepted `containment_mutation_decision`.
