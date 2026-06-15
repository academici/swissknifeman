import { defineConfig } from 'vitepress'
import { withMermaid } from 'vitepress-plugin-mermaid'

export default withMermaid(defineConfig({
  lang: 'ru-RU',
  title: 'mAInd',
  description:
    'Центральный узел экосистемы academici: память агентов, граф связей, реестр агентов и проектов, MCP-сервер',
  base: '/maind/',
  lastUpdated: true,

  themeConfig: {
    nav: [
      { text: 'Гайд', link: '/guide/', activeMatch: '/guide/' },
      { text: 'Экосистема', link: '/ecosystem', activeMatch: '/ecosystem' },
      { text: 'Архитектура', link: '/architecture', activeMatch: '/architecture' },
      { text: 'Roadmap', link: '/roadmap', activeMatch: '/roadmap' },
    ],

    sidebar: {
      '/': [
        {
          text: 'Гайд',
          items: [
            { text: 'Что такое mAInd', link: '/guide/' },
            { text: 'Установка', link: '/guide/installation' },
            { text: 'CLI', link: '/guide/cli' },
            { text: 'Память (agent-memory)', link: '/guide/memory' },
            { text: 'Граф связей', link: '/guide/graph' },
            { text: 'Агенты', link: '/guide/agents' },
            { text: 'Проекты', link: '/guide/projects' },
            { text: 'MCP-сервер', link: '/guide/mcp' },
            { text: 'Конфиг .maind.json', link: '/guide/config' },
            { text: 'Миграция', link: '/guide/migration' },
          ],
        },
        {
          text: 'Экосистема',
          items: [
            { text: 'Философия трёх пакетов', link: '/ecosystem' },
            { text: 'Композиция узла', link: '/architecture' },
          ],
        },
        {
          text: 'Roadmap',
          items: [{ text: 'Идеи развития', link: '/roadmap' }],
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
}))
