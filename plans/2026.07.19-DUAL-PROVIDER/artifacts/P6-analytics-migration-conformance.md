# P6.4 analytics migration conformance

Anchor: `2b4621ed` before this evidence artifact.

## Focused integrated matrix

| Seam | Command | Result |
|---|---|---|
| core envelope | `PYTHONPATH=. python3 -m unittest core.tests.test_runs` | GREEN (2 tests) |
| analyst readers/migration | `PYTHONPATH=.:packages/analyst/lib python3 -m unittest packages.analyst.tests.test_provider_readers packages.analyst.tests.test_capture` | GREEN (3 tests) |
| maind consumer | `PYTHONPATH=.:packages/maind/lib:packages/maind python3 -m unittest tests.test_analyze` | GREEN (17 tests) |
| generated harness capture bundle | `PYTHONPATH=.:packages/harness/lib:packages/harness python3 -m unittest tests.test_provider_hooks` | GREEN (9 tests) |

The combined unittest invocation is intentionally not used: both packages expose a top-level
`tests` package, so it resolves one package's tests over the other. Separate package-local
focused runners prove the same seams without changing source or weakening a test.

## Contract assertions

- explicit `(provider_id, schema)` readers reject unknown provider/schema;
- normalized events contain only the D90 allowlisted envelope and opaque provenance;
- writes target `.swissknife/analytics`, never `.claude`;
- legacy migration plan/apply is collision-safe, idempotent, copy+verify, and source-byte preserving;
- mAInd reads only the neutral store;
- the P2 artifact API generates the Codex capture handler, which excludes prompt content.
