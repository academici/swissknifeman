# Bridge orch ↔ Harness (`orch-harness`)

The only place where orch knows Harness's agent-pack role catalog. The role manifests carry `agent_pack_roles`
as plain reference data; this bridge only checks that it matches the partner's `configs/common/agent-packs/roles.json`.

- No runtime verbs: the bridge has no entrypoints; the orch core never reads the partner's file.
- Partner lookup: `SKM_HARNESS_ROOT` (a root holding the catalog) and `SKM_ORCH_ROOT` (or an `orch` command on
  `PATH`). There is no search by neighbouring folders; the test is skipped when either is absent.
- Test: `tests/test_agent_pack_roles.py`, run by `bash scripts/test.sh` or the hub runner `bash scripts/test-bridges.sh`.
