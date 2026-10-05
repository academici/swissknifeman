import { defineConfig } from 'vitepress'
import { withMermaid } from 'vitepress-plugin-mermaid'

export default withMermaid(defineConfig({
  lang: 'en-US',
  title: 'Task',
  description: 'Task commands and executable plan protocol',
  base: '/task/',
  lastUpdated: true,
  ignoreDeadLinks: [/^\/harness\//, /^\/develop/],
  themeConfig: {
    nav: [{ text: 'Overview', link: '/' }, { text: 'Methodology', link: '/methodology' }],
    sidebar: {
      '/': [{
        text: 'Task',
        items: [
          { text: 'Overview', link: '/' },
          { text: 'Methodology', link: '/methodology' },
          { text: 'Plan Structure', link: '/plan-structure' },
          { text: 'Templates', link: '/templates' },
          { text: 'Workflow', link: '/workflows' },
          { text: 'Provider model roles', link: '/reference/provider-model-roles' },
        ],
      }],
    },
    search: { provider: 'local' },
    outline: { label: 'On this page' },
    docFooter: { prev: 'Back', next: 'Forward' },
  },
}))
