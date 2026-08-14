# Карта токенового бюджета

> Сгенерировано `lib/skiller/budget.py` (`skiller budget --write-map`) из `skills.json` и тел `SKILL.md` — не редактировать вручную.
> Пересборка: `skiller registry`.

Трёхъярусная модель раскрытия контекста — что грузит нейросеть и когда:

- **⊕ always** — `name`+`description`: резидентны в КАЖДОМ запросе (по ним агент решает, применять ли скилл). Постоянный «налог».
- **↻ on-trigger** — тело `SKILL.md`: грузится, только когда скилл сработал.
- **⌥ on-demand** — сниппеты и references: по ссылке из тела, опционально.

Цвет узла — heat по **⊕ always** (краснее = дороже постоянный налог описания). Метка `name<br/>⊕always ↻body`. Сплошная стрелка `requires` показывает транзитивный налог: ставишь скилл — тянешь always-цену зависимости. Оценка токенов грубая и языко-зависимая (кириллица ~2.9 chars/tok, латиница/код ~3.4) — для сравнения наборов, не точного учёта.

```mermaid
flowchart LR
  subgraph ai["ai"]
    ai_agents["ai-agents<br/>⊕88 ↻613"]:::warm
    mcp_builder["mcp-builder<br/>⊕85 ↻2560"]:::warm
    token_efficient["token-efficient<br/>⊕111 ↻1405"]:::hot
  end
  subgraph architect["architect"]
    agent_design["agent-design<br/>⊕29 ↻1716"]:::cool
    api_design["api-design<br/>⊕29 ↻1101"]:::cool
    architecture["architecture<br/>⊕32 ↻1302"]:::cool
    codebase_design["codebase-design<br/>⊕117 ↻1996"]:::hot
    data_schema["data-schema<br/>⊕34 ↻896"]:::cool
    dev_engineering_super_skill["dev-engineering-super-skill<br/>⊕133 ↻538"]:::hot
    domain_modeling["domain-modeling<br/>⊕128 ↻2158"]:::hot
    ecosystem_reuse_gate["ecosystem-reuse-gate<br/>⊕108 ↻1315"]:::hot
    eval_design["eval-design<br/>⊕35 ↻1543"]:::cool
    figma_mcp_core["figma-mcp-core<br/>⊕106 ↻1602"]:::warm
    legal_compliance["legal-compliance<br/>⊕33 ↻1814"]:::cool
    observability_design["observability-design<br/>⊕43 ↻1287"]:::mild
    package_contribution_protocol["package-contribution-protocol<br/>⊕106 ↻1829"]:::warm
    security_design["security-design<br/>⊕38 ↻2124"]:::cool
    tech_stack_selection["tech-stack-selection<br/>⊕34 ↻1943"]:::cool
  end
  subgraph axioma["axioma"]
    axioma_doctrine["axioma-doctrine<br/>⊕90 ↻1233"]:::warm
    axioma_glossary["axioma-glossary<br/>⊕110 ↻1311"]:::hot
    axioma_stack["axioma-stack<br/>⊕105 ↻1309"]:::warm
    ecosystem_map["ecosystem-map<br/>⊕47 ↻643"]:::mild
  end
  subgraph azguard["azguard"]
    azguard["azguard<br/>⊕37 ↻1651"]:::cool
  end
  subgraph blender["blender"]
    mcp_blender["mcp-blender<br/>⊕118 ↻1475"]:::hot
    version_gotchas["version-gotchas<br/>⊕28 ↻756"]:::cool
  end
  subgraph blender_modeling["blender-modeling"]
    build_loop["build-loop<br/>⊕103 ↻2847"]:::warm
    config_conventions["config-conventions<br/>⊕114 ↻2191"]:::hot
    model_rules["model-rules<br/>⊕36 ↻733"]:::cool
    model_verification["model-verification<br/>⊕90 ↻1503"]:::warm
    parametric_config["parametric-config<br/>⊕111 ↻2276"]:::hot
    scene_conventions["scene-conventions<br/>⊕95 ↻1135"]:::warm
    threading["threading<br/>⊕33 ↻885"]:::cool
  end
  subgraph botkit["botkit"]
    botkit["botkit<br/>⊕35 ↻206"]:::cool
  end
  subgraph creative["creative"]
    content_creative_super_skill["content-creative-super-skill<br/>⊕111 ↻687"]:::hot
  end
  subgraph dart["dart"]
    dart_package_development["dart-package-development<br/>⊕56 ↻801"]:::mild
  end
  subgraph devops["devops"]
    ci_cd["ci-cd<br/>⊕55 ↻1123"]:::mild
    db_test_preflight["db-test-preflight<br/>⊕104 ↻1676"]:::warm
    docker["docker<br/>⊕66 ↻400"]:::mild
    docker_dev_prod["docker-dev-prod<br/>⊕42 ↻924"]:::cool
    docker_php["docker-php<br/>⊕40 ↻767"]:::cool
    docker_postgres["docker-postgres<br/>⊕43 ↻807"]:::mild
    docker_services["docker-services<br/>⊕48 ↻858"]:::mild
    docker_vite["docker-vite<br/>⊕39 ↻679"]:::cool
    gitops["gitops<br/>⊕35 ↻715"]:::cool
    makefile["makefile<br/>⊕43 ↻732"]:::mild
    node_pnpm_preflight["node-pnpm-preflight<br/>⊕38 ↻228"]:::cool
  end
  subgraph finance["finance"]
    finance_super_skill["finance-super-skill<br/>⊕105 ↻740"]:::warm
  end
  subgraph founder["founder"]
    adversarial_check["adversarial-check<br/>⊕55 ↻1134"]:::mild
    competitive_analysis["competitive-analysis<br/>⊕37 ↻1315"]:::cool
    customer_discovery["customer-discovery<br/>⊕55 ↻1288"]:::mild
    defensibility["defensibility<br/>⊕42 ↻1124"]:::cool
    idea_audit["idea-audit<br/>⊕61 ↻2474"]:::mild
    idea_discovery["idea-discovery<br/>⊕35 ↻1640"]:::cool
    new_project["new-project<br/>⊕31 ↻1449"]:::cool
    pitch_deck["pitch-deck<br/>⊕32 ↻1555"]:::cool
    risk_assessment["risk-assessment<br/>⊕40 ↻1275"]:::cool
    startup_lifecycle["startup-lifecycle<br/>⊕42 ↻1748"]:::cool
  end
  subgraph frontend["frontend"]
    document_writer["document-writer<br/>⊕88 ↻1283"]:::warm
    filepond_upload["filepond-upload<br/>⊕114 ↻2215"]:::hot
    web_design_guidelines["web-design-guidelines<br/>⊕61 ↻296"]:::mild
  end
  subgraph frontend_animations["frontend-animations"]
    motion["motion<br/>⊕55 ↻920"]:::mild
  end
  subgraph frontend_backend["frontend-backend"]
    backend_type_sync["backend-type-sync<br/>⊕100 ↻2047"]:::warm
    inertia_vue["inertia-vue<br/>⊕58 ↻1458"]:::mild
    laravel_echo_client["laravel-echo-client<br/>⊕111 ↻1900"]:::hot
  end
  subgraph frontend_figma["frontend-figma"]
    figma_to_vue["figma-to-vue<br/>⊕99 ↻785"]:::warm
  end
  subgraph frontend_linting["frontend-linting"]
    antfu["antfu<br/>⊕74 ↻1282"]:::mild
    eslint_flat_config["eslint-flat-config<br/>⊕112 ↻2383"]:::hot
    js_code_style["js-code-style<br/>⊕47 ↻870"]:::mild
    ts_library["ts-library<br/>⊕90 ↻1357"]:::warm
  end
  subgraph frontend_naive_ui["frontend-naive-ui"]
    naive_ui_theming["naive-ui-theming<br/>⊕103 ↻2014"]:::warm
  end
  subgraph frontend_nuxt["frontend-nuxt"]
    nuxt["nuxt<br/>⊕80 ↻1095"]:::mild
    nuxt_modules["nuxt-modules<br/>⊕125 ↻644"]:::hot
    nuxt_seo["nuxt-seo<br/>⊕50 ↻825"]:::mild
  end
  subgraph frontend_reka["frontend-reka"]
    reka_ui_cva["reka-ui-cva<br/>⊕105 ↻1980"]:::warm
  end
  subgraph frontend_tailwind["frontend-tailwind"]
    dark_mode["dark-mode<br/>⊕113 ↻2182"]:::hot
    tailwind_conventions["tailwind-conventions<br/>⊕103 ↻2221"]:::warm
  end
  subgraph frontend_vite["frontend-vite"]
    vite["vite<br/>⊕57 ↻615"]:::mild
    vite_module_loader["vite-module-loader<br/>⊕35 ↻665"]:::cool
    vite_multi_build["vite-multi-build<br/>⊕47 ↻986"]:::mild
    vitepress["vitepress<br/>⊕49 ↻830"]:::mild
  end
  subgraph frontend_vue["frontend-vue"]
    pinia["pinia<br/>⊕54 ↻691"]:::mild
    pinia_stores["pinia-stores<br/>⊕104 ↻1893"]:::warm
    vitest["vitest<br/>⊕47 ↻789"]:::mild
    vitest_vue["vitest-vue<br/>⊕55 ↻1049"]:::mild
    vue["vue<br/>⊕63 ↻876"]:::mild
    vue_best_practices["vue-best-practices<br/>⊕99 ↻2560"]:::warm
    vue_composition_api["vue-composition-api<br/>⊕80 ↻503"]:::mild
    vue_dynamic_icons["vue-dynamic-icons<br/>⊕76 ↻1275"]:::mild
    vue_router_best_practices["vue-router-best-practices<br/>⊕126 ↻2792"]:::hot
    vue_testing_best_practices["vue-testing-best-practices<br/>⊕77 ↻2367"]:::mild
    vueuse_functions["vueuse-functions<br/>⊕34 ↻10838"]:::cool
  end
  subgraph frontend_wayfinder["frontend-wayfinder"]
    wayfinder["wayfinder<br/>⊕48 ↻966"]:::mild
  end
  subgraph general["general"]
    anti_drift["anti-drift<br/>⊕32 ↻1971"]:::cool
    compact_responses["compact-responses<br/>⊕60 ↻570"]:::mild
    complex_task_orchestrator["complex-task-orchestrator<br/>⊕33 ↻632"]:::cool
    context_economy["context-economy<br/>⊕48 ↻2673"]:::mild
    cross_layer_change_checklist["cross-layer-change-checklist<br/>⊕32 ↻433"]:::cool
    git_commit_rules["git-commit-rules<br/>⊕30 ↻1097"]:::cool
    git_safety["git-safety<br/>⊕84 ↻600"]:::warm
    grill_with_docs["grill-with-docs<br/>⊕98 ↻911"]:::warm
    implement["implement<br/>⊕88 ↻479"]:::warm
    mcp_advisor["mcp-advisor<br/>⊕107 ↻3188"]:::hot
    naming_conventions["naming-conventions<br/>⊕86 ↻1755"]:::warm
    packages_stack["packages-stack<br/>⊕85 ↻503"]:::warm
    plan_protocol["plan-protocol<br/>⊕31 ↻5969"]:::cool
    project_map["project-map<br/>⊕83 ↻618"]:::warm
    session_handoff["session-handoff<br/>⊕29 ↻590"]:::cool
    shell["shell<br/>⊕73 ↻1997"]:::mild
    skills_ssot["skills-ssot<br/>⊕29 ↻1744"]:::cool
    spec_interview["spec-interview<br/>⊕35 ↻725"]:::cool
    task_brief_template["task-brief-template<br/>⊕47 ↻1226"]:::mild
    verify_claims["verify-claims<br/>⊕110 ↻3004"]:::hot
    workflow_craft["workflow-craft<br/>⊕48 ↻3349"]:::mild
    writing_style["writing-style<br/>⊕98 ↻1878"]:::warm
  end
  subgraph laravel_architecture["laravel-architecture"]
    config_driven_abstraction["config-driven-abstraction<br/>⊕114 ↻460"]:::hot
    eloquent_accessors["eloquent-accessors<br/>⊕119 ↻1228"]:::hot
    enum_attributes["enum-attributes<br/>⊕99 ↻1950"]:::warm
    enum_state_machine["enum-state-machine<br/>⊕104 ↻1557"]:::warm
    laravel_subagents["laravel-subagents<br/>⊕77 ↻1260"]:::mild
    modular_architecture["modular-architecture<br/>⊕83 ↻3112"]:::warm
  end
  subgraph laravel_auth["laravel-auth"]
    attribute_authorization["attribute-authorization<br/>⊕83 ↻2102"]:::warm
    laravel_permissions["laravel-permissions<br/>⊕68 ↻398"]:::mild
    laravel_security_audit["laravel-security-audit<br/>⊕51 ↻775"]:::mild
  end
  subgraph laravel_data_layer["laravel-data-layer"]
    laravel_broadcasting["laravel-broadcasting<br/>⊕40 ↻1257"]:::cool
    laravel_data["laravel-data<br/>⊕120 ↻2030"]:::hot
  end
  subgraph laravel_extras["laravel-extras"]
    medialibrary["medialibrary<br/>⊕35 ↻1020"]:::cool
    pennant_development["pennant-development<br/>⊕58 ↻505"]:::mild
    spatie_settings["spatie-settings<br/>⊕109 ↻2677"]:::hot
  end
  subgraph laravel_filament["laravel-filament"]
    filament["filament<br/>⊕63 ↻2374"]:::mild
  end
  subgraph laravel_livewire["laravel-livewire"]
    livewire_blade_attributes["livewire-blade-attributes<br/>⊕128 ↻1256"]:::hot
  end
  subgraph laravel_testing["laravel-testing"]
    health_checks["health-checks<br/>⊕100 ↻2298"]:::warm
    laravel_dusk["laravel-dusk<br/>⊕34 ↻980"]:::cool
    laravel_testing["laravel-testing<br/>⊕56 ↻3034"]:::mild
    test_isolation_guard["test-isolation-guard<br/>⊕104 ↻1572"]:::warm
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
    capacity_planning["capacity-planning<br/>⊕41 ↻2056"]:::cool
    incident_response["incident-response<br/>⊕41 ↻1817"]:::cool
    oncall_rotation["oncall-rotation<br/>⊕37 ↻1681"]:::cool
    operations_cx_super_skill["operations-cx-super-skill<br/>⊕98 ↻597"]:::warm
    postmortem["postmortem<br/>⊕43 ↻1902"]:::mild
    runbook["runbook<br/>⊕36 ↻1720"]:::cool
  end
  subgraph oss_dev["oss-dev"]
    dependency_audit["dependency-audit<br/>⊕37 ↻1133"]:::cool
    dx_design["dx-design<br/>⊕37 ↻1210"]:::cool
    gh_review["gh-review<br/>⊕77 ↻1135"]:::mild
    github_flow["github-flow<br/>⊕71 ↻2063"]:::mild
    issue_triage["issue-triage<br/>⊕114 ↻2163"]:::hot
    oss_development["oss-development<br/>⊕38 ↻1364"]:::cool
    oss_governance["oss-governance<br/>⊕36 ↻1568"]:::cool
    release_engineering["release-engineering<br/>⊕37 ↻2145"]:::cool
    resolving_merge_conflicts["resolving-merge-conflicts<br/>⊕103 ↻335"]:::warm
    to_issues["to-issues<br/>⊕92 ↻1184"]:::warm
  end
  subgraph php["php"]
    code_style_spatie["code-style-spatie<br/>⊕47 ↻1127"]:::mild
    cursor_pagination_design["cursor-pagination-design<br/>⊕107 ↻385"]:::hot
    database["database<br/>⊕51 ↻933"]:::mild
    dependency_injection["dependency-injection<br/>⊕39 ↻1258"]:::cool
    laravel["laravel<br/>⊕27 ↻1545"]:::cool
    laravel_best_practices["laravel-best-practices<br/>⊕40 ↻1727"]:::cool
    laravel_structure["laravel-structure<br/>⊕44 ↻1992"]:::mild
    named_arguments["named-arguments<br/>⊕50 ↻667"]:::mild
    namespace_refactor_safety["namespace-refactor-safety<br/>⊕110 ↻338"]:::hot
    pao["pao<br/>⊕59 ↻625"]:::mild
    php_naming_conventions["php-naming-conventions<br/>⊕80 ↻1398"]:::mild
    php_patterns["php-patterns<br/>⊕31 ↻2510"]:::cool
    php_upgrade_checklist["php-upgrade-checklist<br/>⊕71 ↻644"]:::mild
    production_readiness_checklist["production-readiness-checklist<br/>⊕128 ↻548"]:::hot
    repositories["repositories<br/>⊕36 ↻1536"]:::cool
    static_analysis["static-analysis<br/>⊕35 ↻1095"]:::cool
    transactional_outbox_relay["transactional-outbox-relay<br/>⊕110 ↻558"]:::hot
  end
  subgraph php_packages["php-packages"]
    laravel_package_compatibility["laravel-package-compatibility<br/>⊕76 ↻446"]:::mild
    laravel_package_docs["laravel-package-docs<br/>⊕75 ↻713"]:::mild
    laravel_package_expressive["laravel-package-expressive<br/>⊕114 ↻578"]:::hot
    laravel_package_generate_skill["laravel-package-generate-skill<br/>⊕84 ↻804"]:::warm
    laravel_package_release["laravel-package-release<br/>⊕68 ↻382"]:::mild
    laravel_package_scaffold["laravel-package-scaffold<br/>⊕77 ↻615"]:::mild
    laravel_package_service_provider["laravel-package-service-provider<br/>⊕73 ↻551"]:::mild
    laravel_package_testing["laravel-package-testing<br/>⊕85 ↻540"]:::warm
    laravel_packages["laravel-packages<br/>⊕38 ↻761"]:::cool
  end
  subgraph pm["pm"]
    brd["brd<br/>⊕34 ↻564"]:::cool
    business_process["business-process<br/>⊕33 ↻544"]:::cool
    go_to_market["go-to-market<br/>⊕32 ↻1298"]:::cool
    monetization_design["monetization-design<br/>⊕36 ↻1372"]:::cool
    pm_super_skill["pm-super-skill<br/>⊕120 ↻618"]:::hot
    pmf_diagnostics["pmf-diagnostics<br/>⊕53 ↻1386"]:::mild
    prd_from_brd["prd-from-brd<br/>⊕38 ↻1414"]:::cool
    product_roadmap["product-roadmap<br/>⊕35 ↻1239"]:::cool
    requirement_critic["requirement-critic<br/>⊕51 ↻1578"]:::mild
    unit_economics["unit-economics<br/>⊕30 ↻812"]:::cool
  end
  subgraph python["python"]
    ml_project_structure["ml-project-structure<br/>⊕30 ↻587"]:::cool
    venv_dependencies["venv-dependencies<br/>⊕33 ↻522"]:::cool
  end
  subgraph quality["quality"]
    artifact_review["artifact-review<br/>⊕93 ↻1472"]:::warm
    code_review["code-review<br/>⊕36 ↻1595"]:::cool
    code_simplifier["code-simplifier<br/>⊕68 ↻1233"]:::mild
    diagnosing_bugs["diagnosing-bugs<br/>⊕106 ↻2577"]:::warm
    mutation_testing["mutation-testing<br/>⊕106 ↻2552"]:::warm
    playwright_e2e["playwright-e2e<br/>⊕107 ↻2517"]:::hot
    refactoring_plan["refactoring-plan<br/>⊕37 ↻1850"]:::cool
    tdd_discipline["tdd-discipline<br/>⊕100 ↻1374"]:::warm
    tech_debt_audit["tech-debt-audit<br/>⊕44 ↻2173"]:::mild
    test_strategy["test-strategy<br/>⊕61 ↻2247"]:::mild
    testing_safety_report["testing-safety-report<br/>⊕77 ↻729"]:::mild
  end
  subgraph repository_bootstrap["repository-bootstrap"]
    cross_project_optimizer["cross-project-optimizer<br/>⊕95 ↻1026"]:::warm
    decision_verification["decision-verification<br/>⊕91 ↻1249"]:::warm
    docs_maintenance["docs-maintenance<br/>⊕88 ↻1017"]:::warm
    ecosystem_integration["ecosystem-integration<br/>⊕77 ↻1965"]:::mild
    ecosystem_mcp["ecosystem-mcp<br/>⊕92 ↻1619"]:::warm
    ecosystem_setup["ecosystem-setup<br/>⊕89 ↻1114"]:::warm
    field_feedback_loop["field-feedback-loop<br/>⊕91 ↻1343"]:::warm
    harness_operations["harness-operations<br/>⊕87 ↻2105"]:::warm
    maind_overview["maind-overview<br/>⊕80 ↻1626"]:::mild
    package_architecture["package-architecture<br/>⊕85 ↻3740"]:::warm
    project_tooling_runbook["project-tooling-runbook<br/>⊕93 ↻6971"]:::warm
    release_discipline["release-discipline<br/>⊕64 ↻805"]:::mild
    skill_authoring["skill-authoring<br/>⊕44 ↻1792"]:::mild
  end
  subgraph research["research"]
    query_craft["query-craft<br/>⊕103 ↻4194"]:::warm
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
    agent_security_super_skill["agent-security-super-skill<br/>⊕103 ↻675"]:::warm
  end
  subgraph system["system"]
    agent_packs["agent-packs<br/>⊕120 ↻2305"]:::hot
    brain_locator["brain-locator<br/>⊕47 ↻1310"]:::mild
    cross_project_coordinator["cross-project-coordinator<br/>⊕83 ↻1402"]:::warm
    local_topology["local-topology<br/>⊕62 ↻1362"]:::mild
    session_observer["session-observer<br/>⊕117 ↻1622"]:::hot
    shared_memory["shared-memory<br/>⊕124 ↻1423"]:::hot
    swissknifeman_locator["swissknifeman-locator<br/>⊕54 ↻1397"]:::mild
  end
  subgraph voice_ai["voice-ai"]
    voice_ai["voice-ai<br/>⊕125 ↻3165"]:::hot
  end
  agent_design -->|requires| architecture
  api_design -->|requires| data_schema
  architecture -->|requires| brd
  architecture -->|requires| tech_stack_selection
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
  implement -->|requires| code_review
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
  classDef hot fill:#c0392b,color:#fff,stroke:#7b241c;
  classDef warm fill:#e67e22,color:#fff,stroke:#a04000;
  classDef mild fill:#f1c40f,color:#222,stroke:#b7950b;
  classDef cool fill:#27ae60,color:#fff,stroke:#1e8449;
```

**Итого:** 231 скиллов · ⊕ always **16110** ток (резидентно всегда, если включить весь реестр) · ↻ bodies 333622 ток · ⌥ on-demand 836992 ток (сниппеты + references).

## По бакетам

| Бакет | Скиллов | ⊕ always | ↻ bodies | ⌥ on-demand |
|---|--:|--:|--:|--:|
| `general` | 22 | 1366 | 35912 | 26005 |
| `repository-bootstrap` | 13 | 1076 | 26372 | 0 |
| `php` | 17 | 1065 | 18886 | 54837 |
| `architect` | 15 | 1005 | 23164 | 33458 |
| `quality` | 11 | 835 | 20319 | 7447 |
| `frontend-vue` | 11 | 815 | 25633 | 248486 |
| `php-packages` | 9 | 690 | 5390 | 520 |
| `oss-dev` | 10 | 642 | 14300 | 10187 |
| `system` | 7 | 607 | 10821 | 834 |
| `laravel-architecture` | 6 | 596 | 9567 | 7994 |
| `blender-modeling` | 7 | 582 | 11570 | 14235 |
| `devops` | 11 | 553 | 8909 | 16993 |
| `pm` | 10 | 462 | 10825 | 23524 |
| `founder` | 10 | 430 | 15002 | 578 |
| `axioma` | 4 | 352 | 4496 | 0 |
| `frontend-linting` | 4 | 323 | 5892 | 18380 |
| `operator` | 6 | 296 | 9773 | 22461 |
| `laravel-testing` | 4 | 294 | 7884 | 15335 |
| `ai` | 3 | 284 | 4578 | 51473 |
| `frontend-backend` | 3 | 269 | 5405 | 7851 |
| `frontend` | 3 | 263 | 3794 | 7958 |
| `frontend-nuxt` | 3 | 255 | 2564 | 24048 |
| `frontend-tailwind` | 2 | 216 | 4403 | 5218 |
| `laravel-auth` | 3 | 202 | 3275 | 5640 |
| `laravel-extras` | 3 | 202 | 4202 | 7664 |
| `research` | 2 | 200 | 4763 | 20472 |
| `frontend-vite` | 4 | 188 | 3096 | 24662 |
| `laravel-data-layer` | 2 | 160 | 3287 | 3977 |
| `blender` | 2 | 146 | 2231 | 1907 |
| `laravel-livewire` | 1 | 128 | 1256 | 1117 |
| `voice-ai` | 1 | 125 | 3165 | 0 |
| `creative` | 1 | 111 | 687 | 26240 |
| `sales` | 1 | 108 | 719 | 25593 |
| `mobile` | 1 | 107 | 840 | 987 |
| `finance` | 1 | 105 | 740 | 21503 |
| `frontend-reka` | 1 | 105 | 1980 | 2536 |
| `frontend-naive-ui` | 1 | 103 | 2014 | 1337 |
| `security` | 1 | 103 | 675 | 30199 |
| `frontend-figma` | 1 | 99 | 785 | 1071 |
| `roles` | 4 | 97 | 5143 | 177 |
| `marketing` | 1 | 95 | 663 | 16617 |
| `legal` | 1 | 93 | 615 | 29248 |
| `laravel-filament` | 1 | 63 | 2374 | 3182 |
| `python` | 2 | 63 | 1109 | 0 |
| `dart` | 1 | 56 | 801 | 0 |
| `frontend-animations` | 1 | 55 | 920 | 5285 |
| `frontend-wayfinder` | 1 | 48 | 966 | 1765 |
| `azguard` | 1 | 37 | 1651 | 7293 |
| `botkit` | 1 | 35 | 206 | 698 |

## Топ ⊕ always (постоянный налог)

Самые дорогие описания — резидентны в каждом запросе.

| Скилл | Бакет | ток |
|---|---|--:|
| `dev-engineering-super-skill` | architect | 133 |
| `domain-modeling` | architect | 128 |
| `livewire-blade-attributes` | laravel-livewire | 128 |
| `production-readiness-checklist` | php | 128 |
| `vue-router-best-practices` | frontend-vue | 126 |
| `nuxt-modules` | frontend-nuxt | 125 |
| `voice-ai` | voice-ai | 125 |
| `shared-memory` | system | 124 |
| `laravel-data` | laravel-data-layer | 120 |
| `pm-super-skill` | pm | 120 |

## Топ ↻ on-trigger (цена срабатывания)

Самые тяжёлые тела — грузятся при применении скилла.

| Скилл | Бакет | ток |
|---|---|--:|
| `vueuse-functions` | frontend-vue | 10838 |
| `project-tooling-runbook` | repository-bootstrap | 6971 |
| `plan-protocol` | general | 5969 |
| `query-craft` | research | 4194 |
| `package-architecture` | repository-bootstrap | 3740 |
| `workflow-craft` | general | 3349 |
| `mcp-advisor` | general | 3188 |
| `voice-ai` | voice-ai | 3165 |
| `modular-architecture` | laravel-architecture | 3112 |
| `laravel-testing` | laravel-testing | 3034 |
