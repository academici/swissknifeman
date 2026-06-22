import { defineConfig } from 'vitepress'
import { withMermaid } from 'vitepress-plugin-mermaid'

// Зонтичная документация экосистемы. Доки живут ВНУТРИ каждого пакета
// (packages/<pkg>/docs) и подключаются сюда симлинками docs/skiller, docs/harness —
// единый сайт собирается из per-package файлов. Общая информация — в корне docs/.
// maind пока — отдельный сайт (его доки используют абсолютные ссылки своей базы);
// агрегация maind — следующий шаг (нормализация ссылок).
export default withMermaid(defineConfig({
  lang: 'ru-RU',
  title: 'SwissKnifeMan',
  description:
    'Зонтик экосистемы academici: скиллы (skiller), окружение Claude Code (harness), память и граф (maind)',
  base: '/swissknifeman/',
  lastUpdated: true,

  themeConfig: {
    nav: [
      { text: 'Обзор', link: '/' },
      { text: 'Окружение', link: '/harness/', activeMatch: '/harness/' },
      { text: 'Скиллы', link: '/skiller/guide/', activeMatch: '/skiller/' },
      {
        text: 'Память и граф (maind)',
        link: 'https://github.com/academici/swissknifeman/tree/main/packages/maind/docs',
      },
    ],

    sidebar: {
      '/harness/': [
        {
          text: 'Окружение (harness)',
          items: [
            { text: 'Обзор: CLI harness', link: '/harness/' },
            { text: 'Permissions для Claude Code', link: '/harness/configs/claude-permissions' },
            { text: 'Конфиги (обзор)', link: '/harness/configs/' },
            { text: 'Настройка Claude Code (машина)', link: '/harness/setup/claude' },
          ],
        },
        {
          text: 'Интеграции (MCP)',
          items: [
            { text: 'Обзор', link: '/harness/integrations/' },
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
          text: 'Скиллы (skiller)',
          items: [
            { text: 'Что такое SwissKnifeMan', link: '/skiller/guide/' },
            { text: 'Установка скиллов', link: '/skiller/guide/installation' },
            { text: 'Vendor-режим (sync)', link: '/skiller/guide/vendor-mode' },
            { text: 'Чеклист интеграции', link: '/skiller/guide/integration-checklist' },
            { text: 'CLI swissknifeman', link: '/skiller/guide/cli' },
            { text: 'Профили и автодетект', link: '/skiller/guide/profiles' },
            { text: 'Анатомия скилла', link: '/skiller/guide/skill-anatomy' },
            { text: 'Адаптерные дельты', link: '/skiller/guide/adapter-deltas' },
            { text: 'Методология: против раздувания кода', link: '/skiller/guide/methodology' },
            { text: 'Семантика loop’ов', link: '/skiller/guide/loop-semantics' },
            { text: 'Создание скиллов', link: '/skiller/guide/creating-skills' },
            { text: 'Скиллы из пакетов', link: '/skiller/guide/vendor-skills' },
            { text: 'Upstream-sync', link: '/skiller/guide/upstream-sync' },
            { text: 'Реестр skills.json', link: '/skiller/guide/registry' },
            { text: 'Граф зависимостей', link: '/skiller/guide/graph' },
            { text: 'Сканер сниппетов', link: '/skiller/guide/scanner' },
            { text: 'CI/CD', link: '/skiller/guide/ci' },
            { text: 'Диагностика и обновление', link: '/skiller/guide/troubleshooting' },
            { text: 'Совместимость с Laravel Boost', link: '/skiller/boost-compatibility' },
          ],
        },
        {
          text: 'Адаптеры IDE',
          items: [
            { text: 'Claude Code', link: '/skiller/adapters/claude-code' },
            { text: 'Cursor', link: '/skiller/adapters/cursor' },
            { text: 'Perplexity', link: '/skiller/adapters/perplexity' },
          ],
        },
        {
          text: 'Воркфлоу',
          items: [
            { text: 'AI-assisted development', link: '/skiller/workflows/' },
            { text: 'Perplexity', link: '/skiller/workflows/perplexity' },
            { text: 'Claude', link: '/skiller/workflows/claude' },
            { text: 'Claude Fable 5', link: '/skiller/workflows/fable-5' },
            { text: 'Cursor / VS Code', link: '/skiller/workflows/cursor' },
            { text: 'Python / 3D', link: '/skiller/workflows/python-3d' },
            { text: 'Фоновые агенты', link: '/skiller/workflows/background-agents' },
          ],
        },
        {
          text: 'Примеры',
          items: [
            { text: 'Laravel-проект с нуля', link: '/skiller/examples/laravel' },
            { text: 'PHP-пакет', link: '/skiller/examples/php-package' },
            { text: 'Obsidian vault', link: '/skiller/examples/obsidian' },
          ],
        },
      ],

      '/': [
        {
          text: 'Экосистема',
          items: [
            { text: 'Обзор', link: '/' },
            { text: 'Роутинг источников и задач', link: '/routing' },
            { text: 'Roadmap', link: '/roadmap' },
          ],
        },
        {
          text: 'Пакеты',
          items: [
            { text: 'Скиллы — skiller', link: '/skiller/guide/' },
            { text: 'Окружение — harness', link: '/harness/' },
            {
              text: 'Память и граф — maind',
              link: 'https://github.com/academici/swissknifeman/tree/main/packages/maind/docs',
            },
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
}))
