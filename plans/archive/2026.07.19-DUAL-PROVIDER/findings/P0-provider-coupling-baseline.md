# P0 provider coupling baseline

## Anchor

- `git rev-parse HEAD`: `9844f499797faf063aede49b79703c71f7ef666e`.
- `git status --short`:

```text
 M .mcp.json.example
 M docs/reference.md
 M packages/skiller/skills/general/plan-protocol/SKILL.md
 M packages/skiller/skills/general/plan-protocol/SKILL.ru.md
 M packages/skiller/skills/general/plan-protocol/snippets/journal-template.md
 M packages/task/.claude-plugin/plugin.json
 M packages/task/commands/plan-design.md
 M packages/task/lib/task/journal.py
 M packages/task/lib/task/plan_lint.py
 M packages/task/tests/test_journal.py
 M packages/task/tests/test_plan_lint.py
 M plans/2026.07.18-FOREMAN/handoff.md
 M plans/2026.07.18-FOREMAN/plan.md
 M plans/ACTIVE.md
?? .agents/
?? .serena/
?? AGENTS.md
?? plans/2026.07.19-DUAL-PROVIDER/
```

The anchor records the complete visible worktree; untracked or dirty files are not included automatically in an item commit.

## Summary

| Surface | Pass 1 | Current | Delta |
|:--|--:|--:|--:|
| canonical skills | 216 | 216 | +0 |
| task commands | 32 | 11 | -21 |
| plugin manifests | 54 | 54 | +0 |
| MCP presets | 8 | 8 | +0 |
| agent packs | 10 | 10 | +0 |
| fleet projects | 25 | 25 | +0 |

The only delta is `task commands` (-21): the frozen pass-1 finding described 32, while the explicit canonical root `packages/task/commands/*.md` currently contains 11. The helper preserves that definition rather than broadening it to unrelated package command directories; P0.2 must decide whether the older label used a different scope.

Raw sorted path/id sets:

### canonical skills

```text
packages/skiller/skills/ai/ai-agents/SKILL.md
packages/skiller/skills/ai/mcp-builder/SKILL.md
packages/skiller/skills/ai/performance/SKILL.md
packages/skiller/skills/architect/agent-design/SKILL.md
packages/skiller/skills/architect/api-design/SKILL.md
packages/skiller/skills/architect/architecture/SKILL.md
packages/skiller/skills/architect/codebase-design/SKILL.md
packages/skiller/skills/architect/data-schema/SKILL.md
packages/skiller/skills/architect/domain-modeling/SKILL.md
packages/skiller/skills/architect/ecosystem-reuse-gate/SKILL.md
packages/skiller/skills/architect/engineering/SKILL.md
packages/skiller/skills/architect/eval-design/SKILL.md
packages/skiller/skills/architect/figma-mcp-core/SKILL.md
packages/skiller/skills/architect/legal-compliance/SKILL.md
packages/skiller/skills/architect/observability-design/SKILL.md
packages/skiller/skills/architect/package-contribution-protocol/SKILL.md
packages/skiller/skills/architect/security-design/SKILL.md
packages/skiller/skills/architect/tech-stack-selection/SKILL.md
packages/skiller/skills/axioma/axioma-doctrine/SKILL.md
packages/skiller/skills/axioma/axioma-glossary/SKILL.md
packages/skiller/skills/axioma/axioma-stack/SKILL.md
packages/skiller/skills/axioma/ecosystem-map/SKILL.md
packages/skiller/skills/azguard/azguard/SKILL.md
packages/skiller/skills/blender-modeling/build-loop/SKILL.md
packages/skiller/skills/blender-modeling/config-conventions/SKILL.md
packages/skiller/skills/blender-modeling/model-rules/SKILL.md
packages/skiller/skills/blender-modeling/parametric-config/SKILL.md
packages/skiller/skills/blender-modeling/scene-conventions/SKILL.md
packages/skiller/skills/blender-modeling/threading/SKILL.md
packages/skiller/skills/blender/mcp-blender/SKILL.md
packages/skiller/skills/blender/version-gotchas/SKILL.md
packages/skiller/skills/botkit/botkit/SKILL.md
packages/skiller/skills/creative/content-creative/SKILL.md
packages/skiller/skills/devops/ci-cd/SKILL.md
packages/skiller/skills/devops/db-test-preflight/SKILL.md
packages/skiller/skills/devops/docker-dev-prod/SKILL.md
packages/skiller/skills/devops/docker-php/SKILL.md
packages/skiller/skills/devops/docker-postgres/SKILL.md
packages/skiller/skills/devops/docker-services/SKILL.md
packages/skiller/skills/devops/docker-vite/SKILL.md
packages/skiller/skills/devops/docker/SKILL.md
packages/skiller/skills/devops/gitops/SKILL.md
packages/skiller/skills/devops/makefile/SKILL.md
packages/skiller/skills/devops/node-pnpm-preflight/SKILL.md
packages/skiller/skills/finance/finance/SKILL.md
packages/skiller/skills/founder/adversarial-check/SKILL.md
packages/skiller/skills/founder/competitive-analysis/SKILL.md
packages/skiller/skills/founder/customer-discovery/SKILL.md
packages/skiller/skills/founder/defensibility/SKILL.md
packages/skiller/skills/founder/idea-audit/SKILL.md
packages/skiller/skills/founder/idea-discovery/SKILL.md
packages/skiller/skills/founder/new-project/SKILL.md
packages/skiller/skills/founder/pitch-deck/SKILL.md
packages/skiller/skills/founder/risk-assessment/SKILL.md
packages/skiller/skills/founder/startup-lifecycle/SKILL.md
packages/skiller/skills/frontend-animations/motion/SKILL.md
packages/skiller/skills/frontend-backend/backend-type-sync/SKILL.md
packages/skiller/skills/frontend-backend/inertia-vue/SKILL.md
packages/skiller/skills/frontend-backend/laravel-echo-client/SKILL.md
packages/skiller/skills/frontend-figma/figma-to-vue/SKILL.md
packages/skiller/skills/frontend-linting/antfu/SKILL.md
packages/skiller/skills/frontend-linting/eslint-flat-config/SKILL.md
packages/skiller/skills/frontend-linting/js-code-style/SKILL.md
packages/skiller/skills/frontend-linting/ts-library/SKILL.md
packages/skiller/skills/frontend-naive-ui/naive-ui-theming/SKILL.md
packages/skiller/skills/frontend-nuxt/nuxt-modules/SKILL.md
packages/skiller/skills/frontend-nuxt/nuxt-seo/SKILL.md
packages/skiller/skills/frontend-nuxt/nuxt/SKILL.md
packages/skiller/skills/frontend-reka/reka-ui-cva/SKILL.md
packages/skiller/skills/frontend-tailwind/dark-mode/SKILL.md
packages/skiller/skills/frontend-tailwind/tailwind-conventions/SKILL.md
packages/skiller/skills/frontend-vite/vite-module-loader/SKILL.md
packages/skiller/skills/frontend-vite/vite-multi-build/SKILL.md
packages/skiller/skills/frontend-vite/vite/SKILL.md
packages/skiller/skills/frontend-vite/vitepress/SKILL.md
packages/skiller/skills/frontend-vue/pinia-stores/SKILL.md
packages/skiller/skills/frontend-vue/pinia/SKILL.md
packages/skiller/skills/frontend-vue/vitest-vue/SKILL.md
packages/skiller/skills/frontend-vue/vitest/SKILL.md
packages/skiller/skills/frontend-vue/vue-best-practices/SKILL.md
packages/skiller/skills/frontend-vue/vue-composition-api/SKILL.md
packages/skiller/skills/frontend-vue/vue-dynamic-icons/SKILL.md
packages/skiller/skills/frontend-vue/vue-router-best-practices/SKILL.md
packages/skiller/skills/frontend-vue/vue-testing-best-practices/SKILL.md
packages/skiller/skills/frontend-vue/vue/SKILL.md
packages/skiller/skills/frontend-vue/vueuse-functions/SKILL.md
packages/skiller/skills/frontend-wayfinder/wayfinder/SKILL.md
packages/skiller/skills/frontend/document-writer/SKILL.md
packages/skiller/skills/frontend/filepond-upload/SKILL.md
packages/skiller/skills/frontend/web-design-guidelines/SKILL.md
packages/skiller/skills/general/anti-drift/SKILL.md
packages/skiller/skills/general/compact-responses/SKILL.md
packages/skiller/skills/general/complex-task-orchestrator/SKILL.md
packages/skiller/skills/general/context-economy/SKILL.md
packages/skiller/skills/general/cross-layer-change-checklist/SKILL.md
packages/skiller/skills/general/git-commit-rules/SKILL.md
packages/skiller/skills/general/git-safety/SKILL.md
packages/skiller/skills/general/grill-with-docs/SKILL.md
packages/skiller/skills/general/implement/SKILL.md
packages/skiller/skills/general/mcp-advisor/SKILL.md
packages/skiller/skills/general/naming-conventions/SKILL.md
packages/skiller/skills/general/packages-stack/SKILL.md
packages/skiller/skills/general/plan-protocol/SKILL.md
packages/skiller/skills/general/project-map/SKILL.md
packages/skiller/skills/general/session-handoff/SKILL.md
packages/skiller/skills/general/shell/SKILL.md
packages/skiller/skills/general/skills-ssot/SKILL.md
packages/skiller/skills/general/spec-interview/SKILL.md
packages/skiller/skills/general/task-brief-template/SKILL.md
packages/skiller/skills/general/verify-claims/SKILL.md
packages/skiller/skills/general/workflow-craft/SKILL.md
packages/skiller/skills/general/writing-style/SKILL.md
packages/skiller/skills/laravel-architecture/config-driven-abstraction/SKILL.md
packages/skiller/skills/laravel-architecture/eloquent-accessors/SKILL.md
packages/skiller/skills/laravel-architecture/enum-attributes/SKILL.md
packages/skiller/skills/laravel-architecture/enum-state-machine/SKILL.md
packages/skiller/skills/laravel-architecture/laravel-subagents/SKILL.md
packages/skiller/skills/laravel-architecture/modular-architecture/SKILL.md
packages/skiller/skills/laravel-auth/attribute-authorization/SKILL.md
packages/skiller/skills/laravel-auth/laravel-permissions/SKILL.md
packages/skiller/skills/laravel-auth/laravel-security-audit/SKILL.md
packages/skiller/skills/laravel-data-layer/laravel-broadcasting/SKILL.md
packages/skiller/skills/laravel-data-layer/laravel-data/SKILL.md
packages/skiller/skills/laravel-extras/medialibrary/SKILL.md
packages/skiller/skills/laravel-extras/pennant-development/SKILL.md
packages/skiller/skills/laravel-extras/spatie-settings/SKILL.md
packages/skiller/skills/laravel-filament/filament/SKILL.md
packages/skiller/skills/laravel-livewire/livewire-blade-attributes/SKILL.md
packages/skiller/skills/laravel-testing/health-checks/SKILL.md
packages/skiller/skills/laravel-testing/laravel-dusk/SKILL.md
packages/skiller/skills/laravel-testing/laravel-testing/SKILL.md
packages/skiller/skills/laravel-testing/test-isolation-guard/SKILL.md
packages/skiller/skills/legal/legal/SKILL.md
packages/skiller/skills/marketing/marketing/SKILL.md
packages/skiller/skills/mobile/figma-to-flutter/SKILL.md
packages/skiller/skills/operator/capacity-planning/SKILL.md
packages/skiller/skills/operator/incident-response/SKILL.md
packages/skiller/skills/operator/oncall-rotation/SKILL.md
packages/skiller/skills/operator/operations-cx/SKILL.md
packages/skiller/skills/operator/postmortem/SKILL.md
packages/skiller/skills/operator/runbook/SKILL.md
packages/skiller/skills/oss-dev/dependency-audit/SKILL.md
packages/skiller/skills/oss-dev/dx-design/SKILL.md
packages/skiller/skills/oss-dev/gh-review/SKILL.md
packages/skiller/skills/oss-dev/github-flow/SKILL.md
packages/skiller/skills/oss-dev/issue-triage/SKILL.md
packages/skiller/skills/oss-dev/oss-development/SKILL.md
packages/skiller/skills/oss-dev/oss-governance/SKILL.md
packages/skiller/skills/oss-dev/release-engineering/SKILL.md
packages/skiller/skills/oss-dev/resolving-merge-conflicts/SKILL.md
packages/skiller/skills/oss-dev/to-issues/SKILL.md
packages/skiller/skills/php-packages/laravel-package-compatibility/SKILL.md
packages/skiller/skills/php-packages/laravel-package-docs/SKILL.md
packages/skiller/skills/php-packages/laravel-package-expressive/SKILL.md
packages/skiller/skills/php-packages/laravel-package-generate-skill/SKILL.md
packages/skiller/skills/php-packages/laravel-package-release/SKILL.md
packages/skiller/skills/php-packages/laravel-package-scaffold/SKILL.md
packages/skiller/skills/php-packages/laravel-package-service-provider/SKILL.md
packages/skiller/skills/php-packages/laravel-package-testing/SKILL.md
packages/skiller/skills/php-packages/laravel-packages/SKILL.md
packages/skiller/skills/php/code-style-spatie/SKILL.md
packages/skiller/skills/php/cursor-pagination-design/SKILL.md
packages/skiller/skills/php/database/SKILL.md
packages/skiller/skills/php/dependency-injection/SKILL.md
packages/skiller/skills/php/laravel-best-practices/SKILL.md
packages/skiller/skills/php/laravel-structure/SKILL.md
packages/skiller/skills/php/laravel/SKILL.md
packages/skiller/skills/php/named-arguments/SKILL.md
packages/skiller/skills/php/namespace-refactor-safety/SKILL.md
packages/skiller/skills/php/naming-conventions/SKILL.md
packages/skiller/skills/php/pao/SKILL.md
packages/skiller/skills/php/php-patterns/SKILL.md
packages/skiller/skills/php/php-upgrade-checklist/SKILL.md
packages/skiller/skills/php/production-readiness-checklist/SKILL.md
packages/skiller/skills/php/repositories/SKILL.md
packages/skiller/skills/php/static-analysis/SKILL.md
packages/skiller/skills/php/transactional-outbox-relay/SKILL.md
packages/skiller/skills/pm/brd/SKILL.md
packages/skiller/skills/pm/business-process/SKILL.md
packages/skiller/skills/pm/go-to-market/SKILL.md
packages/skiller/skills/pm/monetization-design/SKILL.md
packages/skiller/skills/pm/pmf-diagnostics/SKILL.md
packages/skiller/skills/pm/prd-from-brd/SKILL.md
packages/skiller/skills/pm/product-roadmap/SKILL.md
packages/skiller/skills/pm/product/SKILL.md
packages/skiller/skills/pm/requirement-critic/SKILL.md
packages/skiller/skills/pm/unit-economics/SKILL.md
packages/skiller/skills/python/ml-project-structure/SKILL.md
packages/skiller/skills/python/venv-dependencies/SKILL.md
packages/skiller/skills/quality/artifact-review/SKILL.md
packages/skiller/skills/quality/code-review/SKILL.md
packages/skiller/skills/quality/code-simplifier/SKILL.md
packages/skiller/skills/quality/diagnosing-bugs/SKILL.md
packages/skiller/skills/quality/mutation-testing/SKILL.md
packages/skiller/skills/quality/playwright-e2e/SKILL.md
packages/skiller/skills/quality/refactoring-plan/SKILL.md
packages/skiller/skills/quality/tdd-discipline/SKILL.md
packages/skiller/skills/quality/tech-debt-audit/SKILL.md
packages/skiller/skills/quality/test-strategy/SKILL.md
packages/skiller/skills/quality/testing-safety-report/SKILL.md
packages/skiller/skills/research/query-craft/SKILL.md
packages/skiller/skills/research/research/SKILL.md
packages/skiller/skills/roles/open-source-maintainer/SKILL.md
packages/skiller/skills/roles/solo-founder/SKILL.md
packages/skiller/skills/roles/startup-cto/SKILL.md
packages/skiller/skills/roles/tech-lead/SKILL.md
packages/skiller/skills/sales/sales/SKILL.md
packages/skiller/skills/security/security/SKILL.md
packages/skiller/skills/system/agent-packs/SKILL.md
packages/skiller/skills/system/brain-locator/SKILL.md
packages/skiller/skills/system/cross-project-coordinator/SKILL.md
packages/skiller/skills/system/local-topology/SKILL.md
packages/skiller/skills/system/session-observer/SKILL.md
packages/skiller/skills/system/shared-memory/SKILL.md
packages/skiller/skills/system/swissknifeman-locator/SKILL.md
packages/skiller/skills/voice-ai/voice-ai/SKILL.md
```

### task commands

```text
packages/task/commands/design.md
packages/task/commands/dev.md
packages/task/commands/fix.md
packages/task/commands/make-workflow.md
packages/task/commands/plan-audit.md
packages/task/commands/plan-close.md
packages/task/commands/plan-design.md
packages/task/commands/plan-exec.md
packages/task/commands/plan-run.md
packages/task/commands/research.md
packages/task/commands/review.md
```

### plugin manifests

```text
packages/analyst/.claude-plugin/plugin.json
packages/harness/.claude-plugin/plugin.json
packages/maind/.claude-plugin/plugin.json
packages/maind/node_modules/@agentmemory/agentmemory/plugin/.claude-plugin/plugin.json
packages/skiller/generate-skill/.claude-plugin/plugin.json
packages/skiller/skills/ai/.claude-plugin/plugin.json
packages/skiller/skills/architect/.claude-plugin/plugin.json
packages/skiller/skills/axioma/.claude-plugin/plugin.json
packages/skiller/skills/azguard/.claude-plugin/plugin.json
packages/skiller/skills/blender-modeling/.claude-plugin/plugin.json
packages/skiller/skills/blender/.claude-plugin/plugin.json
packages/skiller/skills/botkit/.claude-plugin/plugin.json
packages/skiller/skills/creative/.claude-plugin/plugin.json
packages/skiller/skills/devops/.claude-plugin/plugin.json
packages/skiller/skills/finance/.claude-plugin/plugin.json
packages/skiller/skills/founder/.claude-plugin/plugin.json
packages/skiller/skills/frontend-animations/.claude-plugin/plugin.json
packages/skiller/skills/frontend-backend/.claude-plugin/plugin.json
packages/skiller/skills/frontend-figma/.claude-plugin/plugin.json
packages/skiller/skills/frontend-linting/.claude-plugin/plugin.json
packages/skiller/skills/frontend-naive-ui/.claude-plugin/plugin.json
packages/skiller/skills/frontend-nuxt/.claude-plugin/plugin.json
packages/skiller/skills/frontend-reka/.claude-plugin/plugin.json
packages/skiller/skills/frontend-tailwind/.claude-plugin/plugin.json
packages/skiller/skills/frontend-vite/.claude-plugin/plugin.json
packages/skiller/skills/frontend-vue/.claude-plugin/plugin.json
packages/skiller/skills/frontend-wayfinder/.claude-plugin/plugin.json
packages/skiller/skills/frontend/.claude-plugin/plugin.json
packages/skiller/skills/general/.claude-plugin/plugin.json
packages/skiller/skills/laravel-architecture/.claude-plugin/plugin.json
packages/skiller/skills/laravel-auth/.claude-plugin/plugin.json
packages/skiller/skills/laravel-data-layer/.claude-plugin/plugin.json
packages/skiller/skills/laravel-extras/.claude-plugin/plugin.json
packages/skiller/skills/laravel-filament/.claude-plugin/plugin.json
packages/skiller/skills/laravel-livewire/.claude-plugin/plugin.json
packages/skiller/skills/laravel-testing/.claude-plugin/plugin.json
packages/skiller/skills/legal/.claude-plugin/plugin.json
packages/skiller/skills/marketing/.claude-plugin/plugin.json
packages/skiller/skills/mobile/.claude-plugin/plugin.json
packages/skiller/skills/operator/.claude-plugin/plugin.json
packages/skiller/skills/oss-dev/.claude-plugin/plugin.json
packages/skiller/skills/php-packages/.claude-plugin/plugin.json
packages/skiller/skills/php/.claude-plugin/plugin.json
packages/skiller/skills/pm/.claude-plugin/plugin.json
packages/skiller/skills/python/.claude-plugin/plugin.json
packages/skiller/skills/quality/.claude-plugin/plugin.json
packages/skiller/skills/research/.claude-plugin/plugin.json
packages/skiller/skills/roles/.claude-plugin/plugin.json
packages/skiller/skills/sales/.claude-plugin/plugin.json
packages/skiller/skills/security/.claude-plugin/plugin.json
packages/skiller/skills/system/.claude-plugin/plugin.json
packages/skiller/skills/voice-ai/.claude-plugin/plugin.json
packages/skiller/skm/.claude-plugin/plugin.json
packages/task/.claude-plugin/plugin.json
```

### MCP presets

```text
packages/harness/configs/claude-code/mcp/context7.json
packages/harness/configs/claude-code/mcp/fetch.json
packages/harness/configs/claude-code/mcp/filesystem.json
packages/harness/configs/claude-code/mcp/github.json
packages/harness/configs/claude-code/mcp/memory.json
packages/harness/configs/claude-code/mcp/perplexity.json
packages/harness/configs/claude-code/mcp/playwright.json
packages/harness/configs/claude-code/mcp/sequential-thinking.json
```

### agent packs

```text
packages/harness/configs/claude-code/agent-packs/_common/pack.json
packages/harness/configs/claude-code/agent-packs/backend-laravel/pack.json
packages/harness/configs/claude-code/agent-packs/dart-flutter/pack.json
packages/harness/configs/claude-code/agent-packs/laravel-package/pack.json
packages/harness/configs/claude-code/agent-packs/node-frontend/pack.json
packages/harness/configs/claude-code/agent-packs/python-backend/pack.json
packages/harness/configs/claude-code/agent-packs/role-cto/pack.json
packages/harness/configs/claude-code/agent-packs/role-founder/pack.json
packages/harness/configs/claude-code/agent-packs/role-maintainer/pack.json
packages/harness/configs/claude-code/agent-packs/role-tech-lead/pack.json
```

### fleet projects

```text
agelto
diabox
flexcrm
axiomaerpsdk
azguard
botkit
vaulter
swissknifeman
axiomastudio
corex
memster
cms
edufy
vintera
dterema
dterema-app
sibintek-insiders
chatom
perplexity-web-mcp
loqum
brain
local-repo
local-repo
local-repo
local-repo
```

## Coupling by package

### skiller

Provider-name matches are classified seams, not defects.

```text
packages/skiller/lib/skiller/boost.py
packages/skiller/lib/skiller/brain_sync.py
packages/skiller/lib/skiller/budget.py
packages/skiller/lib/skiller/common.py
packages/skiller/lib/skiller/config.py
packages/skiller/lib/skiller/connect.py
packages/skiller/lib/skiller/doctor.py
packages/skiller/lib/skiller/hub.py
packages/skiller/lib/skiller/integrate.py
packages/skiller/lib/skiller/lock.py
packages/skiller/lib/skiller/quality/analyze.py
packages/skiller/lib/skiller/quality/eval.py
packages/skiller/lib/skiller/registry.py
packages/skiller/lib/skiller/skillset.py
packages/skiller/lib/skiller/state.py
packages/skiller/lib/skiller/status.py
packages/skiller/lib/skiller/update.py
packages/skiller/lib/skiller/vendor.py
```

### task

Provider-name matches are classified seams, not defects.

```text
```

### harness

Provider-name matches are classified seams, not defects.

```text
packages/harness/lib/harness/__init__.py
packages/harness/lib/harness/agentpacks.py
packages/harness/lib/harness/common.py
packages/harness/lib/harness/doctor.py
packages/harness/lib/harness/hooks.py
packages/harness/lib/harness/mcp.py
packages/harness/lib/harness/permissions.py
packages/harness/lib/harness/router.py
packages/harness/lib/harness/safedirs.py
packages/harness/lib/harness/settings.py
packages/harness/lib/harness/settings_audit.py
packages/harness/lib/harness/wf_status.py
```

### maind

Provider-name matches are classified seams, not defects.

```text
packages/maind/lib/maind/analysis/analyze.py
packages/maind/lib/maind/analysis/audit.py
packages/maind/lib/maind/constants.py
packages/maind/lib/maind/doctor.py
packages/maind/lib/maind/health.py
packages/maind/lib/maind/mcp.py
packages/maind/lib/maind/mcpconfig.py
packages/maind/lib/maind/pplxweb.py
packages/maind/lib/maind/probe.py
packages/maind/lib/maind/provision/deploy.py
packages/maind/lib/maind/provision/onboard.py
packages/maind/lib/maind/provision/orchestrate.py
packages/maind/lib/maind/provision/skilldoc.py
packages/maind/lib/maind/provision/start.py
packages/maind/lib/maind/provision/sync.py
packages/maind/lib/maind/provision/workspace.py
```

### analyst

Provider-name matches are classified seams, not defects.

```text
packages/analyst/lib/analyst/__init__.py
packages/analyst/lib/analyst/common.py
packages/analyst/lib/analyst/digest.py
packages/analyst/lib/analyst/ingest.py
packages/analyst/lib/analyst/lessons.py
packages/analyst/lib/analyst/proposals.py
packages/analyst/lib/analyst/scan.py
packages/analyst/lib/analyst/sessions.py
packages/analyst/lib/analyst/suggest.py
packages/analyst/lib/analyst/token_report.py
```

### core

Provider-name matches are classified seams, not defects.

```text
core/block.py
core/pathology.py
core/runs.py
core/usage.py
```

## Classification

### canonical

```text
packages/skiller/skills/ai/ai-agents/SKILL.md
packages/skiller/skills/ai/mcp-builder/SKILL.md
packages/skiller/skills/ai/performance/SKILL.md
packages/skiller/skills/architect/agent-design/SKILL.md
packages/skiller/skills/architect/api-design/SKILL.md
packages/skiller/skills/architect/architecture/SKILL.md
packages/skiller/skills/architect/codebase-design/SKILL.md
packages/skiller/skills/architect/data-schema/SKILL.md
packages/skiller/skills/architect/domain-modeling/SKILL.md
packages/skiller/skills/architect/ecosystem-reuse-gate/SKILL.md
packages/skiller/skills/architect/engineering/SKILL.md
packages/skiller/skills/architect/eval-design/SKILL.md
packages/skiller/skills/architect/figma-mcp-core/SKILL.md
packages/skiller/skills/architect/legal-compliance/SKILL.md
packages/skiller/skills/architect/observability-design/SKILL.md
packages/skiller/skills/architect/package-contribution-protocol/SKILL.md
packages/skiller/skills/architect/security-design/SKILL.md
packages/skiller/skills/architect/tech-stack-selection/SKILL.md
packages/skiller/skills/axioma/axioma-doctrine/SKILL.md
packages/skiller/skills/axioma/axioma-glossary/SKILL.md
packages/skiller/skills/axioma/axioma-stack/SKILL.md
packages/skiller/skills/axioma/ecosystem-map/SKILL.md
packages/skiller/skills/azguard/azguard/SKILL.md
packages/skiller/skills/blender-modeling/build-loop/SKILL.md
packages/skiller/skills/blender-modeling/config-conventions/SKILL.md
packages/skiller/skills/blender-modeling/model-rules/SKILL.md
packages/skiller/skills/blender-modeling/parametric-config/SKILL.md
packages/skiller/skills/blender-modeling/scene-conventions/SKILL.md
packages/skiller/skills/blender-modeling/threading/SKILL.md
packages/skiller/skills/blender/mcp-blender/SKILL.md
packages/skiller/skills/blender/version-gotchas/SKILL.md
packages/skiller/skills/botkit/botkit/SKILL.md
packages/skiller/skills/creative/content-creative/SKILL.md
packages/skiller/skills/devops/ci-cd/SKILL.md
packages/skiller/skills/devops/db-test-preflight/SKILL.md
packages/skiller/skills/devops/docker-dev-prod/SKILL.md
packages/skiller/skills/devops/docker-php/SKILL.md
packages/skiller/skills/devops/docker-postgres/SKILL.md
packages/skiller/skills/devops/docker-services/SKILL.md
packages/skiller/skills/devops/docker-vite/SKILL.md
packages/skiller/skills/devops/docker/SKILL.md
packages/skiller/skills/devops/gitops/SKILL.md
packages/skiller/skills/devops/makefile/SKILL.md
packages/skiller/skills/devops/node-pnpm-preflight/SKILL.md
packages/skiller/skills/finance/finance/SKILL.md
packages/skiller/skills/founder/adversarial-check/SKILL.md
packages/skiller/skills/founder/competitive-analysis/SKILL.md
packages/skiller/skills/founder/customer-discovery/SKILL.md
packages/skiller/skills/founder/defensibility/SKILL.md
packages/skiller/skills/founder/idea-audit/SKILL.md
packages/skiller/skills/founder/idea-discovery/SKILL.md
packages/skiller/skills/founder/new-project/SKILL.md
packages/skiller/skills/founder/pitch-deck/SKILL.md
packages/skiller/skills/founder/risk-assessment/SKILL.md
packages/skiller/skills/founder/startup-lifecycle/SKILL.md
packages/skiller/skills/frontend-animations/motion/SKILL.md
packages/skiller/skills/frontend-backend/backend-type-sync/SKILL.md
packages/skiller/skills/frontend-backend/inertia-vue/SKILL.md
packages/skiller/skills/frontend-backend/laravel-echo-client/SKILL.md
packages/skiller/skills/frontend-figma/figma-to-vue/SKILL.md
packages/skiller/skills/frontend-linting/antfu/SKILL.md
packages/skiller/skills/frontend-linting/eslint-flat-config/SKILL.md
packages/skiller/skills/frontend-linting/js-code-style/SKILL.md
packages/skiller/skills/frontend-linting/ts-library/SKILL.md
packages/skiller/skills/frontend-naive-ui/naive-ui-theming/SKILL.md
packages/skiller/skills/frontend-nuxt/nuxt-modules/SKILL.md
packages/skiller/skills/frontend-nuxt/nuxt-seo/SKILL.md
packages/skiller/skills/frontend-nuxt/nuxt/SKILL.md
packages/skiller/skills/frontend-reka/reka-ui-cva/SKILL.md
packages/skiller/skills/frontend-tailwind/dark-mode/SKILL.md
packages/skiller/skills/frontend-tailwind/tailwind-conventions/SKILL.md
packages/skiller/skills/frontend-vite/vite-module-loader/SKILL.md
packages/skiller/skills/frontend-vite/vite-multi-build/SKILL.md
packages/skiller/skills/frontend-vite/vite/SKILL.md
packages/skiller/skills/frontend-vite/vitepress/SKILL.md
packages/skiller/skills/frontend-vue/pinia-stores/SKILL.md
packages/skiller/skills/frontend-vue/pinia/SKILL.md
packages/skiller/skills/frontend-vue/vitest-vue/SKILL.md
packages/skiller/skills/frontend-vue/vitest/SKILL.md
packages/skiller/skills/frontend-vue/vue-best-practices/SKILL.md
packages/skiller/skills/frontend-vue/vue-composition-api/SKILL.md
packages/skiller/skills/frontend-vue/vue-dynamic-icons/SKILL.md
packages/skiller/skills/frontend-vue/vue-router-best-practices/SKILL.md
packages/skiller/skills/frontend-vue/vue-testing-best-practices/SKILL.md
packages/skiller/skills/frontend-vue/vue/SKILL.md
packages/skiller/skills/frontend-vue/vueuse-functions/SKILL.md
packages/skiller/skills/frontend-wayfinder/wayfinder/SKILL.md
packages/skiller/skills/frontend/document-writer/SKILL.md
packages/skiller/skills/frontend/filepond-upload/SKILL.md
packages/skiller/skills/frontend/web-design-guidelines/SKILL.md
packages/skiller/skills/general/anti-drift/SKILL.md
packages/skiller/skills/general/compact-responses/SKILL.md
packages/skiller/skills/general/complex-task-orchestrator/SKILL.md
packages/skiller/skills/general/context-economy/SKILL.md
packages/skiller/skills/general/cross-layer-change-checklist/SKILL.md
packages/skiller/skills/general/git-commit-rules/SKILL.md
packages/skiller/skills/general/git-safety/SKILL.md
packages/skiller/skills/general/grill-with-docs/SKILL.md
packages/skiller/skills/general/implement/SKILL.md
packages/skiller/skills/general/mcp-advisor/SKILL.md
packages/skiller/skills/general/naming-conventions/SKILL.md
packages/skiller/skills/general/packages-stack/SKILL.md
packages/skiller/skills/general/plan-protocol/SKILL.md
packages/skiller/skills/general/project-map/SKILL.md
packages/skiller/skills/general/session-handoff/SKILL.md
packages/skiller/skills/general/shell/SKILL.md
packages/skiller/skills/general/skills-ssot/SKILL.md
packages/skiller/skills/general/spec-interview/SKILL.md
packages/skiller/skills/general/task-brief-template/SKILL.md
packages/skiller/skills/general/verify-claims/SKILL.md
packages/skiller/skills/general/workflow-craft/SKILL.md
packages/skiller/skills/general/writing-style/SKILL.md
packages/skiller/skills/laravel-architecture/config-driven-abstraction/SKILL.md
packages/skiller/skills/laravel-architecture/eloquent-accessors/SKILL.md
packages/skiller/skills/laravel-architecture/enum-attributes/SKILL.md
packages/skiller/skills/laravel-architecture/enum-state-machine/SKILL.md
packages/skiller/skills/laravel-architecture/laravel-subagents/SKILL.md
packages/skiller/skills/laravel-architecture/modular-architecture/SKILL.md
packages/skiller/skills/laravel-auth/attribute-authorization/SKILL.md
packages/skiller/skills/laravel-auth/laravel-permissions/SKILL.md
packages/skiller/skills/laravel-auth/laravel-security-audit/SKILL.md
packages/skiller/skills/laravel-data-layer/laravel-broadcasting/SKILL.md
packages/skiller/skills/laravel-data-layer/laravel-data/SKILL.md
packages/skiller/skills/laravel-extras/medialibrary/SKILL.md
packages/skiller/skills/laravel-extras/pennant-development/SKILL.md
packages/skiller/skills/laravel-extras/spatie-settings/SKILL.md
packages/skiller/skills/laravel-filament/filament/SKILL.md
packages/skiller/skills/laravel-livewire/livewire-blade-attributes/SKILL.md
packages/skiller/skills/laravel-testing/health-checks/SKILL.md
packages/skiller/skills/laravel-testing/laravel-dusk/SKILL.md
packages/skiller/skills/laravel-testing/laravel-testing/SKILL.md
packages/skiller/skills/laravel-testing/test-isolation-guard/SKILL.md
packages/skiller/skills/legal/legal/SKILL.md
packages/skiller/skills/marketing/marketing/SKILL.md
packages/skiller/skills/mobile/figma-to-flutter/SKILL.md
packages/skiller/skills/operator/capacity-planning/SKILL.md
packages/skiller/skills/operator/incident-response/SKILL.md
packages/skiller/skills/operator/oncall-rotation/SKILL.md
packages/skiller/skills/operator/operations-cx/SKILL.md
packages/skiller/skills/operator/postmortem/SKILL.md
packages/skiller/skills/operator/runbook/SKILL.md
packages/skiller/skills/oss-dev/dependency-audit/SKILL.md
packages/skiller/skills/oss-dev/dx-design/SKILL.md
packages/skiller/skills/oss-dev/gh-review/SKILL.md
packages/skiller/skills/oss-dev/github-flow/SKILL.md
packages/skiller/skills/oss-dev/issue-triage/SKILL.md
packages/skiller/skills/oss-dev/oss-development/SKILL.md
packages/skiller/skills/oss-dev/oss-governance/SKILL.md
packages/skiller/skills/oss-dev/release-engineering/SKILL.md
packages/skiller/skills/oss-dev/resolving-merge-conflicts/SKILL.md
packages/skiller/skills/oss-dev/to-issues/SKILL.md
packages/skiller/skills/php-packages/laravel-package-compatibility/SKILL.md
packages/skiller/skills/php-packages/laravel-package-docs/SKILL.md
packages/skiller/skills/php-packages/laravel-package-expressive/SKILL.md
packages/skiller/skills/php-packages/laravel-package-generate-skill/SKILL.md
packages/skiller/skills/php-packages/laravel-package-release/SKILL.md
packages/skiller/skills/php-packages/laravel-package-scaffold/SKILL.md
packages/skiller/skills/php-packages/laravel-package-service-provider/SKILL.md
packages/skiller/skills/php-packages/laravel-package-testing/SKILL.md
packages/skiller/skills/php-packages/laravel-packages/SKILL.md
packages/skiller/skills/php/code-style-spatie/SKILL.md
packages/skiller/skills/php/cursor-pagination-design/SKILL.md
packages/skiller/skills/php/database/SKILL.md
packages/skiller/skills/php/dependency-injection/SKILL.md
packages/skiller/skills/php/laravel-best-practices/SKILL.md
packages/skiller/skills/php/laravel-structure/SKILL.md
packages/skiller/skills/php/laravel/SKILL.md
packages/skiller/skills/php/named-arguments/SKILL.md
packages/skiller/skills/php/namespace-refactor-safety/SKILL.md
packages/skiller/skills/php/naming-conventions/SKILL.md
packages/skiller/skills/php/pao/SKILL.md
packages/skiller/skills/php/php-patterns/SKILL.md
packages/skiller/skills/php/php-upgrade-checklist/SKILL.md
packages/skiller/skills/php/production-readiness-checklist/SKILL.md
packages/skiller/skills/php/repositories/SKILL.md
packages/skiller/skills/php/static-analysis/SKILL.md
packages/skiller/skills/php/transactional-outbox-relay/SKILL.md
packages/skiller/skills/pm/brd/SKILL.md
packages/skiller/skills/pm/business-process/SKILL.md
packages/skiller/skills/pm/go-to-market/SKILL.md
packages/skiller/skills/pm/monetization-design/SKILL.md
packages/skiller/skills/pm/pmf-diagnostics/SKILL.md
packages/skiller/skills/pm/prd-from-brd/SKILL.md
packages/skiller/skills/pm/product-roadmap/SKILL.md
packages/skiller/skills/pm/product/SKILL.md
packages/skiller/skills/pm/requirement-critic/SKILL.md
packages/skiller/skills/pm/unit-economics/SKILL.md
packages/skiller/skills/python/ml-project-structure/SKILL.md
packages/skiller/skills/python/venv-dependencies/SKILL.md
packages/skiller/skills/quality/artifact-review/SKILL.md
packages/skiller/skills/quality/code-review/SKILL.md
packages/skiller/skills/quality/code-simplifier/SKILL.md
packages/skiller/skills/quality/diagnosing-bugs/SKILL.md
packages/skiller/skills/quality/mutation-testing/SKILL.md
packages/skiller/skills/quality/playwright-e2e/SKILL.md
packages/skiller/skills/quality/refactoring-plan/SKILL.md
packages/skiller/skills/quality/tdd-discipline/SKILL.md
packages/skiller/skills/quality/tech-debt-audit/SKILL.md
packages/skiller/skills/quality/test-strategy/SKILL.md
packages/skiller/skills/quality/testing-safety-report/SKILL.md
packages/skiller/skills/research/query-craft/SKILL.md
packages/skiller/skills/research/research/SKILL.md
packages/skiller/skills/roles/open-source-maintainer/SKILL.md
packages/skiller/skills/roles/solo-founder/SKILL.md
packages/skiller/skills/roles/startup-cto/SKILL.md
packages/skiller/skills/roles/tech-lead/SKILL.md
packages/skiller/skills/sales/sales/SKILL.md
packages/skiller/skills/security/security/SKILL.md
packages/skiller/skills/system/agent-packs/SKILL.md
packages/skiller/skills/system/brain-locator/SKILL.md
packages/skiller/skills/system/cross-project-coordinator/SKILL.md
packages/skiller/skills/system/local-topology/SKILL.md
packages/skiller/skills/system/session-observer/SKILL.md
packages/skiller/skills/system/shared-memory/SKILL.md
packages/skiller/skills/system/swissknifeman-locator/SKILL.md
packages/skiller/skills/voice-ai/voice-ai/SKILL.md
packages/task/commands/design.md
packages/task/commands/dev.md
packages/task/commands/fix.md
packages/task/commands/make-workflow.md
packages/task/commands/plan-audit.md
packages/task/commands/plan-close.md
packages/task/commands/plan-design.md
packages/task/commands/plan-exec.md
packages/task/commands/plan-run.md
packages/task/commands/research.md
packages/task/commands/review.md
```

### provider-adapter

```text
packages/analyst/.claude-plugin/plugin.json
packages/harness/.claude-plugin/plugin.json
packages/harness/configs/claude-code/agent-packs/_common/pack.json
packages/harness/configs/claude-code/agent-packs/backend-laravel/pack.json
packages/harness/configs/claude-code/agent-packs/backend-laravel/settings/settings.fragment.json
packages/harness/configs/claude-code/agent-packs/dart-flutter/pack.json
packages/harness/configs/claude-code/agent-packs/dart-flutter/settings/settings.fragment.json
packages/harness/configs/claude-code/agent-packs/laravel-package/pack.json
packages/harness/configs/claude-code/agent-packs/node-frontend/pack.json
packages/harness/configs/claude-code/agent-packs/node-frontend/settings/settings.fragment.json
packages/harness/configs/claude-code/agent-packs/python-backend/pack.json
packages/harness/configs/claude-code/agent-packs/python-backend/settings/settings.fragment.json
packages/harness/configs/claude-code/agent-packs/role-cto/pack.json
packages/harness/configs/claude-code/agent-packs/role-founder/pack.json
packages/harness/configs/claude-code/agent-packs/role-maintainer/pack.json
packages/harness/configs/claude-code/agent-packs/role-tech-lead/pack.json
packages/harness/configs/claude-code/hooks/agent-router/config.json
packages/harness/configs/claude-code/hooks/auto-approve/config.json
packages/harness/configs/claude-code/hooks/memory/config.json
packages/harness/configs/claude-code/hooks/review-gate/config.json
packages/harness/configs/claude-code/mcp/context7.json
packages/harness/configs/claude-code/mcp/fetch.json
packages/harness/configs/claude-code/mcp/filesystem.json
packages/harness/configs/claude-code/mcp/github.json
packages/harness/configs/claude-code/mcp/memory.json
packages/harness/configs/claude-code/mcp/perplexity.json
packages/harness/configs/claude-code/mcp/playwright.json
packages/harness/configs/claude-code/mcp/sequential-thinking.json
packages/harness/configs/claude-code/policy/base.json
packages/harness/configs/claude-code/policy/max-permissive.json
packages/harness/configs/claude-code/settings-keys.json
packages/harness/configs/claude-code/settings.agent-teams.json
packages/harness/configs/claude-code/settings.base.json
packages/harness/configs/claude-code/settings.docker.json
packages/harness/configs/claude-code/settings.global.json
packages/harness/configs/claude-code/settings.laravel.json
packages/harness/configs/claude-code/settings.node.json
packages/harness/configs/claude-code/settings.observer.json
packages/harness/configs/claude-code/settings.php-package.json
packages/harness/configs/claude-code/settings.product-boundary.json
packages/harness/configs/claude-code/settings.python.json
packages/harness/configs/claude-code/settings.yolo.json
packages/maind/.claude-plugin/plugin.json
packages/task/.claude-plugin/plugin.json
```

### generated

```text
.claude-plugin/marketplace.json
packages/skiller/skills/ai/.claude-plugin/plugin.json
packages/skiller/skills/architect/.claude-plugin/plugin.json
packages/skiller/skills/axioma/.claude-plugin/plugin.json
packages/skiller/skills/azguard/.claude-plugin/plugin.json
packages/skiller/skills/blender-modeling/.claude-plugin/plugin.json
packages/skiller/skills/blender/.claude-plugin/plugin.json
packages/skiller/skills/botkit/.claude-plugin/plugin.json
packages/skiller/skills/creative/.claude-plugin/plugin.json
packages/skiller/skills/devops/.claude-plugin/plugin.json
packages/skiller/skills/finance/.claude-plugin/plugin.json
packages/skiller/skills/founder/.claude-plugin/plugin.json
packages/skiller/skills/frontend-animations/.claude-plugin/plugin.json
packages/skiller/skills/frontend-backend/.claude-plugin/plugin.json
packages/skiller/skills/frontend-figma/.claude-plugin/plugin.json
packages/skiller/skills/frontend-linting/.claude-plugin/plugin.json
packages/skiller/skills/frontend-naive-ui/.claude-plugin/plugin.json
packages/skiller/skills/frontend-nuxt/.claude-plugin/plugin.json
packages/skiller/skills/frontend-reka/.claude-plugin/plugin.json
packages/skiller/skills/frontend-tailwind/.claude-plugin/plugin.json
packages/skiller/skills/frontend-vite/.claude-plugin/plugin.json
packages/skiller/skills/frontend-vue/.claude-plugin/plugin.json
packages/skiller/skills/frontend-wayfinder/.claude-plugin/plugin.json
packages/skiller/skills/frontend/.claude-plugin/plugin.json
packages/skiller/skills/general/.claude-plugin/plugin.json
packages/skiller/skills/laravel-architecture/.claude-plugin/plugin.json
packages/skiller/skills/laravel-auth/.claude-plugin/plugin.json
packages/skiller/skills/laravel-data-layer/.claude-plugin/plugin.json
packages/skiller/skills/laravel-extras/.claude-plugin/plugin.json
packages/skiller/skills/laravel-filament/.claude-plugin/plugin.json
packages/skiller/skills/laravel-livewire/.claude-plugin/plugin.json
packages/skiller/skills/laravel-testing/.claude-plugin/plugin.json
packages/skiller/skills/legal/.claude-plugin/plugin.json
packages/skiller/skills/marketing/.claude-plugin/plugin.json
packages/skiller/skills/mobile/.claude-plugin/plugin.json
packages/skiller/skills/operator/.claude-plugin/plugin.json
packages/skiller/skills/oss-dev/.claude-plugin/plugin.json
packages/skiller/skills/php-packages/.claude-plugin/plugin.json
packages/skiller/skills/php/.claude-plugin/plugin.json
packages/skiller/skills/pm/.claude-plugin/plugin.json
packages/skiller/skills/python/.claude-plugin/plugin.json
packages/skiller/skills/quality/.claude-plugin/plugin.json
packages/skiller/skills/research/.claude-plugin/plugin.json
packages/skiller/skills/roles/.claude-plugin/plugin.json
packages/skiller/skills/sales/.claude-plugin/plugin.json
packages/skiller/skills/security/.claude-plugin/plugin.json
packages/skiller/skills/system/.claude-plugin/plugin.json
packages/skiller/skills/voice-ai/.claude-plugin/plugin.json
```

### bootstrap-only

```text
.mcp.json.example
AGENTS.md
.agents/skills/anti-drift/SKILL.md
.agents/skills/anti-drift/agents/openai.yaml
.agents/skills/architecture/SKILL.md
.agents/skills/architecture/agents/openai.yaml
.agents/skills/codebase-design/SKILL.md
.agents/skills/codebase-design/agents/openai.yaml
.agents/skills/context-economy/SKILL.md
.agents/skills/context-economy/agents/openai.yaml
.agents/skills/domain-modeling/SKILL.md
.agents/skills/domain-modeling/agents/openai.yaml
.agents/skills/package-contribution-protocol/SKILL.md
.agents/skills/package-contribution-protocol/agents/openai.yaml
.agents/skills/plan-protocol/SKILL.md
.agents/skills/plan-protocol/agents/openai.yaml
.agents/skills/query-craft/SKILL.md
.agents/skills/query-craft/agents/openai.yaml
.agents/skills/session-handoff/SKILL.md
.agents/skills/session-handoff/agents/openai.yaml
.agents/skills/task-design/SKILL.md
.agents/skills/task-design/agents/openai.yaml
.agents/skills/task-plan-audit/SKILL.md
.agents/skills/task-plan-audit/agents/openai.yaml
.agents/skills/task-plan-close/SKILL.md
.agents/skills/task-plan-close/agents/openai.yaml
.agents/skills/task-plan-design/SKILL.md
.agents/skills/task-plan-design/agents/openai.yaml
.agents/skills/task-plan-exec/SKILL.md
.agents/skills/task-plan-exec/agents/openai.yaml
.agents/skills/task-plan-run/SKILL.md
.agents/skills/task-plan-run/agents/openai.yaml
.agents/skills/verify-claims/SKILL.md
.agents/skills/verify-claims/agents/openai.yaml
.agents/skills/workflow-craft/SKILL.md
.agents/skills/workflow-craft/agents/openai.yaml
.serena/.gitignore
.serena/cache/python/document_symbols.pkl
.serena/cache/python/raw_document_symbols.pkl
.serena/project.yml
```

## Bootstrap-only state

`AGENTS.md`, `.agents/`, `.serena/`, and `.mcp.json.example` are recorded as bootstrap-only. This inventory neither changes nor treats them as the distribution canon.

## Reproduction

```bash
python3 plans/2026.07.19-DUAL-PROVIDER/artifacts/p0-provider-inventory.py --write
python3 plans/2026.07.19-DUAL-PROVIDER/artifacts/p0-provider-inventory.py --check
```

The helper scans only the explicit roots encoded in this file, sorts every path set, and is read-only except for its plan finding in `--write` mode.
