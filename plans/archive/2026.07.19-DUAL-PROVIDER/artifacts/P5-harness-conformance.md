# P5 harness conformance — P6/P7 inputs

> Generated from the validated deterministic provider-audit report; no second inventory is maintained.

Catalog `sha256:3417643f87ca3b22c519e360201020bc50b6a81c774bd2dd938c612fdbefb66a` is the P5.5 preflight input. Run `harness doctor --provider-audit --json` twice and require byte-identical green output with empty missing/extra/duplicates.

The audit and named Claude settings doctor are separate consumers. It writes no audited package source or target.

## Exact P6 deployment inputs

- Use this report's catalog/source hashes and complete evidence matrix as the preflight input.
- Check and repair are managed-only; repair may change matching managed fixture paths only.
- No live target write, activation, apply authority, MCP start, hook start or workflow start is granted.

## Exact P7 self-host acceptance inputs

- Re-run the byte-identical read-only report twice; retain supported and provider-qualified unsupported rows.
- Accept full access only for exact `self-host-apply` plus trusted `repo:` target; reject project, fleet-project and fleet-defaults inheritance.
- Keep secret evidence value-free and preserve named Claude settings audit as a separate consumer.

## Source and render hashes

| Identity | SHA-256 |
|:--|:--|
| source:configs/claude-code/agent-packs/role-bindings.json | `sha256:d619828f8a5ea9a6e5fff0c7f6b87940e6aaaf40c92269e2bf955c85c403614b` |
| source:configs/claude-code/mcp/bindings.json | `sha256:669011d1fa6042f7abdb143a3761e9d84673795426cdbd3b934f54b802c8ce26` |
| source:configs/codex/config/profile-bindings.json | `sha256:9de3078c203f0cebd1a66e0f243efd96cb78a829341ed8f1faa6bc6ed0b1542e` |
| source:configs/codex/hooks/lifecycle-context-bindings.json | `sha256:2a9dc6cf0a2b029ab9cbbc8bd1893ab6704ea9c31eb5e539c3e772aafc74adf7` |
| source:configs/codex/mcp/bindings.json | `sha256:bd876ab14dcb1d253bb2d0b5771dc335bebc03ea1abcc8fb84718b44541aa087` |
| source:configs/common/agent-packs/roles.json | `sha256:2ba25a3a8f4ef52655403b0d0655f10b1cae3a850594b16c443dc6053462ee75` |
| source:configs/common/mcp/catalog.json | `sha256:26bddfc7f495650855ea183936aaf2d4c7ffa6e8cd91391e1a8fb25156a0842f` |
| source:configs/common/profile-catalog.json | `sha256:3417643f87ca3b22c519e360201020bc50b6a81c774bd2dd938c612fdbefb66a` |
| source:configs/cursor/agent-packs/consumer-mapping.json | `sha256:314f0935b254c8a7e814cfa1ae476b99e373d0fffeb4de91fabf8c756708d67e` |
| source:configs/cursor/config/profile-bindings.json | `sha256:8772a33bbdf9d5082bc12457d135e2a29c3faf945a5f8f3c11a9954695bf1594` |
| source:configs/cursor/hooks/lifecycle-context-bindings.json | `sha256:5695df4d4ab603781ab8f254c52a7c0579b478609ed9ea65a63303c7864016b2` |
| source:configs/cursor/mcp/bindings.json | `sha256:70f8e83eaa179e26308cfbe4848429c824864e4c0e0016c520e59914aeb4b44f` |
| render-manifest:all-provider-qualified-outputs | `sha256:aac43ad899c27533ed24538879452b150feff99cbf66dcebb704d7c45d15b3b8` |

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
| claude-code | lifecycle.daemon-safety | `sha256:d7eefb087ebafb37c2dfd19240e1611c6150925d12977d337c78a6e126ebbf2b` | — | harness.lifecycle.daemon-safety | native-binding:global-hook | supported | `HARNESS_ACTIVATION_NATIVE` |
| claude-code | lifecycle.git-guardrails | `sha256:4d5c38147dc736cb1d6b93c38e04d98324f48c057cc9ebb4ab294c4181559610` | — | harness.lifecycle.git-guardrails | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| claude-code | lifecycle.memory | `sha256:1c68623b21d4eafa0887b798cedea70ec3cf7d0674d35320f61328686e02e3fb` | — | harness.lifecycle.memory | native-binding:global-hook-plus-project-config | supported | `HARNESS_ACTIVATION_NATIVE` |
| claude-code | lifecycle.notification | `sha256:c9e55167aaf018fdc0109cea4553c2c2911d53f709e49d400ed367a8b0683a00` | — | harness.lifecycle.notification | native-binding:global-hook | supported | `HARNESS_ACTIVATION_NATIVE` |
| claude-code | lifecycle.pack-guard | `sha256:05b5c33e3cb01e7ce424631d35b8485adcf77ba6b66a78bd8bf73dfbaa6b9c8e` | — | harness.lifecycle.pack-guard | native-binding:project-settings | supported | `HARNESS_ACTIVATION_NATIVE` |
| claude-code | lifecycle.review-gate | `sha256:a8bdf4c8d37277ab0a8976ee7cfcf215f5ee8e63f4bb69163dca1796ebe44368` | — | harness.lifecycle.review-gate | native-binding:global-hook | supported | `HARNESS_ACTIVATION_NATIVE` |
| claude-code | lifecycle.router | `sha256:3579aac732a227a565edc6175dbfa4ddc27767a10af3aa7fb70091ca4915f283` | — | harness.lifecycle.router | native-binding:project-settings | supported | `HARNESS_ACTIVATION_NATIVE` |
| claude-code | lifecycle.run-report | `sha256:9b92c0ff639e64772a2961e198f3f9d7b93bf120a6aed8e1350a5f0fa6bea13b` | — | harness.lifecycle.run-report | native-binding:project-settings | supported | `HARNESS_ACTIVATION_NATIVE` |
| claude-code | lifecycle.terminal-admission | `sha256:b952c2d83aeee61113c4a474d673dbf7d98334a8d85f6d3ab352a5cad689568f` | — | harness.lifecycle.terminal-admission | native-binding:trusted-project-stop | supported | `HARNESS_ACTIVATION_NATIVE` |
| claude-code | mcp.catalog | `sha256:54dd40ebbd21f976206d42e35be4f3c92f57b4679ff97a013edb3a406c190394` | — | harness.mcp.catalog | artifact:project:.mcp.json | supported | `HARNESS_MCP_PROJECTION_RENDERED` |
| claude-code | security.safe-dirs | `sha256:8ce38a9571be6fd4220f256972925f3f84dd844c144ac1d479a5d561b435f312` | — | harness.security.safe-dirs | native-binding:embedded-in-auto-approval | supported | `HARNESS_ACTIVATION_NATIVE` |
| claude-code | settings.audit | `sha256:da70a0c0e55d4324a8704a211532d8398083192570b00a7f1d4f94ab4d9daba7` | — | harness.settings.audit | non-artifact:named-settings-audit | supported | `HARNESS_SETTINGS_AUDIT_NAMED` |
| claude-code | settings.permissions | `sha256:9049fe9aad45b74bce05c1f7d565cd7f76816605eb3ffd7ffed6b3df6820a745` | — | harness.settings.permissions | artifact:project:.claude/settings.local.json | supported | `HARNESS_PROFILE_RENDERED` |
| claude-code | workflows.status | `sha256:a535a27aec70899044ca8ca0995cc7bd93e1b1783ae577eb5445b50104db3d27` | — | harness.workflows.status | non-artifact:named-workflow-status | supported | `HARNESS_WORKFLOW_STATUS_NAMED` |
| codex | agent-packs.lifecycle | `sha256:6b1474a5f1639a652540c5db8fd351ca5aed822ca2c20f48ba7cde99a3750d76` | — | harness.agent-packs.lifecycle | non-artifact:named-codex-agent-role-lifecycle | supported | `HARNESS_AGENTPACK_LIFECYCLE_NAMED` |
| codex | agents.catalog | `sha256:31178a06201f890a47e2398758a442712966070d36f336b5ac0eafa542921a36` | — | harness.agents.catalog | artifact:project:43-named-agent-targets | supported | `HARNESS_AGENT_ACTIVATION_NATIVE` |
| codex | context.observer | `sha256:98df3b65365820591b7a28539560e3180527b9337c8faf018afd25adf9e376ce` | — | harness.context.observer | artifact:project:.codex/hooks.json+.codex/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| codex | context.output-style | `sha256:bdb667e3bbd31f2fb10de42a11d8f8f07d0a0e8536c28d9961e8ae1149fd27b0` | — | harness.context.output-style | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| codex | context.plans-directory | `sha256:55d7f15dcab4a4c1a5c657fddb5b305450afc5e5a2db40bf8e451d39b63638ce` | — | harness.context.plans-directory | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| codex | doctor.environment | `sha256:a559d78d9d698deeebe696353405507b85f3eaefe96a7f0a621d3be04033c5ec` | — | harness.doctor.environment | non-artifact:named-harness-doctor | supported | `HARNESS_DOCTOR_ENVIRONMENT_NAMED` |
| codex | doctor.provider | `sha256:b697fe554c9c0d0271f950bd875c6a81373c03bf97aaf4e6ba11352ca184273a` | — | harness.doctor.provider | non-artifact:provider-audit | supported | `HARNESS_PROVIDER_AUDIT_NAMED` |
| codex | lifecycle.auto-approval | `sha256:8681c3e09d1ef2a59015ccda5efebf4c4d2417b73f6b47c45bdda4d5bff7e6d9` | — | harness.lifecycle.auto-approval | native-binding:P5.2-config-security-projection | supported | `HARNESS_ACTIVATION_NATIVE` |
| codex | lifecycle.changelog-gate | `sha256:6a1579586594df0a691221c4aca2efe7d7f4835be82c0f807d3ba785b2ea8a9d` | — | harness.lifecycle.changelog-gate | artifact:project:.codex/hooks.json+.codex/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| codex | lifecycle.command-log | `sha256:6c2900af6956f64747429488e3177132cbed547a935cf98bda46a26fe57fe8ad` | — | harness.lifecycle.command-log | artifact:project:.codex/hooks.json+.codex/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| codex | lifecycle.daemon-safety | `sha256:d7eefb087ebafb37c2dfd19240e1611c6150925d12977d337c78a6e126ebbf2b` | — | harness.lifecycle.daemon-safety | artifact:project:.codex/hooks.json+.codex/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| codex | lifecycle.git-guardrails | `sha256:4d5c38147dc736cb1d6b93c38e04d98324f48c057cc9ebb4ab294c4181559610` | — | harness.lifecycle.git-guardrails | artifact:project:.codex/hooks.json+.codex/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| codex | lifecycle.memory | `sha256:1c68623b21d4eafa0887b798cedea70ec3cf7d0674d35320f61328686e02e3fb` | — | harness.lifecycle.memory | artifact:project:.codex/hooks.json+.codex/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| codex | lifecycle.notification | `sha256:c9e55167aaf018fdc0109cea4553c2c2911d53f709e49d400ed367a8b0683a00` | — | harness.lifecycle.notification | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| codex | lifecycle.pack-guard | `sha256:05b5c33e3cb01e7ce424631d35b8485adcf77ba6b66a78bd8bf73dfbaa6b9c8e` | — | harness.lifecycle.pack-guard | artifact:project:.codex/hooks.json+.codex/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| codex | lifecycle.review-gate | `sha256:a8bdf4c8d37277ab0a8976ee7cfcf215f5ee8e63f4bb69163dca1796ebe44368` | — | harness.lifecycle.review-gate | artifact:project:.codex/hooks.json+.codex/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| codex | lifecycle.router | `sha256:3579aac732a227a565edc6175dbfa4ddc27767a10af3aa7fb70091ca4915f283` | — | harness.lifecycle.router | artifact:project:.codex/hooks.json+.codex/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| codex | lifecycle.run-report | `sha256:9b92c0ff639e64772a2961e198f3f9d7b93bf120a6aed8e1350a5f0fa6bea13b` | — | harness.lifecycle.run-report | artifact:project:.codex/hooks.json+.codex/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| codex | lifecycle.terminal-admission | `sha256:b952c2d83aeee61113c4a474d673dbf7d98334a8d85f6d3ab352a5cad689568f` | — | harness.lifecycle.terminal-admission | artifact:project:.codex/hooks.json+.codex/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| codex | mcp.catalog | `sha256:54dd40ebbd21f976206d42e35be4f3c92f57b4679ff97a013edb3a406c190394` | — | harness.mcp.catalog | artifact:project:.codex/config.toml | supported | `HARNESS_MCP_PROJECTION_RENDERED` |
| codex | security.safe-dirs | `sha256:8ce38a9571be6fd4220f256972925f3f84dd844c144ac1d479a5d561b435f312` | — | harness.security.safe-dirs | artifact:project:.codex/hooks.json+.codex/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| codex | settings.audit | `sha256:da70a0c0e55d4324a8704a211532d8398083192570b00a7f1d4f94ab4d9daba7` | — | harness.settings.audit | non-artifact:named-codex-settings-audit | supported | `HARNESS_SETTINGS_AUDIT_NAMED` |
| codex | settings.permissions | `sha256:9049fe9aad45b74bce05c1f7d565cd7f76816605eb3ffd7ffed6b3df6820a745` | — | harness.settings.permissions | artifact:project:.codex/config.toml | supported | `HARNESS_PROFILE_RENDERED` |
| codex | workflows.status | `sha256:a535a27aec70899044ca8ca0995cc7bd93e1b1783ae577eb5445b50104db3d27` | — | harness.workflows.status | non-artifact:missing-native-codex-workflow-status-consumer | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED:codex:workflows.status:missing-native-codex-workflow-status-consumer` |
| cursor | agent-packs.lifecycle | `sha256:6b1474a5f1639a652540c5db8fd351ca5aed822ca2c20f48ba7cde99a3750d76` | — | harness.agent-packs.lifecycle | non-artifact:cursor-consumer-lifecycle-shared-projection | supported | `HARNESS_CURSOR_AGENTPACK_CONSUMER_LIFECYCLE` |
| cursor | agents.catalog | `sha256:31178a06201f890a47e2398758a442712966070d36f336b5ac0eafa542921a36` | — | harness.agents.catalog | non-artifact:cursor-consumer-mapping:44-targets:.claude/agents/*.md | supported | `HARNESS_CURSOR_AGENT_CONSUMER_MAPPING` |
| cursor | context.observer | `sha256:98df3b65365820591b7a28539560e3180527b9337c8faf018afd25adf9e376ce` | — | harness.context.observer | artifact:project:.cursor/rules/swissknifeman-observer.mdc | supported | `HARNESS_CURSOR_STATIC_RULE` |
| cursor | context.output-style | `sha256:bdb667e3bbd31f2fb10de42a11d8f8f07d0a0e8536c28d9961e8ae1149fd27b0` | — | harness.context.output-style | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| cursor | context.plans-directory | `sha256:55d7f15dcab4a4c1a5c657fddb5b305450afc5e5a2db40bf8e451d39b63638ce` | — | harness.context.plans-directory | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| cursor | doctor.environment | `sha256:a559d78d9d698deeebe696353405507b85f3eaefe96a7f0a621d3be04033c5ec` | — | harness.doctor.environment | non-artifact:named-harness-doctor | supported | `HARNESS_DOCTOR_ENVIRONMENT_NAMED` |
| cursor | doctor.provider | `sha256:b697fe554c9c0d0271f950bd875c6a81373c03bf97aaf4e6ba11352ca184273a` | — | harness.doctor.provider | non-artifact:provider-audit | supported | `HARNESS_PROVIDER_AUDIT_NAMED` |
| cursor | lifecycle.auto-approval | `sha256:8681c3e09d1ef2a59015ccda5efebf4c4d2417b73f6b47c45bdda4d5bff7e6d9` | — | harness.lifecycle.auto-approval | native-binding:P5.2-config-security-projection | supported | `HARNESS_ACTIVATION_NATIVE` |
| cursor | lifecycle.changelog-gate | `sha256:6a1579586594df0a691221c4aca2efe7d7f4835be82c0f807d3ba785b2ea8a9d` | — | harness.lifecycle.changelog-gate | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| cursor | lifecycle.command-log | `sha256:6c2900af6956f64747429488e3177132cbed547a935cf98bda46a26fe57fe8ad` | — | harness.lifecycle.command-log | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| cursor | lifecycle.daemon-safety | `sha256:d7eefb087ebafb37c2dfd19240e1611c6150925d12977d337c78a6e126ebbf2b` | — | harness.lifecycle.daemon-safety | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| cursor | lifecycle.git-guardrails | `sha256:4d5c38147dc736cb1d6b93c38e04d98324f48c057cc9ebb4ab294c4181559610` | — | harness.lifecycle.git-guardrails | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| cursor | lifecycle.memory | `sha256:1c68623b21d4eafa0887b798cedea70ec3cf7d0674d35320f61328686e02e3fb` | — | harness.lifecycle.memory | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| cursor | lifecycle.notification | `sha256:c9e55167aaf018fdc0109cea4553c2c2911d53f709e49d400ed367a8b0683a00` | — | harness.lifecycle.notification | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| cursor | lifecycle.pack-guard | `sha256:05b5c33e3cb01e7ce424631d35b8485adcf77ba6b66a78bd8bf73dfbaa6b9c8e` | — | harness.lifecycle.pack-guard | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| cursor | lifecycle.review-gate | `sha256:a8bdf4c8d37277ab0a8976ee7cfcf215f5ee8e63f4bb69163dca1796ebe44368` | — | harness.lifecycle.review-gate | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| cursor | lifecycle.router | `sha256:3579aac732a227a565edc6175dbfa4ddc27767a10af3aa7fb70091ca4915f283` | — | harness.lifecycle.router | artifact:project:.cursor/rules/swissknifeman-router.mdc | supported | `HARNESS_CURSOR_STATIC_RULE` |
| cursor | lifecycle.run-report | `sha256:9b92c0ff639e64772a2961e198f3f9d7b93bf120a6aed8e1350a5f0fa6bea13b` | — | harness.lifecycle.run-report | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| cursor | lifecycle.terminal-admission | `sha256:b952c2d83aeee61113c4a474d673dbf7d98334a8d85f6d3ab352a5cad689568f` | — | harness.lifecycle.terminal-admission | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| cursor | mcp.catalog | `sha256:54dd40ebbd21f976206d42e35be4f3c92f57b4679ff97a013edb3a406c190394` | — | harness.mcp.catalog | artifact:project:.cursor/mcp.json | supported | `HARNESS_MCP_PROJECTION_RENDERED` |
| cursor | security.safe-dirs | `sha256:8ce38a9571be6fd4220f256972925f3f84dd844c144ac1d479a5d561b435f312` | — | harness.security.safe-dirs | artifact:project:.cursor/hooks.json+.cursor/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| cursor | settings.audit | `sha256:da70a0c0e55d4324a8704a211532d8398083192570b00a7f1d4f94ab4d9daba7` | — | harness.settings.audit | non-artifact:named-cursor-settings-audit | supported | `HARNESS_SETTINGS_AUDIT_NAMED` |
| cursor | settings.permissions | `sha256:9049fe9aad45b74bce05c1f7d565cd7f76816605eb3ffd7ffed6b3df6820a745` | — | harness.settings.permissions | artifact:project:.cursor/cli.json+.cursor/permissions.json | supported | `HARNESS_PROFILE_RENDERED` |
| cursor | workflows.status | `sha256:a535a27aec70899044ca8ca0995cc7bd93e1b1783ae577eb5445b50104db3d27` | — | harness.workflows.status | non-artifact:missing-native-cursor-workflow-status-consumer | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED:cursor:workflows.status:missing-native-cursor-workflow-status-consumer` |

## Temp-contained managed lifecycle evidence

The named representative P2 artifacts are rendered only in temporary roots. `create`, second `check`, induced managed drift and explicit `repair` are independently recorded; bytes outside managed targets remain untouched.

| Representative artifact | Create | Second check | Managed drift | Explicit repair | Outside-managed bytes preserved |
|:--|:--|:--|:--|:--|:--|
| profile:codex:trusted-full-access | create | noop | refuse | repair | True |
| mcp:codex:catalog | create | noop | refuse | repair | True |
| agent:codex:backend-laravel.blade-review | create | noop | refuse | repair | True |
| lifecycle:codex:context.observer | create+create | noop+noop | refuse+noop | repair+noop | True |
