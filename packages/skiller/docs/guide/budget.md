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
    agent_design["agent-design<br/>⊕21 ↻1505"]:::cool
    api_design["api-design<br/>⊕22 ↻1016"]:::cool
    architecture["architecture<br/>⊕23 ↻1139"]:::cool
    codebase_design["codebase-design<br/>⊕99 ↻1746"]:::hot
    data_schema["data-schema<br/>⊕23 ↻833"]:::cool
    dev_engineering_super_skill["dev-engineering-super-skill<br/>⊕113 ↻20367"]:::hot
    domain_modeling["domain-modeling<br/>⊕104 ↻1173"]:::hot
    eval_design["eval-design<br/>⊕27 ↻1374"]:::cool
    figma_mcp_core["figma-mcp-core<br/>⊕116 ↻1394"]:::hot
    legal_compliance["legal-compliance<br/>⊕22 ↻1628"]:::cool
    observability_design["observability-design<br/>⊕27 ↻1149"]:::cool
    package_contribution_protocol["package-contribution-protocol<br/>⊕90 ↻1587"]:::warm
    security_design["security-design<br/>⊕33 ↻1870"]:::cool
    tech_stack_selection["tech-stack-selection<br/>⊕27 ↻1689"]:::cool
  end
  subgraph azguard["azguard"]
    azguard["azguard<br/>⊕31 ↻1436"]:::cool
  end
  subgraph blender["blender"]
    mcp_blender["mcp-blender<br/>⊕100 ↻1286"]:::hot
    version_gotchas["version-gotchas<br/>⊕19 ↻675"]:::cool
  end
  subgraph blender_modeling["blender-modeling"]
    build_loop["build-loop<br/>⊕108 ↻1825"]:::hot
    config_conventions["config-conventions<br/>⊕97 ↻2008"]:::warm
    model_rules["model-rules<br/>⊕26 ↻656"]:::cool
    parametric_config["parametric-config<br/>⊕94 ↻1882"]:::warm
    scene_conventions["scene-conventions<br/>⊕81 ↻786"]:::warm
    threading["threading<br/>⊕23 ↻570"]:::cool
  end
  subgraph botkit["botkit"]
    botkit["botkit<br/>⊕25 ↻208"]:::cool
  end
  subgraph creative["creative"]
    content_creative_super_skill["content-creative-super-skill<br/>⊕132 ↻22304"]:::hot
  end
  subgraph devops["devops"]
    ci_cd["ci-cd<br/>⊕46 ↻987"]:::mild
    db_test_preflight["db-test-preflight<br/>⊕88 ↻1457"]:::warm
    docker["docker<br/>⊕44 ↻100"]:::mild
    docker_dev_prod["docker-dev-prod<br/>⊕36 ↻818"]:::mild
    docker_php["docker-php<br/>⊕34 ↻684"]:::mild
    docker_postgres["docker-postgres<br/>⊕36 ↻718"]:::mild
    docker_services["docker-services<br/>⊕41 ↻761"]:::mild
    docker_vite["docker-vite<br/>⊕33 ↻609"]:::cool
    gitops["gitops<br/>⊕25 ↻640"]:::cool
    makefile["makefile<br/>⊕36 ↻654"]:::mild
    node_pnpm_preflight["node-pnpm-preflight<br/>⊕32 ↻226"]:::cool
  end
  subgraph finance["finance"]
    finance_super_skill["finance-super-skill<br/>⊕152 ↻18278"]:::hot
  end
  subgraph founder["founder"]
    adversarial_check["adversarial-check<br/>⊕47 ↻996"]:::mild
    competitive_analysis["competitive-analysis<br/>⊕26 ↻1155"]:::cool
    customer_discovery["customer-discovery<br/>⊕46 ↻1156"]:::mild
    defensibility["defensibility<br/>⊕36 ↻988"]:::mild
    idea_audit["idea-audit<br/>⊕52 ↻2135"]:::mild
    idea_discovery["idea-discovery<br/>⊕29 ↻1467"]:::cool
    new_project["new-project<br/>⊕23 ↻1191"]:::cool
    pitch_deck["pitch-deck<br/>⊕22 ↻1405"]:::cool
    risk_assessment["risk-assessment<br/>⊕27 ↻1116"]:::cool
    startup_lifecycle["startup-lifecycle<br/>⊕35 ↻1518"]:::mild
  end
  subgraph frontend["frontend"]
    document_writer["document-writer<br/>⊕74 ↻1090"]:::warm
    filepond_upload["filepond-upload<br/>⊕116 ↻1915"]:::hot
    web_design_guidelines["web-design-guidelines<br/>⊕52 ↻229"]:::mild
  end
  subgraph frontend_animations["frontend-animations"]
    motion["motion<br/>⊕47 ↻782"]:::mild
  end
  subgraph frontend_backend["frontend-backend"]
    backend_type_sync["backend-type-sync<br/>⊕85 ↻1781"]:::warm
    inertia_vue["inertia-vue<br/>⊕49 ↻1298"]:::mild
    laravel_echo_client["laravel-echo-client<br/>⊕110 ↻1647"]:::hot
  end
  subgraph frontend_figma["frontend-figma"]
    figma_to_vue["figma-to-vue<br/>⊕84 ↻700"]:::warm
  end
  subgraph frontend_linting["frontend-linting"]
    antfu["antfu<br/>⊕63 ↻1090"]:::mild
    eslint_flat_config["eslint-flat-config<br/>⊕95 ↻2058"]:::warm
    js_code_style["js-code-style<br/>⊕40 ↻975"]:::mild
    ts_library["ts-library<br/>⊕77 ↻1153"]:::warm
  end
  subgraph frontend_naive_ui["frontend-naive-ui"]
    naive_ui_theming["naive-ui-theming<br/>⊕87 ↻1744"]:::warm
  end
  subgraph frontend_nuxt["frontend-nuxt"]
    nuxt["nuxt<br/>⊕68 ↻930"]:::warm
    nuxt_modules["nuxt-modules<br/>⊕106 ↻547"]:::hot
    nuxt_seo["nuxt-seo<br/>⊕42 ↻702"]:::mild
  end
  subgraph frontend_reka["frontend-reka"]
    reka_ui_cva["reka-ui-cva<br/>⊕90 ↻1715"]:::warm
  end
  subgraph frontend_tailwind["frontend-tailwind"]
    dark_mode["dark-mode<br/>⊕96 ↻1887"]:::warm
    tailwind_conventions["tailwind-conventions<br/>⊕108 ↻1920"]:::hot
  end
  subgraph frontend_vite["frontend-vite"]
    vite["vite<br/>⊕48 ↻523"]:::mild
    vite_module_loader["vite-module-loader<br/>⊕23 ↻608"]:::cool
    vite_multi_build["vite-multi-build<br/>⊕40 ↻870"]:::mild
    vitepress["vitepress<br/>⊕42 ↻705"]:::mild
  end
  subgraph frontend_vue["frontend-vue"]
    pinia["pinia<br/>⊕46 ↻587"]:::mild
    pinia_stores["pinia-stores<br/>⊕109 ↻1648"]:::hot
    vitest["vitest<br/>⊕40 ↻703"]:::mild
    vitest_vue["vitest-vue<br/>⊕47 ↻923"]:::mild
    vue["vue<br/>⊕54 ↻793"]:::mild
    vue_best_practices["vue-best-practices<br/>⊕84 ↻2198"]:::warm
    vue_composition_api["vue-composition-api<br/>⊕68 ↻462"]:::warm
    vue_dynamic_icons["vue-dynamic-icons<br/>⊕64 ↻1116"]:::mild
    vue_router_best_practices["vue-router-best-practices<br/>⊕120 ↻2970"]:::hot
    vue_testing_best_practices["vue-testing-best-practices<br/>⊕65 ↻2494"]:::warm
    vueuse_functions["vueuse-functions<br/>⊕29 ↻9212"]:::cool
  end
  subgraph frontend_wayfinder["frontend-wayfinder"]
    wayfinder["wayfinder<br/>⊕41 ↻854"]:::mild
  end
  subgraph general["general"]
    anti_drift["anti-drift<br/>⊕37 ↻854"]:::mild
    compact_responses["compact-responses<br/>⊕51 ↻385"]:::mild
    complex_task_orchestrator["complex-task-orchestrator<br/>⊕38 ↻543"]:::mild
    context_economy["context-economy<br/>⊕61 ↻1146"]:::mild
    cross_layer_change_checklist["cross-layer-change-checklist<br/>⊕31 ↻403"]:::cool
    git_commit_rules["git-commit-rules<br/>⊕24 ↻843"]:::cool
    git_safety["git-safety<br/>⊕71 ↻615"]:::warm
    grill_with_docs["grill-with-docs<br/>⊕84 ↻1053"]:::warm
    implement["implement<br/>⊕75 ↻515"]:::warm
    mcp_advisor["mcp-advisor<br/>⊕91 ↻1599"]:::warm
    naming_conventions["naming-conventions<br/>⊕73 ↻1338"]:::warm
    packages_stack["packages-stack<br/>⊕72 ↻460"]:::warm
    project_map["project-map<br/>⊕70 ↻558"]:::warm
    session_handoff["session-handoff<br/>⊕35 ↻441"]:::mild
    skills_ssot["skills-ssot<br/>⊕30 ↻1514"]:::cool
    spec_interview["spec-interview<br/>⊕49 ↻649"]:::mild
    task_brief_template["task-brief-template<br/>⊕67 ↻1187"]:::warm
    verify_claims["verify-claims<br/>⊕136 ↻1408"]:::hot
    writing_style["writing-style<br/>⊕83 ↻1565"]:::warm
  end
  subgraph laravel_architecture["laravel-architecture"]
    eloquent_accessors["eloquent-accessors<br/>⊕101 ↻1067"]:::hot
    enum_attributes["enum-attributes<br/>⊕111 ↻1690"]:::hot
    enum_state_machine["enum-state-machine<br/>⊕135 ↻1356"]:::hot
    laravel_subagents["laravel-subagents<br/>⊕65 ↻1115"]:::warm
    modular_architecture["modular-architecture<br/>⊕71 ↻2677"]:::warm
  end
  subgraph laravel_auth["laravel-auth"]
    attribute_authorization["attribute-authorization<br/>⊕71 ↻1819"]:::warm
    laravel_permissions["laravel-permissions<br/>⊕58 ↻371"]:::mild
    laravel_security_audit["laravel-security-audit<br/>⊕43 ↻691"]:::mild
  end
  subgraph laravel_data_layer["laravel-data-layer"]
    laravel_broadcasting["laravel-broadcasting<br/>⊕34 ↻1279"]:::mild
    laravel_data["laravel-data<br/>⊕102 ↻1758"]:::hot
  end
  subgraph laravel_extras["laravel-extras"]
    medialibrary["medialibrary<br/>⊕28 ↻899"]:::cool
    pennant_development["pennant-development<br/>⊕49 ↻535"]:::mild
    spatie_settings["spatie-settings<br/>⊕114 ↻2307"]:::hot
  end
  subgraph laravel_filament["laravel-filament"]
    filament["filament<br/>⊕53 ↻2311"]:::mild
  end
  subgraph laravel_livewire["laravel-livewire"]
    livewire_blade_attributes["livewire-blade-attributes<br/>⊕132 ↻1100"]:::hot
  end
  subgraph laravel_testing["laravel-testing"]
    health_checks["health-checks<br/>⊕118 ↻1986"]:::hot
    laravel_dusk["laravel-dusk<br/>⊕29 ↻866"]:::cool
    laravel_testing["laravel-testing<br/>⊕48 ↻2648"]:::mild
    test_isolation_guard["test-isolation-guard<br/>⊕88 ↻1368"]:::warm
  end
  subgraph legal["legal"]
    legal_super_skill["legal-super-skill<br/>⊕123 ↻24861"]:::hot
  end
  subgraph marketing["marketing"]
    marketing_super_skill["marketing-super-skill<br/>⊕121 ↻14124"]:::hot
  end
  subgraph mobile["mobile"]
    figma_to_flutter["figma-to-flutter<br/>⊕91 ↻746"]:::warm
  end
  subgraph operator["operator"]
    capacity_planning["capacity-planning<br/>⊕35 ↻1798"]:::mild
    incident_response["incident-response<br/>⊕35 ↻1577"]:::mild
    oncall_rotation["oncall-rotation<br/>⊕32 ↻1515"]:::cool
    operations_cx_super_skill["operations-cx-super-skill<br/>⊕83 ↻19002"]:::warm
    postmortem["postmortem<br/>⊕37 ↻1722"]:::mild
    runbook["runbook<br/>⊕30 ↻1494"]:::cool
  end
  subgraph oss_dev["oss-dev"]
    dependency_audit["dependency-audit<br/>⊕28 ↻1003"]:::cool
    dx_design["dx-design<br/>⊕27 ↻1060"]:::cool
    gh_review["gh-review<br/>⊕65 ↻997"]:::warm
    github_flow["github-flow<br/>⊕60 ↻1785"]:::mild
    issue_triage["issue-triage<br/>⊕97 ↻1914"]:::warm
    oss_development["oss-development<br/>⊕32 ↻1275"]:::cool
    oss_governance["oss-governance<br/>⊕26 ↻1365"]:::cool
    release_engineering["release-engineering<br/>⊕32 ↻1420"]:::cool
    resolving_merge_conflicts["resolving-merge-conflicts<br/>⊕87 ↻302"]:::warm
    to_issues["to-issues<br/>⊕78 ↻1083"]:::warm
  end
  subgraph php["php"]
    code_style_spatie["code-style-spatie<br/>⊕40 ↻1238"]:::mild
    database["database<br/>⊕44 ↻826"]:::mild
    dependency_injection["dependency-injection<br/>⊕33 ↻1102"]:::cool
    laravel["laravel<br/>⊕18 ↻1346"]:::cool
    laravel_best_practices["laravel-best-practices<br/>⊕34 ↻1868"]:::mild
    laravel_structure["laravel-structure<br/>⊕37 ↻1726"]:::mild
    named_arguments["named-arguments<br/>⊕42 ↻599"]:::mild
    pao["pao<br/>⊕50 ↻565"]:::mild
    php_naming_conventions["php-naming-conventions<br/>⊕68 ↻1221"]:::warm
    php_patterns["php-patterns<br/>⊕21 ↻2166"]:::cool
    php_upgrade_checklist["php-upgrade-checklist<br/>⊕61 ↻580"]:::mild
    repositories["repositories<br/>⊕26 ↻1338"]:::cool
    static_analysis["static-analysis<br/>⊕29 ↻963"]:::cool
  end
  subgraph php_packages["php-packages"]
    laravel_package_compatibility["laravel-package-compatibility<br/>⊕65 ↻379"]:::warm
    laravel_package_docs["laravel-package-docs<br/>⊕63 ↻606"]:::mild
    laravel_package_expressive["laravel-package-expressive<br/>⊕97 ↻491"]:::warm
    laravel_package_generate_skill["laravel-package-generate-skill<br/>⊕71 ↻684"]:::warm
    laravel_package_release["laravel-package-release<br/>⊕58 ↻325"]:::mild
    laravel_package_scaffold["laravel-package-scaffold<br/>⊕66 ↻523"]:::warm
    laravel_package_service_provider["laravel-package-service-provider<br/>⊕62 ↻468"]:::mild
    laravel_package_testing["laravel-package-testing<br/>⊕72 ↻463"]:::warm
    laravel_packages["laravel-packages<br/>⊕28 ↻679"]:::cool
  end
  subgraph pm["pm"]
    brd["brd<br/>⊕24 ↻514"]:::cool
    business_process["business-process<br/>⊕23 ↻517"]:::cool
    go_to_market["go-to-market<br/>⊕22 ↻1136"]:::cool
    monetization_design["monetization-design<br/>⊕31 ↻1245"]:::cool
    pm_super_skill["pm-super-skill<br/>⊕102 ↻19581"]:::hot
    pmf_diagnostics["pmf-diagnostics<br/>⊕45 ↻1210"]:::mild
    prd_from_brd["prd-from-brd<br/>⊕32 ↻1234"]:::cool
    product_roadmap["product-roadmap<br/>⊕30 ↻1171"]:::cool
    requirement_critic["requirement-critic<br/>⊕44 ↻1429"]:::mild
    unit_economics["unit-economics<br/>⊕20 ↻722"]:::cool
  end
  subgraph python["python"]
    ml_project_structure["ml-project-structure<br/>⊕24 ↻531"]:::cool
    venv_dependencies["venv-dependencies<br/>⊕25 ↻483"]:::cool
  end
  subgraph quality["quality"]
    code_review["code-review<br/>⊕31 ↻1410"]:::cool
    code_simplifier["code-simplifier<br/>⊕57 ↻1080"]:::mild
    diagnosing_bugs["diagnosing-bugs<br/>⊕90 ↻2221"]:::warm
    mutation_testing["mutation-testing<br/>⊕90 ↻2202"]:::warm
    playwright_e2e["playwright-e2e<br/>⊕91 ↻2171"]:::warm
    refactoring_plan["refactoring-plan<br/>⊕28 ↻1605"]:::cool
    tdd_discipline["tdd-discipline<br/>⊕85 ↻1201"]:::warm
    tech_debt_audit["tech-debt-audit<br/>⊕38 ↻1879"]:::mild
    test_strategy["test-strategy<br/>⊕52 ↻1978"]:::mild
    testing_safety_report["testing-safety-report<br/>⊕66 ↻668"]:::warm
  end
  subgraph research["research"]
    research_knowledge_super_skill["research-knowledge-super-skill<br/>⊕165 ↻17401"]:::hot
  end
  subgraph roles["roles"]
    open_source_maintainer["open-source-maintainer<br/>⊕16 ↻1059"]:::cool
    solo_founder["solo-founder<br/>⊕14 ↻1018"]:::cool
    startup_cto["startup-cto<br/>⊕19 ↻1213"]:::cool
    tech_lead["tech-lead<br/>⊕18 ↻1210"]:::cool
  end
  subgraph sales["sales"]
    sales_super_skill["sales-super-skill<br/>⊕121 ↻21754"]:::hot
  end
  subgraph security["security"]
    agent_security_super_skill["agent-security-super-skill<br/>⊕156 ↻25669"]:::hot
  end
  subgraph system["system"]
    agent_packs["agent-packs<br/>⊕102 ↻1991"]:::hot
    brain_locator["brain-locator<br/>⊕40 ↻1145"]:::mild
    cross_project_coordinator["cross-project-coordinator<br/>⊕70 ↻1224"]:::warm
    local_topology["local-topology<br/>⊕53 ↻1190"]:::mild
    session_observer["session-observer<br/>⊕99 ↻1411"]:::hot
    shared_memory["shared-memory<br/>⊕105 ↻1242"]:::hot
    swissknifeman_locator["swissknifeman-locator<br/>⊕46 ↻1220"]:::mild
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

**Итого:** 199 скиллов · ⊕ always **11914** ток (резидентно всегда, если включить весь реестр) · ↻ bodies 432881 ток · ⌥ snippets 158029 ток.

## По бакетам

| Бакет | Скиллов | ⊕ always | ↻ bodies | ⌥ snippets |
|---|--:|--:|--:|--:|
| `general` | 19 | 1178 | 17076 | 5120 |
| `architect` | 14 | 747 | 38470 | 7503 |
| `frontend-vue` | 11 | 726 | 23106 | 7058 |
| `quality` | 10 | 628 | 16415 | 7125 |
| `php-packages` | 9 | 582 | 4618 | 489 |
| `oss-dev` | 10 | 532 | 12204 | 4313 |
| `system` | 7 | 515 | 9423 | 797 |
| `php` | 13 | 503 | 15538 | 26763 |
| `laravel-architecture` | 5 | 483 | 7905 | 7460 |
| `devops` | 11 | 451 | 7654 | 15388 |
| `blender-modeling` | 6 | 429 | 7727 | 11772 |
| `pm` | 10 | 373 | 28759 | 197 |
| `founder` | 10 | 343 | 13127 | 494 |
| `laravel-testing` | 4 | 283 | 6868 | 14531 |
| `frontend-linting` | 4 | 275 | 5276 | 2914 |
| `operator` | 6 | 252 | 27108 | 90 |
| `frontend-backend` | 3 | 244 | 4726 | 7459 |
| `frontend` | 3 | 242 | 3234 | 3393 |
| `frontend-nuxt` | 3 | 216 | 2179 | 0 |
| `frontend-tailwind` | 2 | 204 | 3807 | 4980 |
| `laravel-extras` | 3 | 191 | 3741 | 3192 |
| `laravel-auth` | 3 | 172 | 2881 | 3020 |
| `ai` | 2 | 170 | 1834 | 0 |
| `research` | 1 | 165 | 17401 | 0 |
| `security` | 1 | 156 | 25669 | 0 |
| `frontend-vite` | 4 | 153 | 2706 | 1351 |
| `finance` | 1 | 152 | 18278 | 0 |
| `laravel-data-layer` | 2 | 136 | 3037 | 3785 |
| `creative` | 1 | 132 | 22304 | 0 |
| `laravel-livewire` | 1 | 132 | 1100 | 1079 |
| `legal` | 1 | 123 | 24861 | 0 |
| `marketing` | 1 | 121 | 14124 | 0 |
| `sales` | 1 | 121 | 21754 | 0 |
| `blender` | 2 | 119 | 1961 | 325 |
| `mobile` | 1 | 91 | 746 | 884 |
| `frontend-reka` | 1 | 90 | 1715 | 2414 |
| `frontend-naive-ui` | 1 | 87 | 1744 | 1270 |
| `frontend-figma` | 1 | 84 | 700 | 949 |
| `roles` | 4 | 67 | 4500 | 148 |
| `laravel-filament` | 1 | 53 | 2311 | 2749 |
| `python` | 2 | 49 | 1014 | 0 |
| `frontend-animations` | 1 | 47 | 782 | 0 |
| `frontend-wayfinder` | 1 | 41 | 854 | 1658 |
| `azguard` | 1 | 31 | 1436 | 6767 |
| `botkit` | 1 | 25 | 208 | 592 |

## Топ ⊕ always (постоянный налог)

Самые дорогие описания — резидентны в каждом запросе.

| Скилл | Бакет | ток |
|---|---|--:|
| `research-knowledge-super-skill` | research | 165 |
| `agent-security-super-skill` | security | 156 |
| `finance-super-skill` | finance | 152 |
| `verify-claims` | general | 136 |
| `enum-state-machine` | laravel-architecture | 135 |
| `content-creative-super-skill` | creative | 132 |
| `livewire-blade-attributes` | laravel-livewire | 132 |
| `legal-super-skill` | legal | 123 |
| `marketing-super-skill` | marketing | 121 |
| `sales-super-skill` | sales | 121 |

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
