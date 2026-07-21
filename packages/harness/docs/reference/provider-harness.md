# Provider harness conformance

> Generated from the validated deterministic provider-audit report; do not maintain an inventory here.

`harness doctor --provider-audit [--json]` is read-only. `settings_audit.py` remains the named Claude Code checker behind `harness doctor --settings`; provider audit never universalizes Claude merge rules.

Validated catalog `sha256:b14bdcff863dd0738ecfc3ed08151c5cb611bdde1a6a13746e922aab1e0eb835`: 3 profiles, 23 semantic surfaces, 8 MCP descriptors and 44 agent roles.

Reports retain missing/extra and expected/actual duplicate identities. Full access is only explicit `self-host-apply` for a trusted repository; default, project and fleet selection are rejected. Secret references are value-free.

## Deterministic evidence matrix

| Category | Provider | Surface or role | Case | State | Diagnostic |
|:--|:--|:--|:--|:--|:--|
| activation | claude-code | role:_common.orchestrator | positive | supported | `HARNESS_AGENT_ACTIVATION_NATIVE` |
| activation | claude-code | surface:context.observer | negative | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| activation | claude-code | surface:lifecycle.daemon-safety | negative | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| activation | claude-code | surface:lifecycle.git-guardrails | negative | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| activation | codex | role:_common.orchestrator | negative | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED:codex:command.workflow-carrier:P4` |
| activation | codex | role:backend-laravel.blade-review | positive | supported | `HARNESS_AGENT_ACTIVATION_NATIVE` |
| activation | codex | surface:context.output-style | negative | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| activation | codex | surface:context.plans-directory | negative | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| activation | codex | surface:lifecycle.changelog-gate | negative | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| activation | codex | surface:lifecycle.command-log | negative | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| activation | codex | surface:lifecycle.daemon-safety | negative | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| activation | codex | surface:lifecycle.git-guardrails | negative | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| activation | codex | surface:lifecycle.memory | negative | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| activation | codex | surface:lifecycle.notification | negative | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| activation | codex | surface:lifecycle.pack-guard | negative | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| activation | codex | surface:lifecycle.review-gate | negative | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| activation | codex | surface:lifecycle.router | negative | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| activation | codex | surface:lifecycle.run-report | negative | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| capability | claude-code | mcp:catalog | positive | supported | `HARNESS_MCP_PROJECTION_RENDERED` |
| capability | claude-code | mcp:missing-capability | negative | refused | `HARNESS_CATALOG_MISMATCH` |
| capability | codex | mcp:catalog | positive | supported | `HARNESS_MCP_PROJECTION_RENDERED` |
| capability | codex | mcp:missing-capability | negative | refused | `HARNESS_CATALOG_MISMATCH` |
| secret | claude-code | mcp:catalog | negative | refused | `HARNESS_SECRET_VALUE_EXPOSED` |
| secret | claude-code | mcp:catalog | positive | value-free | `HARNESS_SECRET_REFERENCES_ONLY` |
| secret | codex | mcp:catalog | negative | refused | `HARNESS_SECRET_VALUE_EXPOSED` |
| secret | codex | mcp:catalog | positive | value-free | `HARNESS_SECRET_REFERENCES_ONLY` |
| security | claude-code | origin:fleet-defaults | negative | refused | `HARNESS_FULL_ACCESS_INHERITANCE_FORBIDDEN` |
| security | claude-code | profile:observe | positive | supported | `HARNESS_PROFILE_RESOLVED` |
| security | claude-code | profile:trusted-full-access | negative | refused | `HARNESS_FULL_ACCESS_EXPLICIT_REQUIRED` |
| security | claude-code | profile:trusted-full-access | positive | supported | `HARNESS_FULL_ACCESS_EXPLICIT` |
| security | claude-code | profile:workspace-contained | positive | supported | `HARNESS_PROFILE_RESOLVED` |
| security | codex | origin:fleet-defaults | negative | refused | `HARNESS_FULL_ACCESS_INHERITANCE_FORBIDDEN` |
| security | codex | profile:observe | positive | supported | `HARNESS_PROFILE_RESOLVED` |
| security | codex | profile:trusted-full-access | negative | refused | `HARNESS_FULL_ACCESS_EXPLICIT_REQUIRED` |
| security | codex | profile:trusted-full-access | positive | supported | `HARNESS_FULL_ACCESS_EXPLICIT` |
| security | codex | profile:workspace-contained | positive | supported | `HARNESS_PROFILE_RESOLVED` |
| trust | claude-code | mcp:catalog | negative | refused | `HARNESS_TRUST_REQUIRED` |
| trust | claude-code | profile:workspace-contained | positive | supported | `HARNESS_TRUST_SATISFIED` |
| trust | codex | mcp:catalog | negative | refused | `HARNESS_TRUST_REQUIRED` |
| trust | codex | profile:workspace-contained | positive | supported | `HARNESS_TRUST_SATISFIED` |
