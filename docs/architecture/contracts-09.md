# Shared integration projections

These files preserve the existing target renderer contracts; they add no ports or registrations.

| File | Contract | Owner |
|---|---|---|
| `src/skm/adapters/integrations/_mcp.py` | `build_server_entry`: common MCP fields and opaque SecretRef validation | P10.02–P10.04.b |
| `tests/unit/adapters/integrations/test_mcp_entries.py` | Four-target entry parity, validation errors and target-specific name rules | Integration projection regression tests |
