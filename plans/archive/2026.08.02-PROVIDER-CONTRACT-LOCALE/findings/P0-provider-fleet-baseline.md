# P0.1 — provider and fleet baseline

**Observation scope:** the live SKM project registry at item execution, each registered
repository's allowlisted provider carriers, and read-only SKM observer commands. This
finding is anchored by the item commit that introduces the sibling evidence bundle; it
does not classify or repair any observation.

## Evidence bundle

- Producer: `PYTHONPATH=. python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p0-provider-fleet-inventory.py --write`
- Verification: `--check`, `--self-test`, and `evidence/verify.py` returned `allow`.
- Privacy: the bundle stores redacted stable project IDs, relative carrier paths, schema-only
  config observations, and safe digests. It excludes absolute roots, config values and
  value-derived hashes, transcripts, tool payload bodies, and secrets.
- Coverage: 57 registry records collapse into 23 stable redacted projects; both `claude-code`
  and `codex` have 23 explicit provider rows. The carrier snapshot contains 13,421 allowlisted
  paths. These counts are observations at the item commit, not claims about a future fleet.

## Observer outcomes

| Observation | Result | Evidence class |
|:--|:--|:--|
| `harness hooks --target . --provider codex --observer --trusted --dry-run` | red (exit 1): `ValueError: root must be explicit and absolute` | public-CLI defect baseline |
| Same command with resolved absolute target | green (exit 0), plan identity and operation set present | no-write control |
| `harness doctor --provider-audit --json` | green (exit 0), diagnostics empty | provider audit |
| `maind health --cwd --strict` | green (exit 0) | SKM health |
| `codex doctor --json` | green (exit 0), `overallStatus=ok` | Codex runtime |
| `codex plugin list --json` | green (exit 0), `task@swissknifeman` installed/enabled | Codex plugin provenance |
| `skiller bucket-audit` and `skiller budget --profiles` | green (exit 0) | pre-change skill/audit/profile baseline |

The relative-target hook failure is retained as required evidence for P3.2; this item makes
no repair. The absolute-target dry-run is an observer-only control and records no target-file
mutation.

## Verification boundary

Each project has one independent row per provider. A provider is never inferred green from
the other provider's row; unavailable, red, and not-selected states remain explicit. The
verifier rejects the mandatory negative fixtures: missing project, extra path, duplicate
artifact ID, absolute-root leak, secret-like value/digest, bundle-member mismatch,
broken-symlink misclassification, unsupported provider, and malformed command result.

## P0.5 forward repair — 2026-08-10

P0.5 rebuilt the baseline without any fleet, provider, credential, trust, or consumer write.
The production verifier now requires exact registry/snapshot project IDs, the full Claude/Codex
provider-row cross-product, every provider carrier-path set, and unique artifact IDs. The machine
carrier retains source-skill/bucket counts, source-class and multi-label observations, repeated
warnings, plus separate provider-qualified profile measurements with unit, method, raw-output SHA,
tool commit, observation/expiry and explicit availability.

`artifacts/P0.5/fixtures/test_negative_fixtures.py` copies the baseline for each test, mutates one
class, and calls the production verifier. All required negative classes reject deterministically;
an unchanged second `--write` is byte-stable.
