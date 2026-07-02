import { defineConfig } from 'vitepress'

// Standalone-сборка доков пакета harness (окружение Claude Code). В зонтичном
// агрегате эта .vitepress отбрасывается (scripts/docs-sync.sh), а доки собираются
// общим docs/.vitepress/config.mts под базой /swissknifeman/. Внутренние ссылки
// доков относительные → один и тот же источник собирается и здесь, и в агрегате.
export default defineConfig({
  lang: 'ru-RU',
  title: 'harness',
  description:
    'Настройка окружения Claude Code: пресеты permissions, режимы auto-approve/bypass, MCP-серверы, хуки',
  base: '/harness/',
  lastUpdated: true,

  themeConfig: {
    nav: [
      { text: 'Обзор', link: '/' },
      { text: 'Permissions', link: '/configs/claude-permissions' },
      { text: 'Agent-packs', link: '/configs/agent-packs' },
      { text: 'Интеграции', link: '/integrations/', activeMatch: '/integrations/' },
    ],

    sidebar: {
      '/': [
        {
          text: 'Окружение (harness)',
          items: [
            { text: 'Обзор: CLI harness', link: '/' },
            { text: 'Permissions для Claude Code', link: '/configs/claude-permissions' },
            { text: 'Agent-packs: паки субагентов', link: '/configs/agent-packs' },
            { text: 'Конфиги (обзор)', link: '/configs/' },
            { text: 'Настройка Claude Code (машина)', link: '/setup/claude' },
          ],
        },
        {
          text: 'Интеграции (MCP)',
          items: [
            { text: 'Обзор', link: '/integrations/' },
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
          button: { buttonText: 'Поиск', buttonAriaLabel: 'Поиск' },
          modal: {
            noResultsText: 'Ничего не найдено',
            resetButtonTitle: 'Сбросить',
            footer: { selectText: 'выбрать', navigateText: 'навигация', closeText: 'закрыть' },
          },
        },
      },
    },

    outline: { label: 'На этой странице' },
    docFooter: { prev: 'Назад', next: 'Вперёд' },
    lastUpdated: { text: 'Обновлено' },
    darkModeSwitchLabel: 'Тема',
    sidebarMenuLabel: 'Меню',
    returnToTopLabel: 'Наверх',
  },
})
