# Граф зависимостей скиллов

> Сгенерировано `skiller registry` (registry.render_graph) из `skills.json` — не редактировать вручную.
> Пересборка: `skiller registry`.

Сплошная стрелка `A --> B` — `A` требует `B` (`requires`): `skiller vendor` дотянет `B`
при установке `A`. Пунктирная `A -.-> B` — результат `A` служит входом для `B`
(`produces_for`). Показаны только скиллы, участвующие в графе; изолированные —
в таблице ниже.

```mermaid
flowchart LR
  subgraph architect["architect"]
    agent_design["agent-design"]
    api_design["api-design"]
    architecture["architecture"]
    codebase_design["codebase-design"]
    data_schema["data-schema"]
    domain_modeling["domain-modeling"]
    ecosystem_reuse_gate["ecosystem-reuse-gate"]
    eval_design["eval-design"]
    figma_mcp_core["figma-mcp-core"]
    legal_compliance["legal-compliance"]
    observability_design["observability-design"]
    package_contribution_protocol["package-contribution-protocol"]
    security_design["security-design"]
    tech_stack_selection["tech-stack-selection"]
  end
  subgraph axioma["axioma"]
    axioma_stack["axioma-stack"]
  end
  subgraph blender["blender"]
    mcp_blender["mcp-blender"]
    version_gotchas["version-gotchas"]
  end
  subgraph blender_modeling["blender-modeling"]
    build_loop["build-loop"]
    config_conventions["config-conventions"]
    model_rules["model-rules"]
    parametric_config["parametric-config"]
    scene_conventions["scene-conventions"]
    threading["threading"]
  end
  subgraph botkit["botkit"]
    botkit["botkit"]
  end
  subgraph devops["devops"]
    ci_cd["ci-cd"]
    db_test_preflight["db-test-preflight"]
    docker_dev_prod["docker-dev-prod"]
    docker_php["docker-php"]
    docker_postgres["docker-postgres"]
    docker_services["docker-services"]
    docker_vite["docker-vite"]
    gitops["gitops"]
    makefile["makefile"]
    node_pnpm_preflight["node-pnpm-preflight"]
  end
  subgraph founder["founder"]
    adversarial_check["adversarial-check"]
    competitive_analysis["competitive-analysis"]
    customer_discovery["customer-discovery"]
    defensibility["defensibility"]
    idea_audit["idea-audit"]
    idea_discovery["idea-discovery"]
    new_project["new-project"]
    pitch_deck["pitch-deck"]
    risk_assessment["risk-assessment"]
    startup_lifecycle["startup-lifecycle"]
  end
  subgraph frontend_backend["frontend-backend"]
    backend_type_sync["backend-type-sync"]
    inertia_vue["inertia-vue"]
  end
  subgraph frontend_figma["frontend-figma"]
    figma_to_vue["figma-to-vue"]
  end
  subgraph frontend_naive_ui["frontend-naive-ui"]
    naive_ui_theming["naive-ui-theming"]
  end
  subgraph frontend_reka["frontend-reka"]
    reka_ui_cva["reka-ui-cva"]
  end
  subgraph frontend_tailwind["frontend-tailwind"]
    dark_mode["dark-mode"]
    tailwind_conventions["tailwind-conventions"]
  end
  subgraph frontend_vite["frontend-vite"]
    vite_module_loader["vite-module-loader"]
    vite_multi_build["vite-multi-build"]
  end
  subgraph frontend_vue["frontend-vue"]
    vitest["vitest"]
    vue["vue"]
    vue_testing_best_practices["vue-testing-best-practices"]
  end
  subgraph frontend_wayfinder["frontend-wayfinder"]
    wayfinder["wayfinder"]
  end
  subgraph general["general"]
    anti_drift["anti-drift"]
    complex_task_orchestrator["complex-task-orchestrator"]
    context_economy["context-economy"]
    cross_layer_change_checklist["cross-layer-change-checklist"]
    git_commit_rules["git-commit-rules"]
    grill_with_docs["grill-with-docs"]
    implement["implement"]
    mcp_advisor["mcp-advisor"]
    plan_protocol["plan-protocol"]
    project_map["project-map"]
    session_handoff["session-handoff"]
    spec_interview["spec-interview"]
    task_brief_template["task-brief-template"]
    verify_claims["verify-claims"]
  end
  subgraph laravel_architecture["laravel-architecture"]
    modular_architecture["modular-architecture"]
  end
  subgraph laravel_auth["laravel-auth"]
    attribute_authorization["attribute-authorization"]
    laravel_permissions["laravel-permissions"]
    laravel_security_audit["laravel-security-audit"]
  end
  subgraph laravel_data_layer["laravel-data-layer"]
    laravel_data["laravel-data"]
  end
  subgraph laravel_filament["laravel-filament"]
    filament["filament"]
  end
  subgraph laravel_testing["laravel-testing"]
    laravel_testing["laravel-testing"]
    test_isolation_guard["test-isolation-guard"]
  end
  subgraph mobile["mobile"]
    figma_to_flutter["figma-to-flutter"]
  end
  subgraph operator["operator"]
    capacity_planning["capacity-planning"]
    incident_response["incident-response"]
    oncall_rotation["oncall-rotation"]
    postmortem["postmortem"]
    runbook["runbook"]
  end
  subgraph oss_dev["oss-dev"]
    dependency_audit["dependency-audit"]
    dx_design["dx-design"]
    gh_review["gh-review"]
    github_flow["github-flow"]
    issue_triage["issue-triage"]
    oss_development["oss-development"]
    oss_governance["oss-governance"]
    release_engineering["release-engineering"]
    resolving_merge_conflicts["resolving-merge-conflicts"]
    to_issues["to-issues"]
  end
  subgraph php["php"]
    database["database"]
    dependency_injection["dependency-injection"]
    laravel["laravel"]
    laravel_structure["laravel-structure"]
    repositories["repositories"]
    static_analysis["static-analysis"]
  end
  subgraph pm["pm"]
    brd["brd"]
    business_process["business-process"]
    go_to_market["go-to-market"]
    monetization_design["monetization-design"]
    pmf_diagnostics["pmf-diagnostics"]
    prd_from_brd["prd-from-brd"]
    product_roadmap["product-roadmap"]
    requirement_critic["requirement-critic"]
    unit_economics["unit-economics"]
  end
  subgraph python["python"]
    ml_project_structure["ml-project-structure"]
    venv_dependencies["venv-dependencies"]
  end
  subgraph quality["quality"]
    code_review["code-review"]
    code_simplifier["code-simplifier"]
    diagnosing_bugs["diagnosing-bugs"]
    mutation_testing["mutation-testing"]
    playwright_e2e["playwright-e2e"]
    refactoring_plan["refactoring-plan"]
    tdd_discipline["tdd-discipline"]
    tech_debt_audit["tech-debt-audit"]
    test_strategy["test-strategy"]
    testing_safety_report["testing-safety-report"]
  end
  subgraph research["research"]
    query_craft["query-craft"]
  end
  subgraph system["system"]
    brain_locator["brain-locator"]
    cross_project_coordinator["cross-project-coordinator"]
    local_topology["local-topology"]
    session_observer["session-observer"]
    shared_memory["shared-memory"]
    swissknifeman_locator["swissknifeman-locator"]
  end
  agent_design -->|requires| architecture
  api_design -->|requires| data_schema
  architecture -->|requires| brd
  architecture -->|requires| tech_stack_selection
  attribute_authorization -->|requires| laravel_permissions
  axioma_stack -->|requires| ecosystem_reuse_gate
  backend_type_sync -->|requires| wayfinder
  botkit -->|requires| laravel
  brain_locator -->|requires| local_topology
  brd -->|requires| business_process
  build_loop -->|requires| config_conventions
  build_loop -->|requires| mcp_blender
  build_loop -->|requires| model_rules
  build_loop -->|requires| parametric_config
  build_loop -->|requires| scene_conventions
  build_loop -->|requires| threading
  capacity_planning -->|requires| observability_design
  competitive_analysis -->|requires| idea_discovery
  cross_project_coordinator -->|requires| local_topology
  customer_discovery -->|requires| idea_discovery
  dark_mode -->|requires| tailwind_conventions
  data_schema -->|requires| brd
  database -->|requires| laravel
  db_test_preflight -->|requires| docker_postgres
  dependency_audit -->|requires| oss_development
  docker_dev_prod -->|requires| docker_php
  docker_services -->|requires| docker_php
  docker_services -->|requires| docker_postgres
  dx_design -->|requires| oss_development
  eval_design -->|requires| agent_design
  figma_to_flutter -->|requires| figma_mcp_core
  figma_to_vue -->|requires| figma_mcp_core
  filament -->|requires| laravel
  filament -->|requires| laravel_structure
  gh_review -->|requires| context_economy
  git_commit_rules -->|requires| node_pnpm_preflight
  github_flow -->|requires| gh_review
  github_flow -->|requires| git_commit_rules
  github_flow -->|requires| release_engineering
  go_to_market -->|requires| competitive_analysis
  go_to_market -->|requires| monetization_design
  grill_with_docs -->|requires| domain_modeling
  grill_with_docs -->|requires| spec_interview
  idea_audit -->|requires| idea_discovery
  implement -->|requires| code_review
  implement -->|requires| tdd_discipline
  issue_triage -->|requires| github_flow
  laravel_security_audit -->|requires| static_analysis
  legal_compliance -->|requires| architecture
  mcp_blender -->|requires| version_gotchas
  modular_architecture -->|requires| laravel
  monetization_design -->|requires| idea_discovery
  mutation_testing -->|requires| test_strategy
  naive_ui_theming -->|requires| tailwind_conventions
  new_project -->|requires| competitive_analysis
  new_project -->|requires| ecosystem_reuse_gate
  new_project -->|requires| idea_discovery
  new_project -->|requires| risk_assessment
  observability_design -->|requires| architecture
  oss_governance -->|requires| oss_development
  package_contribution_protocol -->|requires| anti_drift
  package_contribution_protocol -->|requires| api_design
  package_contribution_protocol -->|requires| architecture
  package_contribution_protocol -->|requires| task_brief_template
  parametric_config -->|requires| model_rules
  parametric_config -->|requires| threading
  parametric_config -->|requires| version_gotchas
  pitch_deck -->|requires| competitive_analysis
  pitch_deck -->|requires| go_to_market
  pitch_deck -->|requires| unit_economics
  pmf_diagnostics -->|requires| product_roadmap
  postmortem -->|requires| incident_response
  prd_from_brd -->|requires| brd
  product_roadmap -->|requires| brd
  product_roadmap -->|requires| go_to_market
  refactoring_plan -->|requires| tech_debt_audit
  reka_ui_cva -->|requires| tailwind_conventions
  release_engineering -->|requires| oss_development
  requirement_critic -->|requires| brd
  resolving_merge_conflicts -->|requires| git_commit_rules
  security_design -->|requires| architecture
  session_observer -->|requires| shared_memory
  shared_memory -->|requires| local_topology
  swissknifeman_locator -->|requires| local_topology
  tech_stack_selection -->|requires| brd
  tech_stack_selection -->|requires| ecosystem_reuse_gate
  test_isolation_guard -->|requires| laravel_testing
  to_issues -->|requires| github_flow
  unit_economics -->|requires| monetization_design
  venv_dependencies -->|requires| ml_project_structure
  vite_multi_build -->|requires| vite_module_loader
  vitest -->|requires| inertia_vue
  vue_testing_best_practices -->|requires| vitest
  vue_testing_best_practices -->|requires| vue
  adversarial_check -.->|feeds| competitive_analysis
  adversarial_check -.->|feeds| idea_discovery
  adversarial_check -.->|feeds| new_project
  adversarial_check -.->|feeds| pmf_diagnostics
  adversarial_check -.->|feeds| risk_assessment
  adversarial_check -.->|feeds| startup_lifecycle
  agent_design -.->|feeds| observability_design
  anti_drift -.->|feeds| session_handoff
  architecture -.->|feeds| api_design
  architecture -.->|feeds| data_schema
  ci_cd -.->|feeds| release_engineering
  code_simplifier -.->|feeds| code_review
  codebase_design -.->|feeds| architecture
  codebase_design -.->|feeds| refactoring_plan
  complex_task_orchestrator -.->|feeds| cross_layer_change_checklist
  config_conventions -.->|feeds| parametric_config
  cross_project_coordinator -.->|feeds| refactoring_plan
  customer_discovery -.->|feeds| competitive_analysis
  customer_discovery -.->|feeds| monetization_design
  customer_discovery -.->|feeds| new_project
  db_test_preflight -.->|feeds| laravel_testing
  db_test_preflight -.->|feeds| test_isolation_guard
  defensibility -.->|feeds| go_to_market
  defensibility -.->|feeds| pitch_deck
  dependency_audit -.->|feeds| release_engineering
  dependency_audit -.->|feeds| security_design
  diagnosing_bugs -.->|feeds| code_review
  docker_dev_prod -.->|feeds| docker_services
  docker_php -.->|feeds| docker_vite
  docker_postgres -.->|feeds| docker_dev_prod
  docker_vite -.->|feeds| docker_dev_prod
  domain_modeling -.->|feeds| api_design
  domain_modeling -.->|feeds| architecture
  domain_modeling -.->|feeds| data_schema
  eval_design -.->|feeds| observability_design
  figma_to_vue -.->|feeds| dark_mode
  figma_to_vue -.->|feeds| naive_ui_theming
  figma_to_vue -.->|feeds| reka_ui_cva
  figma_to_vue -.->|feeds| tailwind_conventions
  gitops -.->|feeds| github_flow
  grill_with_docs -.->|feeds| task_brief_template
  grill_with_docs -.->|feeds| to_issues
  idea_audit -.->|feeds| architecture
  idea_audit -.->|feeds| brd
  idea_audit -.->|feeds| competitive_analysis
  idea_audit -.->|feeds| new_project
  idea_audit -.->|feeds| risk_assessment
  laravel -.->|feeds| dependency_injection
  laravel -.->|feeds| repositories
  laravel_data -.->|feeds| backend_type_sync
  laravel_security_audit -.->|feeds| security_design
  legal_compliance -.->|feeds| security_design
  makefile -.->|feeds| docker_dev_prod
  makefile -.->|feeds| docker_services
  mcp_advisor -.->|feeds| context_economy
  monetization_design -.->|feeds| brd
  mutation_testing -.->|feeds| code_review
  observability_design -.->|feeds| incident_response
  observability_design -.->|feeds| runbook
  oncall_rotation -.->|feeds| incident_response
  oss_governance -.->|feeds| dependency_audit
  plan_protocol -.->|feeds| complex_task_orchestrator
  plan_protocol -.->|feeds| session_handoff
  postmortem -.->|feeds| runbook
  postmortem -.->|feeds| tech_debt_audit
  prd_from_brd -.->|feeds| api_design
  prd_from_brd -.->|feeds| architecture
  prd_from_brd -.->|feeds| product_roadmap
  project_map -.->|feeds| cross_layer_change_checklist
  query_craft -.->|feeds| verify_claims
  refactoring_plan -.->|feeds| testing_safety_report
  risk_assessment -.->|feeds| pitch_deck
  runbook -.->|feeds| incident_response
  spec_interview -.->|feeds| task_brief_template
  startup_lifecycle -.->|feeds| customer_discovery
  startup_lifecycle -.->|feeds| defensibility
  startup_lifecycle -.->|feeds| new_project
  startup_lifecycle -.->|feeds| pmf_diagnostics
  task_brief_template -.->|feeds| complex_task_orchestrator
  tdd_discipline -.->|feeds| code_review
  tech_stack_selection -.->|feeds| oss_development
  tech_stack_selection -.->|feeds| release_engineering
  test_strategy -.->|feeds| code_review
  test_strategy -.->|feeds| playwright_e2e
  to_issues -.->|feeds| implement
  unit_economics -.->|feeds| go_to_market
  verify_claims -.->|feeds| architecture
  verify_claims -.->|feeds| tech_stack_selection
```

**В графе:** 129 скиллов, 94 рёбер requires, 88 рёбер produces_for.

## Изолированные скиллы (83)

Скиллы без связей `requires`/`produces_for` — самодостаточны.

| Бакет | Скиллы |
|---|---|
| ai | `ai-agents`, `token-efficient` |
| architect | `dev-engineering-super-skill` |
| axioma | `axioma-doctrine` |
| azguard | `azguard` |
| creative | `content-creative-super-skill` |
| devops | `docker` |
| finance | `finance-super-skill` |
| frontend | `document-writer`, `filepond-upload`, `web-design-guidelines` |
| frontend-animations | `motion` |
| frontend-backend | `laravel-echo-client` |
| frontend-linting | `antfu`, `eslint-flat-config`, `js-code-style`, `ts-library` |
| frontend-nuxt | `nuxt`, `nuxt-modules`, `nuxt-seo` |
| frontend-vite | `vite`, `vitepress` |
| frontend-vue | `pinia`, `pinia-stores`, `vitest-vue`, `vue-best-practices`, `vue-composition-api`, `vue-dynamic-icons`, `vue-router-best-practices`, `vueuse-functions` |
| general | `compact-responses`, `git-safety`, `naming-conventions`, `packages-stack`, `skills-ssot`, `workflow-craft`, `writing-style` |
| laravel-architecture | `config-driven-abstraction`, `eloquent-accessors`, `enum-attributes`, `enum-state-machine`, `laravel-subagents` |
| laravel-data-layer | `laravel-broadcasting` |
| laravel-extras | `medialibrary`, `pennant-development`, `spatie-settings` |
| laravel-livewire | `livewire-blade-attributes` |
| laravel-testing | `health-checks`, `laravel-dusk` |
| legal | `legal-super-skill` |
| marketing | `marketing-super-skill` |
| operator | `operations-cx-super-skill` |
| php | `code-style-spatie`, `cursor-pagination-design`, `laravel-best-practices`, `named-arguments`, `namespace-refactor-safety`, `pao`, `php-naming-conventions`, `php-patterns`, `php-upgrade-checklist`, `production-readiness-checklist`, `transactional-outbox-relay` |
| php-packages | `laravel-package-compatibility`, `laravel-package-docs`, `laravel-package-expressive`, `laravel-package-generate-skill`, `laravel-package-release`, `laravel-package-scaffold`, `laravel-package-service-provider`, `laravel-package-testing`, `laravel-packages` |
| pm | `pm-super-skill` |
| quality | `artifact-review` |
| research | `research-knowledge-super-skill` |
| roles | `open-source-maintainer`, `solo-founder`, `startup-cto`, `tech-lead` |
| sales | `sales-super-skill` |
| security | `agent-security-super-skill` |
| system | `agent-packs` |
| voice-ai | `voice-ai` |
