# P5 harness conformance — P6/P7 inputs

P5.5 provides a deterministic, read-only input through
`harness doctor --provider-audit --json`. The report derives expected identities from
`tests/fixtures_data/provider-harness-cases.json`, authored from frozen contract/current
declared sources before projection output is evaluated. It verifies 3 profiles, 23 surfaces,
8 MCP records, and 44 agent roles for independent Claude Code and Codex projections.

## P6 deployment inputs

- Run provider audit twice; require byte-identical ordered JSON and `green=true`.
- Require every row to have `missing=[]`, `extra=[]`, `duplicates=[]`; retain qualified
  `HARNESS_ACTIVATION_UNSUPPORTED` entries as visible support state, never as silent parity.
- Record the source SHA-256 map from the report before planning a deployment.
- Use P2 artifact plans only: check/dry-run is no-write; repair is explicit and managed-only.

## P7 self-host acceptance inputs

- Re-run the same report in the target checkout before and after self-host planning; no
  current user/global/project provider target is written by P5.5.
- Verify default/project/fleet examples never select full access; only the exact trusted
  `self-host-apply` operation may use it.
- Require value-free secret diagnostics, explicit trust/capability/activation outcomes, and
  existing named Claude settings-doctor compatibility checks.
- Apply/release, hooks, MCP servers, workflows and agents remain P7 authority.
