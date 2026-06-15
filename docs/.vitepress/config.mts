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
          text: 'Знакомство',
          items: [
            { text: 'Что такое mAInd', link: '/guide/' },
            { text: 'Философия экосистемы', link: '/ecosystem' },
            { text: 'Архитектура узла', link: '/architecture' },
            { text: 'Как это всё работает', link: '/guide/how-it-works' },
            { text: 'Установка', link: '/guide/installation' },
            { text: 'Конфиг .maind.json', link: '/guide/config' },
          ],
        },
        {
          text: 'Связи: память + граф',
          items: [
            { text: 'Память (agent-memory)', link: '/guide/memory' },
            { text: 'Граф связей', link: '/guide/graph' },
            { text: 'Федерация', link: '/guide/federation' },
            { text: 'Namespaces', link: '/guide/namespaces' },
            { text: 'graphify (граф кода)', link: '/guide/graphify' },
          ],
        },
        {
          text: 'Провижининг и эксплуатация',
          items: [
            { text: 'CLI', link: '/guide/cli' },
            { text: 'MCP-сервер', link: '/guide/mcp' },
            { text: 'Healthcheck', link: '/guide/health' },
            { text: 'Sync', link: '/guide/sync' },
            { text: 'Демон памяти (systemd)', link: '/guide/systemd' },
            { text: 'Доверие (workspace)', link: '/guide/workspace' },
          ],
        },
        {
          text: 'Реестры и миграция',
          items: [
            { text: 'Агенты', link: '/guide/agents' },
            { text: 'Проекты', link: '/guide/projects' },
            { text: 'Миграция', link: '/guide/migration' },
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
