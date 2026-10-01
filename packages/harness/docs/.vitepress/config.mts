import { defineConfig } from 'vitepress'

// Standalone-building package docks harness (environment Claude Code). In the umbrella
// this unit .vitepress discarded (scripts/docs-sync.sh), and the docks are gathering
// general docs/.vitepress/config.mts under the base /swissknifeman/. Internal links
// docks relative → the same source is collected here too, and in the unit.
export default defineConfig({
  lang: 'en-US',
  title: 'harness',
  description:
    'Setting up the environment Claude Code: presets permissions, modes auto-approve/bypass, MCP-servers, hooks',
  base: '/harness/',
  lastUpdated: true,

  ignoreDeadLinks: [/^\/skiller\//, /^\/task\//, /^\/maind\//],

  themeConfig: {
    nav: [
      { text: 'Overview', link: '/' },
      { text: 'Permissions', link: '/configs/claude-permissions' },
      { text: 'Agent-packs', link: '/configs/agent-packs' },
      { text: 'Integrations', link: '/integrations/', activeMatch: '/integrations/' },
    ],

    sidebar: {
      '/': [
        {
          text: 'Environment (harness)',
          items: [
            { text: 'Harness CLI overview', link: '/' },
            { text: 'Permissions for Claude Code', link: '/configs/claude-permissions' },
            { text: 'Agent-packs: packs of subagents', link: '/configs/agent-packs' },
            { text: 'Statusline: context and notifications', link: '/configs/statusline' },
            { text: 'Configuration overview', link: '/configs/' },
            { text: 'Claude Code host setup', link: '/setup/claude' },
            { text: 'Settings Cursor', link: '/setup/cursor' },
            { text: 'Canon of root instructions', link: '/reference/instruction-canon' },
            { text: '*.env.ini: hook intent', link: '/reference/hook-intent-files' },
            { text: 'Execution Policy', link: '/reference/execution-policy' },
            { text: 'Exec-wave driver', link: '/reference/exec-wave' },
          ],
        },
        {
          text: 'Integrations (MCP)',
          items: [
            { text: 'Overview', link: '/integrations/' },
            { text: 'Context7 MCP', link: '/integrations/context7' },
            { text: 'Playwright MCP', link: '/integrations/playwright-mcp' },
            { text: 'filesystem MCP', link: '/integrations/filesystem' },
            { text: 'fetch MCP', link: '/integrations/fetch' },
            { text: 'memory MCP', link: '/integrations/memory' },
            { text: 'sequential-thinking MCP', link: '/integrations/sequential-thinking' },
            { text: 'GitHub MCP', link: '/integrations/github' },
            { text: 'Task Master AI', link: '/integrations/task-master' },
            { text: 'GitHub Spec Kit', link: '/integrations/spec-kit' },
            { text: 'Claude Code Router', link: '/integrations/claude-code-router' },
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
})
