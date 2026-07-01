import { defineConfig } from 'vitepress'

// Standalone-конфиг доков analyst. В зонтичном агрегате этот .vitepress удаляется
// (scripts/docs-sync.sh), сайт собирается общим docs/.vitepress. Внутренние ссылки
// доков — относительные (работают и standalone, и в агрегате); кросс-пакетные
// (/maind/, /skiller/, /harness/, /routing, /roadmap) в standalone мёртвые → ignoreDeadLinks.
export default defineConfig({
  lang: 'ru-RU',
  title: 'analyst',
  description:
    'Continuous learning экосистемы academici: детерминированный захват уроков из прогонов с человеком в гейте',
  base: '/analyst/',
  lastUpdated: true,

  ignoreDeadLinks: [/^\/harness\//, /^\/maind\//, /^\/skiller\//, /^\/routing/, /^\/roadmap/],

  themeConfig: {
    nav: [
      { text: 'Гайд', link: '/guide/', activeMatch: '/guide/' },
      { text: 'Архитектура', link: '/architecture', activeMatch: '/architecture' },
      { text: 'Roadmap', link: '/roadmap', activeMatch: '/roadmap' },
    ],

    sidebar: {
      '/': [
        {
          text: 'Знакомство',
          items: [
            { text: 'Что такое analyst', link: '/guide/' },
            { text: 'Архитектура пакета', link: '/architecture' },
          ],
        },
        {
          text: 'Как это работает',
          items: [
            { text: 'CLI и команды', link: '/guide/cli' },
            { text: 'Жизненный цикл урока', link: '/guide/lifecycle' },
            { text: 'suggest — черновик скилла (P4)', link: '/guide/suggest' },
          ],
        },
        {
          text: 'Roadmap',
          items: [{ text: 'Отложенное (P5)', link: '/roadmap' }],
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
