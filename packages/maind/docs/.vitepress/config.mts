import { defineConfig } from 'vitepress'
import { withMermaid } from 'vitepress-plugin-mermaid'

export default withMermaid(defineConfig({
  lang: 'en-US',
  title: 'mAInd',
  description:
    'Central node of the ecosystem academici: agent memory, connection graph, register of agents and projects, MCP-server',
  base: '/maind/',
  lastUpdated: true,

  themeConfig: {
    nav: [
      { text: 'Hyde', link: '/guide/', activeMatch: '/guide/' },
      { text: 'Ecosystem', link: '/ecosystem', activeMatch: '/ecosystem' },
      { text: 'Architecture', link: '/architecture', activeMatch: '/architecture' },
      { text: 'Roadmap', link: '/roadmap', activeMatch: '/roadmap' },
    ],

    sidebar: {
      '/': [
        {
          text: 'Getting started',
          items: [
            { text: 'About mAInd', link: '/guide/' },
            { text: 'Ecosystem philosophy', link: '/ecosystem' },
            { text: 'Node architecture', link: '/architecture' },
            { text: 'How does it all work', link: '/guide/how-it-works' },
            { text: 'FAQ — frequently asked questions', link: '/guide/faq' },
            { text: 'Solutions, trade-offs, restrictions', link: '/guide/design-notes' },
            { text: 'Installation', link: '/guide/installation' },
            { text: 'Config config.json', link: '/guide/config' },
            { text: 'Decision tree: project setup', link: '/guide/onboarding-decision-tree' },
          ],
        },
        {
          text: 'Connections: memory + graph',
          items: [
            { text: 'Memory (agent-memory)', link: '/guide/memory' },
            { text: 'Connection graph', link: '/guide/graph' },
            { text: 'Federation', link: '/guide/federation' },
            { text: 'Namespaces', link: '/guide/namespaces' },
            { text: 'Code graph (Serena)', link: '/guide/code-graph' },
          ],
        },
        {
          text: 'Provisioning and operation',
          items: [
            { text: 'CLI', link: '/guide/cli' },
            { text: 'Fleet (interproject layer)', link: '/guide/fleet' },
            { text: 'MCP-server', link: '/guide/mcp' },
            { text: 'Plugin Claude Code', link: '/guide/plugin' },
            { text: 'Healthcheck', link: '/guide/health' },
            { text: 'Sync', link: '/guide/sync' },
            { text: 'Memory daemon (systemd)', link: '/guide/systemd' },
            { text: 'Trust (workspace)', link: '/guide/workspace' },
          ],
        },
        {
          text: 'Registries and migration',
          items: [
            { text: 'Agents', link: '/guide/agents' },
            { text: 'Projects', link: '/guide/projects' },
            { text: 'Migration', link: '/guide/migration' },
          ],
        },
        {
          text: 'Roadmap',
          items: [{ text: 'Development ideas', link: '/roadmap' }],
        },
      ],
    },

    socialLinks: [
      { icon: 'github', link: 'https://github.com/academici/maind' },
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
