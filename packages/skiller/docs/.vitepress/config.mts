import { defineConfig } from 'vitepress'
import { withMermaid } from 'vitepress-plugin-mermaid'

// Standalone-сборка доков пакета skiller (реестр AI-скиллов). В зонтичном агрегате
// эта .vitepress отбрасывается (scripts/docs-sync.sh), а доки собираются общим
// docs/.vitepress/config.mts под базой /swissknifeman/. Внутренние ссылки доков
// относительные → один и тот же источник собирается и здесь, и в агрегате.
// Кросс-пакетные ссылки (на доки harness и зонтичный /routing) резолвятся только
// в агрегате — в standalone они «наружу», поэтому помечены ignoreDeadLinks.
export default withMermaid(defineConfig({
  lang: 'ru-RU',
  title: 'SwissKnifeMan',
  description:
    'Универсальный личный реестр AI-скиллов: один источник истины, установка в любой проект и любую IDE',
  base: '/skiller/',
  lastUpdated: true,

  ignoreDeadLinks: [/^\/harness\//, /^\/routing/, /^\/roadmap/, /^\/maind\//],

  themeConfig: {
    nav: [
      { text: 'Обзор', link: '/' },
      { text: 'Гайд', link: '/guide/', activeMatch: '/guide/' },
      { text: 'Адаптеры', link: '/adapters/claude-code', activeMatch: '/adapters/' },
      { text: 'Воркфлоу', link: '/workflows/', activeMatch: '/workflows/' },
      { text: 'Примеры', link: '/examples/laravel', activeMatch: '/examples/' },
    ],

    sidebar: {
      '/': [
        {
          text: 'Скиллы (skiller)',
          items: [
            { text: 'Что такое SwissKnifeMan', link: '/guide/' },
            { text: 'Архитектура скиллов (реальность)', link: '/guide/skills-architecture' },
            { text: 'Установка скиллов', link: '/guide/installation' },
            { text: 'Vendor-режим (sync)', link: '/guide/vendor-mode' },
            { text: 'Чеклист интеграции', link: '/guide/integration-checklist' },
            { text: 'CLI swissknifeman', link: '/guide/cli' },
            { text: 'Профили и автодетект', link: '/guide/profiles' },
            { text: 'Архетипы: рецепты и развилки', link: '/guide/archetypes' },
            { text: 'Анатомия скилла', link: '/guide/skill-anatomy' },
            { text: 'Таксономия и гранулярность', link: '/guide/skill-taxonomy' },
            { text: 'Адаптерные дельты', link: '/guide/adapter-deltas' },
            { text: 'Методология: против раздувания кода', link: '/guide/methodology' },
            { text: 'Семантика loop’ов', link: '/guide/loop-semantics' },
            { text: 'Создание скиллов', link: '/guide/creating-skills' },
            { text: 'Поведенческие тесты (evals)', link: '/guide/evals' },
            { text: 'Скиллы из пакетов', link: '/guide/vendor-skills' },
            { text: 'Upstream-sync', link: '/guide/upstream-sync' },
            { text: 'Вендоренные скиллы: доверие и триаж', link: '/guide/vendored-skills' },
            { text: 'Реестр skills.json', link: '/guide/registry' },
            { text: 'Граф зависимостей', link: '/guide/graph' },
            { text: 'Карта токенового бюджета', link: '/guide/budget' },
            { text: 'Bucket-аудит 2026-07', link: '/guide/bucket-audit-2026-07' },
            { text: 'Polyglot-монорепо', link: '/guide/polyglot-monorepo' },
            { text: 'Сканер сниппетов', link: '/guide/scanner' },
            { text: 'CI/CD', link: '/guide/ci' },
            { text: 'Диагностика и обновление', link: '/guide/troubleshooting' },
            { text: 'Совместимость с Laravel Boost', link: '/boost-compatibility' },
            { text: 'Раздача локального .ai/ на провайдеры (dev-план)', link: '/multi-provider-distribution' },
          ],
        },
        {
          text: 'Адаптеры IDE',
          items: [
            { text: 'Claude Code', link: '/adapters/claude-code' },
            { text: 'Cursor', link: '/adapters/cursor' },
            { text: 'Perplexity', link: '/adapters/perplexity' },
          ],
        },
        {
          text: 'Воркфлоу',
          items: [
            { text: 'AI-assisted development', link: '/workflows/' },
            { text: 'Perplexity', link: '/workflows/perplexity' },
            { text: 'Claude', link: '/workflows/claude' },
            { text: 'Claude Fable 5', link: '/workflows/fable-5' },
            { text: 'Cursor / VS Code', link: '/workflows/cursor' },
            { text: 'Python / 3D', link: '/workflows/python-3d' },
            { text: 'Фоновые агенты', link: '/workflows/background-agents' },
            { text: 'Аудит каркаса (Perplexity)', link: '/workflows/framework-audit' },
          ],
        },
        {
          text: 'Agent Framework',
          items: [
            { text: 'Обзор каркаса', link: '/agent-framework/' },
            { text: 'Текущее состояние', link: '/agent-framework/framework-overview' },
            { text: 'Реестр решений', link: '/agent-framework/decisions-ledger' },
            { text: 'Универсальные роли', link: '/agent-framework/roles' },
            { text: 'Hub = Skills Index', link: '/agent-framework/skills-index-and-hub' },
            { text: 'Чеклист после внедрения', link: '/agent-framework/post-integration-checklist' },
            { text: 'Agent Teams (Mesh)', link: '/agent-framework/agent-teams' },
            { text: 'Архив аудитов', link: '/audits/' },
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
