# Slice A design synthesis

## Target flow

```text
build canonical candidate
  → bind snapshot/fingerprint
  → apply explicit owner authority path (existing contract)
  → normalize and inspect latest phase-audit subject
      ├─ current GREEN      → allow audited close
      ├─ stale/ATTN/RED/bad → exact refusal
      └─ absent             → Phase Assurance admission
          ├─ valid isolated/direct-close + all objective evidence green → allow
          └─ otherwise → audit-required with exact reason
```

## Phase Assurance normalized contract

`phase_assurance.py` owns enums, parsing, canonicalization and typed diagnostics. Consumers never
parse the Markdown independently. Canonical payload contains:

- `schema_version="phase-assurance/v1"`;
- `impact` closed enum;
- unique sorted seam IDs;
- boolean live/irreversible marker;
- closed audit intent;
- normalized nonblank rationale.

The payload is conditionally added to the candidate snapshot and digest only when valid. Invalid
present input refuses candidate/direct-close admission; absent legacy input remains digest-compatible
but cannot self-authorize direct close.

### Resolved fingerprint trade-off (D3)

- **Recommended and accepted: optional canonical payload.** It stales on semantic assurance edits,
  preserves legacy P1 bytes and ignores formatting-only equivalence.
- **Rejected: assurance outside fingerprint.** It would let a post-audit public/required contract
  change to isolated/direct-close without invalidating the audit.
- **Rejected: always-present null/sentinel or raw Markdown.** The former breaks P1 recovery; the
  latter turns whitespace/prose formatting into repeat-audit noise.

## First-audit admission matrix

| Current evidence | Outcome |
|:--|:--|
| matching GREEN audit | audited close, regardless of missing legacy assurance |
| matching stale/ATTENTION/RED/invalid audit | exact refusal; no declaration fallback |
| candidate unresolved, non-green head, material risk, invalid terminal evidence | audit-required/repair with exact reason |
| assurance missing/invalid, `auto`, `required`, public/security, live, or nonempty seams | audit-required |
| valid `isolated` + empty seams + `no` + `direct-close-eligible` + all green objective evidence | direct close |

`Review` remains item review depth/effective metadata. Item count remains topology. Neither is an
independent phase-audit trigger.

## Publication and validation topology

1. Implement runtime/schema and focused negative tests.
2. Synchronize commands, plan-protocol canon/reference/template and package docs.
3. Regenerate Task provider artifacts; regenerate Skiller registry projections; sync aggregate docs.
4. Run focused tests, Task validation, Skiller validation, generated `--check` gates and plan lint.
5. In a separate phase, consume the existing P1 GREEN audit and close only its phase bookkeeping.

## Deliberate exclusions

No impact-mode carrier, diff graph, dependency closure, validation receipt v2, evidence TTL/reuse,
repeat-full justification/budget, P10 broker implementation or target-P1 product revalidation.
