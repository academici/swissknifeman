# Provider harness conformance

> Generated from the validated deterministic provider-audit report; do not maintain an inventory here.

`harness doctor --provider-audit [--json]` is read-only. `settings_audit.py` remains the named Claude Code checker behind `harness doctor --settings`; provider audit never universalizes Claude merge rules.

Validated catalog `sha256:26b30154b872eb44c92ab17789f6f17939ef57982b603175940b32af079e7bdd`: 3 profiles, 26 semantic surfaces, 7 MCP descriptors and 44 agent roles.

Reports retain missing/extra and expected/actual duplicate identities. Full access is only explicit `self-host-apply` for a trusted repository; project, fleet-project and fleet-defaults selection are rejected. Secret references are value-free.

No live target write, activation, apply authority, MCP start, hook start or workflow start is granted. `settings_audit.py` remains Claude-specific.

## Source and render hashes

| Identity | SHA-256 |
|:--|:--|
| source:configs/claude-code/agent-packs/role-bindings.json | `sha256:d619828f8a5ea9a6e5fff0c7f6b87940e6aaaf40c92269e2bf955c85c403614b` |
| source:configs/claude-code/mcp/bindings.json | `sha256:80fcf080664a04c51bf950568b468a7acb4b3bc829866023c3708a08241089aa` |
| source:configs/codex/config/profile-bindings.json | `sha256:9de3078c203f0cebd1a66e0f243efd96cb78a829341ed8f1faa6bc6ed0b1542e` |
| source:configs/codex/hooks/lifecycle-context-bindings.json | `sha256:c8ddcbd49036bd993b66326df3a84c48695b032f2a38683cfddbb28ff1635941` |
| source:configs/codex/mcp/bindings.json | `sha256:7cfaa92d8314f01a20d52f227a0bbda2495f11b4b508bd5376c22670a0de8772` |
| source:configs/common/agent-packs/roles.json | `sha256:cab36fb368e089614ebba5a25359fd3ba6bd05b683dbe7a166e831aa8335ff1d` |
| source:configs/common/mcp/catalog.json | `sha256:95be667cbd19a671f88d946739b7161a6ca33407429ca7d7cb0cd93f6f714419` |
| source:configs/common/profile-catalog.json | `sha256:26b30154b872eb44c92ab17789f6f17939ef57982b603175940b32af079e7bdd` |
| source:configs/cursor/agent-packs/consumer-mapping.json | `sha256:314f0935b254c8a7e814cfa1ae476b99e373d0fffeb4de91fabf8c756708d67e` |
| source:configs/cursor/config/profile-bindings.json | `sha256:8772a33bbdf9d5082bc12457d135e2a29c3faf945a5f8f3c11a9954695bf1594` |
| source:configs/cursor/hooks/lifecycle-context-bindings.json | `sha256:f346a3e406d9da765b875b16cfca6a686172b6e3f94100830710c200f19d9668` |
| source:configs/cursor/mcp/bindings.json | `sha256:c4a5b15e4417cdf05da6cd6130b05890b3feca860c09cb19342754f776a218a6` |
| source:configs/grok/agent-packs/consumer-mapping.json | `sha256:970924a96eefa7f3487491badf52ec87b87c184db962c47ba0befd95d5af5805` |
| source:configs/grok/config/profile-bindings.json | `sha256:3917201ee56b3b9b8c2ea88c9a42d1560a784510eabd92039092a3c3648a50fd` |
| source:configs/grok/hooks/lifecycle-context-bindings.json | `sha256:aaeb65d2fc2717c66736e80ca33fa35e2889394d574a6a766e6d08e7f1c948f3` |
| source:configs/grok/mcp/bindings.json | `sha256:a6d49601aa1729a8aee745a53f8110dd6f59b55851248a607c49da1b32edc89d` |
| render-manifest:all-provider-qualified-outputs | `sha256:1719ba6d0252b3c1f6f69cbe56b6cf8305a084ca5a49fc6a8f00aeee168fd364` |

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
| claude-code | lifecycle.plan-guard | `sha256:0bf5800b008c1b773af44982fe8a310db971429f1d0e1eef2e808a60d47da15a` | — | harness.lifecycle.plan-guard | native-binding:project-settings | supported | `HARNESS_ACTIVATION_NATIVE` |
| claude-code | lifecycle.plan-regen | `sha256:d51fcb747b9ffeff08befb583d000fa33efbae5129f2a08083b3694f1f1c7890` | — | harness.lifecycle.plan-regen | native-binding:project-settings | supported | `HARNESS_ACTIVATION_NATIVE` |
| claude-code | lifecycle.review-gate | `sha256:a8bdf4c8d37277ab0a8976ee7cfcf215f5ee8e63f4bb69163dca1796ebe44368` | — | harness.lifecycle.review-gate | native-binding:global-hook | supported | `HARNESS_ACTIVATION_NATIVE` |
| claude-code | lifecycle.router | `sha256:3579aac732a227a565edc6175dbfa4ddc27767a10af3aa7fb70091ca4915f283` | — | harness.lifecycle.router | native-binding:project-settings | supported | `HARNESS_ACTIVATION_NATIVE` |
| claude-code | lifecycle.run-report | `sha256:9b92c0ff639e64772a2961e198f3f9d7b93bf120a6aed8e1350a5f0fa6bea13b` | — | harness.lifecycle.run-report | native-binding:project-settings | supported | `HARNESS_ACTIVATION_NATIVE` |
| claude-code | lifecycle.tool-telemetry | `sha256:6907facd80a1eeef47b08c686355698cb724f30f27f27ad790ad25019679f176` | — | harness.lifecycle.tool-telemetry | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
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
| codex | lifecycle.plan-guard | `sha256:0bf5800b008c1b773af44982fe8a310db971429f1d0e1eef2e808a60d47da15a` | — | harness.lifecycle.plan-guard | artifact:project:.codex/hooks.json+.codex/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| codex | lifecycle.plan-regen | `sha256:d51fcb747b9ffeff08befb583d000fa33efbae5129f2a08083b3694f1f1c7890` | — | harness.lifecycle.plan-regen | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| codex | lifecycle.review-gate | `sha256:a8bdf4c8d37277ab0a8976ee7cfcf215f5ee8e63f4bb69163dca1796ebe44368` | — | harness.lifecycle.review-gate | artifact:project:.codex/hooks.json+.codex/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| codex | lifecycle.router | `sha256:3579aac732a227a565edc6175dbfa4ddc27767a10af3aa7fb70091ca4915f283` | — | harness.lifecycle.router | artifact:project:.codex/hooks.json+.codex/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| codex | lifecycle.run-report | `sha256:9b92c0ff639e64772a2961e198f3f9d7b93bf120a6aed8e1350a5f0fa6bea13b` | — | harness.lifecycle.run-report | artifact:project:.codex/hooks.json+.codex/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| codex | lifecycle.tool-telemetry | `sha256:6907facd80a1eeef47b08c686355698cb724f30f27f27ad790ad25019679f176` | — | harness.lifecycle.tool-telemetry | artifact:project:.codex/hooks.json+.codex/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
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
| cursor | lifecycle.changelog-gate | `sha256:6a1579586594df0a691221c4aca2efe7d7f4835be82c0f807d3ba785b2ea8a9d` | — | harness.lifecycle.changelog-gate | artifact:project:.cursor/hooks.json+.cursor/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| cursor | lifecycle.command-log | `sha256:6c2900af6956f64747429488e3177132cbed547a935cf98bda46a26fe57fe8ad` | — | harness.lifecycle.command-log | artifact:project:.cursor/hooks.json+.cursor/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| cursor | lifecycle.daemon-safety | `sha256:d7eefb087ebafb37c2dfd19240e1611c6150925d12977d337c78a6e126ebbf2b` | — | harness.lifecycle.daemon-safety | artifact:project:.cursor/hooks.json+.cursor/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| cursor | lifecycle.git-guardrails | `sha256:4d5c38147dc736cb1d6b93c38e04d98324f48c057cc9ebb4ab294c4181559610` | — | harness.lifecycle.git-guardrails | artifact:project:.cursor/hooks.json+.cursor/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| cursor | lifecycle.memory | `sha256:1c68623b21d4eafa0887b798cedea70ec3cf7d0674d35320f61328686e02e3fb` | — | harness.lifecycle.memory | artifact:project:.cursor/hooks.json+.cursor/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| cursor | lifecycle.notification | `sha256:c9e55167aaf018fdc0109cea4553c2c2911d53f709e49d400ed367a8b0683a00` | — | harness.lifecycle.notification | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| cursor | lifecycle.pack-guard | `sha256:05b5c33e3cb01e7ce424631d35b8485adcf77ba6b66a78bd8bf73dfbaa6b9c8e` | — | harness.lifecycle.pack-guard | artifact:project:.cursor/hooks.json+.cursor/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| cursor | lifecycle.plan-guard | `sha256:0bf5800b008c1b773af44982fe8a310db971429f1d0e1eef2e808a60d47da15a` | — | harness.lifecycle.plan-guard | artifact:project:.cursor/hooks.json+.cursor/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| cursor | lifecycle.plan-regen | `sha256:d51fcb747b9ffeff08befb583d000fa33efbae5129f2a08083b3694f1f1c7890` | — | harness.lifecycle.plan-regen | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| cursor | lifecycle.review-gate | `sha256:a8bdf4c8d37277ab0a8976ee7cfcf215f5ee8e63f4bb69163dca1796ebe44368` | — | harness.lifecycle.review-gate | artifact:project:.cursor/hooks.json+.cursor/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| cursor | lifecycle.router | `sha256:3579aac732a227a565edc6175dbfa4ddc27767a10af3aa7fb70091ca4915f283` | — | harness.lifecycle.router | artifact:project:.cursor/rules/swissknifeman-router.mdc | supported | `HARNESS_CURSOR_STATIC_RULE` |
| cursor | lifecycle.run-report | `sha256:9b92c0ff639e64772a2961e198f3f9d7b93bf120a6aed8e1350a5f0fa6bea13b` | — | harness.lifecycle.run-report | artifact:project:.cursor/hooks.json+.cursor/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| cursor | lifecycle.tool-telemetry | `sha256:6907facd80a1eeef47b08c686355698cb724f30f27f27ad790ad25019679f176` | — | harness.lifecycle.tool-telemetry | artifact:project:.cursor/hooks.json+.cursor/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| cursor | mcp.catalog | `sha256:54dd40ebbd21f976206d42e35be4f3c92f57b4679ff97a013edb3a406c190394` | — | harness.mcp.catalog | artifact:project:.cursor/mcp.json | supported | `HARNESS_MCP_PROJECTION_RENDERED` |
| cursor | security.safe-dirs | `sha256:8ce38a9571be6fd4220f256972925f3f84dd844c144ac1d479a5d561b435f312` | — | harness.security.safe-dirs | artifact:project:.cursor/hooks.json+.cursor/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| cursor | settings.audit | `sha256:da70a0c0e55d4324a8704a211532d8398083192570b00a7f1d4f94ab4d9daba7` | — | harness.settings.audit | non-artifact:named-cursor-settings-audit | supported | `HARNESS_SETTINGS_AUDIT_NAMED` |
| cursor | settings.permissions | `sha256:9049fe9aad45b74bce05c1f7d565cd7f76816605eb3ffd7ffed6b3df6820a745` | — | harness.settings.permissions | artifact:project:.cursor/cli.json+.cursor/permissions.json | supported | `HARNESS_PROFILE_RENDERED` |
| cursor | workflows.status | `sha256:a535a27aec70899044ca8ca0995cc7bd93e1b1783ae577eb5445b50104db3d27` | — | harness.workflows.status | non-artifact:missing-native-cursor-workflow-status-consumer | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED:cursor:workflows.status:missing-native-cursor-workflow-status-consumer` |
| grok | agent-packs.lifecycle | `sha256:6b1474a5f1639a652540c5db8fd351ca5aed822ca2c20f48ba7cde99a3750d76` | — | harness.agent-packs.lifecycle | non-artifact:grok-consumer-lifecycle-shared-projection | supported | `HARNESS_CURSOR_AGENTPACK_CONSUMER_LIFECYCLE` |
| grok | agents.catalog | `sha256:31178a06201f890a47e2398758a442712966070d36f336b5ac0eafa542921a36` | — | harness.agents.catalog | non-artifact:grok-consumer-mapping:44-targets:.claude/agents/*.md | supported | `HARNESS_CURSOR_AGENT_CONSUMER_MAPPING` |
| grok | context.observer | `sha256:98df3b65365820591b7a28539560e3180527b9337c8faf018afd25adf9e376ce` | — | harness.context.observer | artifact:project:.grok/hooks/swissknifeman.json+.grok/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| grok | context.output-style | `sha256:bdb667e3bbd31f2fb10de42a11d8f8f07d0a0e8536c28d9961e8ae1149fd27b0` | — | harness.context.output-style | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| grok | context.plans-directory | `sha256:55d7f15dcab4a4c1a5c657fddb5b305450afc5e5a2db40bf8e451d39b63638ce` | — | harness.context.plans-directory | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| grok | doctor.environment | `sha256:a559d78d9d698deeebe696353405507b85f3eaefe96a7f0a621d3be04033c5ec` | — | harness.doctor.environment | non-artifact:named-harness-doctor | supported | `HARNESS_DOCTOR_ENVIRONMENT_NAMED` |
| grok | doctor.provider | `sha256:b697fe554c9c0d0271f950bd875c6a81373c03bf97aaf4e6ba11352ca184273a` | — | harness.doctor.provider | non-artifact:provider-audit | supported | `HARNESS_PROVIDER_AUDIT_NAMED` |
| grok | lifecycle.auto-approval | `sha256:8681c3e09d1ef2a59015ccda5efebf4c4d2417b73f6b47c45bdda4d5bff7e6d9` | — | harness.lifecycle.auto-approval | native-binding:P5.2-config-security-projection | supported | `HARNESS_ACTIVATION_NATIVE` |
| grok | lifecycle.changelog-gate | `sha256:6a1579586594df0a691221c4aca2efe7d7f4835be82c0f807d3ba785b2ea8a9d` | — | harness.lifecycle.changelog-gate | artifact:project:.grok/hooks/swissknifeman.json+.grok/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| grok | lifecycle.command-log | `sha256:6c2900af6956f64747429488e3177132cbed547a935cf98bda46a26fe57fe8ad` | — | harness.lifecycle.command-log | artifact:project:.grok/hooks/swissknifeman.json+.grok/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| grok | lifecycle.daemon-safety | `sha256:d7eefb087ebafb37c2dfd19240e1611c6150925d12977d337c78a6e126ebbf2b` | — | harness.lifecycle.daemon-safety | artifact:project:.grok/hooks/swissknifeman.json+.grok/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| grok | lifecycle.git-guardrails | `sha256:4d5c38147dc736cb1d6b93c38e04d98324f48c057cc9ebb4ab294c4181559610` | — | harness.lifecycle.git-guardrails | artifact:project:.grok/hooks/swissknifeman.json+.grok/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| grok | lifecycle.memory | `sha256:1c68623b21d4eafa0887b798cedea70ec3cf7d0674d35320f61328686e02e3fb` | — | harness.lifecycle.memory | artifact:project:.grok/hooks/swissknifeman.json+.grok/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| grok | lifecycle.notification | `sha256:c9e55167aaf018fdc0109cea4553c2c2911d53f709e49d400ed367a8b0683a00` | — | harness.lifecycle.notification | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| grok | lifecycle.pack-guard | `sha256:05b5c33e3cb01e7ce424631d35b8485adcf77ba6b66a78bd8bf73dfbaa6b9c8e` | — | harness.lifecycle.pack-guard | artifact:project:.grok/hooks/swissknifeman.json+.grok/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| grok | lifecycle.plan-guard | `sha256:0bf5800b008c1b773af44982fe8a310db971429f1d0e1eef2e808a60d47da15a` | — | harness.lifecycle.plan-guard | artifact:project:.grok/hooks/swissknifeman.json+.grok/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| grok | lifecycle.plan-regen | `sha256:d51fcb747b9ffeff08befb583d000fa33efbae5129f2a08083b3694f1f1c7890` | — | harness.lifecycle.plan-regen | non-artifact:unsupported-native-binding | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED` |
| grok | lifecycle.review-gate | `sha256:a8bdf4c8d37277ab0a8976ee7cfcf215f5ee8e63f4bb69163dca1796ebe44368` | — | harness.lifecycle.review-gate | artifact:project:.grok/hooks/swissknifeman.json+.grok/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| grok | lifecycle.router | `sha256:3579aac732a227a565edc6175dbfa4ddc27767a10af3aa7fb70091ca4915f283` | — | harness.lifecycle.router | artifact:project:.grok/hooks/swissknifeman.json+.grok/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| grok | lifecycle.run-report | `sha256:9b92c0ff639e64772a2961e198f3f9d7b93bf120a6aed8e1350a5f0fa6bea13b` | — | harness.lifecycle.run-report | artifact:project:.grok/hooks/swissknifeman.json+.grok/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| grok | lifecycle.tool-telemetry | `sha256:6907facd80a1eeef47b08c686355698cb724f30f27f27ad790ad25019679f176` | — | harness.lifecycle.tool-telemetry | artifact:project:.grok/hooks/swissknifeman.json+.grok/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| grok | mcp.catalog | `sha256:54dd40ebbd21f976206d42e35be4f3c92f57b4679ff97a013edb3a406c190394` | — | harness.mcp.catalog | artifact:project:.grok/config.toml | supported | `HARNESS_MCP_PROJECTION_RENDERED` |
| grok | security.safe-dirs | `sha256:8ce38a9571be6fd4220f256972925f3f84dd844c144ac1d479a5d561b435f312` | — | harness.security.safe-dirs | artifact:project:.grok/hooks/swissknifeman.json+.grok/hooks/lifecycle.py | supported | `HARNESS_ACTIVATION_NATIVE` |
| grok | settings.audit | `sha256:da70a0c0e55d4324a8704a211532d8398083192570b00a7f1d4f94ab4d9daba7` | — | harness.settings.audit | non-artifact:named-grok-settings-audit | supported | `HARNESS_SETTINGS_AUDIT_NAMED` |
| grok | settings.permissions | `sha256:9049fe9aad45b74bce05c1f7d565cd7f76816605eb3ffd7ffed6b3df6820a745` | — | harness.settings.permissions | artifact:project:.grok/config.toml | supported | `HARNESS_PROFILE_RENDERED` |
| grok | workflows.status | `sha256:a535a27aec70899044ca8ca0995cc7bd93e1b1783ae577eb5445b50104db3d27` | — | harness.workflows.status | non-artifact:missing-native-grok-workflow-status-consumer | unsupported | `HARNESS_ACTIVATION_UNSUPPORTED:grok:workflows.status:missing-native-grok-workflow-status-consumer` |

## Temp-contained managed lifecycle evidence

The named representative P2 artifacts are rendered only in temporary roots. `create`, second `check`, induced managed drift and explicit `repair` are independently recorded; bytes outside managed targets remain untouched.

| Representative artifact | Create | Second check | Managed drift | Explicit repair | Outside-managed bytes preserved |
|:--|:--|:--|:--|:--|:--|
| profile:codex:trusted-full-access | create | noop | refuse | repair | True |
| mcp:codex:catalog | create | noop | refuse | repair | True |
| agent:codex:backend-laravel.blade-review | create | noop | refuse | repair | True |
| lifecycle:codex:context.observer | create+create | noop+noop | refuse+noop | repair+noop | True |
