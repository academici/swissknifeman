# Token Budget Map

> Generated `lib/skiller/budget.py` (`skiller budget --write-map`) from `skills.json` and tel. `SKILL.md` — cannot be edited manually.
> Reassembly: `skiller registry`.

Three-tier context disclosure model - what loads the neural network and when:

- **⊕ always** — `name`+`description`: are resident in EVERY request (based on them the agent decides whether to use the skill). Permanent «tax».
- **↻ on-trigger** — body `SKILL.md`: is loaded only when the skill is triggered.
- **⌥ on-demand** — snippets and references: via link from the body, optional.

Node color - heat by **⊕ always** (redder = more expensive permanent tax descriptions). Label `name<br/>⊕always ↻body`. Solid arrow `requires` shows a transitive tax: you put a skill - you pull always-price dependencies. Token valuation is rough and language dependent (Cyrillic ~2.9 chars/tok, Latin/code ~3.4) — for comparison of sets, not exact accounting.

```mermaid
flowchart LR
  subgraph ai["ai"]
    ai_agents["ai-agents<br/>⊕88 ↻580"]:::warm
    mcp_builder["mcp-builder<br/>⊕85 ↻2560"]:::warm
    token_efficient["token-efficient<br/>⊕111 ↻1405"]:::hot
  end
  subgraph architect["architect"]
    agent_design["agent-design<br/>⊕29 ↻1078"]:::cool
    api_design["api-design<br/>⊕32 ↻788"]:::cool
    architecture["architecture<br/>⊕33 ↻785"]:::mild
    codebase_design["codebase-design<br/>⊕117 ↻1978"]:::hot
    data_schema["data-schema<br/>⊕34 ↻879"]:::mild
    dev_engineering_super_skill["dev-engineering-super-skill<br/>⊕133 ↻538"]:::hot
    domain_modeling["domain-modeling<br/>⊕128 ↻2158"]:::hot
    ecosystem_reuse_gate["ecosystem-reuse-gate<br/>⊕108 ↻1315"]:::hot
    eval_design["eval-design<br/>⊕35 ↻1534"]:::mild
    figma_mcp_core["figma-mcp-core<br/>⊕106 ↻1602"]:::hot
    legal_compliance["legal-compliance<br/>⊕33 ↻1784"]:::mild
    observability_design["observability-design<br/>⊕43 ↻1279"]:::warm
    package_contribution_protocol["package-contribution-protocol<br/>⊕39 ↻1095"]:::mild
    security_design["security-design<br/>⊕33 ↻1059"]:::mild
    tech_stack_selection["tech-stack-selection<br/>⊕34 ↻1914"]:::mild
  end
  subgraph axioma["axioma"]
    axioma_doctrine["axioma-doctrine<br/>⊕90 ↻1233"]:::warm
    axioma_glossary["axioma-glossary<br/>⊕110 ↻1311"]:::hot
    axioma_stack["axioma-stack<br/>⊕105 ↻1309"]:::hot
    ecosystem_map["ecosystem-map<br/>⊕47 ↻643"]:::warm
  end
  subgraph azguard["azguard"]
    azguard["azguard<br/>⊕37 ↻1647"]:::mild
  end
  subgraph blender["blender"]
    mcp_blender["mcp-blender<br/>⊕118 ↻1475"]:::hot
    version_gotchas["version-gotchas<br/>⊕28 ↻756"]:::cool
  end
  subgraph blender_modeling["blender-modeling"]
    build_loop["build-loop<br/>⊕103 ↻2847"]:::hot
    config_conventions["config-conventions<br/>⊕114 ↻2164"]:::hot
    model_rules["model-rules<br/>⊕36 ↻733"]:::mild
    model_verification["model-verification<br/>⊕90 ↻1503"]:::warm
    parametric_config["parametric-config<br/>⊕111 ↻2275"]:::hot
    scene_conventions["scene-conventions<br/>⊕95 ↻1135"]:::warm
    threading["threading<br/>⊕33 ↻885"]:::mild
  end
  subgraph botkit["botkit"]
    botkit["botkit<br/>⊕35 ↻206"]:::mild
  end
  subgraph creative["creative"]
    content_creative_super_skill["content-creative-super-skill<br/>⊕111 ↻687"]:::hot
  end
  subgraph dart["dart"]
    dart_package_development["dart-package-development<br/>⊕56 ↻801"]:::warm
  end
  subgraph devops["devops"]
    ci_cd["ci-cd<br/>⊕55 ↻1123"]:::warm
    db_test_preflight["db-test-preflight<br/>⊕104 ↻1676"]:::hot
    docker["docker<br/>⊕66 ↻400"]:::warm
    docker_dev_prod["docker-dev-prod<br/>⊕42 ↻924"]:::mild
    docker_php["docker-php<br/>⊕40 ↻767"]:::mild
    docker_postgres["docker-postgres<br/>⊕43 ↻807"]:::warm
    docker_services["docker-services<br/>⊕48 ↻858"]:::warm
    docker_vite["docker-vite<br/>⊕39 ↻679"]:::mild
    gitops["gitops<br/>⊕35 ↻715"]:::mild
    makefile["makefile<br/>⊕43 ↻732"]:::warm
    node_pnpm_preflight["node-pnpm-preflight<br/>⊕38 ↻228"]:::mild
  end
  subgraph finance["finance"]
    finance_super_skill["finance-super-skill<br/>⊕105 ↻740"]:::hot
  end
  subgraph founder["founder"]
    adversarial_check["adversarial-check<br/>⊕55 ↻1134"]:::warm
    competitive_analysis["competitive-analysis<br/>⊕37 ↻1315"]:::mild
    customer_discovery["customer-discovery<br/>⊕55 ↻1280"]:::warm
    defensibility["defensibility<br/>⊕42 ↻1124"]:::mild
    idea_audit["idea-audit<br/>⊕61 ↻2474"]:::warm
    idea_discovery["idea-discovery<br/>⊕35 ↻1630"]:::mild
    new_project["new-project<br/>⊕31 ↻1447"]:::cool
    pitch_deck["pitch-deck<br/>⊕32 ↻1549"]:::cool
    risk_assessment["risk-assessment<br/>⊕40 ↻1275"]:::mild
    startup_lifecycle["startup-lifecycle<br/>⊕42 ↻1748"]:::mild
  end
  subgraph frontend["frontend"]
    document_writer["document-writer<br/>⊕88 ↻1283"]:::warm
    filepond_upload["filepond-upload<br/>⊕114 ↻2215"]:::hot
    web_design_guidelines["web-design-guidelines<br/>⊕61 ↻296"]:::warm
  end
  subgraph frontend_animations["frontend-animations"]
    motion["motion<br/>⊕55 ↻920"]:::warm
  end
  subgraph frontend_backend["frontend-backend"]
    backend_type_sync["backend-type-sync<br/>⊕31 ↻2043"]:::cool
    inertia_vue["inertia-vue<br/>⊕29 ↻1445"]:::cool
    laravel_echo_client["laravel-echo-client<br/>⊕33 ↻1900"]:::mild
  end
  subgraph frontend_figma["frontend-figma"]
    figma_to_vue["figma-to-vue<br/>⊕99 ↻785"]:::hot
  end
  subgraph frontend_linting["frontend-linting"]
    antfu["antfu<br/>⊕74 ↻1282"]:::warm
    eslint_flat_config["eslint-flat-config<br/>⊕112 ↻2383"]:::hot
    js_code_style["js-code-style<br/>⊕47 ↻796"]:::warm
    ts_library["ts-library<br/>⊕90 ↻1357"]:::warm
  end
  subgraph frontend_naive_ui["frontend-naive-ui"]
    naive_ui_theming["naive-ui-theming<br/>⊕30 ↻2014"]:::cool
  end
  subgraph frontend_nuxt["frontend-nuxt"]
    nuxt["nuxt<br/>⊕29 ↻1095"]:::cool
    nuxt_modules["nuxt-modules<br/>⊕31 ↻644"]:::cool
    nuxt_seo["nuxt-seo<br/>⊕28 ↻825"]:::cool
  end
  subgraph frontend_reka["frontend-reka"]
    reka_ui_cva["reka-ui-cva<br/>⊕105 ↻1980"]:::hot
  end
  subgraph frontend_tailwind["frontend-tailwind"]
    dark_mode["dark-mode<br/>⊕29 ↻2182"]:::cool
    tailwind_conventions["tailwind-conventions<br/>⊕34 ↻2221"]:::mild
  end
  subgraph frontend_vite["frontend-vite"]
    vite["vite<br/>⊕57 ↻615"]:::warm
    vite_module_loader["vite-module-loader<br/>⊕35 ↻659"]:::mild
    vite_multi_build["vite-multi-build<br/>⊕47 ↻986"]:::warm
    vitepress["vitepress<br/>⊕49 ↻830"]:::warm
  end
  subgraph frontend_vue["frontend-vue"]
    pinia["pinia<br/>⊕28 ↻691"]:::cool
    pinia_stores["pinia-stores<br/>⊕30 ↻1892"]:::cool
    vitest["vitest<br/>⊕30 ↻789"]:::cool
    vitest_vue["vitest-vue<br/>⊕29 ↻1030"]:::cool
    vue["vue<br/>⊕25 ↻852"]:::cool
    vue_best_practices["vue-best-practices<br/>⊕33 ↻2546"]:::mild
    vue_composition_api["vue-composition-api<br/>⊕33 ↻502"]:::mild
    vue_dynamic_icons["vue-dynamic-icons<br/>⊕32 ↻1275"]:::cool
    vue_router_best_practices["vue-router-best-practices<br/>⊕36 ↻2569"]:::mild
    vue_testing_best_practices["vue-testing-best-practices<br/>⊕34 ↻2215"]:::mild
    vueuse_functions["vueuse-functions<br/>⊕30 ↻400"]:::cool
  end
  subgraph frontend_wayfinder["frontend-wayfinder"]
    wayfinder["wayfinder<br/>⊕31 ↻966"]:::cool
  end
  subgraph general["general"]
    anti_drift["anti-drift<br/>⊕29 ↻1010"]:::cool
    compact_responses["compact-responses<br/>⊕40 ↻227"]:::mild
    complex_task_orchestrator["complex-task-orchestrator<br/>⊕33 ↻630"]:::mild
    context_economy["context-economy<br/>⊕39 ↻490"]:::mild
    cross_layer_change_checklist["cross-layer-change-checklist<br/>⊕32 ↻432"]:::cool
    git_commit_rules["git-commit-rules<br/>⊕30 ↻1077"]:::cool
    git_safety["git-safety<br/>⊕84 ↻570"]:::warm
    grill_with_docs["grill-with-docs<br/>⊕98 ↻858"]:::hot
    implement["implement<br/>⊕83 ↻543"]:::warm
    mcp_advisor["mcp-advisor<br/>⊕107 ↻3188"]:::hot
    naming_conventions["naming-conventions<br/>⊕86 ↻1755"]:::warm
    packages_stack["packages-stack<br/>⊕85 ↻503"]:::warm
    plan_protocol["plan-protocol<br/>⊕26 ↻11132"]:::cool
    project_map["project-map<br/>⊕83 ↻618"]:::warm
    session_handoff["session-handoff<br/>⊕29 ↻590"]:::cool
    shell["shell<br/>⊕73 ↻1989"]:::warm
    skills_ssot["skills-ssot<br/>⊕34 ↻941"]:::mild
    spec_interview["spec-interview<br/>⊕35 ↻725"]:::mild
    task_brief_template["task-brief-template<br/>⊕47 ↻1176"]:::warm
    verify_claims["verify-claims<br/>⊕41 ↻341"]:::mild
    workflow_craft["workflow-craft<br/>⊕48 ↻3538"]:::warm
    writing_style["writing-style<br/>⊕98 ↻1819"]:::hot
  end
  subgraph laravel_architecture["laravel-architecture"]
    config_driven_abstraction["config-driven-abstraction<br/>⊕114 ↻460"]:::hot
    eloquent_accessors["eloquent-accessors<br/>⊕119 ↻1228"]:::hot
    enum_attributes["enum-attributes<br/>⊕99 ↻1950"]:::hot
    enum_state_machine["enum-state-machine<br/>⊕104 ↻1557"]:::hot
    laravel_subagents["laravel-subagents<br/>⊕77 ↻1257"]:::warm
    modular_architecture["modular-architecture<br/>⊕83 ↻3112"]:::warm
  end
  subgraph laravel_auth["laravel-auth"]
    attribute_authorization["attribute-authorization<br/>⊕34 ↻2102"]:::mild
    laravel_permissions["laravel-permissions<br/>⊕30 ↻398"]:::cool
    laravel_security_audit["laravel-security-audit<br/>⊕32 ↻775"]:::cool
  end
  subgraph laravel_data_layer["laravel-data-layer"]
    laravel_broadcasting["laravel-broadcasting<br/>⊕31 ↻1210"]:::cool
    laravel_data["laravel-data<br/>⊕30 ↻2030"]:::cool
  end
  subgraph laravel_extras["laravel-extras"]
    medialibrary["medialibrary<br/>⊕35 ↻1020"]:::mild
    pennant_development["pennant-development<br/>⊕58 ↻462"]:::warm
    spatie_settings["spatie-settings<br/>⊕109 ↻2677"]:::hot
  end
  subgraph laravel_filament["laravel-filament"]
    filament["filament<br/>⊕31 ↻2299"]:::cool
  end
  subgraph laravel_livewire["laravel-livewire"]
    livewire_blade_attributes["livewire-blade-attributes<br/>⊕128 ↻1256"]:::hot
  end
  subgraph laravel_testing["laravel-testing"]
    health_checks["health-checks<br/>⊕31 ↻2298"]:::cool
    laravel_dusk["laravel-dusk<br/>⊕30 ↻980"]:::cool
    laravel_testing["laravel-testing<br/>⊕33 ↻3024"]:::mild
    test_isolation_guard["test-isolation-guard<br/>⊕34 ↻1965"]:::mild
  end
  subgraph legal["legal"]
    legal_super_skill["legal-super-skill<br/>⊕93 ↻615"]:::warm
  end
  subgraph marketing["marketing"]
    marketing_super_skill["marketing-super-skill<br/>⊕95 ↻663"]:::warm
  end
  subgraph mobile["mobile"]
    figma_to_flutter["figma-to-flutter<br/>⊕107 ↻840"]:::hot
  end
  subgraph operator["operator"]
    capacity_planning["capacity-planning<br/>⊕41 ↻2051"]:::mild
    incident_response["incident-response<br/>⊕41 ↻1817"]:::mild
    oncall_rotation["oncall-rotation<br/>⊕37 ↻1667"]:::mild
    operations_cx_super_skill["operations-cx-super-skill<br/>⊕98 ↻597"]:::hot
    postmortem["postmortem<br/>⊕43 ↻1883"]:::warm
    runbook["runbook<br/>⊕36 ↻1720"]:::mild
  end
  subgraph oss_dev["oss-dev"]
    dependency_audit["dependency-audit<br/>⊕30 ↻1128"]:::cool
    dx_design["dx-design<br/>⊕30 ↻1210"]:::cool
    gh_review["gh-review<br/>⊕30 ↻1135"]:::cool
    github_flow["github-flow<br/>⊕30 ↻2063"]:::cool
    issue_triage["issue-triage<br/>⊕29 ↻2147"]:::cool
    oss_development["oss-development<br/>⊕32 ↻1327"]:::cool
    oss_governance["oss-governance<br/>⊕32 ↻1568"]:::cool
    release_engineering["release-engineering<br/>⊕34 ↻2145"]:::mild
    resolving_merge_conflicts["resolving-merge-conflicts<br/>⊕34 ↻327"]:::mild
    to_issues["to-issues<br/>⊕32 ↻1175"]:::cool
  end
  subgraph php["php"]
    code_style_spatie["code-style-spatie<br/>⊕31 ↻1032"]:::cool
    cursor_pagination_design["cursor-pagination-design<br/>⊕32 ↻385"]:::cool
    database["database<br/>⊕28 ↻933"]:::cool
    dependency_injection["dependency-injection<br/>⊕32 ↻1425"]:::cool
    laravel["laravel<br/>⊕29 ↻1691"]:::cool
    laravel_best_practices["laravel-best-practices<br/>⊕34 ↻535"]:::mild
    laravel_structure["laravel-structure<br/>⊕27 ↻2138"]:::cool
    named_arguments["named-arguments<br/>⊕29 ↻667"]:::cool
    namespace_refactor_safety["namespace-refactor-safety<br/>⊕33 ↻338"]:::mild
    pao["pao<br/>⊕28 ↻625"]:::cool
    php_naming_conventions["php-naming-conventions<br/>⊕31 ↻1398"]:::cool
    php_patterns["php-patterns<br/>⊕31 ↻2510"]:::cool
    php_upgrade_checklist["php-upgrade-checklist<br/>⊕33 ↻644"]:::mild
    production_readiness_checklist["production-readiness-checklist<br/>⊕37 ↻548"]:::mild
    repositories["repositories<br/>⊕31 ↻1709"]:::cool
    static_analysis["static-analysis<br/>⊕30 ↻1095"]:::cool
    transactional_outbox_relay["transactional-outbox-relay<br/>⊕35 ↻558"]:::mild
  end
  subgraph php_packages["php-packages"]
    laravel_package_compatibility["laravel-package-compatibility<br/>⊕35 ↻446"]:::mild
    laravel_package_docs["laravel-package-docs<br/>⊕32 ↻713"]:::cool
    laravel_package_expressive["laravel-package-expressive<br/>⊕36 ↻578"]:::mild
    laravel_package_generate_skill["laravel-package-generate-skill<br/>⊕35 ↻804"]:::mild
    laravel_package_release["laravel-package-release<br/>⊕35 ↻382"]:::mild
    laravel_package_scaffold["laravel-package-scaffold<br/>⊕36 ↻615"]:::mild
    laravel_package_service_provider["laravel-package-service-provider<br/>⊕38 ↻551"]:::mild
    laravel_package_testing["laravel-package-testing<br/>⊕36 ↻538"]:::mild
    laravel_packages["laravel-packages<br/>⊕32 ↻761"]:::cool
  end
  subgraph pm["pm"]
    brd["brd<br/>⊕34 ↻563"]:::mild
    business_process["business-process<br/>⊕33 ↻535"]:::mild
    go_to_market["go-to-market<br/>⊕32 ↻1298"]:::cool
    monetization_design["monetization-design<br/>⊕36 ↻1355"]:::mild
    pm_super_skill["pm-super-skill<br/>⊕120 ↻618"]:::hot
    pmf_diagnostics["pmf-diagnostics<br/>⊕53 ↻1390"]:::warm
    prd_from_brd["prd-from-brd<br/>⊕38 ↻1414"]:::mild
    product_roadmap["product-roadmap<br/>⊕35 ↻1221"]:::mild
    requirement_critic["requirement-critic<br/>⊕51 ↻1569"]:::warm
    unit_economics["unit-economics<br/>⊕30 ↻812"]:::cool
  end
  subgraph python["python"]
    ml_project_structure["ml-project-structure<br/>⊕30 ↻587"]:::cool
    venv_dependencies["venv-dependencies<br/>⊕33 ↻519"]:::mild
  end
  subgraph quality["quality"]
    artifact_review["artifact-review<br/>⊕31 ↻784"]:::cool
    code_review["code-review<br/>⊕29 ↻864"]:::cool
    code_simplifier["code-simplifier<br/>⊕33 ↻1233"]:::mild
    diagnosing_bugs["diagnosing-bugs<br/>⊕33 ↻946"]:::mild
    mutation_testing["mutation-testing<br/>⊕30 ↻2552"]:::cool
    playwright_e2e["playwright-e2e<br/>⊕28 ↻2517"]:::cool
    refactoring_plan["refactoring-plan<br/>⊕31 ↻1850"]:::cool
    tdd_discipline["tdd-discipline<br/>⊕33 ↻765"]:::mild
    tech_debt_audit["tech-debt-audit<br/>⊕31 ↻2211"]:::cool
    test_strategy["test-strategy<br/>⊕33 ↻1022"]:::mild
    testing_safety_report["testing-safety-report<br/>⊕34 ↻723"]:::mild
  end
  subgraph repository_bootstrap["repository-bootstrap"]
    cross_project_optimizer["cross-project-optimizer<br/>⊕95 ↻1015"]:::warm
    decision_verification["decision-verification<br/>⊕39 ↻293"]:::mild
    docs_maintenance["docs-maintenance<br/>⊕88 ↻1005"]:::warm
    ecosystem_integration["ecosystem-integration<br/>⊕77 ↻1954"]:::warm
    ecosystem_mcp["ecosystem-mcp<br/>⊕92 ↻1608"]:::warm
    ecosystem_setup["ecosystem-setup<br/>⊕89 ↻1103"]:::warm
    field_feedback_loop["field-feedback-loop<br/>⊕91 ↻1325"]:::warm
    harness_operations["harness-operations<br/>⊕87 ↻2093"]:::warm
    maind_overview["maind-overview<br/>⊕80 ↻1615"]:::warm
    package_architecture["package-architecture<br/>⊕85 ↻3698"]:::warm
    project_tooling_runbook["project-tooling-runbook<br/>⊕42 ↻7466"]:::mild
    release_discipline["release-discipline<br/>⊕64 ↻1488"]:::warm
    skill_authoring["skill-authoring<br/>⊕44 ↻1846"]:::warm
    task_development_philosophy["task-development-philosophy<br/>⊕74 ↻3745"]:::warm
  end
  subgraph research["research"]
    query_craft["query-craft<br/>⊕35 ↻257"]:::mild
    research_knowledge_super_skill["research-knowledge-super-skill<br/>⊕97 ↻569"]:::warm
  end
  subgraph roles["roles"]
    open_source_maintainer["open-source-maintainer<br/>⊕25 ↻1208"]:::cool
    solo_founder["solo-founder<br/>⊕22 ↻1160"]:::cool
    startup_cto["startup-cto<br/>⊕26 ↻1389"]:::cool
    tech_lead["tech-lead<br/>⊕24 ↻1386"]:::cool
  end
  subgraph sales["sales"]
    sales_super_skill["sales-super-skill<br/>⊕108 ↻719"]:::hot
  end
  subgraph security["security"]
    agent_security_super_skill["agent-security-super-skill<br/>⊕103 ↻675"]:::hot
  end
  subgraph system["system"]
    agent_packs["agent-packs<br/>⊕120 ↻2305"]:::hot
    brain_locator["brain-locator<br/>⊕47 ↻1310"]:::warm
    cross_project_coordinator["cross-project-coordinator<br/>⊕83 ↻1402"]:::warm
    local_topology["local-topology<br/>⊕62 ↻1362"]:::warm
    session_observer["session-observer<br/>⊕117 ↻1622"]:::hot
    shared_memory["shared-memory<br/>⊕62 ↻1389"]:::warm
    swissknifeman_locator["swissknifeman-locator<br/>⊕54 ↻1397"]:::warm
  end
  subgraph voice_ai["voice-ai"]
    voice_ai["voice-ai<br/>⊕125 ↻3165"]:::hot
  end
  attribute_authorization -->|requires| laravel_permissions
  axioma_glossary -->|requires| domain_modeling
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
  implement -->|requires| tdd_discipline
  issue_triage -->|requires| github_flow
  laravel_security_audit -->|requires| static_analysis
  legal_compliance -->|requires| architecture
  mcp_blender -->|requires| version_gotchas
  model_verification -->|requires| mcp_blender
  model_verification -->|requires| model_rules
  model_verification -->|requires| parametric_config
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
  classDef hot fill:#c0392b,color:#fff,stroke:#7b241c;
  classDef warm fill:#e67e22,color:#fff,stroke:#a04000;
  classDef mild fill:#f1c40f,color:#222,stroke:#b7950b;
  classDef cool fill:#27ae60,color:#fff,stroke:#1e8449;
```

**Total:** 232 skills · ⊕ always **12586** current (is always resident if you include the entire registry) · ↻ bodies 311875 current · ⌥ on-demand 850300 current (snippets + references).

## By buckets

| Bucket | Skills | ⊕ always | ↻ bodies | ⌥ on-demand |
|---|--:|--:|--:|--:|
| `general` | 22 | 1260 | 34152 | 33347 |
| `repository-bootstrap` | 14 | 1047 | 30254 | 0 |
| `architect` | 15 | 937 | 19786 | 33082 |
| `laravel-architecture` | 6 | 596 | 9564 | 7832 |
| `blender-modeling` | 7 | 582 | 11542 | 13519 |
| `devops` | 11 | 553 | 8909 | 16736 |
| `system` | 7 | 545 | 10787 | 816 |
| `php` | 17 | 531 | 18231 | 54365 |
| `pm` | 10 | 462 | 10775 | 23510 |
| `founder` | 10 | 430 | 14976 | 577 |
| `axioma` | 4 | 352 | 4496 | 0 |
| `quality` | 11 | 346 | 15467 | 6562 |
| `frontend-vue` | 11 | 340 | 14761 | 257982 |
| `frontend-linting` | 4 | 323 | 5818 | 18280 |
| `php-packages` | 9 | 315 | 5388 | 507 |
| `oss-dev` | 10 | 313 | 14225 | 9876 |
| `operator` | 6 | 296 | 9735 | 22461 |
| `ai` | 3 | 284 | 4545 | 51473 |
| `frontend` | 3 | 263 | 3794 | 7847 |
| `laravel-extras` | 3 | 202 | 4159 | 7570 |
| `frontend-vite` | 4 | 188 | 3090 | 24643 |
| `blender` | 2 | 146 | 2231 | 1821 |
| `research` | 2 | 132 | 826 | 20472 |
| `laravel-livewire` | 1 | 128 | 1256 | 1071 |
| `laravel-testing` | 4 | 128 | 8267 | 16534 |
| `voice-ai` | 1 | 125 | 3165 | 0 |
| `creative` | 1 | 111 | 687 | 26239 |
| `sales` | 1 | 108 | 719 | 25593 |
| `mobile` | 1 | 107 | 840 | 980 |
| `finance` | 1 | 105 | 740 | 21503 |
| `frontend-reka` | 1 | 105 | 1980 | 2444 |
| `security` | 1 | 103 | 675 | 30198 |
| `frontend-figma` | 1 | 99 | 785 | 1058 |
| `roles` | 4 | 97 | 5143 | 177 |
| `laravel-auth` | 3 | 96 | 3275 | 5439 |
| `marketing` | 1 | 95 | 663 | 16617 |
| `frontend-backend` | 3 | 93 | 5388 | 7602 |
| `legal` | 1 | 93 | 615 | 29248 |
| `frontend-nuxt` | 3 | 88 | 2564 | 24048 |
| `frontend-tailwind` | 2 | 63 | 4403 | 5097 |
| `python` | 2 | 63 | 1106 | 0 |
| `laravel-data-layer` | 2 | 61 | 3240 | 3892 |
| `dart` | 1 | 56 | 801 | 0 |
| `frontend-animations` | 1 | 55 | 920 | 5285 |
| `azguard` | 1 | 37 | 1647 | 7123 |
| `botkit` | 1 | 35 | 206 | 698 |
| `frontend-wayfinder` | 1 | 31 | 966 | 1727 |
| `laravel-filament` | 1 | 31 | 2299 | 3172 |
| `frontend-naive-ui` | 1 | 30 | 2014 | 1277 |

## Top ⊕ always (permanent tax)

The most expensive descriptions are resident in each request.

| Skill | Bucket | current |
|---|---|--:|
| `dev-engineering-super-skill` | architect | 133 |
| `domain-modeling` | architect | 128 |
| `livewire-blade-attributes` | laravel-livewire | 128 |
| `voice-ai` | voice-ai | 125 |
| `pm-super-skill` | pm | 120 |
| `agent-packs` | system | 120 |
| `eloquent-accessors` | laravel-architecture | 119 |
| `mcp-blender` | blender | 118 |
| `codebase-design` | architect | 117 |
| `session-observer` | system | 117 |

## Top ↻ on-trigger (trigger price)

The heaviest bodies are loaded when using the skill.

| Skill | Bucket | current |
|---|---|--:|
| `plan-protocol` | general | 11132 |
| `project-tooling-runbook` | repository-bootstrap | 7466 |
| `task-development-philosophy` | repository-bootstrap | 3745 |
| `package-architecture` | repository-bootstrap | 3698 |
| `workflow-craft` | general | 3538 |
| `mcp-advisor` | general | 3188 |
| `voice-ai` | voice-ai | 3165 |
| `modular-architecture` | laravel-architecture | 3112 |
| `laravel-testing` | laravel-testing | 3024 |
| `build-loop` | blender-modeling | 2847 |
