# P2 provider-artifact conformance

**Producer:** P2.4 + P2.5 D76 remediation · **Inputs:** frozen `provider-artifact` and
`provider-capability` v1.0.0 contracts · **Tree anchor:** P2.5 remediation tree

The executable evidence is `core/tests/test_provider_artifact_e2e.py`. It uses
only `TemporaryDirectory` roots for render targets and lock application; preview
and doctor consume an already-built immutable plan and do not call a writer.

## Synthetic contract matrix

| Case | Scenario | Expected observation / action | Expected severity |
|:--|:--|:--|:--|
| C1 | whole-file clean managed artifact | `clean` / `noop`, zero target/backup/lock writes | `green` |
| C2 | whole-file source or adapter change | `stale-source` / `update` | `warning` |
| C3 | local managed-byte edit | `managed-drift` / `refuse` | `error` |
| C4 | whole-file target missing with valid lock | `missing` / `create` | `warning` |
| C5 | existing unowned target | `ownership-conflict` / `refuse` | `error` |
| C6 | malformed provenance or override lock record | `provenance-invalid` / `refuse`, no write | `error` |
| C7 | unsupported required capability | `unsupported` / `refuse` | `error` |
| C8 | explicit repair after managed drift | `managed-drift` / `repair` | `warning`, then `green` |
| C9 | caller-coded managed-block update | `stale-source` / `update`; prefix/inter-block/suffix preserved byte-for-byte | `warning`, then `green` |
| C10 | valid project Override changes source envelope | `stale-source` / `update`, not local drift | `warning` |
| C11 | duplicate/nested/missing/reordered managed blocks | `boundary-invalid` / `refuse`, no write | `error` |
| C12 | D110 exact chained D104 + `.mcp.json` admission | three canonical lock records; MCP bytes unchanged; altered path/hash/ID/boundary/server/predecessor and stale preconditions refuse with writer `0`; every write-boundary failure restores the exact temporary-root pre-state | `warning`, then `green` |

## Assertions

- Synthetic Claude Code and Codex descriptors produce one stable catalog order.
- `artifact_dry_run(plan)` and `artifact_doctor(plan)` project the same immutable
  `ArtifactPlan` that `apply_plan(root, plan)` receives; two previews are
  byte-identical as data and no filesystem bytes change before explicit apply.
- After create or explicit repair, doctor is `green` and the second apply is a
  no-op plan that does not invoke the target, backup, or lock writer.
- Provenance and every Override layer are validated both at render and lock-parse
  boundaries: sources are non-empty/canonically ordered and each layer has exact
  `{id, owner, order, provenance}` data with unique IDs/owners/orders.
- Managed-block fixtures supply an explicit per-artifact extract/replace codec;
  they prove two ordered blocks, project-override stale-source/update, preservation
  of outside bytes, and refusal for duplicate, nested, missing, or reordered blocks.
- Repository `config.json`, FOREMAN plan sentinel, and external fleet config
  sentinel are snapshotted before/after under the fixture parent; delta is 0.
  No real repository, FOREMAN, or fleet root is passed to the engine.
- D110 conformance builds only the sealed D104 hooks pair plus the exact whole-file MCP
  record below `TemporaryDirectory`. It verifies the ordered three-record lock, preserves the
  MCP bytes while retaining its recoverable backup, rejects every closed-admission mutation
  before the writer, and injects a failure at each transaction write boundary to prove exact
  rollback without a live-root path.

## Reproduction

```bash
PYTHONPATH=. python3 -m unittest discover -s core/tests -p 'test_provider_artifact_e2e.py'
PYTHONPATH=. python3 -m unittest discover -s core/tests
```
