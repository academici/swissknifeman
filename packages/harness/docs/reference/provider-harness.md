# Provider harness conformance

> Generated from the validated deterministic provider-audit report; do not maintain an inventory here.

`harness doctor --provider-audit [--json]` is read-only. `settings_audit.py` remains the named Claude Code checker behind `harness doctor --settings`; provider audit never universalizes Claude merge rules.

Validated catalog `sha256:b14bdcff863dd0738ecfc3ed08151c5cb611bdde1a6a13746e922aab1e0eb835`: 3 profiles, 23 semantic surfaces, 8 MCP descriptors and 44 agent roles.

Reports retain missing/extra and expected/actual duplicate identities. Full access is only explicit `self-host-apply` for a trusted repository; project, fleet-project and fleet-defaults selection are rejected. Secret references are value-free.

No live target write, activation, apply authority, MCP start, hook start or workflow start is granted. `settings_audit.py` remains Claude-specific.

## Source and render hashes

| Identity | SHA-256 |
|:--|:--|
| source:configs/claude-code/agent-packs/role-bindings.json | `sha256:d619828f8a5ea9a6e5fff0c7f6b87940e6aaaf40c92269e2bf955c85c403614b` |
| source:configs/claude-code/mcp/bindings.json | `sha256:dfe5e893b876f2450f9b0ce94274df61ff7ac6de928e0b9ccded48de7b8dcfd8` |
| source:configs/codex/config/profile-bindings.json | `sha256:9de3078c203f0cebd1a66e0f243efd96cb78a829341ed8f1faa6bc6ed0b1542e` |
| source:configs/codex/hooks/lifecycle-context-bindings.json | `sha256:0d8a6aa8d9c0fecb753c00c769fb498d7b9d2f378090ed45495d040066acb1ce` |
| source:configs/codex/mcp/bindings.json | `sha256:96edfa4686ff45bc8a886dd14418be1fde29dbee3098777574a21f1fc79e483a` |
| source:configs/common/agent-packs/roles.json | `sha256:9c5d803b2da977d2875cb8f71ba4505dad077321edcf138e0fd0998c9cd94e24` |
| source:configs/common/mcp/catalog.json | `sha256:26bddfc7f495650855ea183936aaf2d4c7ffa6e8cd91391e1a8fb25156a0842f` |
| source:configs/common/profile-catalog.json | `sha256:b14bdcff863dd0738ecfc3ed08151c5cb611bdde1a6a13746e922aab1e0eb835` |
| render-manifest:all-provider-qualified-outputs | `sha256:bdc4e200d23d8383195b4bf8e34745891c4ad604bc63f56c8082ae20c802ae73` |

The read-only JSON report retains every individual provider-qualified render hash; this manifest hash covers all of them deterministically.

## Exact provider-surface map

Every provider-qualified surface row is required: missing, extra or duplicate rows make the report RED.

| Provider | Surface ID | Semantic SHA-256 | Required capabilities | Security intent or ownership | Artifact / target scope / state | Activation | Diagnostic |
|:--|:--|:--|:--|:--|:--|:--|:--|
| claude-code | agent-packs.lifecycle | `sha256:6b1474a5f1639a652540c5db8fd351ca5aed822ca2c20f48ba7cde99a3750d76` | — | harness.agent-packs.lifecycle | non-artifact:named-agent-pack-engine | supported | `HARNESS_AGENTPACK_LIFECYCLE_NAMED` |
| claude-code | agents.catalog | `sha256:31178a06201f890a47e2398758a442712966070d36f336b5ac0eafa542921a36` | — | harness.agents.catalog | artifact:project:44-named-agent-targets | supported | `HARNESS_AGENT_ACTIVATION_NATIVE` |
| claude-code | context.observer | `sha256:98df3b65365820591b7a28539560e3180527b9337c8faf018afd25adf9e376ce` | — | harness.context.observer | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| claude-code | context.output-style | `sha256:bdb667e3bbd31f2fb10de42a11d8f8f07d0a0e8536c28d9961e8ae1149fd27b0` | — | harness.context.output-style | native-binding:new-session | supported | `HARNESS_ACTIVATION_NATIVE` |
| claude-code | context.plans-directory | `sha256:55d7f15dcab4a4c1a5c657fddb5b305450afc5e5a2db40bf8e451d39b63638ce` | — | harness.context.plans-directory | native-binding:project-settings | supported | `HARNESS_ACTIVATION_NATIVE` |
| claude-code | doctor.environment | `sha256:a559d78d9d698deeebe696353405507b85f3eaefe96a7f0a621d3be04033c5ec` | — | harness.doctor.environment | non-artifact:named-harness-doctor | supported | `HARNESS_DOCTOR_ENVIRONMENT_NAMED` |
| claude-code | doctor.provider | `sha256:b697fe554c9c0d0271f950bd875c6a81373c03bf97aaf4e6ba11352ca184273a` | — | harness.doctor.provider | non-artifact:provider-audit | supported | `HARNESS_PROVIDER_AUDIT_NAMED` |
| claude-code | lifecycle.auto-approval | `sha256:8681c3e09d1ef2a59015ccda5efebf4c4d2417b73f6b47c45bdda4d5bff7e6d9` | — | harness.lifecycle.auto-approval | native-binding:project-settings | supported | `HARNESS_ACTIVATION_NATIVE` |
| claude-code | lifecycle.changelog-gate | `sha256:6a1579586594df0a691221c4aca2efe7d7f4835be82c0f807d3ba785b2ea8a9d` | — | harness.lifecycle.changelog-gate | native-binding:project-settings | supported | `HARNESS_ACTIVATION_NATIVE` |
| claude-code | lifecycle.command-log | `sha256:6c2900af6956f64747429488e3177132cbed547a935cf98bda46a26fe57fe8ad` | — | harness.lifecycle.command-log | native-binding:global-hook | supported | `HARNESS_ACTIVATION_NATIVE` |
| claude-code | lifecycle.daemon-safety | `sha256:d7eefb087ebafb37c2dfd19240e1611c6150925d12977d337c78a6e126ebbf2b` | — | harness.lifecycle.daemon-safety | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| claude-code | lifecycle.git-guardrails | `sha256:4d5c38147dc736cb1d6b93c38e04d98324f48c057cc9ebb4ab294c4181559610` | — | harness.lifecycle.git-guardrails | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| claude-code | lifecycle.memory | `sha256:1c68623b21d4eafa0887b798cedea70ec3cf7d0674d35320f61328686e02e3fb` | — | harness.lifecycle.memory | native-binding:global-hook-plus-project-config | supported | `HARNESS_ACTIVATION_NATIVE` |
| claude-code | lifecycle.notification | `sha256:c9e55167aaf018fdc0109cea4553c2c2911d53f709e49d400ed367a8b0683a00` | — | harness.lifecycle.notification | native-binding:global-hook | supported | `HARNESS_ACTIVATION_NATIVE` |
| claude-code | lifecycle.pack-guard | `sha256:05b5c33e3cb01e7ce424631d35b8485adcf77ba6b66a78bd8bf73dfbaa6b9c8e` | — | harness.lifecycle.pack-guard | native-binding:project-settings | supported | `HARNESS_ACTIVATION_NATIVE` |
| claude-code | lifecycle.review-gate | `sha256:a8bdf4c8d37277ab0a8976ee7cfcf215f5ee8e63f4bb69163dca1796ebe44368` | — | harness.lifecycle.review-gate | native-binding:global-hook | supported | `HARNESS_ACTIVATION_NATIVE` |
| claude-code | lifecycle.router | `sha256:3579aac732a227a565edc6175dbfa4ddc27767a10af3aa7fb70091ca4915f283` | — | harness.lifecycle.router | native-binding:project-settings | supported | `HARNESS_ACTIVATION_NATIVE` |
| claude-code | lifecycle.run-report | `sha256:9b92c0ff639e64772a2961e198f3f9d7b93bf120a6aed8e1350a5f0fa6bea13b` | — | harness.lifecycle.run-report | native-binding:project-settings | supported | `HARNESS_ACTIVATION_NATIVE` |
| claude-code | mcp.catalog | `sha256:54dd40ebbd21f976206d42e35be4f3c92f57b4679ff97a013edb3a406c190394` | — | harness.mcp.catalog | artifact:project:.mcp.json | supported | `HARNESS_MCP_PROJECTION_RENDERED` |
| claude-code | security.safe-dirs | `sha256:8ce38a9571be6fd4220f256972925f3f84dd844c144ac1d479a5d561b435f312` | — | harness.security.safe-dirs | non-artifact:machine-owned-safe-dirs | supported | `HARNESS_SAFE_DIRS_NAMED` |
| claude-code | settings.audit | `sha256:da70a0c0e55d4324a8704a211532d8398083192570b00a7f1d4f94ab4d9daba7` | — | harness.settings.audit | non-artifact:named-settings-audit | supported | `HARNESS_SETTINGS_AUDIT_NAMED` |
| claude-code | settings.permissions | `sha256:9049fe9aad45b74bce05c1f7d565cd7f76816605eb3ffd7ffed6b3df6820a745` | — | harness.settings.permissions | artifact:project:.claude/settings.local.json | supported | `HARNESS_PROFILE_RENDERED` |
| claude-code | workflows.status | `sha256:a535a27aec70899044ca8ca0995cc7bd93e1b1783ae577eb5445b50104db3d27` | — | harness.workflows.status | non-artifact:named-workflow-status | supported | `HARNESS_WORKFLOW_STATUS_NAMED` |
| codex | agent-packs.lifecycle | `sha256:6b1474a5f1639a652540c5db8fd351ca5aed822ca2c20f48ba7cde99a3750d76` | — | harness.agent-packs.lifecycle | non-artifact:named-agent-pack-engine | supported | `HARNESS_AGENTPACK_LIFECYCLE_NAMED` |
| codex | agents.catalog | `sha256:31178a06201f890a47e2398758a442712966070d36f336b5ac0eafa542921a36` | — | harness.agents.catalog | artifact:project:43-named-agent-targets | supported | `HARNESS_AGENT_ACTIVATION_NATIVE` |
| codex | context.observer | `sha256:98df3b65365820591b7a28539560e3180527b9337c8faf018afd25adf9e376ce` | — | harness.context.observer | artifact:project:.codex/hooks.json+.codex/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| codex | context.output-style | `sha256:bdb667e3bbd31f2fb10de42a11d8f8f07d0a0e8536c28d9961e8ae1149fd27b0` | — | harness.context.output-style | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| codex | context.plans-directory | `sha256:55d7f15dcab4a4c1a5c657fddb5b305450afc5e5a2db40bf8e451d39b63638ce` | — | harness.context.plans-directory | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| codex | doctor.environment | `sha256:a559d78d9d698deeebe696353405507b85f3eaefe96a7f0a621d3be04033c5ec` | — | harness.doctor.environment | non-artifact:named-harness-doctor | supported | `HARNESS_DOCTOR_ENVIRONMENT_NAMED` |
| codex | doctor.provider | `sha256:b697fe554c9c0d0271f950bd875c6a81373c03bf97aaf4e6ba11352ca184273a` | — | harness.doctor.provider | non-artifact:provider-audit | supported | `HARNESS_PROVIDER_AUDIT_NAMED` |
| codex | lifecycle.auto-approval | `sha256:8681c3e09d1ef2a59015ccda5efebf4c4d2417b73f6b47c45bdda4d5bff7e6d9` | — | harness.lifecycle.auto-approval | native-binding:P5.2-config-security-projection | supported | `HARNESS_ACTIVATION_NATIVE` |
| codex | lifecycle.changelog-gate | `sha256:6a1579586594df0a691221c4aca2efe7d7f4835be82c0f807d3ba785b2ea8a9d` | — | harness.lifecycle.changelog-gate | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| codex | lifecycle.command-log | `sha256:6c2900af6956f64747429488e3177132cbed547a935cf98bda46a26fe57fe8ad` | — | harness.lifecycle.command-log | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| codex | lifecycle.daemon-safety | `sha256:d7eefb087ebafb37c2dfd19240e1611c6150925d12977d337c78a6e126ebbf2b` | — | harness.lifecycle.daemon-safety | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| codex | lifecycle.git-guardrails | `sha256:4d5c38147dc736cb1d6b93c38e04d98324f48c057cc9ebb4ab294c4181559610` | — | harness.lifecycle.git-guardrails | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| codex | lifecycle.memory | `sha256:1c68623b21d4eafa0887b798cedea70ec3cf7d0674d35320f61328686e02e3fb` | — | harness.lifecycle.memory | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| codex | lifecycle.notification | `sha256:c9e55167aaf018fdc0109cea4553c2c2911d53f709e49d400ed367a8b0683a00` | — | harness.lifecycle.notification | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| codex | lifecycle.pack-guard | `sha256:05b5c33e3cb01e7ce424631d35b8485adcf77ba6b66a78bd8bf73dfbaa6b9c8e` | — | harness.lifecycle.pack-guard | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| codex | lifecycle.review-gate | `sha256:a8bdf4c8d37277ab0a8976ee7cfcf215f5ee8e63f4bb69163dca1796ebe44368` | — | harness.lifecycle.review-gate | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| codex | lifecycle.router | `sha256:3579aac732a227a565edc6175dbfa4ddc27767a10af3aa7fb70091ca4915f283` | — | harness.lifecycle.router | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| codex | lifecycle.run-report | `sha256:9b92c0ff639e64772a2961e198f3f9d7b93bf120a6aed8e1350a5f0fa6bea13b` | — | harness.lifecycle.run-report | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| codex | mcp.catalog | `sha256:54dd40ebbd21f976206d42e35be4f3c92f57b4679ff97a013edb3a406c190394` | — | harness.mcp.catalog | artifact:project:.codex/config.toml | supported | `HARNESS_MCP_PROJECTION_RENDERED` |
| codex | security.safe-dirs | `sha256:8ce38a9571be6fd4220f256972925f3f84dd844c144ac1d479a5d561b435f312` | — | harness.security.safe-dirs | non-artifact:no-codex-safe-dirs-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| codex | settings.audit | `sha256:da70a0c0e55d4324a8704a211532d8398083192570b00a7f1d4f94ab4d9daba7` | — | harness.settings.audit | non-artifact:claude-only-settings-audit | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| codex | settings.permissions | `sha256:9049fe9aad45b74bce05c1f7d565cd7f76816605eb3ffd7ffed6b3df6820a745` | — | harness.settings.permissions | artifact:project:.codex/config.toml | supported | `HARNESS_PROFILE_RENDERED` |
| codex | workflows.status | `sha256:a535a27aec70899044ca8ca0995cc7bd93e1b1783ae577eb5445b50104db3d27` | — | harness.workflows.status | non-artifact:named-workflow-status | supported | `HARNESS_WORKFLOW_STATUS_NAMED` |

## Temp-contained managed lifecycle evidence

The named representative P2 artifacts are rendered only in temporary roots. `create`, second `check`, induced managed drift and explicit `repair` are independently recorded; bytes outside managed targets remain untouched.

| Representative artifact | Create | Second check | Managed drift | Explicit repair | Outside-managed bytes preserved |
|:--|:--|:--|:--|:--|:--|
| profile:codex:trusted-full-access | create | noop | refuse | repair | True |
| mcp:codex:catalog | create | noop | refuse | repair | True |
| agent:codex:backend-laravel.blade-review | create | noop | refuse | repair | True |
| lifecycle:codex:context.observer | create+create | noop+noop | refuse+noop | repair+noop | True |
