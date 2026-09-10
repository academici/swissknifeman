# P2 authoring carrier matrix

Generated from `P2-authoring-carrier-matrix.json`. Do not edit manually.

Contract: `1.0.0` · source: `en` · overlays: `ru`

| Carrier | Pattern | Class | Canonical owner | Localization | Overlay namespace | Generated owner | Migration admission | Rollback |
|:--|:--|:--|:--|:--|:--|:--|:--|:--|
| `code.comments` | `**/*.{py,sh,js,ts,php}:comments` | `english-only` | owning package source | `forbidden` | — | — | owner+preimage+review+rollback | restore exact source preimage |
| `code.docstrings` | `**/*.{py,js,ts,php}:internal-docstrings` | `english-only` | owning package source | `forbidden` | — | — | owner+preimage+review+rollback | restore exact source preimage |
| `development.docs` | `docs/**\|packages/*/docs/**\|README.md\|CONTRIBUTING.md` | `english-only` | documentation source | `forbidden` | — | declared docs generator when marked generated | owner+preimage+review+generated-owner+rollback | restore source and regenerated target preimages |
| `diagnostic.message` | `provider-neutral diagnostic message catalogs` | `render-resource` | diagnostic contract owner | `sparse-overlay` | `diagnostic.<package>.<code>.message` | diagnostic renderer | owner+preimage+semantic-review+rollback | restore catalog preimage |
| `generated.provider-target` | `.claude/**\|.agents/**\|**/.claude-plugin/**\|**/.codex-plugin/**\|*lock*.json` | `generated-target` | none; derived only | `renderer-only` | — | declared provider adapter/generator | regenerate-only+exact-target-preimage+rollback | restore exact provider-qualified target preimages |
| `legacy.skill-ru` | `packages/skiller/skills/**/SKILL.ru.md` | `legacy-input` | unresolved until P4 admission | `input-only` | — | — | owner+source-preimage+equivalence+generated-owner+rollback | preserve or restore exact legacy preimage |
| `machine.identity` | `IDs\|paths\|commands\|schema keys\|placeholders\|parser literals\|codes\|URLs\|provenance` | `machine-identity` | owning contract/schema/source | `immutable-token` | — | — | byte-parity+owner+preimage+rollback | restore exact owning source preimage |
| `plan.human-text` | `plans/**:human-renderable prose` | `render-resource` | plan semantic source | `sparse-overlay` | `plan.<plan_id>.<section_id>` | plan renderer for generated views | owner+preimage+semantic-review+generated-owner+rollback | restore source and generated view preimages |
| `plugin.human-metadata` | `canonical plugin name/description/category/tag metadata` | `semantic-source` | owning package metadata | `sparse-overlay` | `plugin.<plugin_id>.<field>` | publication generator | owner+preimage+semantic-review+generated-owner+rollback | restore metadata and regenerated manifest preimages |
| `provider.human-message` | `provider adapter user-facing messages` | `render-resource` | provider-neutral message catalog | `sparse-overlay` | `message.<package>.<message_id>` | owning provider adapter | owner+preimage+semantic-review+generated-owner+rollback | restore catalog and provider target preimages |
| `semantic.command` | `packages/task/commands/*.md` | `semantic-source` | task command catalog | `sparse-overlay` | `command.<command_id>.<section_id>` | task provider command renderer | owner+preimage+semantic-review+generated-owner+rollback | restore command and provider projection preimages |
| `semantic.skill` | `packages/skiller/skills/**/SKILL.md` | `semantic-source` | skiller skill registry | `sparse-overlay` | `skill.<semantic_id>.<section_id>` | skiller publication generator | owner+preimage+semantic-review+generated-owner+rollback | restore skill, overlay, registry, and provider target preimages |
