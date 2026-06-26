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
    ai_agents["ai-agents<br/>⊕123 ↻639"]:::hot
  end
  subgraph architect["architect"]
    agent_design["agent-design<br/>⊕21 ↻1505"]:::cool
    api_design["api-design<br/>⊕22 ↻1009"]:::cool
    architecture["architecture<br/>⊕23 ↻987"]:::cool
    codebase_design["codebase-design<br/>⊕155 ↻1746"]:::hot
    data_schema["data-schema<br/>⊕23 ↻833"]:::cool
    dev_engineering_super_skill["dev-engineering-super-skill<br/>⊕111 ↻20241"]:::hot
    domain_modeling["domain-modeling<br/>⊕178 ↻1173"]:::hot
    eval_design["eval-design<br/>⊕27 ↻1374"]:::cool
    figma_mcp_core["figma-mcp-core<br/>⊕116 ↻1394"]:::hot
    legal_compliance["legal-compliance<br/>⊕22 ↻1628"]:::cool
    observability_design["observability-design<br/>⊕27 ↻1146"]:::cool
    package_contribution_protocol["package-contribution-protocol<br/>⊕90 ↻1587"]:::warm
    security_design["security-design<br/>⊕33 ↻1862"]:::cool
    tech_stack_selection["tech-stack-selection<br/>⊕27 ↻1660"]:::cool
  end
  subgraph azguard["azguard"]
    azguard["azguard<br/>⊕31 ↻1422"]:::cool
  end
  subgraph blender["blender"]
    mcp_blender["mcp-blender<br/>⊕100 ↻1286"]:::warm
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
    botkit["botkit<br/>⊕25 ↻205"]:::cool
  end
  subgraph creative["creative"]
    content_creative_super_skill["content-creative-super-skill<br/>⊕132 ↻22304"]:::hot
  end
  subgraph devops["devops"]
    ci_cd["ci-cd<br/>⊕46 ↻981"]:::mild
    db_test_preflight["db-test-preflight<br/>⊕88 ↻1451"]:::warm
    docker["docker<br/>⊕44 ↻100"]:::mild
    docker_dev_prod["docker-dev-prod<br/>⊕36 ↻818"]:::mild
    docker_php["docker-php<br/>⊕34 ↻681"]:::mild
    docker_postgres["docker-postgres<br/>⊕36 ↻712"]:::mild
    docker_services["docker-services<br/>⊕41 ↻754"]:::mild
    docker_vite["docker-vite<br/>⊕33 ↻607"]:::cool
    gitops["gitops<br/>⊕25 ↻640"]:::cool
    makefile["makefile<br/>⊕36 ↻654"]:::mild
    node_pnpm_preflight["node-pnpm-preflight<br/>⊕32 ↻226"]:::cool
  end
  subgraph finance["finance"]
    finance_super_skill["finance-super-skill<br/>⊕152 ↻18278"]:::hot
  end
  subgraph founder["founder"]
    adversarial_check["adversarial-check<br/>⊕47 ↻875"]:::mild
    competitive_analysis["competitive-analysis<br/>⊕26 ↻1155"]:::cool
    customer_discovery["customer-discovery<br/>⊕46 ↻1156"]:::mild
    defensibility["defensibility<br/>⊕36 ↻988"]:::mild
    idea_discovery["idea-discovery<br/>⊕29 ↻1399"]:::cool
    new_project["new-project<br/>⊕23 ↻1191"]:::cool
    pitch_deck["pitch-deck<br/>⊕22 ↻1405"]:::cool
    risk_assessment["risk-assessment<br/>⊕22 ↻1051"]:::cool
    startup_lifecycle["startup-lifecycle<br/>⊕35 ↻1447"]:::mild
  end
  subgraph frontend["frontend"]
    document_writer["document-writer<br/>⊕74 ↻1090"]:::warm
    filepond_upload["filepond-upload<br/>⊕116 ↻1907"]:::hot
    web_design_guidelines["web-design-guidelines<br/>⊕52 ↻229"]:::mild
  end
  subgraph frontend_animations["frontend-animations"]
    motion["motion<br/>⊕47 ↻782"]:::mild
  end
  subgraph frontend_backend["frontend-backend"]
    backend_type_sync["backend-type-sync<br/>⊕85 ↻1752"]:::warm
    inertia_vue["inertia-vue<br/>⊕49 ↻1282"]:::mild
    laravel_echo_client["laravel-echo-client<br/>⊕110 ↻1636"]:::hot
  end
  subgraph frontend_figma["frontend-figma"]
    figma_to_vue["figma-to-vue<br/>⊕84 ↻700"]:::warm
  end
  subgraph frontend_linting["frontend-linting"]
    antfu["antfu<br/>⊕63 ↻1090"]:::mild
    eslint_flat_config["eslint-flat-config<br/>⊕95 ↻2031"]:::warm
    js_code_style["js-code-style<br/>⊕65 ↻972"]:::warm
    ts_library["ts-library<br/>⊕77 ↻1153"]:::warm
  end
  subgraph frontend_naive_ui["frontend-naive-ui"]
    naive_ui_theming["naive-ui-theming<br/>⊕87 ↻1731"]:::warm
  end
  subgraph frontend_nuxt["frontend-nuxt"]
    nuxt["nuxt<br/>⊕68 ↻930"]:::warm
    nuxt_modules["nuxt-modules<br/>⊕106 ↻547"]:::warm
    nuxt_seo["nuxt-seo<br/>⊕42 ↻702"]:::mild
  end
  subgraph frontend_reka["frontend-reka"]
    reka_ui_cva["reka-ui-cva<br/>⊕90 ↻1706"]:::warm
  end
  subgraph frontend_tailwind["frontend-tailwind"]
    dark_mode["dark-mode<br/>⊕96 ↻1870"]:::warm
    tailwind_conventions["tailwind-conventions<br/>⊕108 ↻1908"]:::hot
  end
  subgraph frontend_vite["frontend-vite"]
    vite["vite<br/>⊕48 ↻523"]:::mild
    vite_module_loader["vite-module-loader<br/>⊕23 ↻602"]:::cool
    vite_multi_build["vite-multi-build<br/>⊕40 ↻864"]:::mild
    vitepress["vitepress<br/>⊕42 ↻705"]:::mild
  end
  subgraph frontend_vue["frontend-vue"]
    pinia["pinia<br/>⊕46 ↻587"]:::mild
    pinia_stores["pinia-stores<br/>⊕109 ↻1642"]:::hot
    vitest["vitest<br/>⊕40 ↻697"]:::mild
    vitest_vue["vitest-vue<br/>⊕47 ↻923"]:::mild
    vue["vue<br/>⊕54 ↻793"]:::mild
    vue_best_practices["vue-best-practices<br/>⊕84 ↻2198"]:::warm
    vue_composition_api["vue-composition-api<br/>⊕68 ↻455"]:::warm
    vue_dynamic_icons["vue-dynamic-icons<br/>⊕64 ↻1110"]:::mild
    vue_router_best_practices["vue-router-best-practices<br/>⊕181 ↻2963"]:::hot
    vue_testing_best_practices["vue-testing-best-practices<br/>⊕86 ↻2484"]:::warm
    vueuse_functions["vueuse-functions<br/>⊕29 ↻9212"]:::cool
  end
  subgraph frontend_wayfinder["frontend-wayfinder"]
    wayfinder["wayfinder<br/>⊕41 ↻847"]:::mild
  end
  subgraph general["general"]
    anti_drift["anti-drift<br/>⊕37 ↻854"]:::mild
    compact_responses["compact-responses<br/>⊕51 ↻385"]:::mild
    complex_task_orchestrator["complex-task-orchestrator<br/>⊕38 ↻539"]:::mild
    context_economy["context-economy<br/>⊕61 ↻1146"]:::mild
    cross_layer_change_checklist["cross-layer-change-checklist<br/>⊕31 ↻403"]:::cool
    git_commit_rules["git-commit-rules<br/>⊕24 ↻843"]:::cool
    git_safety["git-safety<br/>⊕101 ↻615"]:::warm
    grill_with_docs["grill-with-docs<br/>⊕147 ↻1053"]:::hot
    implement["implement<br/>⊕106 ↻515"]:::warm
    mcp_advisor["mcp-advisor<br/>⊕91 ↻1470"]:::warm
    naming_conventions["naming-conventions<br/>⊕73 ↻1336"]:::warm
    packages_stack["packages-stack<br/>⊕72 ↻458"]:::warm
    project_map["project-map<br/>⊕70 ↻558"]:::warm
    session_handoff["session-handoff<br/>⊕35 ↻441"]:::mild
    skills_ssot["skills-ssot<br/>⊕30 ↻1514"]:::cool
    spec_interview["spec-interview<br/>⊕49 ↻649"]:::mild
    task_brief_template["task-brief-template<br/>⊕67 ↻1187"]:::warm
    token_efficient["token-efficient<br/>⊕95 ↻1195"]:::warm
    writing_style["writing-style<br/>⊕83 ↻1565"]:::warm
  end
  subgraph laravel_architecture["laravel-architecture"]
    enum_attributes["enum-attributes<br/>⊕111 ↻1674"]:::hot
    enum_state_machine["enum-state-machine<br/>⊕135 ↻1340"]:::hot
    laravel_subagents["laravel-subagents<br/>⊕65 ↻1112"]:::warm
    modular_architecture["modular-architecture<br/>⊕71 ↻2668"]:::warm
  end
  subgraph laravel_auth["laravel-auth"]
    attribute_authorization["attribute-authorization<br/>⊕71 ↻1805"]:::warm
    laravel_permissions["laravel-permissions<br/>⊕58 ↻362"]:::mild
    laravel_security_audit["laravel-security-audit<br/>⊕43 ↻686"]:::mild
  end
  subgraph laravel_data_layer["laravel-data-layer"]
    laravel_broadcasting["laravel-broadcasting<br/>⊕39 ↻1279"]:::mild
    laravel_data["laravel-data<br/>⊕102 ↻1745"]:::warm
  end
  subgraph laravel_extras["laravel-extras"]
    medialibrary["medialibrary<br/>⊕28 ↻889"]:::cool
    pennant_development["pennant-development<br/>⊕63 ↻535"]:::mild
    spatie_settings["spatie-settings<br/>⊕114 ↻2288"]:::hot
  end
  subgraph laravel_filament["laravel-filament"]
    filament["filament<br/>⊕70 ↻2311"]:::warm
  end
  subgraph laravel_livewire["laravel-livewire"]
    livewire_blade_attributes["livewire-blade-attributes<br/>⊕132 ↻1095"]:::hot
  end
  subgraph laravel_testing["laravel-testing"]
    health_checks["health-checks<br/>⊕118 ↻1983"]:::hot
    laravel_dusk["laravel-dusk<br/>⊕29 ↻858"]:::cool
    laravel_testing["laravel-testing<br/>⊕48 ↻2642"]:::mild
    test_isolation_guard["test-isolation-guard<br/>⊕88 ↻1356"]:::warm
  end
  subgraph legal["legal"]
    legal_super_skill["legal-super-skill<br/>⊕123 ↻24815"]:::hot
  end
  subgraph marketing["marketing"]
    marketing_super_skill["marketing-super-skill<br/>⊕121 ↻14124"]:::hot
  end
  subgraph mobile["mobile"]
    figma_to_flutter["figma-to-flutter<br/>⊕91 ↻746"]:::warm
  end
  subgraph operator["operator"]
    capacity_planning["capacity-planning<br/>⊕35 ↻1795"]:::mild
    incident_response["incident-response<br/>⊕35 ↻1577"]:::mild
    oncall_rotation["oncall-rotation<br/>⊕32 ↻1515"]:::cool
    operations_cx_super_skill["operations-cx-super-skill<br/>⊕161 ↻18919"]:::hot
    postmortem["postmortem<br/>⊕37 ↻1722"]:::mild
    runbook["runbook<br/>⊕30 ↻1489"]:::cool
  end
  subgraph oss_dev["oss-dev"]
    dependency_audit["dependency-audit<br/>⊕28 ↻1001"]:::cool
    dx_design["dx-design<br/>⊕27 ↻1058"]:::cool
    gh_review["gh-review<br/>⊕65 ↻997"]:::warm
    github_flow["github-flow<br/>⊕60 ↻1785"]:::mild
    issue_triage["issue-triage<br/>⊕125 ↻1914"]:::hot
    oss_development["oss-development<br/>⊕32 ↻1273"]:::cool
    oss_governance["oss-governance<br/>⊕26 ↻1365"]:::cool
    release_engineering["release-engineering<br/>⊕32 ↻1418"]:::cool
    resolving_merge_conflicts["resolving-merge-conflicts<br/>⊕143 ↻302"]:::hot
    to_issues["to-issues<br/>⊕116 ↻1083"]:::hot
  end
  subgraph php["php"]
    code_style_spatie["code-style-spatie<br/>⊕54 ↻1237"]:::mild
    database["database<br/>⊕44 ↻820"]:::mild
    dependency_injection["dependency-injection<br/>⊕33 ↻1102"]:::cool
    laravel["laravel<br/>⊕18 ↻1333"]:::cool
    laravel_best_practices["laravel-best-practices<br/>⊕53 ↻1868"]:::mild
    laravel_structure["laravel-structure<br/>⊕37 ↻1710"]:::mild
    named_arguments["named-arguments<br/>⊕42 ↻598"]:::mild
    naming_conventions["naming-conventions<br/>⊕67 ↻1221"]:::warm
    pao["pao<br/>⊕50 ↻562"]:::mild
    php_patterns["php-patterns<br/>⊕21 ↻2151"]:::cool
    php_upgrade_checklist["php-upgrade-checklist<br/>⊕61 ↻577"]:::mild
    repositories["repositories<br/>⊕26 ↻1329"]:::cool
    static_analysis["static-analysis<br/>⊕29 ↻961"]:::cool
  end
  subgraph php_packages["php-packages"]
    laravel_package_compatibility["laravel-package-compatibility<br/>⊕65 ↻379"]:::warm
    laravel_package_docs["laravel-package-docs<br/>⊕63 ↻606"]:::mild
    laravel_package_expressive["laravel-package-expressive<br/>⊕107 ↻491"]:::warm
    laravel_package_generate_skill["laravel-package-generate-skill<br/>⊕71 ↻684"]:::warm
    laravel_package_release["laravel-package-release<br/>⊕58 ↻325"]:::mild
    laravel_package_scaffold["laravel-package-scaffold<br/>⊕66 ↻523"]:::warm
    laravel_package_service_provider["laravel-package-service-provider<br/>⊕62 ↻468"]:::mild
    laravel_package_testing["laravel-package-testing<br/>⊕72 ↻463"]:::warm
    laravel_packages["laravel-packages<br/>⊕28 ↻665"]:::cool
  end
  subgraph pm["pm"]
    brd["brd<br/>⊕24 ↻514"]:::cool
    business_process["business-process<br/>⊕23 ↻512"]:::cool
    go_to_market["go-to-market<br/>⊕22 ↻1136"]:::cool
    monetization_design["monetization-design<br/>⊕31 ↻1245"]:::cool
    pm_super_skill["pm-super-skill<br/>⊕115 ↻19473"]:::hot
    pmf_diagnostics["pmf-diagnostics<br/>⊕45 ↻1210"]:::mild
    prd_from_brd["prd-from-brd<br/>⊕32 ↻1234"]:::cool
    product_roadmap["product-roadmap<br/>⊕30 ↻1171"]:::cool
    requirement_critic["requirement-critic<br/>⊕27 ↻1020"]:::cool
    unit_economics["unit-economics<br/>⊕20 ↻722"]:::cool
  end
  subgraph python["python"]
    ml_project_structure["ml-project-structure<br/>⊕24 ↻531"]:::cool
    venv_dependencies["venv-dependencies<br/>⊕25 ↻483"]:::cool
  end
  subgraph quality["quality"]
    code_review["code-review<br/>⊕31 ↻1410"]:::cool
    code_simplifier["code-simplifier<br/>⊕57 ↻1080"]:::mild
    diagnosing_bugs["diagnosing-bugs<br/>⊕156 ↻2221"]:::hot
    mutation_testing["mutation-testing<br/>⊕90 ↻2199"]:::warm
    playwright_e2e["playwright-e2e<br/>⊕91 ↻2163"]:::warm
    refactoring_plan["refactoring-plan<br/>⊕28 ↻1605"]:::cool
    tdd_discipline["tdd-discipline<br/>⊕132 ↻1201"]:::hot
    tech_debt_audit["tech-debt-audit<br/>⊕38 ↻1879"]:::mild
    test_strategy["test-strategy<br/>⊕52 ↻1960"]:::mild
    testing_safety_report["testing-safety-report<br/>⊕66 ↻665"]:::warm
  end
  subgraph research["research"]
    research_knowledge_super_skill["research-knowledge-super-skill<br/>⊕165 ↻17354"]:::hot
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
    agent_security_super_skill["agent-security-super-skill<br/>⊕156 ↻25622"]:::hot
  end
  subgraph system["system"]
    agent_packs["agent-packs<br/>⊕102 ↻1987"]:::warm
    cross_project_coordinator["cross-project-coordinator<br/>⊕70 ↻1216"]:::warm
    local_topology["local-topology<br/>⊕53 ↻1072"]:::mild
    session_observer["session-observer<br/>⊕99 ↻1411"]:::warm
    shared_memory["shared-memory<br/>⊕105 ↻1242"]:::warm
  end
  agent_design -->|requires| architecture
  api_design -->|requires| data_schema
  architecture -->|requires| brd
  architecture -->|requires| tech_stack_selection
  attribute_authorization -->|requires| laravel_permissions
  backend_type_sync -->|requires| wayfinder
  botkit -->|requires| laravel
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

**Итого:** 194 скиллов · ⊕ always **12328** ток (резидентно всегда, если включить весь реестр) · ↻ bodies 423712 ток · ⌥ snippets 157306 ток.

## По бакетам

| Бакет | Скиллов | ⊕ always | ↻ bodies | ⌥ snippets |
|---|--:|--:|--:|--:|
| `general` | 19 | 1261 | 16726 | 5120 |
| `architect` | 14 | 875 | 38145 | 7503 |
| `frontend-vue` | 11 | 808 | 23064 | 7058 |
| `quality` | 10 | 741 | 16383 | 7091 |
| `oss-dev` | 10 | 654 | 12196 | 4313 |
| `php-packages` | 9 | 592 | 4604 | 489 |
| `php` | 13 | 535 | 15469 | 26763 |
| `devops` | 11 | 451 | 7624 | 15385 |
| `blender-modeling` | 6 | 429 | 7727 | 11772 |
| `system` | 5 | 429 | 6928 | 797 |
| `laravel-architecture` | 4 | 382 | 6794 | 6779 |
| `pm` | 10 | 369 | 28237 | 197 |
| `operator` | 6 | 330 | 27017 | 90 |
| `frontend-linting` | 4 | 300 | 5246 | 2914 |
| `founder` | 9 | 286 | 10667 | 494 |
| `laravel-testing` | 4 | 283 | 6839 | 14531 |
| `frontend-backend` | 3 | 244 | 4670 | 7454 |
| `frontend` | 3 | 242 | 3226 | 3393 |
| `frontend-nuxt` | 3 | 216 | 2179 | 0 |
| `laravel-extras` | 3 | 205 | 3712 | 3192 |
| `frontend-tailwind` | 2 | 204 | 3778 | 4980 |
| `laravel-auth` | 3 | 172 | 2853 | 3020 |
| `research` | 1 | 165 | 17354 | 0 |
| `security` | 1 | 156 | 25622 | 0 |
| `frontend-vite` | 4 | 153 | 2694 | 1351 |
| `finance` | 1 | 152 | 18278 | 0 |
| `laravel-data-layer` | 2 | 141 | 3024 | 3785 |
| `creative` | 1 | 132 | 22304 | 0 |
| `laravel-livewire` | 1 | 132 | 1095 | 1079 |
| `ai` | 1 | 123 | 639 | 0 |
| `legal` | 1 | 123 | 24815 | 0 |
| `marketing` | 1 | 121 | 14124 | 0 |
| `sales` | 1 | 121 | 21754 | 0 |
| `blender` | 2 | 119 | 1961 | 325 |
| `mobile` | 1 | 91 | 746 | 884 |
| `frontend-reka` | 1 | 90 | 1706 | 2414 |
| `frontend-naive-ui` | 1 | 87 | 1731 | 1270 |
| `frontend-figma` | 1 | 84 | 700 | 949 |
| `laravel-filament` | 1 | 70 | 2311 | 2749 |
| `roles` | 4 | 67 | 4500 | 148 |
| `python` | 2 | 49 | 1014 | 0 |
| `frontend-animations` | 1 | 47 | 782 | 0 |
| `frontend-wayfinder` | 1 | 41 | 847 | 1658 |
| `azguard` | 1 | 31 | 1422 | 6767 |
| `botkit` | 1 | 25 | 205 | 592 |

## Топ ⊕ always (постоянный налог)

Самые дорогие описания — резидентны в каждом запросе.

| Скилл | Бакет | ток |
|---|---|--:|
| `vue-router-best-practices` | frontend-vue | 181 |
| `domain-modeling` | architect | 178 |
| `research-knowledge-super-skill` | research | 165 |
| `operations-cx-super-skill` | operator | 161 |
| `diagnosing-bugs` | quality | 156 |
| `agent-security-super-skill` | security | 156 |
| `codebase-design` | architect | 155 |
| `finance-super-skill` | finance | 152 |
| `grill-with-docs` | general | 147 |
| `resolving-merge-conflicts` | oss-dev | 143 |

## Топ ↻ on-trigger (цена срабатывания)

Самые тяжёлые тела — грузятся при применении скилла.

| Скилл | Бакет | ток |
|---|---|--:|
| `agent-security-super-skill` | security | 25622 |
| `legal-super-skill` | legal | 24815 |
| `content-creative-super-skill` | creative | 22304 |
| `sales-super-skill` | sales | 21754 |
| `dev-engineering-super-skill` | architect | 20241 |
| `pm-super-skill` | pm | 19473 |
| `operations-cx-super-skill` | operator | 18919 |
| `finance-super-skill` | finance | 18278 |
| `research-knowledge-super-skill` | research | 17354 |
| `marketing-super-skill` | marketing | 14124 |
