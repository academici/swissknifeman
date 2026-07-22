# P6.4 analytics migration conformance

Anchor: `810bf587` before this evidence artifact.

## Focused integrated matrix

| Seam | Command | Result |
|---|---|---|
| core envelope | `PYTHONPATH=. python3 -m unittest core.tests.test_runs -q` | GREEN (2 tests) |
| analyst readers/migration/consumers | `PYTHONPATH=.:packages/analyst/lib python3 -m unittest packages.analyst.tests.test_provider_readers packages.analyst.tests.test_capture packages.analyst.tests.test_digest packages.analyst.tests.test_sessions packages.analyst.tests.test_token_report packages.analyst.tests.test_lessons -q` | GREEN (80 tests) |
| maind consumer | `PYTHONPATH=.:packages/maind/lib:packages/maind python3 -m unittest tests.test_analyze` | GREEN (17 tests) |
| generated harness capture bundle | `PYTHONPATH=.:packages/harness/lib:packages/harness python3 -m unittest tests.test_provider_hooks -q` | GREEN (9 tests) |

The combined unittest invocation is intentionally not used: both packages expose a top-level
`tests` package, so it resolves one package's tests over the other. Separate package-local
focused runners prove the same seams without changing source or weakening a test.

## Contract assertions

- explicit immutable `(provider_id, schema)` readers reject unknown provider/schema;
- reader provenance hashes the exact source bytes supplied by `analyst capture`; mismatch,
  missing provenance, traversal, prompt/secret values, nested metrics, and unknown metrics fail closed;
- stable event IDs derive from source bytes, not parsed-dict order; projections expose only observed
  neutral metrics plus contributing provenance and do not synthesize raw-shaped defaults;
- all new machine writes target `.swissknife/analytics`; all new analyst state writes target
  `.swissknife/analyst`, with bounded legacy reads retained for compatible historical data;
- legacy migration plan/dry-run/check are no-write; apply is copy+verify, idempotent, collision-safe,
  and source-byte preserving;
- mAInd consumes neutral events and reports deterministic metrics/provenance; sessions remains a
  read-only bounded legacy transcript acquisition and has a focused no-write proof;
- the P2 artifact API generates a Codex handler that rejects prompt/nested input. Its safe stdout is
  written as a source file and consumed through the public `analyst capture` path, proving stored
  provenance SHA-256 equals the exact file bytes.

## Supervisor acceptance repair — `acfdbaac`

| Seam | Command | Result |
|---|---|---|
| Claude reader and immediate analyst consumers | `PYTHONPATH=.:packages/analyst/lib python3 -m unittest packages.analyst.tests.test_provider_readers packages.analyst.tests.test_digest packages.analyst.tests.test_token_report packages.analyst.tests.test_sessions packages.analyst.tests.test_lessons -q` | GREEN (81 tests) |
| mAInd neutral consumer | `PYTHONPATH=.:packages/maind/lib:packages/maind python3 -m unittest tests.test_analyze -q` | GREEN (17 tests) |

The Claude SCHEMA=2 reader now emits a metric only when its named source evidence exists:
`tools.total`, `tools.by_name.Read`, list cardinalities for files/workflows/tool failures,
`retrieval.calls`, documented devloop list cardinalities, mAInd `calls`, and numeric usage
aggregated from totals or main/subagent rows. Missing evidence stays absent. A malformed scalar
fails with `ANALYTICS_CORRUPT_EVENT` without exposing its value; harmless additive raw fields are
ignored. This repair preserves immutable reader registration and exact source-byte provenance.
