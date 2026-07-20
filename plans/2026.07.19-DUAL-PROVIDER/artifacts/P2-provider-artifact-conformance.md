# P2 provider-artifact conformance

**Producer:** P2.4 · **Inputs:** frozen `provider-artifact` and
`provider-capability` v1.0.0 contracts · **Tree anchor:** `56c579f`

The executable evidence is `core/tests/test_provider_artifact_e2e.py`. It uses
only `TemporaryDirectory` roots for render targets and lock application; preview
and doctor consume an already-built immutable plan and do not call a writer.

## Synthetic contract matrix

| Case | Scenario | Expected observation / action | Expected severity |
|:--|:--|:--|:--|
| C1 | clean managed artifact | `clean` / `noop` | `green` |
| C2 | source or adapter change | `stale-source` / `update` | `warning` |
| C3 | local managed-byte edit | `managed-drift` / `refuse` | `error` |
| C4 | target missing with valid lock | `missing` / `create` | `warning` |
| C5 | existing unowned target | `ownership-conflict` / `refuse` | `error` |
| C6 | malformed lock | `provenance-invalid` / `refuse` | `error` |
| C7 | unsupported required capability | `unsupported` / `refuse` | `error` |
| C8 | explicit repair after managed drift | `managed-drift` / `repair` | `warning`, then `green` |

## Assertions

- Synthetic Claude Code and Codex descriptors produce one stable catalog order.
- `artifact_dry_run(plan)` and `artifact_doctor(plan)` project the same immutable
  `ArtifactPlan` that `apply_plan(root, plan)` receives; two previews are
  byte-identical as data and no filesystem bytes change before explicit apply.
- After create or explicit repair, doctor is `green` and the second apply is a
  no-op plan.
- Repository `config.json`, FOREMAN plan sentinel, and external fleet config
  sentinel are snapshotted before/after under the fixture parent; delta is 0.
  No real repository, FOREMAN, or fleet root is passed to the engine.

## Reproduction

```bash
PYTHONPATH=. python3 -m unittest discover -s core/tests -p 'test_provider_artifact_e2e.py'
PYTHONPATH=. python3 -m unittest discover -s core/tests
```
