import { defineConfig } from 'vitepress'

export default defineConfig({
  lang: 'ru-RU',
  title: 'SwissKnifeMan',
  description:
    'Универсальный личный реестр AI-скиллов и конфигов: один источник истины для любого проекта и любой IDE',
  base: '/swissknifeman/',
  lastUpdated: true,

  themeConfig: {
    nav: [
      { text: 'Гайд', link: '/guide/', activeMatch: '/guide/' },
      { text: 'Конфиги', link: '/configs/', activeMatch: '/configs/' },
      { text: 'Адаптеры', link: '/adapters/claude-code', activeMatch: '/adapters/' },
      { text: 'Примеры', link: '/examples/laravel', activeMatch: '/examples/' },
    ],

    sidebar: {
      '/': [
        {
          text: 'Гайд',
          items: [
            { text: 'Что такое SwissKnifeMan', link: '/guide/' },
            { text: 'Установка скиллов', link: '/guide/installation' },
            { text: 'Профили и автодетект', link: '/guide/profiles' },
            { text: 'Анатомия скилла', link: '/guide/skill-anatomy' },
            { text: 'Адаптерные дельты', link: '/guide/adapter-deltas' },
            { text: 'Создание скиллов', link: '/guide/creating-skills' },
            { text: 'Скиллы из пакетов', link: '/guide/vendor-skills' },
            { text: 'Upstream-sync', link: '/guide/upstream-sync' },
            { text: 'Реестр skills.json', link: '/guide/registry' },
            { text: 'Сканер сниппетов', link: '/guide/scanner' },
            { text: 'CI/CD', link: '/guide/ci' },
          ],
        },
        {
          text: 'Окружение',
          items: [
            { text: 'Настройка Claude Code', link: '/setup/claude' },
          ],
        },
        {
          text: 'Конфиги',
          items: [
            { text: 'Обзор', link: '/configs/' },
            { text: 'Permissions для Claude Code', link: '/configs/claude-permissions' },
          ],
        },
        {
          text: 'Адаптеры',
          items: [
            { text: 'Claude Code', link: '/adapters/claude-code' },
            { text: 'Cursor', link: '/adapters/cursor' },
            { text: 'Perplexity', link: '/adapters/perplexity' },
          ],
        },
        {
          text: 'Примеры',
          items: [
            { text: 'Laravel-проект с нуля', link: '/examples/laravel' },
            { text: 'PHP-пакет', link: '/examples/php-package' },
            { text: 'Obsidian vault', link: '/examples/obsidian' },
          ],
        },
        {
          text: 'Roadmap',
          items: [{ text: 'Идеи развития', link: '/roadmap' }],
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
