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

  themeConfig: {
    nav: [
      { text: 'Overview', link: '/' },
      { text: 'Development', link: '/develop', activeMatch: '/develop' },
      { text: 'Status', link: '/status', activeMatch: '/status' },
      { text: 'Environment', link: '/harness/', activeMatch: '/harness/' },
      { text: 'Skills', link: '/skiller/guide/', activeMatch: '/skiller/' },
      { text: 'Memory and graph', link: '/maind/', activeMatch: '/maind/' },
      { text: 'Learning', link: '/analyst/', activeMatch: '/analyst/' },
      { text: 'References', link: '/reference', activeMatch: '/reference' },
      { text: 'core', link: '/core/', activeMatch: '/core/' },
      { text: 'task', link: '/task/', activeMatch: '/task/' },
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

      '/task/': [
        {
          text: 'Intent commands (task)',
          items: [{ text: 'Overview: /task:* commands', link: '/task/' }],
        },
        {
          text: 'Methodology plan-protocol',
          items: [
            { text: 'Full cycle', link: '/task/methodology' },
            { text: 'Plan Structure', link: '/task/plan-structure' },
            { text: 'Templates', link: '/task/templates' },
            { text: 'Constructor workflow', link: '/task/workflows' },
          ],
        },
      ],

      '/': [
        {
          text: 'Ecosystem',
          items: [
            { text: 'Overview', link: '/' },
            { text: 'Get started', link: '/getting-started' },
            { text: 'Development with Claude Code', link: '/develop' },
            { text: 'Deployment: new host / team', link: '/deploy' },
            { text: 'Routing sources and tasks', link: '/routing' },
            { text: 'Control-surface projects', link: '/control-surface' },
            { text: 'Roadmap', link: '/roadmap' },
          ],
        },
        {
          text: 'Packages',
          items: [
            { text: 'Skills — skiller', link: '/skiller/guide/' },
            { text: 'Environment — harness', link: '/harness/' },
            { text: 'Memory and graph — maind', link: '/maind/' },
            { text: 'Learning — analyst', link: '/analyst/' },
            { text: 'Foundation — core', link: '/core/' },
            { text: 'Intent commands — task', link: '/task/' },
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
