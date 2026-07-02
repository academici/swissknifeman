# Карта токенового бюджета

> Сгенерировано `lib/skiller/budget.py` (`skiller budget --write-map`) из `skills.json` и тел `SKILL.md` — не редактировать вручную.
> Пересборка: `skiller registry`.

Трёхъярусная модель раскрытия контекста — что грузит нейросеть и когда:

- **⊕ always** — `name`+`description`: резидентны в КАЖДОМ запросе (по ним агент решает, применять ли скилл). Постоянный «налог».
- **↻ on-trigger** — тело `SKILL.md`: грузится, только когда скилл сработал.
- **⌥ on-demand** — сниппеты: по ссылке из тела, опционально.

Цвет узла — heat по **⊕ always** (краснее = дороже постоянный налог описания). Метка `name<br/>⊕always ↻body`. Сплошная стрелка `requires` показывает транзитивный налог: ставишь скилл — тянешь always-цену зависимости. Оценка токенов грубая и языко-зависимая (кириллица ~2.2 chars/tok, латиница/код ~4) — для сравнения наборов, не точного учёта.

```mermaid
flowchart LR
  subgraph ai["ai"]
    ai_agents["ai-agents<br/>⊕75 ↻639"]:::warm
    token_efficient["token-efficient<br/>⊕95 ↻1195"]:::warm
  end
  subgraph architect["architect"]
    agent_design["agent-design<br/>⊕21 ↻1496"]:::cool
    api_design["api-design<br/>⊕22 ↻1007"]:::cool
    architecture["architecture<br/>⊕23 ↻1130"]:::cool
    codebase_design["codebase-design<br/>⊕99 ↻1746"]:::warm
    data_schema["data-schema<br/>⊕23 ↻824"]:::cool
    dev_engineering_super_skill["dev-engineering-super-skill<br/>⊕113 ↻20367"]:::hot
    domain_modeling["domain-modeling<br/>⊕104 ↻1173"]:::hot
    eval_design["eval-design<br/>⊕27 ↻1365"]:::cool
    figma_mcp_core["figma-mcp-core<br/>⊕116 ↻1385"]:::hot
    legal_compliance["legal-compliance<br/>⊕22 ↻1619"]:::cool
    observability_design["observability-design<br/>⊕27 ↻1140"]:::cool
    package_contribution_protocol["package-contribution-protocol<br/>⊕90 ↻1578"]:::warm
    security_design["security-design<br/>⊕33 ↻1861"]:::cool
    tech_stack_selection["tech-stack-selection<br/>⊕27 ↻1680"]:::cool
  end
  subgraph azguard["azguard"]
    azguard["azguard<br/>⊕31 ↻1427"]:::cool
  end
  subgraph blender["blender"]
    mcp_blender["mcp-blender<br/>⊕100 ↻1277"]:::warm
    version_gotchas["version-gotchas<br/>⊕19 ↻666"]:::cool
  end
  subgraph blender_modeling["blender-modeling"]
    build_loop["build-loop<br/>⊕108 ↻1816"]:::hot
    config_conventions["config-conventions<br/>⊕97 ↻1999"]:::warm
    model_rules["model-rules<br/>⊕26 ↻647"]:::cool
    parametric_config["parametric-config<br/>⊕94 ↻1873"]:::warm
    scene_conventions["scene-conventions<br/>⊕81 ↻777"]:::warm
    threading["threading<br/>⊕23 ↻561"]:::cool
  end
  subgraph botkit["botkit"]
    botkit["botkit<br/>⊕25 ↻199"]:::cool
  end
  subgraph creative["creative"]
    content_creative_super_skill["content-creative-super-skill<br/>⊕132 ↻22304"]:::hot
  end
  subgraph devops["devops"]
    ci_cd["ci-cd<br/>⊕46 ↻978"]:::mild
    db_test_preflight["db-test-preflight<br/>⊕88 ↻1448"]:::warm
    docker["docker<br/>⊕56 ↻340"]:::mild
    docker_dev_prod["docker-dev-prod<br/>⊕36 ↻809"]:::mild
    docker_php["docker-php<br/>⊕34 ↻675"]:::cool
    docker_postgres["docker-postgres<br/>⊕36 ↻709"]:::mild
    docker_services["docker-services<br/>⊕41 ↻752"]:::mild
    docker_vite["docker-vite<br/>⊕33 ↻600"]:::cool
    gitops["gitops<br/>⊕25 ↻631"]:::cool
    makefile["makefile<br/>⊕36 ↻645"]:::mild
    node_pnpm_preflight["node-pnpm-preflight<br/>⊕32 ↻217"]:::cool
  end
  subgraph finance["finance"]
    finance_super_skill["finance-super-skill<br/>⊕152 ↻18278"]:::hot
  end
  subgraph founder["founder"]
    adversarial_check["adversarial-check<br/>⊕47 ↻987"]:::mild
    competitive_analysis["competitive-analysis<br/>⊕26 ↻1146"]:::cool
    customer_discovery["customer-discovery<br/>⊕46 ↻1147"]:::mild
    defensibility["defensibility<br/>⊕36 ↻979"]:::mild
    idea_audit["idea-audit<br/>⊕52 ↻2126"]:::mild
    idea_discovery["idea-discovery<br/>⊕29 ↻1458"]:::cool
    new_project["new-project<br/>⊕23 ↻1182"]:::cool
    pitch_deck["pitch-deck<br/>⊕22 ↻1396"]:::cool
    risk_assessment["risk-assessment<br/>⊕27 ↻1107"]:::cool
    startup_lifecycle["startup-lifecycle<br/>⊕35 ↻1509"]:::mild
  end
  subgraph frontend["frontend"]
    document_writer["document-writer<br/>⊕74 ↻1090"]:::warm
    filepond_upload["filepond-upload<br/>⊕116 ↻1906"]:::hot
    web_design_guidelines["web-design-guidelines<br/>⊕52 ↻229"]:::mild
  end
  subgraph frontend_animations["frontend-animations"]
    motion["motion<br/>⊕47 ↻782"]:::mild
  end
  subgraph frontend_backend["frontend-backend"]
    backend_type_sync["backend-type-sync<br/>⊕85 ↻1772"]:::warm
    inertia_vue["inertia-vue<br/>⊕49 ↻1289"]:::mild
    laravel_echo_client["laravel-echo-client<br/>⊕110 ↻1638"]:::hot
  end
  subgraph frontend_figma["frontend-figma"]
    figma_to_vue["figma-to-vue<br/>⊕84 ↻691"]:::warm
  end
  subgraph frontend_linting["frontend-linting"]
    antfu["antfu<br/>⊕63 ↻1090"]:::mild
    eslint_flat_config["eslint-flat-config<br/>⊕95 ↻2049"]:::warm
    js_code_style["js-code-style<br/>⊕40 ↻975"]:::mild
    ts_library["ts-library<br/>⊕77 ↻1153"]:::warm
  end
  subgraph frontend_naive_ui["frontend-naive-ui"]
    naive_ui_theming["naive-ui-theming<br/>⊕87 ↻1735"]:::warm
  end
  subgraph frontend_nuxt["frontend-nuxt"]
    nuxt["nuxt<br/>⊕68 ↻930"]:::warm
    nuxt_modules["nuxt-modules<br/>⊕106 ↻547"]:::hot
    nuxt_seo["nuxt-seo<br/>⊕42 ↻702"]:::mild
  end
  subgraph frontend_reka["frontend-reka"]
    reka_ui_cva["reka-ui-cva<br/>⊕90 ↻1706"]:::warm
  end
  subgraph frontend_tailwind["frontend-tailwind"]
    dark_mode["dark-mode<br/>⊕96 ↻1878"]:::warm
    tailwind_conventions["tailwind-conventions<br/>⊕108 ↻1911"]:::hot
  end
  subgraph frontend_vite["frontend-vite"]
    vite["vite<br/>⊕48 ↻523"]:::mild
    vite_module_loader["vite-module-loader<br/>⊕23 ↻599"]:::cool
    vite_multi_build["vite-multi-build<br/>⊕40 ↻861"]:::mild
    vitepress["vitepress<br/>⊕42 ↻705"]:::mild
  end
  subgraph frontend_vue["frontend-vue"]
    pinia["pinia<br/>⊕46 ↻587"]:::mild
    pinia_stores["pinia-stores<br/>⊕109 ↻1639"]:::hot
    vitest["vitest<br/>⊕40 ↻694"]:::mild
    vitest_vue["vitest-vue<br/>⊕47 ↻923"]:::mild
    vue["vue<br/>⊕54 ↻793"]:::mild
    vue_best_practices["vue-best-practices<br/>⊕84 ↻2198"]:::warm
    vue_composition_api["vue-composition-api<br/>⊕68 ↻453"]:::warm
    vue_dynamic_icons["vue-dynamic-icons<br/>⊕64 ↻1107"]:::mild
    vue_router_best_practices["vue-router-best-practices<br/>⊕120 ↻2970"]:::hot
    vue_testing_best_practices["vue-testing-best-practices<br/>⊕65 ↻2494"]:::mild
    vueuse_functions["vueuse-functions<br/>⊕29 ↻9212"]:::cool
  end
  subgraph frontend_wayfinder["frontend-wayfinder"]
    wayfinder["wayfinder<br/>⊕41 ↻845"]:::mild
  end
  subgraph general["general"]
    anti_drift["anti-drift<br/>⊕37 ↻1069"]:::mild
    compact_responses["compact-responses<br/>⊕51 ↻503"]:::mild
    complex_task_orchestrator["complex-task-orchestrator<br/>⊕38 ↻534"]:::mild
    context_economy["context-economy<br/>⊕61 ↻1813"]:::mild
    cross_layer_change_checklist["cross-layer-change-checklist<br/>⊕31 ↻394"]:::cool
    git_commit_rules["git-commit-rules<br/>⊕24 ↻834"]:::cool
    git_safety["git-safety<br/>⊕71 ↻615"]:::warm
    grill_with_docs["grill-with-docs<br/>⊕84 ↻1053"]:::warm
    implement["implement<br/>⊕75 ↻515"]:::warm
    mcp_advisor["mcp-advisor<br/>⊕91 ↻1609"]:::warm
    naming_conventions["naming-conventions<br/>⊕73 ↻1329"]:::warm
    packages_stack["packages-stack<br/>⊕72 ↻451"]:::warm
    project_map["project-map<br/>⊕70 ↻549"]:::warm
    session_handoff["session-handoff<br/>⊕35 ↻438"]:::mild
    skills_ssot["skills-ssot<br/>⊕30 ↻1505"]:::cool
    spec_interview["spec-interview<br/>⊕49 ↻640"]:::mild
    task_brief_template["task-brief-template<br/>⊕67 ↻1178"]:::warm
    verify_claims["verify-claims<br/>⊕113 ↻2306"]:::hot
    writing_style["writing-style<br/>⊕83 ↻1556"]:::warm
  end
  subgraph laravel_architecture["laravel-architecture"]
    config_driven_abstraction["config-driven-abstraction<br/>⊕115 ↻414"]:::hot
    eloquent_accessors["eloquent-accessors<br/>⊕101 ↻1067"]:::warm
    enum_attributes["enum-attributes<br/>⊕111 ↻1681"]:::hot
    enum_state_machine["enum-state-machine<br/>⊕112 ↻1347"]:::hot
    laravel_subagents["laravel-subagents<br/>⊕65 ↻1106"]:::mild
    modular_architecture["modular-architecture<br/>⊕71 ↻2668"]:::warm
  end
  subgraph laravel_auth["laravel-auth"]
    attribute_authorization["attribute-authorization<br/>⊕71 ↻1810"]:::warm
    laravel_permissions["laravel-permissions<br/>⊕58 ↻362"]:::mild
    laravel_security_audit["laravel-security-audit<br/>⊕43 ↻682"]:::mild
  end
  subgraph laravel_data_layer["laravel-data-layer"]
    laravel_broadcasting["laravel-broadcasting<br/>⊕34 ↻1279"]:::cool
    laravel_data["laravel-data<br/>⊕102 ↻1749"]:::hot
  end
  subgraph laravel_extras["laravel-extras"]
    medialibrary["medialibrary<br/>⊕28 ↻890"]:::cool
    pennant_development["pennant-development<br/>⊕49 ↻535"]:::mild
    spatie_settings["spatie-settings<br/>⊕114 ↻2298"]:::hot
  end
  subgraph laravel_filament["laravel-filament"]
    filament["filament<br/>⊕53 ↻2311"]:::mild
  end
  subgraph laravel_livewire["laravel-livewire"]
    livewire_blade_attributes["livewire-blade-attributes<br/>⊕109 ↻1091"]:::hot
  end
  subgraph laravel_testing["laravel-testing"]
    health_checks["health-checks<br/>⊕109 ↻1977"]:::hot
    laravel_dusk["laravel-dusk<br/>⊕29 ↻857"]:::cool
    laravel_testing["laravel-testing<br/>⊕48 ↻2639"]:::mild
    test_isolation_guard["test-isolation-guard<br/>⊕88 ↻1359"]:::warm
  end
  subgraph legal["legal"]
    legal_super_skill["legal-super-skill<br/>⊕123 ↻24861"]:::hot
  end
  subgraph marketing["marketing"]
    marketing_super_skill["marketing-super-skill<br/>⊕121 ↻14124"]:::hot
  end
  subgraph mobile["mobile"]
    figma_to_flutter["figma-to-flutter<br/>⊕91 ↻737"]:::warm
  end
  subgraph operator["operator"]
    capacity_planning["capacity-planning<br/>⊕35 ↻1789"]:::mild
    incident_response["incident-response<br/>⊕35 ↻1568"]:::mild
    oncall_rotation["oncall-rotation<br/>⊕32 ↻1506"]:::cool
    operations_cx_super_skill["operations-cx-super-skill<br/>⊕83 ↻19002"]:::warm
    postmortem["postmortem<br/>⊕37 ↻1713"]:::mild
    runbook["runbook<br/>⊕30 ↻1485"]:::cool
  end
  subgraph oss_dev["oss-dev"]
    dependency_audit["dependency-audit<br/>⊕28 ↻994"]:::cool
    dx_design["dx-design<br/>⊕27 ↻1051"]:::cool
    gh_review["gh-review<br/>⊕65 ↻988"]:::mild
    github_flow["github-flow<br/>⊕60 ↻1776"]:::mild
    issue_triage["issue-triage<br/>⊕97 ↻1914"]:::warm
    oss_development["oss-development<br/>⊕32 ↻1266"]:::cool
    oss_governance["oss-governance<br/>⊕26 ↻1356"]:::cool
    release_engineering["release-engineering<br/>⊕32 ↻1411"]:::cool
    resolving_merge_conflicts["resolving-merge-conflicts<br/>⊕87 ↻302"]:::warm
    to_issues["to-issues<br/>⊕78 ↻1083"]:::warm
  end
  subgraph php["php"]
    code_style_spatie["code-style-spatie<br/>⊕40 ↻1238"]:::mild
    cursor_pagination_design["cursor-pagination-design<br/>⊕115 ↻350"]:::hot
    database["database<br/>⊕44 ↻817"]:::mild
    dependency_injection["dependency-injection<br/>⊕33 ↻1093"]:::cool
    laravel["laravel<br/>⊕18 ↻1337"]:::cool
    laravel_best_practices["laravel-best-practices<br/>⊕34 ↻1868"]:::cool
    laravel_structure["laravel-structure<br/>⊕37 ↻1717"]:::mild
    named_arguments["named-arguments<br/>⊕42 ↻590"]:::mild
    namespace_refactor_safety["namespace-refactor-safety<br/>⊕111 ↻310"]:::hot
    pao["pao<br/>⊕50 ↻556"]:::mild
    php_naming_conventions["php-naming-conventions<br/>⊕68 ↻1212"]:::warm
    php_patterns["php-patterns<br/>⊕21 ↻2157"]:::cool
    php_upgrade_checklist["php-upgrade-checklist<br/>⊕61 ↻571"]:::mild
    production_readiness_checklist["production-readiness-checklist<br/>⊕109 ↻489"]:::hot
    repositories["repositories<br/>⊕26 ↻1329"]:::cool
    static_analysis["static-analysis<br/>⊕29 ↻954"]:::cool
    transactional_outbox_relay["transactional-outbox-relay<br/>⊕114 ↻497"]:::hot
  end
  subgraph php_packages["php-packages"]
    laravel_package_compatibility["laravel-package-compatibility<br/>⊕65 ↻379"]:::mild
    laravel_package_docs["laravel-package-docs<br/>⊕63 ↻606"]:::mild
    laravel_package_expressive["laravel-package-expressive<br/>⊕97 ↻491"]:::warm
    laravel_package_generate_skill["laravel-package-generate-skill<br/>⊕71 ↻684"]:::warm
    laravel_package_release["laravel-package-release<br/>⊕58 ↻325"]:::mild
    laravel_package_scaffold["laravel-package-scaffold<br/>⊕66 ↻523"]:::warm
    laravel_package_service_provider["laravel-package-service-provider<br/>⊕62 ↻468"]:::mild
    laravel_package_testing["laravel-package-testing<br/>⊕72 ↻463"]:::warm
    laravel_packages["laravel-packages<br/>⊕28 ↻670"]:::cool
  end
  subgraph pm["pm"]
    brd["brd<br/>⊕24 ↻505"]:::cool
    business_process["business-process<br/>⊕23 ↻508"]:::cool
    go_to_market["go-to-market<br/>⊕22 ↻1127"]:::cool
    monetization_design["monetization-design<br/>⊕31 ↻1236"]:::cool
    pm_super_skill["pm-super-skill<br/>⊕102 ↻19581"]:::hot
    pmf_diagnostics["pmf-diagnostics<br/>⊕45 ↻1201"]:::mild
    prd_from_brd["prd-from-brd<br/>⊕32 ↻1225"]:::cool
    product_roadmap["product-roadmap<br/>⊕30 ↻1162"]:::cool
    requirement_critic["requirement-critic<br/>⊕44 ↻1420"]:::mild
    unit_economics["unit-economics<br/>⊕20 ↻713"]:::cool
  end
  subgraph python["python"]
    ml_project_structure["ml-project-structure<br/>⊕24 ↻522"]:::cool
    venv_dependencies["venv-dependencies<br/>⊕25 ↻474"]:::cool
  end
  subgraph quality["quality"]
    code_review["code-review<br/>⊕31 ↻1401"]:::cool
    code_simplifier["code-simplifier<br/>⊕57 ↻1071"]:::mild
    diagnosing_bugs["diagnosing-bugs<br/>⊕90 ↻2221"]:::warm
    mutation_testing["mutation-testing<br/>⊕90 ↻2193"]:::warm
    playwright_e2e["playwright-e2e<br/>⊕91 ↻2162"]:::warm
    refactoring_plan["refactoring-plan<br/>⊕28 ↻1596"]:::cool
    tdd_discipline["tdd-discipline<br/>⊕85 ↻1201"]:::warm
    tech_debt_audit["tech-debt-audit<br/>⊕38 ↻1870"]:::mild
    test_strategy["test-strategy<br/>⊕52 ↻1969"]:::mild
    testing_safety_report["testing-safety-report<br/>⊕66 ↻659"]:::warm
  end
  subgraph research["research"]
    query_craft["query-craft<br/>⊕110 ↻3339"]:::hot
    research_knowledge_super_skill["research-knowledge-super-skill<br/>⊕165 ↻17401"]:::hot
  end
  subgraph roles["roles"]
    open_source_maintainer["open-source-maintainer<br/>⊕16 ↻1050"]:::cool
    solo_founder["solo-founder<br/>⊕14 ↻1009"]:::cool
    startup_cto["startup-cto<br/>⊕19 ↻1204"]:::cool
    tech_lead["tech-lead<br/>⊕18 ↻1201"]:::cool
  end
  subgraph sales["sales"]
    sales_super_skill["sales-super-skill<br/>⊕121 ↻21754"]:::hot
  end
  subgraph security["security"]
    agent_security_super_skill["agent-security-super-skill<br/>⊕156 ↻25669"]:::hot
  end
  subgraph system["system"]
    agent_packs["agent-packs<br/>⊕102 ↻1982"]:::hot
    brain_locator["brain-locator<br/>⊕40 ↻1136"]:::mild
    cross_project_coordinator["cross-project-coordinator<br/>⊕70 ↻1215"]:::warm
    local_topology["local-topology<br/>⊕53 ↻1181"]:::mild
    session_observer["session-observer<br/>⊕99 ↻1402"]:::warm
    shared_memory["shared-memory<br/>⊕105 ↻1233"]:::hot
    swissknifeman_locator["swissknifeman-locator<br/>⊕46 ↻1211"]:::mild
  end
  agent_design -->|requires| architecture
  api_design -->|requires| data_schema
  architecture -->|requires| brd
  architecture -->|requires| tech_stack_selection
  attribute_authorization -->|requires| laravel_permissions
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

**Итого:** 205 скиллов · ⊕ always **12522** ток (резидентно всегда, если включить весь реестр) · ↻ bodies 439183 ток · ⌥ snippets 158040 ток.

## По бакетам

| Бакет | Скиллов | ⊕ always | ↻ bodies | ⌥ snippets |
|---|--:|--:|--:|--:|
| `general` | 19 | 1155 | 18891 | 5131 |
| `php` | 17 | 952 | 17085 | 26763 |
| `architect` | 14 | 747 | 38371 | 7503 |
| `frontend-vue` | 11 | 726 | 23070 | 7058 |
| `quality` | 10 | 628 | 16343 | 7125 |
| `php-packages` | 9 | 582 | 4609 | 489 |
| `laravel-architecture` | 6 | 575 | 8283 | 7460 |
| `oss-dev` | 10 | 532 | 12141 | 4313 |
| `system` | 7 | 515 | 9360 | 797 |
| `devops` | 11 | 463 | 7804 | 15388 |
| `blender-modeling` | 6 | 429 | 7673 | 11772 |
| `pm` | 10 | 373 | 28678 | 197 |
| `founder` | 10 | 343 | 13037 | 494 |
| `frontend-linting` | 4 | 275 | 5267 | 2914 |
| `research` | 2 | 275 | 20740 | 0 |
| `laravel-testing` | 4 | 274 | 6832 | 14531 |
| `operator` | 6 | 252 | 27063 | 90 |
| `frontend-backend` | 3 | 244 | 4699 | 7459 |
| `frontend` | 3 | 242 | 3225 | 3393 |
| `frontend-nuxt` | 3 | 216 | 2179 | 0 |
| `frontend-tailwind` | 2 | 204 | 3789 | 4980 |
| `laravel-extras` | 3 | 191 | 3723 | 3192 |
| `laravel-auth` | 3 | 172 | 2854 | 3020 |
| `ai` | 2 | 170 | 1834 | 0 |
| `security` | 1 | 156 | 25669 | 0 |
| `frontend-vite` | 4 | 153 | 2688 | 1351 |
| `finance` | 1 | 152 | 18278 | 0 |
| `laravel-data-layer` | 2 | 136 | 3028 | 3785 |
| `creative` | 1 | 132 | 22304 | 0 |
| `legal` | 1 | 123 | 24861 | 0 |
| `marketing` | 1 | 121 | 14124 | 0 |
| `sales` | 1 | 121 | 21754 | 0 |
| `blender` | 2 | 119 | 1943 | 325 |
| `laravel-livewire` | 1 | 109 | 1091 | 1079 |
| `mobile` | 1 | 91 | 737 | 884 |
| `frontend-reka` | 1 | 90 | 1706 | 2414 |
| `frontend-naive-ui` | 1 | 87 | 1735 | 1270 |
| `frontend-figma` | 1 | 84 | 691 | 949 |
| `roles` | 4 | 67 | 4464 | 148 |
| `laravel-filament` | 1 | 53 | 2311 | 2749 |
| `python` | 2 | 49 | 996 | 0 |
| `frontend-animations` | 1 | 47 | 782 | 0 |
| `frontend-wayfinder` | 1 | 41 | 845 | 1658 |
| `azguard` | 1 | 31 | 1427 | 6767 |
| `botkit` | 1 | 25 | 199 | 592 |

## Топ ⊕ always (постоянный налог)

Самые дорогие описания — резидентны в каждом запросе.

| Скилл | Бакет | ток |
|---|---|--:|
| `research-knowledge-super-skill` | research | 165 |
| `agent-security-super-skill` | security | 156 |
| `finance-super-skill` | finance | 152 |
| `content-creative-super-skill` | creative | 132 |
| `legal-super-skill` | legal | 123 |
| `marketing-super-skill` | marketing | 121 |
| `sales-super-skill` | sales | 121 |
| `vue-router-best-practices` | frontend-vue | 120 |
| `figma-mcp-core` | architect | 116 |
| `filepond-upload` | frontend | 116 |

## Топ ↻ on-trigger (цена срабатывания)

Самые тяжёлые тела — грузятся при применении скилла.

| Скилл | Бакет | ток |
|---|---|--:|
| `agent-security-super-skill` | security | 25669 |
| `legal-super-skill` | legal | 24861 |
| `content-creative-super-skill` | creative | 22304 |
| `sales-super-skill` | sales | 21754 |
| `dev-engineering-super-skill` | architect | 20367 |
| `pm-super-skill` | pm | 19581 |
| `operations-cx-super-skill` | operator | 19002 |
| `finance-super-skill` | finance | 18278 |
| `research-knowledge-super-skill` | research | 17401 |
| `marketing-super-skill` | marketing | 14124 |
