# P4 command-parity conformance

**Producer:** P4.5 · **Contracts:** provider-command-routing, provider-capability,
provider-config, provider-artifact and provider-skill-publication v1.0.0 ·
**Evidence owner:** `packages/task/tests/test_provider_command_parity.py`

## Independent inventory and projections

The expected command set is read directly from the canonical
`packages/task/commands/*.md` filenames and the frozen command-inventory table. The
contract-authored `provider-command-parity.json` records the expected semantic metadata,
provider mappings, diagnostics and Next cases; neither provider renderer supplies expected
values or updates the fixture.

| Surface | Expected | Result |
|:--|--:|:--|
| Semantic commands | 11 | `missing=[]`, `extra=[]`, `duplicates=[]` |
| Claude Code artifacts | 12 | `missing=[]`, `extra=[]`, `duplicates=[]` |
| Codex artifacts | 24 | `missing=[]`, `extra=[]`, `duplicates=[]` |
| Semantic Next forms | 11 | every form has a positive carrier and invalid negative case |
| Stable diagnostics | 12 | every code has a clean baseline and fail-closed negative case |

For every command the deterministic report links semantic ID, independently hashed
canonical source, neutral route and capabilities to the Claude artifact/invocation and the
Codex wrapper/runtime artifacts/invocation. Each provider row records rendered hashes,
native selector/effort and diagnostics. The generated operator reference is rendered only
from this validated report.

## Failure and no-write matrix

| Condition | Required result |
|:--|:--|
| unknown/ambiguous command identity | `CMD_ID_UNKNOWN` / `CMD_ID_AMBIGUOUS`; no render/write |
| missing/extra/duplicate inventory | `CMD_CATALOG_MISMATCH`; no render/write |
| unknown contract version | `CMD_VERSION_UNSUPPORTED`; no fallback/write |
| wrong provider projection | `CMD_PROVIDER_DISABLED`; no artifacts |
| missing capability | `CMD_CAPABILITY_UNSUPPORTED`; no artifacts |
| missing/ambiguous selector | `CMD_MAPPING_MISSING` / `CMD_MAPPING_AMBIGUOUS`; no invocation/write |
| route undershoot | `CMD_ROUTE_UNDERSHOOT`; no invocation/write |
| legal route overshoot | `CMD_ROUTE_OVERSHOOT`; invocation retained |
| malformed invocation/Next | `CMD_INVOCATION_INVALID`; no invocation |
| source/plugin drift | `CMD_SOURCE_DRIFT`; no artifacts/write |

Tests use explicit inputs and temporary roots. The Claude canonical check is empty; the
Codex P2 lock classifier returns only `noop` on committed generated artifacts. Repeated
reports and generated reference bytes are identical.

## Consumer handoff

- P5 consumes stable command IDs, capability requirements, neutral class/effort minima and
  provider-qualified failure codes when it designs harness/security projections.
- P6 consumes semantic Next carriers and dual invocation rendering; deployment remains the
  owner of provider target selection and must not copy command bodies or infer permissions.
- P7 consumes the exact-set report, generated operator reference, Claude compatibility
  evidence and Codex provenance locks for self-host/release verification.
- A post-P7 reconcile may consume the frozen D84 contract plus this conformance artifact;
  it receives no authority here to edit or execute any external plan, fleet target or live
  provider configuration.

## Reproduction

```bash
PYTHONPATH=packages/task/lib:. python3 -m unittest \
  packages.task.tests.test_provider_command_parity \
  packages.task.tests.test_plan_command_routing \
  packages.task.tests.test_claude_command_adapter \
  packages.task.tests.test_codex_command_adapter
```

The focused suite passed twice with the same ordered test report. Full task/skiller
validation, docs/release assessment, phase close and independent audit remain the single
terminal P4 gate under D80/D82.
