import { defineConfig } from 'vitepress'
import { withMermaid } from 'vitepress-plugin-mermaid'

// Umbrella ecosystem documentation. Docs live INSIDE every package
// (packages/<pkg>/docs); scripts/docs-sync.sh copies them to docs/skiller, docs/harness,
// docs/maind (gitignored) — a single site is assembled from per-package files. General
// information — at the root docs/. Internal links package docs relative → package
// gets ready and standalone (mine .vitepress), and in this unit.
export default withMermaid(defineConfig({
  lang: 'en-US',
  title: 'SwissKnifeMan',
  description:
    'Ecosystem umbrella academici: skills (skiller), environment Claude Code (harness), memory and graph (maind)',
  base: '/swissknifeman/',
  lastUpdated: true,
  // docs/orch/configuration.md is a copy of a module page that links to the module's generated config.example.toml,
  // which lives outside the site.
  ignoreDeadLinks: [/config\.example\.toml$/],

  themeConfig: {
    nav: [
      { text: 'Overview', link: '/' },
      { text: 'How it works', link: '/overview' },
      { text: 'Philosophy', link: '/philosophy' },
      { text: 'Development', link: '/develop', activeMatch: '/develop' },
      { text: 'Architecture', link: '/architecture/', activeMatch: '/architecture/' },
      { text: 'Status', link: '/status', activeMatch: '/status' },
      { text: 'Environment', link: '/harness/', activeMatch: '/harness/' },
      { text: 'Skills', link: '/skiller/guide/', activeMatch: '/skiller/' },
      { text: 'Memory and graph', link: '/maind/', activeMatch: '/maind/' },
      { text: 'Learning', link: '/analyst/', activeMatch: '/analyst/' },
      { text: 'Vault', link: '/brain/', activeMatch: '/brain/' },
      { text: 'References', link: '/reference', activeMatch: '/reference' },
      { text: 'core → aicore', link: '/core/', activeMatch: '/core/' },
      { text: 'planner', link: '/planner/', activeMatch: '/planner/' },
      { text: 'orch', link: '/orch/', activeMatch: '/orch/' },
    ],

    sidebar: {
      '/harness/': [
        {
          text: 'Environment (harness)',
          items: [
            { text: 'Harness CLI overview', link: '/harness/' },
            { text: 'Permissions for Claude Code', link: '/harness/configs/claude-permissions' },
            { text: 'Configuration overview', link: '/harness/configs/' },
            { text: 'Claude Code host setup', link: '/harness/setup/claude' },
            { text: 'Cursor host setup', link: '/harness/setup/cursor' },
            { text: 'Grok host setup', link: '/harness/setup/grok' },
            { text: 'Canon of root instructions', link: '/harness/reference/instruction-canon' },
            { text: '*.env.ini: hook intent', link: '/harness/reference/hook-intent-files' },
            { text: 'Execution Policy', link: '/harness/reference/execution-policy' },
            { text: 'Exec-wave driver', link: '/harness/reference/exec-wave' },
          ],
        },
        {
          text: 'Integrations (MCP)',
          items: [
            { text: 'Overview', link: '/harness/integrations/' },
            { text: 'Context7 MCP', link: '/harness/integrations/context7' },
            { text: 'Playwright MCP', link: '/harness/integrations/playwright-mcp' },
            { text: 'filesystem MCP', link: '/harness/integrations/filesystem' },
            { text: 'fetch MCP', link: '/harness/integrations/fetch' },
            { text: 'memory MCP', link: '/harness/integrations/memory' },
            { text: 'sequential-thinking MCP', link: '/harness/integrations/sequential-thinking' },
            { text: 'GitHub MCP', link: '/harness/integrations/github' },
            { text: 'Task Master AI', link: '/harness/integrations/task-master' },
            { text: 'GitHub Spec Kit', link: '/harness/integrations/spec-kit' },
            { text: 'Claude Code Router', link: '/harness/integrations/claude-code-router' },
          ],
        },
      ],

      '/skiller/': [
        {
          text: 'Skills (skiller)',
          items: [
            { text: 'About SwissKnifeMan', link: '/skiller/guide/' },
            { text: 'Skill architecture (reality)', link: '/skiller/guide/skills-architecture' },
            { text: 'Installing skills', link: '/skiller/guide/installation' },
            { text: 'Vendor-mode (sync)', link: '/skiller/guide/vendor-mode' },
            { text: 'Configuration and metadata', link: '/skiller/guide/configuration' },
            { text: 'Integration checklist', link: '/skiller/guide/integration-checklist' },
            { text: 'CLI swissknifeman', link: '/skiller/guide/cli' },
            { text: 'Profiles and auto detection', link: '/skiller/guide/profiles' },
            { text: 'Anatomy of a skill', link: '/skiller/guide/skill-anatomy' },
            { text: 'Adapter deltas', link: '/skiller/guide/adapter-deltas' },
            { text: 'Methodology: against code bloat', link: '/skiller/guide/methodology' },
            { text: 'Loop semantics', link: '/skiller/guide/loop-semantics' },
            { text: 'Creating skills', link: '/skiller/guide/creating-skills' },
            { text: 'Skills from packages', link: '/skiller/guide/vendor-skills' },
            { text: 'Upstream-sync', link: '/skiller/guide/upstream-sync' },
            { text: 'Vendor skills: trust and triage', link: '/skiller/guide/vendored-skills' },
            { text: 'Registry skills.json', link: '/skiller/guide/registry' },
            { text: 'Dependency graph', link: '/skiller/guide/graph' },
            { text: 'Snippet scanner', link: '/skiller/guide/scanner' },
            { text: 'CI/CD', link: '/skiller/guide/ci' },
            { text: 'Diagnostics and update', link: '/skiller/guide/troubleshooting' },
            { text: 'Compatible with Laravel Boost', link: '/skiller/boost-compatibility' },
          ],
        },
        {
          text: 'Adapters IDE',
          items: [
            { text: 'Claude Code', link: '/skiller/adapters/claude-code' },
            { text: 'Cursor', link: '/skiller/adapters/cursor' },
            { text: 'Grok', link: '/skiller/adapters/grok' },
            { text: 'Perplexity', link: '/skiller/adapters/perplexity' },
          ],
        },
        {
          text: 'Workflow',
          items: [
            { text: 'AI-assisted development', link: '/skiller/workflows/' },
            { text: 'Perplexity', link: '/skiller/workflows/perplexity' },
            { text: 'Claude', link: '/skiller/workflows/claude' },
            { text: 'Claude Fable 5', link: '/skiller/workflows/fable-5' },
            { text: 'Cursor / VS Code', link: '/skiller/workflows/cursor' },
            { text: 'Python / 3D', link: '/skiller/workflows/python-3d' },
            { text: 'Background agents', link: '/skiller/workflows/background-agents' },
            { text: 'Frame audit (Perplexity)', link: '/skiller/workflows/framework-audit' },
          ],
        },
        {
          text: 'Agent Framework',
          items: [
            { text: 'Frame overview', link: '/skiller/agent-framework/' },
            { text: 'Current Status', link: '/skiller/agent-framework/framework-overview' },
            { text: 'Register of decisions', link: '/skiller/agent-framework/decisions-ledger' },
            { text: 'Universal roles', link: '/skiller/agent-framework/roles' },
            { text: 'Hub = Skills Index', link: '/skiller/agent-framework/skills-index-and-hub' },
            { text: 'Checklist after implementation', link: '/skiller/agent-framework/post-integration-checklist' },
            { text: 'Agent Teams (Mesh)', link: '/skiller/agent-framework/agent-teams' },
            { text: 'Audit archive', link: '/skiller/audits/' },
          ],
        },
        {
          text: 'Examples',
          items: [
            { text: 'Laravel-project from scratch', link: '/skiller/examples/laravel' },
            { text: 'PHP package', link: '/skiller/examples/php-package' },
            { text: 'Obsidian vault', link: '/skiller/examples/obsidian' },
          ],
        },
      ],

      '/maind/': [
        {
          text: 'Getting started',
          items: [
            { text: 'mAInd overview', link: '/maind/' },
            { text: 'About mAInd', link: '/maind/guide/' },
            { text: 'Ecosystem philosophy', link: '/maind/ecosystem' },
            { text: 'Node architecture', link: '/maind/architecture' },
            { text: 'How does it all work', link: '/maind/guide/how-it-works' },
            { text: 'FAQ — frequently asked questions', link: '/maind/guide/faq' },
            { text: 'Solutions, trade-offs, restrictions', link: '/maind/guide/design-notes' },
            { text: 'Installation', link: '/maind/guide/installation' },
            { text: 'Config config.json', link: '/maind/guide/config' },
          ],
        },
        {
          text: 'Connections: memory + graph',
          items: [
            { text: 'Memory (agent-memory)', link: '/maind/guide/memory' },
            { text: 'Connection graph', link: '/maind/guide/graph' },
            { text: 'Federation', link: '/maind/guide/federation' },
            { text: 'Namespaces', link: '/maind/guide/namespaces' },
            { text: 'Code graph (Serena)', link: '/maind/guide/code-graph' },
          ],
        },
        {
          text: 'Provisioning and operation',
          items: [
            { text: 'CLI', link: '/maind/guide/cli' },
            { text: 'Fleet (interproject layer)', link: '/maind/guide/fleet' },
            { text: 'MCP-server', link: '/maind/guide/mcp' },
            { text: 'Plugin Claude Code', link: '/maind/guide/plugin' },
            { text: 'Healthcheck', link: '/maind/guide/health' },
            { text: 'Sync', link: '/maind/guide/sync' },
            { text: 'Memory daemon (systemd)', link: '/maind/guide/systemd' },
            { text: 'Trust (workspace)', link: '/maind/guide/workspace' },
          ],
        },
        {
          text: 'Registries and migration',
          items: [
            { text: 'Agents', link: '/maind/guide/agents' },
            { text: 'Projects', link: '/maind/guide/projects' },
            { text: 'Migration', link: '/maind/guide/migration' },
          ],
        },
        {
          text: 'Roadmap',
          items: [{ text: 'Development ideas', link: '/maind/roadmap' }],
        },
      ],

      '/analyst/': [
        {
          text: 'Learning (analyst)',
          items: [
            { text: 'Analyst overview', link: '/analyst/' },
            { text: 'About analyst', link: '/analyst/guide/' },
            { text: 'Package architecture', link: '/analyst/architecture' },
          ],
        },
        {
          text: 'How does this work',
          items: [
            { text: 'CLI and commands', link: '/analyst/guide/cli' },
            { text: 'Lesson life cycle', link: '/analyst/guide/lifecycle' },
            { text: 'Pathology catalog', link: '/analyst/guide/pathologies' },
            { text: 'Tuning-parameters', link: '/analyst/guide/tuning' },
            { text: 'suggest — skill draft (P4)', link: '/analyst/guide/suggest' },
          ],
        },
        {
          text: 'Roadmap',
          items: [{ text: 'Deferred (P5)', link: '/analyst/roadmap' }],
        },
      ],

      '/brain/': [
        {
          text: 'Vault (brain)',
          items: [
            { text: 'Brain overview', link: '/brain/' },
            { text: 'Guide', link: '/brain/guide/' },
          ],
        },
        {
          text: 'Reference',
          items: [{ text: 'Command reference', link: '/brain/reference/cli' }],
        },
      ],

      '/orch/': [
        {
          text: 'Orchestration contracts (orch)',
          items: [
            { text: 'Overview', link: '/orch/' },
            { text: 'Architecture', link: '/orch/architecture' },
            { text: 'Contracts exec/v1', link: '/orch/contracts' },
            { text: 'Engine Port', link: '/orch/engine-port' },
            { text: 'Adding an engine', link: '/orch/adding-an-engine' },
          ],
        },
        {
          text: 'Conducting work',
          items: [
            { text: 'Quickstart', link: '/orch/quickstart' },
            { text: 'How work flows (diagrams)', link: '/orch/flows' },
            { text: 'Conductor', link: '/orch/conductor' },
            { text: 'Agent mode', link: '/orch/agent-mode' },
            { text: 'Work source', link: '/orch/work-source' },
            { text: 'Run-policy packs', link: '/orch/run-policies' },
            { text: 'Research sources', link: '/orch/research' },
            { text: 'Configuration', link: '/orch/configuration' },
            { text: 'Events', link: '/orch/events' },
            { text: 'Engine conformance', link: '/orch/conformance' },
          ],
        },
      ],

      '/planner/': [
        {
          text: 'Intent commands (planner)',
          items: [{ text: 'Overview: /planner:* commands', link: '/planner/' }],
        },
        {
          text: 'Methodology plan-protocol',
          items: [
            { text: 'Full cycle', link: '/planner/methodology' },
            { text: 'Plan Structure', link: '/planner/plan-structure' },
            { text: 'Templates', link: '/planner/templates' },
            { text: 'Constructor workflow', link: '/planner/workflows' },
            { text: 'Configuration', link: '/planner/configuration' },
            { text: 'Events and extensions', link: '/planner/extensions' },
          ],
        },
      ],

      '/architecture/': [
        {
          text: 'Architecture',
          items: [
            { text: 'Overview', link: '/architecture/' },
            { text: 'Ecosystem', link: '/architecture/ecosystem' },
            { text: 'Contracts', link: '/architecture/contracts' },
            { text: 'Ownership map', link: '/architecture/ownership' },
            { text: 'Portable workspace', link: '/workspace' },
          ],
        },
        {
          text: 'Decisions',
          collapsed: true,
          items: [
            { text: 'Format and index', link: '/architecture/decisions/README' },
            { text: '0001 Modules are isolated folders with a manifest; no new repositories yet', link: '/architecture/decisions/0001-modules-as-isolated-folders' },
            { text: '0002 A module depends only on its own library and on aicore', link: '/architecture/decisions/0002-module-dependencies-only-on-aicore' },
            { text: '0003 Three kinds of links; bridges connect planner and orch', link: '/architecture/decisions/0003-three-kinds-of-links-and-bridges' },
            { text: '0004 aicore is the foundation, with a strict generalisation boundary', link: '/architecture/decisions/0004-aicore-foundation-and-generalisation-boundary' },
            { text: '0005 Layered configuration and standard state locations', link: '/architecture/decisions/0005-layered-config-and-standard-state-locations' },
            { text: '0006 Extensibility through events, subscriptions, overlays and external commands', link: '/architecture/decisions/0006-extensibility-events-subscriptions-overlays' },
            { text: '0007 brain is a hub module; only its foundation is in scope', link: '/architecture/decisions/0007-brain-module-scope' },
            { text: '0008 Only shared skills stay in skiller; module skills move to their module', link: '/architecture/decisions/0008-skills-live-in-their-module' },
            { text: '0009 task becomes planner, with aliases; plan URNs do not change', link: '/architecture/decisions/0009-task-renamed-to-planner' },
            { text: '0010 Transition through swissknifeman upgrade and an upgrade guide', link: '/architecture/decisions/0010-upgrade-command-and-guide' },
            { text: '0011 TOML for human-edited configuration layers, JSON for generated state', link: '/architecture/decisions/0011-toml-for-human-edited-config' },
            { text: '0012 Planner budgets, thresholds and behaviour are configurable', link: '/architecture/decisions/0012-planner-configuration' },
            { text: '0013 Orchestration scenarios and execution through a prepared brief', link: '/architecture/decisions/0013-orchestration-scenarios-and-prepared-brief' },
            { text: '0014 Language-neutral contracts live in aicore', link: '/architecture/decisions/0014-language-neutral-contracts-in-aicore' },
            { text: '0015 Versions by dimension and stability stages', link: '/architecture/decisions/0015-versions-by-dimension-and-stability-stages' },
            { text: '0016 Extension model: levels, manifest before launch, handshake, trust', link: '/architecture/decisions/0016-extension-model-levels-and-trust' },
            { text: '0017 Boundary between aicore.provider and the orch engines; error taxonomy', link: '/architecture/decisions/0017-provider-boundary-and-error-taxonomy' },
            { text: '0018 Execution protocol: event identity, fencing, idempotency, immutable launch plan', link: '/architecture/decisions/0018-execution-protocol-identity-fencing-idempotency' },
            { text: '0019 Configuration semantics: merging, removal, explain, secrets, invocation layer', link: '/architecture/decisions/0019-config-semantics' },
            { text: '0020 Migration discipline: golden fixtures, shims with a window, shadow comparison, rollback', link: '/architecture/decisions/0020-migration-discipline' },
            { text: '0021 Durable architecture documentation and decision records in the repository', link: '/architecture/decisions/0021-durable-architecture-docs' },
            { text: '0022 Doctor is a contract of every module', link: '/architecture/decisions/0022-doctor-as-module-contract' },
            { text: '0023 Releases and supply chain: what is needed now and what waits for a trigger', link: '/architecture/decisions/0023-releases-and-supply-chain' },
            { text: '0024 Python package names of modules', link: '/architecture/decisions/0024-python-package-names' },
            { text: '0025 Shape of unit.json and the aicore skeleton', link: '/architecture/decisions/0025-unit-manifest-shape-and-aicore-skeleton' },
            { text: '0026 The folder-is-a-module rule through a pinned root common instruction', link: '/architecture/decisions/0026-pinned-root-common-instruction' },
            { text: '0027 Golden fixtures: location, normalisation, lifecycle outside CI', link: '/architecture/decisions/0027-golden-fixtures-lifecycle' },
            { text: '0072 The umbrella CLI reads modules from unit.json; aliases are data', link: '/architecture/decisions/0072-umbrella-reads-modules-from-unit-json' },
            { text: '0073 swissknifeman doctor aggregates the doctor probes of modules', link: '/architecture/decisions/0073-doctor-aggregator' },
            { text: '0074 swissknifeman install with profiles; install.sh is a wrapper', link: '/architecture/decisions/0074-install-profiles' },
            { text: '0075 The marketplace and the Codex index come from unit.json', link: '/architecture/decisions/0075-marketplace-from-unit-json' },
            { text: '0076 Conformance kit for plugins and engines', link: '/architecture/decisions/0076-conformance-kit' },
            { text: '0077 Release bundle: compat manifest, schemas, attestation, checksums', link: '/architecture/decisions/0077-release-bundle' },
            { text: '0078 Installed-form smoke and a CI matrix from unit.json', link: '/architecture/decisions/0078-installed-form-smoke-and-ci-matrix' },
            { text: '0079 The skm front door is a plugin of the hub root', link: '/architecture/decisions/0079-umbrella-front-door-plugin-at-the-root' },
          ],
        },
      ],

      '/': [
        {
          text: 'Ecosystem',
          items: [
            { text: 'Overview', link: '/' },
            { text: 'How SwissKnifeMan works', link: '/overview' },
            { text: 'Get started', link: '/getting-started' },
            { text: 'Install profiles', link: '/install-profiles' },
            { text: 'Development with Claude Code', link: '/develop' },
            { text: 'Architecture', link: '/architecture/' },
            { text: 'Deployment: new host / team', link: '/deploy' },
            { text: 'Routing sources and tasks', link: '/routing' },
            { text: 'Control-surface projects', link: '/control-surface' },
            { text: 'Roadmap', link: '/roadmap' },
          ],
        },
        {
          text: 'Hub reference',
          items: [
            { text: 'Umbrella CLI', link: '/reference/umbrella' },
            { text: 'Doctor aggregator', link: '/reference/doctor' },
            { text: 'Conformance kit', link: '/reference/conformance' },
            { text: 'Release bundle', link: '/reference/release-bundle' },
          ],
        },
        {
          text: 'Packages',
          items: [
            { text: 'Skills — skiller', link: '/skiller/guide/' },
            { text: 'Environment — harness', link: '/harness/' },
            { text: 'Memory and graph — maind', link: '/maind/' },
            { text: 'Learning — analyst', link: '/analyst/' },
            { text: 'Vault — brain', link: '/brain/' },
            { text: 'Foundation — core moved to aicore', link: '/core/' },
            { text: 'Intent commands — planner', link: '/planner/' },
          ],
        },
      ],
    },

    socialLinks: [
      { icon: 'github', link: 'https://github.com/academici/swissknifeman' },
    ],

    search: {
      provider: 'local',
      options: {
        translations: {
          button: { buttonText: 'Search', buttonAriaLabel: 'Search' },
          modal: {
            noResultsText: 'Nothing found',
            resetButtonTitle: 'Reset',
            footer: { selectText: 'choose', navigateText: 'navigation', closeText: 'close' },
          },
        },
      },
    },

    outline: { label: 'On this page' },
    docFooter: { prev: 'Back', next: 'Forward' },
    lastUpdated: { text: 'Updated' },
    darkModeSwitchLabel: 'Subject',
    sidebarMenuLabel: 'Menu',
    returnToTopLabel: 'Top',
  },
}))
