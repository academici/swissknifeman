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
    agent_design["agent-design<br/>⊕25 ↻1744"]:::cool
    api_design["api-design<br/>⊕26 ↻1129"]:::cool
    architecture["architecture<br/>⊕27 ↻1329"]:::cool
    codebase_design["codebase-design<br/>⊕117 ↻1996"]:::hot
    data_schema["data-schema<br/>⊕28 ↻924"]:::cool
    dev_engineering_super_skill["dev-engineering-super-skill<br/>⊕133 ↻538"]:::hot
    domain_modeling["domain-modeling<br/>⊕128 ↻2185"]:::hot
    ecosystem_reuse_gate["ecosystem-reuse-gate<br/>⊕108 ↻1342"]:::hot
    eval_design["eval-design<br/>⊕32 ↻1570"]:::cool
    figma_mcp_core["figma-mcp-core<br/>⊕106 ↻1629"]:::warm
    legal_compliance["legal-compliance<br/>⊕26 ↻1841"]:::cool
    observability_design["observability-design<br/>⊕32 ↻1315"]:::cool
    package_contribution_protocol["package-contribution-protocol<br/>⊕106 ↻1857"]:::warm
    security_design["security-design<br/>⊕38 ↻2151"]:::cool
    tech_stack_selection["tech-stack-selection<br/>⊕32 ↻1970"]:::cool
  end
  subgraph axioma["axioma"]
    axioma_doctrine["axioma-doctrine<br/>⊕90 ↻1260"]:::warm
    axioma_glossary["axioma-glossary<br/>⊕110 ↻1338"]:::hot
    axioma_stack["axioma-stack<br/>⊕105 ↻1337"]:::warm
    ecosystem_map["ecosystem-map<br/>⊕47 ↻670"]:::mild
  end
  subgraph azguard["azguard"]
    azguard["azguard<br/>⊕37 ↻1679"]:::cool
  end
  subgraph blender["blender"]
    mcp_blender["mcp-blender<br/>⊕118 ↻1503"]:::hot
    version_gotchas["version-gotchas<br/>⊕22 ↻784"]:::cool
  end
  subgraph blender_modeling["blender-modeling"]
    build_loop["build-loop<br/>⊕103 ↻2137"]:::warm
    config_conventions["config-conventions<br/>⊕114 ↻2219"]:::hot
    model_rules["model-rules<br/>⊕31 ↻761"]:::cool
    parametric_config["parametric-config<br/>⊕111 ↻2196"]:::hot
    scene_conventions["scene-conventions<br/>⊕95 ↻914"]:::warm
    threading["threading<br/>⊕27 ↻660"]:::cool
  end
  subgraph botkit["botkit"]
    botkit["botkit<br/>⊕29 ↻234"]:::cool
  end
  subgraph creative["creative"]
    content_creative_super_skill["content-creative-super-skill<br/>⊕111 ↻687"]:::hot
  end
  subgraph devops["devops"]
    ci_cd["ci-cd<br/>⊕55 ↻1150"]:::mild
    db_test_preflight["db-test-preflight<br/>⊕104 ↻1703"]:::warm
    docker["docker<br/>⊕66 ↻400"]:::mild
    docker_dev_prod["docker-dev-prod<br/>⊕42 ↻952"]:::mild
    docker_php["docker-php<br/>⊕40 ↻794"]:::cool
    docker_postgres["docker-postgres<br/>⊕43 ↻834"]:::mild
    docker_services["docker-services<br/>⊕48 ↻885"]:::mild
    docker_vite["docker-vite<br/>⊕39 ↻706"]:::cool
    gitops["gitops<br/>⊕30 ↻743"]:::cool
    makefile["makefile<br/>⊕43 ↻759"]:::mild
    node_pnpm_preflight["node-pnpm-preflight<br/>⊕38 ↻255"]:::cool
  end
  subgraph finance["finance"]
    finance_super_skill["finance-super-skill<br/>⊕105 ↻740"]:::warm
  end
  subgraph founder["founder"]
    adversarial_check["adversarial-check<br/>⊕55 ↻1162"]:::mild
    competitive_analysis["competitive-analysis<br/>⊕30 ↻1343"]:::cool
    customer_discovery["customer-discovery<br/>⊕55 ↻1315"]:::mild
    defensibility["defensibility<br/>⊕42 ↻1151"]:::mild
    idea_audit["idea-audit<br/>⊕61 ↻2502"]:::mild
    idea_discovery["idea-discovery<br/>⊕35 ↻1668"]:::cool
    new_project["new-project<br/>⊕28 ↻1476"]:::cool
    pitch_deck["pitch-deck<br/>⊕26 ↻1583"]:::cool
    risk_assessment["risk-assessment<br/>⊕32 ↻1302"]:::cool
    startup_lifecycle["startup-lifecycle<br/>⊕42 ↻1775"]:::mild
  end
  subgraph frontend["frontend"]
    document_writer["document-writer<br/>⊕88 ↻1283"]:::warm
    filepond_upload["filepond-upload<br/>⊕114 ↻2242"]:::hot
    web_design_guidelines["web-design-guidelines<br/>⊕61 ↻270"]:::mild
  end
  subgraph frontend_animations["frontend-animations"]
    motion["motion<br/>⊕55 ↻920"]:::mild
  end
  subgraph frontend_backend["frontend-backend"]
    backend_type_sync["backend-type-sync<br/>⊕100 ↻2075"]:::warm
    inertia_vue["inertia-vue<br/>⊕58 ↻1485"]:::mild
    laravel_echo_client["laravel-echo-client<br/>⊕111 ↻1928"]:::hot
  end
  subgraph frontend_figma["frontend-figma"]
    figma_to_vue["figma-to-vue<br/>⊕99 ↻813"]:::warm
  end
  subgraph frontend_linting["frontend-linting"]
    antfu["antfu<br/>⊕74 ↻1282"]:::mild
    eslint_flat_config["eslint-flat-config<br/>⊕112 ↻2411"]:::hot
    js_code_style["js-code-style<br/>⊕47 ↻870"]:::mild
    ts_library["ts-library<br/>⊕90 ↻1357"]:::warm
  end
  subgraph frontend_naive_ui["frontend-naive-ui"]
    naive_ui_theming["naive-ui-theming<br/>⊕103 ↻2041"]:::warm
  end
  subgraph frontend_nuxt["frontend-nuxt"]
    nuxt["nuxt<br/>⊕80 ↻1095"]:::warm
    nuxt_modules["nuxt-modules<br/>⊕125 ↻644"]:::hot
    nuxt_seo["nuxt-seo<br/>⊕50 ↻825"]:::mild
  end
  subgraph frontend_reka["frontend-reka"]
    reka_ui_cva["reka-ui-cva<br/>⊕105 ↻2007"]:::warm
  end
  subgraph frontend_tailwind["frontend-tailwind"]
    dark_mode["dark-mode<br/>⊕113 ↻2209"]:::hot
    tailwind_conventions["tailwind-conventions<br/>⊕103 ↻2249"]:::warm
  end
  subgraph frontend_vite["frontend-vite"]
    vite["vite<br/>⊕57 ↻615"]:::mild
    vite_module_loader["vite-module-loader<br/>⊕27 ↻692"]:::cool
    vite_multi_build["vite-multi-build<br/>⊕47 ↻1013"]:::mild
    vitepress["vitepress<br/>⊕49 ↻830"]:::mild
  end
  subgraph frontend_vue["frontend-vue"]
    pinia["pinia<br/>⊕54 ↻691"]:::mild
    pinia_stores["pinia-stores<br/>⊕104 ↻1920"]:::warm
    vitest["vitest<br/>⊕47 ↻817"]:::mild
    vitest_vue["vitest-vue<br/>⊕55 ↻1049"]:::mild
    vue["vue<br/>⊕63 ↻876"]:::mild
    vue_best_practices["vue-best-practices<br/>⊕99 ↻2560"]:::warm
    vue_composition_api["vue-composition-api<br/>⊕80 ↻531"]:::warm
    vue_dynamic_icons["vue-dynamic-icons<br/>⊕76 ↻1303"]:::mild
    vue_router_best_practices["vue-router-best-practices<br/>⊕126 ↻2792"]:::hot
    vue_testing_best_practices["vue-testing-best-practices<br/>⊕77 ↻2367"]:::mild
    vueuse_functions["vueuse-functions<br/>⊕34 ↻10838"]:::cool
  end
  subgraph frontend_wayfinder["frontend-wayfinder"]
    wayfinder["wayfinder<br/>⊕48 ↻994"]:::mild
  end
  subgraph general["general"]
    anti_drift["anti-drift<br/>⊕43 ↻1258"]:::mild
    compact_responses["compact-responses<br/>⊕60 ↻570"]:::mild
    complex_task_orchestrator["complex-task-orchestrator<br/>⊕44 ↻659"]:::mild
    context_economy["context-economy<br/>⊕71 ↻2380"]:::mild
    cross_layer_change_checklist["cross-layer-change-checklist<br/>⊕37 ↻461"]:::cool
    git_commit_rules["git-commit-rules<br/>⊕29 ↻1124"]:::cool
    git_safety["git-safety<br/>⊕84 ↻600"]:::warm
    grill_with_docs["grill-with-docs<br/>⊕98 ↻911"]:::warm
    implement["implement<br/>⊕88 ↻479"]:::warm
    mcp_advisor["mcp-advisor<br/>⊕107 ↻1893"]:::warm
    naming_conventions["naming-conventions<br/>⊕86 ↻1782"]:::warm
    packages_stack["packages-stack<br/>⊕85 ↻530"]:::warm
    plan_protocol["plan-protocol<br/>⊕82 ↻13812"]:::warm
    project_map["project-map<br/>⊕83 ↻645"]:::warm
    session_handoff["session-handoff<br/>⊕41 ↻618"]:::cool
    skills_ssot["skills-ssot<br/>⊕35 ↻1771"]:::cool
    spec_interview["spec-interview<br/>⊕58 ↻753"]:::mild
    task_brief_template["task-brief-template<br/>⊕79 ↻1253"]:::mild
    verify_claims["verify-claims<br/>⊕110 ↻2696"]:::hot
    workflow_craft["workflow-craft<br/>⊕48 ↻2373"]:::mild
    writing_style["writing-style<br/>⊕98 ↻1905"]:::warm
  end
  subgraph laravel_architecture["laravel-architecture"]
    config_driven_abstraction["config-driven-abstraction<br/>⊕114 ↻487"]:::hot
    eloquent_accessors["eloquent-accessors<br/>⊕119 ↻1255"]:::hot
    enum_attributes["enum-attributes<br/>⊕99 ↻1977"]:::warm
    enum_state_machine["enum-state-machine<br/>⊕104 ↻1585"]:::warm
    laravel_subagents["laravel-subagents<br/>⊕77 ↻1287"]:::mild
    modular_architecture["modular-architecture<br/>⊕83 ↻3139"]:::warm
  end
  subgraph laravel_auth["laravel-auth"]
    attribute_authorization["attribute-authorization<br/>⊕83 ↻2129"]:::warm
    laravel_permissions["laravel-permissions<br/>⊕68 ↻426"]:::mild
    laravel_security_audit["laravel-security-audit<br/>⊕51 ↻803"]:::mild
  end
  subgraph laravel_data_layer["laravel-data-layer"]
    laravel_broadcasting["laravel-broadcasting<br/>⊕40 ↻1257"]:::cool
    laravel_data["laravel-data<br/>⊕120 ↻2057"]:::hot
  end
  subgraph laravel_extras["laravel-extras"]
    medialibrary["medialibrary<br/>⊕33 ↻1048"]:::cool
    pennant_development["pennant-development<br/>⊕58 ↻505"]:::mild
    spatie_settings["spatie-settings<br/>⊕109 ↻2704"]:::hot
  end
  subgraph laravel_filament["laravel-filament"]
    filament["filament<br/>⊕63 ↻2374"]:::mild
  end
  subgraph laravel_livewire["laravel-livewire"]
    livewire_blade_attributes["livewire-blade-attributes<br/>⊕128 ↻1283"]:::hot
  end
  subgraph laravel_testing["laravel-testing"]
    health_checks["health-checks<br/>⊕100 ↻2325"]:::warm
    laravel_dusk["laravel-dusk<br/>⊕34 ↻1008"]:::cool
    laravel_testing["laravel-testing<br/>⊕56 ↻3061"]:::mild
    test_isolation_guard["test-isolation-guard<br/>⊕104 ↻1599"]:::warm
  end
  subgraph legal["legal"]
    legal_super_skill["legal-super-skill<br/>⊕93 ↻615"]:::warm
  end
  subgraph marketing["marketing"]
    marketing_super_skill["marketing-super-skill<br/>⊕95 ↻663"]:::warm
  end
  subgraph mobile["mobile"]
    figma_to_flutter["figma-to-flutter<br/>⊕107 ↻867"]:::warm
  end
  subgraph operator["operator"]
    capacity_planning["capacity-planning<br/>⊕41 ↻2083"]:::cool
    incident_response["incident-response<br/>⊕41 ↻1845"]:::cool
    oncall_rotation["oncall-rotation<br/>⊕37 ↻1708"]:::cool
    operations_cx_super_skill["operations-cx-super-skill<br/>⊕98 ↻597"]:::warm
    postmortem["postmortem<br/>⊕43 ↻1929"]:::mild
    runbook["runbook<br/>⊕36 ↻1748"]:::cool
  end
  subgraph oss_dev["oss-dev"]
    dependency_audit["dependency-audit<br/>⊕33 ↻1160"]:::cool
    dx_design["dx-design<br/>⊕31 ↻1237"]:::cool
    gh_review["gh-review<br/>⊕77 ↻1162"]:::mild
    github_flow["github-flow<br/>⊕71 ↻2090"]:::mild
    issue_triage["issue-triage<br/>⊕114 ↻2163"]:::hot
    oss_development["oss-development<br/>⊕38 ↻1392"]:::cool
    oss_governance["oss-governance<br/>⊕31 ↻1595"]:::cool
    release_engineering["release-engineering<br/>⊕37 ↻2173"]:::cool
    resolving_merge_conflicts["resolving-merge-conflicts<br/>⊕103 ↻335"]:::warm
    to_issues["to-issues<br/>⊕92 ↻1184"]:::warm
  end
  subgraph php["php"]
    code_style_spatie["code-style-spatie<br/>⊕47 ↻1127"]:::mild
    cursor_pagination_design["cursor-pagination-design<br/>⊕107 ↻412"]:::warm
    database["database<br/>⊕51 ↻961"]:::mild
    dependency_injection["dependency-injection<br/>⊕39 ↻1285"]:::cool
    laravel["laravel<br/>⊕21 ↻1573"]:::cool
    laravel_best_practices["laravel-best-practices<br/>⊕40 ↻1727"]:::cool
    laravel_structure["laravel-structure<br/>⊕44 ↻2020"]:::mild
    named_arguments["named-arguments<br/>⊕50 ↻694"]:::mild
    namespace_refactor_safety["namespace-refactor-safety<br/>⊕110 ↻365"]:::hot
    pao["pao<br/>⊕59 ↻652"]:::mild
    php_naming_conventions["php-naming-conventions<br/>⊕80 ↻1426"]:::warm
    php_patterns["php-patterns<br/>⊕25 ↻2538"]:::cool
    php_upgrade_checklist["php-upgrade-checklist<br/>⊕71 ↻672"]:::mild
    production_readiness_checklist["production-readiness-checklist<br/>⊕128 ↻575"]:::hot
    repositories["repositories<br/>⊕31 ↻1563"]:::cool
    static_analysis["static-analysis<br/>⊕35 ↻1123"]:::cool
    transactional_outbox_relay["transactional-outbox-relay<br/>⊕110 ↻585"]:::hot
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
    laravel_packages["laravel-packages<br/>⊕33 ↻788"]:::cool
  end
  subgraph pm["pm"]
    brd["brd<br/>⊕28 ↻592"]:::cool
    business_process["business-process<br/>⊕27 ↻572"]:::cool
    go_to_market["go-to-market<br/>⊕26 ↻1325"]:::cool
    monetization_design["monetization-design<br/>⊕36 ↻1400"]:::cool
    pm_super_skill["pm-super-skill<br/>⊕120 ↻618"]:::hot
    pmf_diagnostics["pmf-diagnostics<br/>⊕53 ↻1413"]:::mild
    prd_from_brd["prd-from-brd<br/>⊕38 ↻1441"]:::cool
    product_roadmap["product-roadmap<br/>⊕35 ↻1266"]:::cool
    requirement_critic["requirement-critic<br/>⊕51 ↻1606"]:::mild
    unit_economics["unit-economics<br/>⊕24 ↻839"]:::cool
  end
  subgraph python["python"]
    ml_project_structure["ml-project-structure<br/>⊕28 ↻614"]:::cool
    venv_dependencies["venv-dependencies<br/>⊕30 ↻549"]:::cool
  end
  subgraph quality["quality"]
    artifact_review["artifact-review<br/>⊕93 ↻1499"]:::warm
    code_review["code-review<br/>⊕36 ↻1622"]:::cool
    code_simplifier["code-simplifier<br/>⊕68 ↻1260"]:::mild
    diagnosing_bugs["diagnosing-bugs<br/>⊕106 ↻2577"]:::warm
    mutation_testing["mutation-testing<br/>⊕106 ↻2580"]:::warm
    playwright_e2e["playwright-e2e<br/>⊕107 ↻2544"]:::warm
    refactoring_plan["refactoring-plan<br/>⊕33 ↻1878"]:::cool
    tdd_discipline["tdd-discipline<br/>⊕100 ↻1374"]:::warm
    tech_debt_audit["tech-debt-audit<br/>⊕44 ↻2200"]:::mild
    test_strategy["test-strategy<br/>⊕61 ↻2274"]:::mild
    testing_safety_report["testing-safety-report<br/>⊕77 ↻756"]:::mild
  end
  subgraph research["research"]
    query_craft["query-craft<br/>⊕103 ↻4221"]:::warm
    research_knowledge_super_skill["research-knowledge-super-skill<br/>⊕97 ↻569"]:::warm
  end
  subgraph roles["roles"]
    open_source_maintainer["open-source-maintainer<br/>⊕19 ↻1235"]:::cool
    solo_founder["solo-founder<br/>⊕17 ↻1188"]:::cool
    startup_cto["startup-cto<br/>⊕23 ↻1417"]:::cool
    tech_lead["tech-lead<br/>⊕21 ↻1413"]:::cool
  end
  subgraph sales["sales"]
    sales_super_skill["sales-super-skill<br/>⊕108 ↻719"]:::hot
  end
  subgraph security["security"]
    agent_security_super_skill["agent-security-super-skill<br/>⊕103 ↻675"]:::warm
  end
  subgraph system["system"]
    agent_packs["agent-packs<br/>⊕120 ↻2332"]:::hot
    brain_locator["brain-locator<br/>⊕47 ↻1337"]:::mild
    cross_project_coordinator["cross-project-coordinator<br/>⊕83 ↻1430"]:::warm
    local_topology["local-topology<br/>⊕62 ↻1389"]:::mild
    session_observer["session-observer<br/>⊕117 ↻1649"]:::hot
    shared_memory["shared-memory<br/>⊕124 ↻1450"]:::hot
    swissknifeman_locator["swissknifeman-locator<br/>⊕54 ↻1425"]:::mild
  end
  subgraph voice_ai["voice-ai"]
    voice_ai["voice-ai<br/>⊕125 ↻3193"]:::hot
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

**Итого:** 215 скиллов · ⊕ always **14798** ток (резидентно всегда, если включить весь реестр) · ↻ bodies 310053 ток · ⌥ on-demand 821406 ток (сниппеты + references).

## По бакетам

| Бакет | Скиллов | ⊕ always | ↻ bodies | ⌥ on-demand |
|---|--:|--:|--:|--:|
| `general` | 21 | 1466 | 38473 | 14099 |
| `php` | 17 | 1048 | 19298 | 54837 |
| `architect` | 15 | 964 | 23520 | 33458 |
| `quality` | 11 | 831 | 20564 | 7447 |
| `frontend-vue` | 11 | 815 | 25744 | 248486 |
| `php-packages` | 9 | 685 | 5417 | 520 |
| `oss-dev` | 10 | 627 | 14491 | 10187 |
| `system` | 7 | 607 | 11012 | 834 |
| `laravel-architecture` | 6 | 596 | 9730 | 7994 |
| `devops` | 11 | 548 | 9181 | 16993 |
| `blender-modeling` | 6 | 481 | 8887 | 12586 |
| `pm` | 10 | 438 | 11072 | 23524 |
| `founder` | 10 | 406 | 15277 | 578 |
| `axioma` | 4 | 352 | 4605 | 0 |
| `frontend-linting` | 4 | 323 | 5920 | 18380 |
| `operator` | 6 | 296 | 9910 | 22461 |
| `laravel-testing` | 4 | 294 | 7993 | 15335 |
| `ai` | 3 | 284 | 4578 | 51473 |
| `frontend-backend` | 3 | 269 | 5488 | 7851 |
| `frontend` | 3 | 263 | 3795 | 5927 |
| `frontend-nuxt` | 3 | 255 | 2564 | 24048 |
| `frontend-tailwind` | 2 | 216 | 4458 | 5218 |
| `laravel-auth` | 3 | 202 | 3358 | 5640 |
| `laravel-extras` | 3 | 200 | 4257 | 7664 |
| `research` | 2 | 200 | 4790 | 20472 |
| `frontend-vite` | 4 | 180 | 3150 | 24662 |
| `laravel-data-layer` | 2 | 160 | 3314 | 3977 |
| `blender` | 2 | 140 | 2287 | 1907 |
| `laravel-livewire` | 1 | 128 | 1283 | 1117 |
| `voice-ai` | 1 | 125 | 3193 | 0 |
| `creative` | 1 | 111 | 687 | 26240 |
| `sales` | 1 | 108 | 719 | 25593 |
| `mobile` | 1 | 107 | 867 | 987 |
| `finance` | 1 | 105 | 740 | 21503 |
| `frontend-reka` | 1 | 105 | 2007 | 2536 |
| `frontend-naive-ui` | 1 | 103 | 2041 | 1337 |
| `security` | 1 | 103 | 675 | 30199 |
| `frontend-figma` | 1 | 99 | 813 | 1071 |
| `marketing` | 1 | 95 | 663 | 16617 |
| `legal` | 1 | 93 | 615 | 29248 |
| `roles` | 4 | 80 | 5253 | 177 |
| `laravel-filament` | 1 | 63 | 2374 | 3182 |
| `python` | 2 | 58 | 1163 | 0 |
| `frontend-animations` | 1 | 55 | 920 | 5285 |
| `frontend-wayfinder` | 1 | 48 | 994 | 1765 |
| `azguard` | 1 | 37 | 1679 | 7293 |
| `botkit` | 1 | 29 | 234 | 698 |

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
| `plan-protocol` | general | 13812 |
| `vueuse-functions` | frontend-vue | 10838 |
| `query-craft` | research | 4221 |
| `voice-ai` | voice-ai | 3193 |
| `modular-architecture` | laravel-architecture | 3139 |
| `laravel-testing` | laravel-testing | 3061 |
| `vue-router-best-practices` | frontend-vue | 2792 |
| `spatie-settings` | laravel-extras | 2704 |
| `verify-claims` | general | 2696 |
| `mutation-testing` | quality | 2580 |
