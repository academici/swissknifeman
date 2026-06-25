# Карта токенового бюджета

> Сгенерировано `lib/skiller/budget.py` (`skiller budget --write-map`) из `skills.json` и тел `SKILL.md` — не редактировать вручную.
> Пересборка: `skiller registry`.

Трёхъярусная модель раскрытия контекста — что грузит нейросеть и когда:

- **⊕ always** — `name`+`description`: резидентны в КАЖДОМ запросе (по ним агент решает, применять ли скилл). Постоянный «налог».
- **↻ on-trigger** — тело `SKILL.md`: грузится, только когда скилл сработал.
- **⌥ on-demand** — сниппеты: по ссылке из тела, опционально.

Цвет узла — heat по **⊕ always** (краснее = дороже постоянный налог описания). Метка `name<br/>⊕always ↻body`. Сплошная стрелка `requires` показывает транзитивный налог: ставишь скилл — тянешь always-цену зависимости. Оценка токенов грубая (`len/3`), для сравнения наборов, не точного учёта.

```mermaid
flowchart LR
  subgraph ai["ai"]
    ai_agents["ai-agents<br/>⊕105 ↻652"]:::warm
  end
  subgraph architect["architect"]
    agent_design["agent-design<br/>⊕31 ↻2082"]:::cool
    api_design["api-design<br/>⊕33 ↻1315"]:::cool
    architecture["architecture<br/>⊕30 ↻1371"]:::cool
    data_schema["data-schema<br/>⊕32 ↻1063"]:::cool
    dev_engineering_super_skill["dev-engineering-super-skill<br/>⊕148 ↻26988"]:::hot
    eval_design["eval-design<br/>⊕36 ↻2118"]:::cool
    figma_mcp_core["figma-mcp-core<br/>⊕171 ↻1995"]:::hot
    legal_compliance["legal-compliance<br/>⊕33 ↻2387"]:::cool
    observability_design["observability-design<br/>⊕37 ↻1671"]:::cool
    package_contribution_protocol["package-contribution-protocol<br/>⊕121 ↻2275"]:::warm
    security_design["security-design<br/>⊕48 ↻2612"]:::mild
    tech_stack_selection["tech-stack-selection<br/>⊕38 ↻2254"]:::cool
  end
  subgraph azguard["azguard"]
    azguard["azguard<br/>⊕45 ↻1921"]:::mild
  end
  subgraph blender["blender"]
    mcp_blender["mcp-blender<br/>⊕146 ↻1862"]:::hot
    version_gotchas["version-gotchas<br/>⊕23 ↻970"]:::cool
  end
  subgraph blender_modeling["blender-modeling"]
    build_loop["build-loop<br/>⊕178 ↻2747"]:::hot
    config_conventions["config-conventions<br/>⊕149 ↻2631"]:::hot
    model_rules["model-rules<br/>⊕37 ↻917"]:::cool
    parametric_config["parametric-config<br/>⊕140 ↻2803"]:::hot
    scene_conventions["scene-conventions<br/>⊕118 ↻1134"]:::warm
    threading["threading<br/>⊕32 ↻842"]:::cool
  end
  subgraph botkit["botkit"]
    botkit["botkit<br/>⊕33 ↻249"]:::cool
  end
  subgraph creative["creative"]
    content_creative_super_skill["content-creative-super-skill<br/>⊕175 ↻29738"]:::hot
  end
  subgraph devops["devops"]
    ci_cd["ci-cd<br/>⊕61 ↻1339"]:::mild
    db_test_preflight["db-test-preflight<br/>⊕125 ↻2327"]:::warm
    docker["docker<br/>⊕59 ↻121"]:::mild
    docker_dev_prod["docker-dev-prod<br/>⊕48 ↻1184"]:::mild
    docker_php["docker-php<br/>⊕47 ↻1056"]:::mild
    docker_postgres["docker-postgres<br/>⊕49 ↻991"]:::mild
    docker_services["docker-services<br/>⊕57 ↻999"]:::mild
    docker_vite["docker-vite<br/>⊕44 ↻932"]:::cool
    gitops["gitops<br/>⊕34 ↻925"]:::cool
    makefile["makefile<br/>⊕50 ↻935"]:::mild
    node_pnpm_preflight["node-pnpm-preflight<br/>⊕47 ↻301"]:::mild
  end
  subgraph finance["finance"]
    finance_super_skill["finance-super-skill<br/>⊕203 ↻24370"]:::hot
  end
  subgraph founder["founder"]
    adversarial_check["adversarial-check<br/>⊕66 ↻1337"]:::mild
    competitive_analysis["competitive-analysis<br/>⊕39 ↻1615"]:::cool
    customer_discovery["customer-discovery<br/>⊕65 ↻1566"]:::mild
    defensibility["defensibility<br/>⊕47 ↻1421"]:::mild
    idea_discovery["idea-discovery<br/>⊕40 ↻1885"]:::cool
    new_project["new-project<br/>⊕32 ↻1717"]:::cool
    pitch_deck["pitch-deck<br/>⊕33 ↻1904"]:::cool
    risk_assessment["risk-assessment<br/>⊕30 ↻1590"]:::cool
    startup_lifecycle["startup-lifecycle<br/>⊕47 ↻2017"]:::mild
  end
  subgraph frontend["frontend"]
    document_writer["document-writer<br/>⊕99 ↻1453"]:::warm
    filepond_upload["filepond-upload<br/>⊕168 ↻2893"]:::hot
    web_design_guidelines["web-design-guidelines<br/>⊕69 ↻306"]:::mild
  end
  subgraph frontend_animations["frontend-animations"]
    motion["motion<br/>⊕63 ↻1043"]:::mild
  end
  subgraph frontend_backend["frontend-backend"]
    backend_type_sync["backend-type-sync<br/>⊕125 ↻2692"]:::warm
    inertia_vue["inertia-vue<br/>⊕65 ↻1819"]:::mild
    laravel_echo_client["laravel-echo-client<br/>⊕146 ↻2499"]:::hot
  end
  subgraph frontend_figma["frontend-figma"]
    figma_to_vue["figma-to-vue<br/>⊕122 ↻968"]:::warm
  end
  subgraph frontend_linting["frontend-linting"]
    antfu["antfu<br/>⊕83 ↻1453"]:::mild
    eslint_flat_config["eslint-flat-config<br/>⊕129 ↻2880"]:::warm
    js_code_style["js-code-style<br/>⊕59 ↻897"]:::mild
    ts_library["ts-library<br/>⊕102 ↻1537"]:::warm
  end
  subgraph frontend_naive_ui["frontend-naive-ui"]
    naive_ui_theming["naive-ui-theming<br/>⊕118 ↻2567"]:::warm
  end
  subgraph frontend_nuxt["frontend-nuxt"]
    nuxt["nuxt<br/>⊕91 ↻1240"]:::warm
    nuxt_modules["nuxt-modules<br/>⊕142 ↻729"]:::hot
    nuxt_seo["nuxt-seo<br/>⊕56 ↻935"]:::mild
  end
  subgraph frontend_reka["frontend-reka"]
    reka_ui_cva["reka-ui-cva<br/>⊕116 ↻2528"]:::warm
  end
  subgraph frontend_tailwind["frontend-tailwind"]
    dark_mode["dark-mode<br/>⊕140 ↻2850"]:::hot
    tailwind_conventions["tailwind-conventions<br/>⊕142 ↻2778"]:::hot
  end
  subgraph frontend_vite["frontend-vite"]
    vite["vite<br/>⊕64 ↻697"]:::mild
    vite_module_loader["vite-module-loader<br/>⊕36 ↻945"]:::cool
    vite_multi_build["vite-multi-build<br/>⊕59 ↻1201"]:::mild
    vitepress["vitepress<br/>⊕56 ↻940"]:::mild
  end
  subgraph frontend_vue["frontend-vue"]
    pinia["pinia<br/>⊕61 ↻783"]:::mild
    pinia_stores["pinia-stores<br/>⊕150 ↻2467"]:::hot
    vitest["vitest<br/>⊕57 ↻1085"]:::mild
    vitest_vue["vitest-vue<br/>⊕63 ↻1177"]:::mild
    vue["vue<br/>⊕72 ↻976"]:::mild
    vue_best_practices["vue-best-practices<br/>⊕112 ↻2893"]:::warm
    vue_composition_api["vue-composition-api<br/>⊕87 ↻622"]:::warm
    vue_dynamic_icons["vue-dynamic-icons<br/>⊕99 ↻1670"]:::warm
    vue_router_best_practices["vue-router-best-practices<br/>⊕180 ↻2943"]:::hot
    vue_testing_best_practices["vue-testing-best-practices<br/>⊕86 ↻2498"]:::warm
    vueuse_functions["vueuse-functions<br/>⊕38 ↻12283"]:::cool
  end
  subgraph frontend_wayfinder["frontend-wayfinder"]
    wayfinder["wayfinder<br/>⊕57 ↻1168"]:::mild
  end
  subgraph general["general"]
    anti_drift["anti-drift<br/>⊕52 ↻1210"]:::mild
    compact_responses["compact-responses<br/>⊕88 ↻509"]:::warm
    complex_task_orchestrator["complex-task-orchestrator<br/>⊕54 ↻774"]:::mild
    context_economy["context-economy<br/>⊕91 ↻1580"]:::warm
    cross_layer_change_checklist["cross-layer-change-checklist<br/>⊕46 ↻554"]:::mild
    git_commit_rules["git-commit-rules<br/>⊕45 ↻1159"]:::mild
    naming_conventions["naming-conventions<br/>⊕103 ↻1909"]:::warm
    packages_stack["packages-stack<br/>⊕108 ↻656"]:::warm
    project_map["project-map<br/>⊕103 ↻784"]:::warm
    session_handoff["session-handoff<br/>⊕57 ↻629"]:::mild
    skills_ssot["skills-ssot<br/>⊕40 ↻2224"]:::cool
    spec_interview["spec-interview<br/>⊕61 ↻750"]:::mild
    task_brief_template["task-brief-template<br/>⊕92 ↻1318"]:::warm
    token_efficient["token-efficient<br/>⊕126 ↻1593"]:::warm
    writing_style["writing-style<br/>⊕118 ↻2179"]:::warm
  end
  subgraph laravel_architecture["laravel-architecture"]
    enum_attributes["enum-attributes<br/>⊕164 ↻2404"]:::hot
    enum_state_machine["enum-state-machine<br/>⊕177 ↻2024"]:::hot
    laravel_subagents["laravel-subagents<br/>⊕92 ↻1715"]:::warm
    modular_architecture["modular-architecture<br/>⊕102 ↻4055"]:::warm
  end
  subgraph laravel_auth["laravel-auth"]
    attribute_authorization["attribute-authorization<br/>⊕103 ↻2498"]:::warm
    laravel_permissions["laravel-permissions<br/>⊕73 ↻476"]:::mild
    laravel_security_audit["laravel-security-audit<br/>⊕62 ↻947"]:::mild
  end
  subgraph laravel_data_layer["laravel-data-layer"]
    laravel_broadcasting["laravel-broadcasting<br/>⊕44 ↻1349"]:::cool
    laravel_data["laravel-data<br/>⊕141 ↻2666"]:::hot
  end
  subgraph laravel_extras["laravel-extras"]
    medialibrary["medialibrary<br/>⊕38 ↻1203"]:::cool
    pennant_development["pennant-development<br/>⊕66 ↻535"]:::mild
    spatie_settings["spatie-settings<br/>⊕157 ↻3370"]:::hot
  end
  subgraph laravel_filament["laravel-filament"]
    filament["filament<br/>⊕73 ↻2587"]:::mild
  end
  subgraph laravel_livewire["laravel-livewire"]
    livewire_blade_attributes["livewire-blade-attributes<br/>⊕185 ↻1530"]:::hot
  end
  subgraph laravel_testing["laravel-testing"]
    health_checks["health-checks<br/>⊕163 ↻3080"]:::hot
    laravel_dusk["laravel-dusk<br/>⊕44 ↻1272"]:::cool
    laravel_testing["laravel-testing<br/>⊕67 ↻3803"]:::mild
    test_isolation_guard["test-isolation-guard<br/>⊕128 ↻2366"]:::warm
  end
  subgraph legal["legal"]
    legal_super_skill["legal-super-skill<br/>⊕164 ↻33086"]:::hot
  end
  subgraph marketing["marketing"]
    marketing_super_skill["marketing-super-skill<br/>⊕161 ↻18832"]:::hot
  end
  subgraph mobile["mobile"]
    figma_to_flutter["figma-to-flutter<br/>⊕128 ↻1042"]:::warm
  end
  subgraph operator["operator"]
    capacity_planning["capacity-planning<br/>⊕51 ↻2487"]:::mild
    incident_response["incident-response<br/>⊕49 ↻2291"]:::mild
    oncall_rotation["oncall-rotation<br/>⊕42 ↻2033"]:::cool
    operations_cx_super_skill["operations-cx-super-skill<br/>⊕214 ↻25225"]:::hot
    postmortem["postmortem<br/>⊕48 ↻2357"]:::mild
    runbook["runbook<br/>⊕42 ↻2207"]:::cool
  end
  subgraph oss_dev["oss-dev"]
    dependency_audit["dependency-audit<br/>⊕39 ↻1385"]:::cool
    dx_design["dx-design<br/>⊕36 ↻1537"]:::cool
    gh_review["gh-review<br/>⊕86 ↻1499"]:::warm
    github_flow["github-flow<br/>⊕81 ↻2508"]:::mild
    oss_development["oss-development<br/>⊕42 ↻1628"]:::cool
    oss_governance["oss-governance<br/>⊕34 ↻1934"]:::cool
    release_engineering["release-engineering<br/>⊕41 ↻2059"]:::cool
  end
  subgraph php["php"]
    code_style_spatie["code-style-spatie<br/>⊕53 ↻1176"]:::mild
    database["database<br/>⊕58 ↻1179"]:::mild
    dependency_injection["dependency-injection<br/>⊕45 ↻1618"]:::mild
    laravel["laravel<br/>⊕24 ↻1854"]:::cool
    laravel_best_practices["laravel-best-practices<br/>⊕48 ↻1814"]:::mild
    laravel_structure["laravel-structure<br/>⊕56 ↻2354"]:::mild
    named_arguments["named-arguments<br/>⊕65 ↻1042"]:::mild
    naming_conventions["naming-conventions<br/>⊕98 ↻1791"]:::warm
    pao["pao<br/>⊕77 ↻782"]:::mild
    php_patterns["php-patterns<br/>⊕22 ↻3259"]:::cool
    php_upgrade_checklist["php-upgrade-checklist<br/>⊕89 ↻927"]:::warm
    repositories["repositories<br/>⊕37 ↻1920"]:::cool
    static_analysis["static-analysis<br/>⊕41 ↻1620"]:::cool
  end
  subgraph php_packages["php-packages"]
    laravel_package_compatibility["laravel-package-compatibility<br/>⊕86 ↻505"]:::warm
    laravel_package_docs["laravel-package-docs<br/>⊕84 ↻808"]:::warm
    laravel_package_expressive["laravel-package-expressive<br/>⊕126 ↻654"]:::warm
    laravel_package_generate_skill["laravel-package-generate-skill<br/>⊕95 ↻911"]:::warm
    laravel_package_release["laravel-package-release<br/>⊕77 ↻433"]:::mild
    laravel_package_scaffold["laravel-package-scaffold<br/>⊕87 ↻697"]:::warm
    laravel_package_service_provider["laravel-package-service-provider<br/>⊕82 ↻624"]:::mild
    laravel_package_testing["laravel-package-testing<br/>⊕96 ↻610"]:::warm
    laravel_packages["laravel-packages<br/>⊕40 ↻945"]:::cool
  end
  subgraph pm["pm"]
    brd["brd<br/>⊕32 ↻705"]:::cool
    business_process["business-process<br/>⊕31 ↻639"]:::cool
    go_to_market["go-to-market<br/>⊕29 ↻1696"]:::cool
    monetization_design["monetization-design<br/>⊕41 ↻1610"]:::cool
    pm_super_skill["pm-super-skill<br/>⊕153 ↻25963"]:::hot
    pmf_diagnostics["pmf-diagnostics<br/>⊕60 ↻1605"]:::mild
    prd_from_brd["prd-from-brd<br/>⊕42 ↻1774"]:::cool
    product_roadmap["product-roadmap<br/>⊕36 ↻1462"]:::cool
    requirement_critic["requirement-critic<br/>⊕38 ↻1457"]:::cool
    unit_economics["unit-economics<br/>⊕27 ↻996"]:::cool
  end
  subgraph python["python"]
    ml_project_structure["ml-project-structure<br/>⊕38 ↻865"]:::cool
    venv_dependencies["venv-dependencies<br/>⊕36 ↻886"]:::cool
  end
  subgraph quality["quality"]
    code_review["code-review<br/>⊕49 ↻1995"]:::mild
    code_simplifier["code-simplifier<br/>⊕84 ↻1537"]:::warm
    mutation_testing["mutation-testing<br/>⊕128 ↻3431"]:::warm
    playwright_e2e["playwright-e2e<br/>⊕133 ↻3265"]:::warm
    refactoring_plan["refactoring-plan<br/>⊕42 ↻2336"]:::cool
    tech_debt_audit["tech-debt-audit<br/>⊕51 ↻2807"]:::mild
    test_strategy["test-strategy<br/>⊕73 ↻2846"]:::mild
    testing_safety_report["testing-safety-report<br/>⊕98 ↻937"]:::warm
  end
  subgraph research["research"]
    research_knowledge_super_skill["research-knowledge-super-skill<br/>⊕220 ↻23138"]:::hot
  end
  subgraph roles["roles"]
    open_source_maintainer["open-source-maintainer<br/>⊕22 ↻1603"]:::cool
    solo_founder["solo-founder<br/>⊕19 ↻1745"]:::cool
    startup_cto["startup-cto<br/>⊕26 ↻1878"]:::cool
    tech_lead["tech-lead<br/>⊕23 ↻1740"]:::cool
  end
  subgraph sales["sales"]
    sales_super_skill["sales-super-skill<br/>⊕161 ↻29005"]:::hot
  end
  subgraph security["security"]
    agent_security_super_skill["agent-security-super-skill<br/>⊕208 ↻34162"]:::hot
  end
  subgraph system["system"]
    agent_packs["agent-packs<br/>⊕139 ↻2768"]:::warm
    cross_project_coordinator["cross-project-coordinator<br/>⊕107 ↻1678"]:::warm
    local_topology["local-topology<br/>⊕71 ↻1693"]:::mild
    session_observer["session-observer<br/>⊕140 ↻2042"]:::hot
    shared_memory["shared-memory<br/>⊕160 ↻1855"]:::hot
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
  security_design -->|requires| architecture
  session_observer -->|requires| shared_memory
  shared_memory -->|requires| local_topology
  tech_stack_selection -->|requires| brd
  test_isolation_guard -->|requires| laravel_testing
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

**Итого:** 183 скиллов · ⊕ always **14798** ток (резидентно всегда, если включить весь реестр) · ↻ bodies 561004 ток · ⌥ snippets 171334 ток.

## По бакетам

| Бакет | Скиллов | ⊕ always | ↻ bodies | ⌥ snippets |
|---|--:|--:|--:|--:|
| `general` | 15 | 1184 | 17828 | 5011 |
| `frontend-vue` | 11 | 1005 | 29397 | 7979 |
| `php-packages` | 9 | 773 | 6187 | 572 |
| `architect` | 12 | 758 | 48131 | 3295 |
| `php` | 13 | 713 | 21336 | 31527 |
| `quality` | 8 | 658 | 19154 | 6554 |
| `blender-modeling` | 6 | 654 | 11074 | 11792 |
| `devops` | 11 | 621 | 11110 | 18907 |
| `system` | 5 | 617 | 10036 | 913 |
| `laravel-architecture` | 4 | 535 | 10198 | 7977 |
| `pm` | 10 | 489 | 37907 | 262 |
| `operator` | 6 | 446 | 36600 | 120 |
| `laravel-testing` | 4 | 402 | 10521 | 16843 |
| `founder` | 9 | 399 | 15052 | 653 |
| `frontend-linting` | 4 | 373 | 6767 | 3443 |
| `oss-dev` | 7 | 359 | 12550 | 1332 |
| `frontend` | 3 | 336 | 4652 | 3829 |
| `frontend-backend` | 3 | 336 | 7010 | 8609 |
| `frontend-nuxt` | 3 | 289 | 2904 | 0 |
| `frontend-tailwind` | 2 | 282 | 5628 | 5719 |
| `laravel-extras` | 3 | 261 | 5108 | 3691 |
| `laravel-auth` | 3 | 238 | 3921 | 3608 |
| `research` | 1 | 220 | 23138 | 0 |
| `frontend-vite` | 4 | 215 | 3783 | 1651 |
| `security` | 1 | 208 | 34162 | 0 |
| `finance` | 1 | 203 | 24370 | 0 |
| `laravel-data-layer` | 2 | 185 | 4015 | 4363 |
| `laravel-livewire` | 1 | 185 | 1530 | 1220 |
| `creative` | 1 | 175 | 29738 | 0 |
| `blender` | 2 | 169 | 2832 | 330 |
| `legal` | 1 | 164 | 33086 | 0 |
| `marketing` | 1 | 161 | 18832 | 0 |
| `sales` | 1 | 161 | 29005 | 0 |
| `mobile` | 1 | 128 | 1042 | 1102 |
| `frontend-figma` | 1 | 122 | 968 | 1199 |
| `frontend-naive-ui` | 1 | 118 | 2567 | 1467 |
| `frontend-reka` | 1 | 116 | 2528 | 2781 |
| `ai` | 1 | 105 | 652 | 0 |
| `roles` | 4 | 90 | 6966 | 197 |
| `python` | 2 | 74 | 1751 | 0 |
| `laravel-filament` | 1 | 73 | 2587 | 3590 |
| `frontend-animations` | 1 | 63 | 1043 | 0 |
| `frontend-wayfinder` | 1 | 57 | 1168 | 1944 |
| `azguard` | 1 | 45 | 1921 | 8064 |
| `botkit` | 1 | 33 | 249 | 790 |

## Топ ⊕ always (постоянный налог)

Самые дорогие описания — резидентны в каждом запросе.

| Скилл | Бакет | ток |
|---|---|--:|
| `research-knowledge-super-skill` | research | 220 |
| `operations-cx-super-skill` | operator | 214 |
| `agent-security-super-skill` | security | 208 |
| `finance-super-skill` | finance | 203 |
| `livewire-blade-attributes` | laravel-livewire | 185 |
| `vue-router-best-practices` | frontend-vue | 180 |
| `build-loop` | blender-modeling | 178 |
| `enum-state-machine` | laravel-architecture | 177 |
| `content-creative-super-skill` | creative | 175 |
| `figma-mcp-core` | architect | 171 |

## Топ ↻ on-trigger (цена срабатывания)

Самые тяжёлые тела — грузятся при применении скилла.

| Скилл | Бакет | ток |
|---|---|--:|
| `agent-security-super-skill` | security | 34162 |
| `legal-super-skill` | legal | 33086 |
| `content-creative-super-skill` | creative | 29738 |
| `sales-super-skill` | sales | 29005 |
| `dev-engineering-super-skill` | architect | 26988 |
| `pm-super-skill` | pm | 25963 |
| `operations-cx-super-skill` | operator | 25225 |
| `finance-super-skill` | finance | 24370 |
| `research-knowledge-super-skill` | research | 23138 |
| `marketing-super-skill` | marketing | 18832 |
