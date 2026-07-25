# P3 skill-publication conformance

**Producer:** P3.5 · **Contracts:** provider-skill-publication, provider-capability,
provider-artifact and provider-config v1.0.0 · **Evidence owner:**
`packages/skiller/tests/test_provider_publication_parity.py`

## Independent inventory and projections

The expected semantic inventory is read directly from `packages/skiller/skills.json`
and `configs/core-policy.json`; the test does not derive that expectation from a
Claude or Codex renderer. On the P3.5 item tree it contains 216 semantic IDs in 47
buckets, plus the `core`, `generate-skill`, and `skm` publication units. The test
requires unique IDs, core-policy order/uniqueness, direct bucket projection for both
providers, exact Codex marketplace unit set, package-version provenance, and exactly
the declared self-contained Codex core members.

| Projection | Generated artifacts | Deterministic digest |
|:--|--:|:--|
| Claude | 49 | `66b27d5466ed935844ed7d51aeb22cb7139e34fb2f1ae7dfa55e00d2995eb6fd` |
| Codex | 63 | `da6747e95d63092082dbf7c8e84de222e17a1125755d8ab3758ff272094d64c8` |

The digest is a SHA-256 over pathlib-sorted repository-relative target path, NUL,
and exact rendered bytes. It is diagnostic only; the executable assertion compares
two independently repeated renders rather than fixing a count or digest as an
expected semantic set.

## Vendor and no-write matrix

All targets are `TemporaryDirectory` projects, except the explicit render-only
snapshot of the real `.claude-plugin`, bootstrap `.agents/skills`, and
`plans/2026.07.18-FOREMAN` surfaces. The latter has byte delta zero. No real user
home, FOREMAN, or fleet target is passed to sync/apply.

| Case | Required outcome | Executable assertion |
|:--|:--|:--|
| dry-run | no project bytes written | pre/post recursive snapshot equal |
| dual vendor apply | Claude and Codex locked copies exist | provider-qualified targets present |
| second apply | byte-idempotent | pre/post recursive snapshot equal |
| unmanaged Codex target | fail closed before Claude write | complete pre/post snapshot equal |
| managed byte drift | ordinary sync refuses | complete pre/post snapshot equal |
| explicit repair | pre-image and observed/expected/source hashes | backup exists; all three hashes are `sha256:` values |
| corrupt/newer lock | fail closed before config/provider write | complete pre/post snapshot equal |
| native install on dry-run | explicit-boundary diagnostic, no subprocess | `SPUB_INSTALL_EXPLICIT_REQUIRED`; runner count 0 |

`provider-publication-cases.json` records the stable case inventory. The harness
also asserts complete source/rendered provenance labels for every rendered artifact.

## Reproduction

```bash
PYTHONPATH=packages/skiller/lib:packages/skiller:. python3 -m unittest \
  tests.test_provider_publication_parity tests.test_channel_parity
```

The command passed twice with the same ordered unittest report. Per D80, terminal
package validation, `skiller registry --check`, release/docs assessment, phase close,
and independent audit remain phase-boundary work after this P3.5 item commit.

## Downstream handoff

P4 and P7 consume only the frozen publication boundary: canonical skills stay below
`packages/skiller/skills`, Claude identities remain compatible, Codex marketplace is
`.agents/plugins/marketplace.json`, self-host adapters stay thin, and consumer vendor
copies are provider-qualified and provenance-locked. Task invocation semantics and
live self-host installation remain out of scope.
