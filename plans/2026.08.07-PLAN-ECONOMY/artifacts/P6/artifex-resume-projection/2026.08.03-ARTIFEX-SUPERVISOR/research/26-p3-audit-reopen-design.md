# P3 audit reopen design

## Inputs

- `brief/13-p3-audit-reopen.md`
- `findings/P3-audit-reopen-recon-2026-08-04.md`
- `phases/P3.md` → `## Audit P3 — 2026-08-04`
- prior P3 design: `research/09-p3-provider-adapter-design.md`,
  `research/24-p3.4-native-tool-projection-design.md`,
  `research/25-p3.4-successor-manifest-design.md`

## Forward-only remediation topology

The terminal P3.4 record stays historical. Rewriting it would not place the spec before
`d1362247` and would create a second false provenance claim. The reopened phase therefore adds
three sequential items whose specifications and `Files` sets are fixed before implementation:

1. **P3.5 runtime binding.** Add one provider-neutral `ProviderActivityPort` at the CLI edge.
   It receives the already verified indexed admission, resolves exactly one adapter, performs
   version/capability/binary preflight, and invokes `worker.run` only after a green preflight.
   The worker normalizes bounded stdout through the selected adapter before returning; raw
   output never enters the scheduler journal. CLI result counts come from the actual activity
   observation rather than a constant. The P2 scheduler/authority/dispatch modules remain
   provider-free. RAG:— (repo-grounded: recon facts 1–2 and frozen D74/D77/D80).
2. **P3.6 evidence proof.** Replace the fixture writer with a probe that opens the indexed
   admissions and calls the same activity preflight/dispatch path. A lawful preflight refusal
   remains non-green `real` evidence with zero process count; a fake-binary integration test
   proves the admitted green-preflight branch reaches a fresh bounded process and normalizes
   its envelope. The manifest gains a closed historical P2 anchor plus a closed current P3
   file set; the validator uses strict arguments, literal `git show` argv and adversarial
   mutations. RAG:— (repo-grounded: recon facts 2–3 and D81).
3. **P3.7 regression/closure fan-in.** Repair the Task invariant test so it discovers the
   current unique item set instead of asserting an obsolete cardinality, then rerun the full
   Task validation and every P3 closure gate. It produces closure-ready evidence but does not
   close the phase; `task:plan-close ... P3` remains the sole closure writer. RAG:—
   (repo-grounded: recon fact 5 and plan-protocol closure ownership).

The items are sequentially coupled: P3.6 hashes and probes P3.5 outputs; P3.7 validates the
complete P3.5/P3.6 tree. Therefore the binary orchestration criterion does not fire.

## Provenance repair

The plan-design change itself must be committed before P3.5 starts. P3.5 checks that its exact
heading and `Files` are present in `HEAD`, and refuses on a dirty target plan carrier. This
repairs pre-exec provenance forward without pretending the historical P3.4 item commit contained
future design files. The append-only Update Log receives a separate P3.1–P3.4 commit map instead
of rewriting old rows. RAG:— (repo-grounded: recon facts 4 and 6).

## Closure path

P3.5 → P3.6 → P3.7 → `task:plan-close 2026.08.03-ARTIFEX-SUPERVISOR P3` → cold independent
`task:plan-audit 2026.08.03-ARTIFEX-SUPERVISOR P3`. P4 remains gated until that audit is GREEN.
