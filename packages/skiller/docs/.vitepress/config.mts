import { defineConfig } from 'vitepress'
import { withMermaid } from 'vitepress-plugin-mermaid'

// Standalone-building package docks skiller (registry AI-skills). In an umbrella unit
// this .vitepress discarded (scripts/docs-sync.sh), and the docks are collected in common
// docs/.vitepress/config.mts under the base /swissknifeman/. Internal Dock Links
// relative → the same source is collected here too, and in the unit.
// Cross-package links (to the docks harness and umbrella /routing) only resolve
// in the unit — V standalone They «outward», therefore marked ignoreDeadLinks.
export default withMermaid(defineConfig({
  lang: 'en-US',
  title: 'SwissKnifeMan',
  description:
    'Universal personal registry AI-skills: one source of truth, installation in any project and any IDE',
  base: '/skiller/',
  lastUpdated: true,

  ignoreDeadLinks: [/^\/harness\//, /^\/task\//, /^\/routing/, /^\/roadmap\b/, /^\/maind\//],

  themeConfig: {
    nav: [
      { text: 'Overview', link: '/' },
      { text: 'Hyde', link: '/guide/', activeMatch: '/guide/' },
      { text: 'Adapters', link: '/adapters/claude-code', activeMatch: '/adapters/' },
      { text: 'Workflow', link: '/workflows/', activeMatch: '/workflows/' },
      { text: 'Examples', link: '/examples/laravel', activeMatch: '/examples/' },
    ],

    sidebar: {
      '/': [
        {
          text: 'Skills (skiller)',
          items: [
            { text: 'About SwissKnifeMan', link: '/guide/' },
            { text: 'Skill architecture (reality)', link: '/guide/skills-architecture' },
            { text: 'Installing skills', link: '/guide/installation' },
            { text: 'Vendor-mode (sync)', link: '/guide/vendor-mode' },
            { text: 'Integration checklist', link: '/guide/integration-checklist' },
            { text: 'CLI swissknifeman', link: '/guide/cli' },
            { text: 'Profiles and auto detection', link: '/guide/profiles' },
            { text: 'Archetypes: recipes and forks', link: '/guide/archetypes' },
            { text: 'Anatomy of a skill', link: '/guide/skill-anatomy' },
            { text: 'Taxonomy and granularity', link: '/guide/skill-taxonomy' },
            { text: 'Adapter deltas', link: '/guide/adapter-deltas' },
            { text: 'Methodology: against code bloat', link: '/guide/methodology' },
            { text: 'Loop semantics', link: '/guide/loop-semantics' },
            { text: 'Creating skills', link: '/guide/creating-skills' },
            { text: 'Behavioral tests (evals)', link: '/guide/evals' },
            { text: 'Skills from packages', link: '/guide/vendor-skills' },
            { text: 'Upstream-sync', link: '/guide/upstream-sync' },
            { text: 'Vendor skills: trust and triage', link: '/guide/vendored-skills' },
            { text: 'Registry skills.json', link: '/guide/registry' },
            { text: 'Dependency graph', link: '/guide/graph' },
            { text: 'Token Budget Map', link: '/guide/budget' },
            { text: 'Bucket-audit 2026-07', link: '/guide/bucket-audit-2026-07' },
            { text: 'Polyglot-monorepo', link: '/guide/polyglot-monorepo' },
            { text: 'Snippet scanner', link: '/guide/scanner' },
            { text: 'CI/CD', link: '/guide/ci' },
            { text: 'Diagnostics and update', link: '/guide/troubleshooting' },
            { text: 'Compatible with Laravel Boost', link: '/boost-compatibility' },
            { text: 'Local distribution .ai/ to providers (dev-plan)', link: '/multi-provider-distribution' },
          ],
        },
        {
          text: 'Adapters IDE',
          items: [
            { text: 'Claude Code', link: '/adapters/claude-code' },
            { text: 'Cursor', link: '/adapters/cursor' },
            { text: 'Perplexity', link: '/adapters/perplexity' },
          ],
        },
        {
          text: 'Workflow',
          items: [
            { text: 'AI-assisted development', link: '/workflows/' },
            { text: 'Perplexity', link: '/workflows/perplexity' },
            { text: 'Claude', link: '/workflows/claude' },
            { text: 'Claude Fable 5', link: '/workflows/fable-5' },
            { text: 'Cursor / VS Code', link: '/workflows/cursor' },
            { text: 'Python / 3D', link: '/workflows/python-3d' },
            { text: 'Background agents', link: '/workflows/background-agents' },
            { text: 'Frame audit (Perplexity)', link: '/workflows/framework-audit' },
          ],
        },
        {
          text: 'Agent Framework',
          items: [
            { text: 'Frame overview', link: '/agent-framework/' },
            { text: 'Current Status', link: '/agent-framework/framework-overview' },
            { text: 'Register of decisions', link: '/agent-framework/decisions-ledger' },
            { text: 'Universal roles', link: '/agent-framework/roles' },
            { text: 'Hub = Skills Index', link: '/agent-framework/skills-index-and-hub' },
            { text: 'Checklist after implementation', link: '/agent-framework/post-integration-checklist' },
            { text: 'Agent Teams (Mesh)', link: '/agent-framework/agent-teams' },
            { text: 'Audit archive', link: '/audits/' },
          ],
        },
        {
          text: 'Examples',
          items: [
            { text: 'Laravel-project from scratch', link: '/examples/laravel' },
            { text: 'PHP package', link: '/examples/php-package' },
            { text: 'Obsidian vault', link: '/examples/obsidian' },
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
