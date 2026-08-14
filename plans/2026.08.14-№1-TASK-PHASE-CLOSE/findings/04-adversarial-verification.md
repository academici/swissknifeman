# Adversarial verification — Slice A boundaries

**Дата:** 2026-08-14
**Evidence:** RAG:— (independent repository-grounded review of recon findings).

## Verdicts

1. **Fingerprint:** hash only a valid canonical assurance payload, conditionally. Hash semantic
   fields, not raw Markdown. Missing/invalid legacy assurance leaves the old digest input byte-for-byte,
   preserving `7ce1…`; semantic assurance change on a new phase changes its fingerprint; formatting-only
   canonical equivalence does not.
2. **Gate ordering:** after snapshot binding and any explicit owner authority path, find the latest
   audit by normalized subject before direct-close policy. Same-fingerprint GREEN allows; stale,
   ATTENTION, RED and invalid deny. Only complete absence of phase-audit rows permits unaudited policy.
3. **Schema owner:** a tiny stdlib-only `phase_assurance.py` avoids the real
   `plan_gates → plan_bundle → plan_lint → plan_gates` cycle and prevents duplicate parsers.
4. **Scope:** `audit-impact/v1`, mode broker, receipt v2, diff/dependency graph, executed/reused
   telemetry and repeated-full budget belong to Slice B/C and must not appear in Slice A code.

## Acceptance invariants

- Canonical and legacy subject are identical for writer/readers, while new writes persist only `Pn`.
- Valid green multi-item isolated direct-close phase closes without audit regardless of `Review`.
- Missing/invalid/public/security/live/seamed/material/non-green input cannot direct-close.
- Negative/stale audit evidence cannot be hidden by assurance.
- Legacy P1 GREEN closes with fingerprint `7ce1…`, without new audit or item Validation.
