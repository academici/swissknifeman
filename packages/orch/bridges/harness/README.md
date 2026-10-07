# Bridge orch ↔ Harness

The only place where orch knows Harness's agent-pack role catalog. The role manifests carry `agent_pack_roles`
as plain reference data; this bridge only checks that it matches the partner's `configs/common/agent-packs/roles.json`.

- No runtime verbs: `bridge.json` has no entrypoints; the orch core never reads the partner's file.
- Partner lookup: `SKM_HARNESS_ROOT`, then the monorepo sibling package. The test is skipped when the catalog is absent.
- Test: `tests/test_agent_pack_roles.py`, run by the package validate.
