import { defineConfig } from 'vitepress'
import { withMermaid } from 'vitepress-plugin-mermaid'

// Зонтичная документация экосистемы. Доки живут ВНУТРИ каждого пакета
// (packages/<pkg>/docs); scripts/docs-sync.sh копирует их в docs/skiller, docs/harness,
// docs/maind (gitignored) — единый сайт собирается из per-package файлов. Общая
// информация — в корне docs/. Внутренние ссылки package-доков относительные → пакет
// собирается и standalone (свой .vitepress), и в этом агрегате.
export default withMermaid(defineConfig({
  lang: 'ru-RU',
  title: 'SwissKnifeMan',
  description:
    'Зонтик экосистемы academici: скиллы (skiller), окружение Claude Code (harness), память и граф (maind)',
  base: '/swissknifeman/',
  lastUpdated: true,
  // roadmap/ живёт в корне репо (вне srcDir доков) — ссылки на него из docs/reference.md
  // указывают на реальные файлы репозитория, но не на страницы сайта: не считаем мёртвыми.
  ignoreDeadLinks: [/roadmap\//],

  themeConfig: {
    nav: [
      { text: 'Обзор', link: '/' },
      { text: 'Разработка', link: '/develop', activeMatch: '/develop' },
      { text: 'Окружение', link: '/harness/', activeMatch: '/harness/' },
      { text: 'Скиллы', link: '/skiller/guide/', activeMatch: '/skiller/' },
      { text: 'Память и граф', link: '/maind/', activeMatch: '/maind/' },
      { text: 'Обучение', link: '/analyst/', activeMatch: '/analyst/' },
      { text: 'Референсы', link: '/reference', activeMatch: '/reference' },
      { text: 'core', link: '/core/', activeMatch: '/core/' },
      { text: 'task', link: '/task/', activeMatch: '/task/' },
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
            { text: 'Архитектура скиллов (реальность)', link: '/skiller/guide/skills-architecture' },
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
            { text: 'Аудит каркаса (Perplexity)', link: '/skiller/workflows/framework-audit' },
          ],
        },
        {
          text: 'Agent Framework',
          items: [
            { text: 'Обзор каркаса', link: '/skiller/agent-framework/' },
            { text: 'Текущее состояние', link: '/skiller/agent-framework/framework-overview' },
            { text: 'Реестр решений', link: '/skiller/agent-framework/decisions-ledger' },
            { text: 'Универсальные роли', link: '/skiller/agent-framework/roles' },
            { text: 'Hub = Skills Index', link: '/skiller/agent-framework/skills-index-and-hub' },
            { text: 'Чеклист после внедрения', link: '/skiller/agent-framework/post-integration-checklist' },
            { text: 'Agent Teams (Mesh)', link: '/skiller/agent-framework/agent-teams' },
            { text: 'Архив аудитов', link: '/skiller/audits/' },
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

      '/maind/': [
        {
          text: 'Знакомство',
          items: [
            { text: 'Обзор mAInd', link: '/maind/' },
            { text: 'Что такое mAInd', link: '/maind/guide/' },
            { text: 'Философия экосистемы', link: '/maind/ecosystem' },
            { text: 'Архитектура узла', link: '/maind/architecture' },
            { text: 'Как это всё работает', link: '/maind/guide/how-it-works' },
            { text: 'FAQ — частые вопросы', link: '/maind/guide/faq' },
            { text: 'Решения, трейд-оффы, ограничения', link: '/maind/guide/design-notes' },
            { text: 'Установка', link: '/maind/guide/installation' },
            { text: 'Конфиг config.json', link: '/maind/guide/config' },
          ],
        },
        {
          text: 'Связи: память + граф',
          items: [
            { text: 'Память (agent-memory)', link: '/maind/guide/memory' },
            { text: 'Граф связей', link: '/maind/guide/graph' },
            { text: 'Федерация', link: '/maind/guide/federation' },
            { text: 'Namespaces', link: '/maind/guide/namespaces' },
            { text: 'Граф кода (Serena)', link: '/maind/guide/code-graph' },
          ],
        },
        {
          text: 'Провижининг и эксплуатация',
          items: [
            { text: 'CLI', link: '/maind/guide/cli' },
            { text: 'Fleet (межпроектный слой)', link: '/maind/guide/fleet' },
            { text: 'MCP-сервер', link: '/maind/guide/mcp' },
            { text: 'Плагин Claude Code', link: '/maind/guide/plugin' },
            { text: 'Healthcheck', link: '/maind/guide/health' },
            { text: 'Sync', link: '/maind/guide/sync' },
            { text: 'Демон памяти (systemd)', link: '/maind/guide/systemd' },
            { text: 'Доверие (workspace)', link: '/maind/guide/workspace' },
          ],
        },
        {
          text: 'Реестры и миграция',
          items: [
            { text: 'Агенты', link: '/maind/guide/agents' },
            { text: 'Проекты', link: '/maind/guide/projects' },
            { text: 'Миграция', link: '/maind/guide/migration' },
          ],
        },
        {
          text: 'Roadmap',
          items: [{ text: 'Идеи развития', link: '/maind/roadmap' }],
        },
      ],

      '/analyst/': [
        {
          text: 'Обучение (analyst)',
          items: [
            { text: 'Обзор analyst', link: '/analyst/' },
            { text: 'Что такое analyst', link: '/analyst/guide/' },
            { text: 'Архитектура пакета', link: '/analyst/architecture' },
          ],
        },
        {
          text: 'Как это работает',
          items: [
            { text: 'CLI и команды', link: '/analyst/guide/cli' },
            { text: 'Жизненный цикл урока', link: '/analyst/guide/lifecycle' },
            { text: 'Каталог патологий', link: '/analyst/guide/pathologies' },
            { text: 'Тюнинг-параметры', link: '/analyst/guide/tuning' },
            { text: 'suggest — черновик скилла (P4)', link: '/analyst/guide/suggest' },
          ],
        },
        {
          text: 'Roadmap',
          items: [{ text: 'Отложенное (P5)', link: '/analyst/roadmap' }],
        },
      ],

      '/task/': [
        {
          text: 'Интент-команды (task)',
          items: [{ text: 'Обзор: команды /task:*', link: '/task/' }],
        },
        {
          text: 'Методология plan-protocol',
          items: [
            { text: 'Полный цикл', link: '/task/methodology' },
            { text: 'Структура плана', link: '/task/plan-structure' },
            { text: 'Шаблоны', link: '/task/templates' },
            { text: 'Конструктор workflow', link: '/task/workflows' },
          ],
        },
      ],

      '/': [
        {
          text: 'Экосистема',
          items: [
            { text: 'Обзор', link: '/' },
            { text: 'Разработка с Claude Code', link: '/develop' },
            { text: 'Роутинг источников и задач', link: '/routing' },
            { text: 'Control-surface проектов', link: '/control-surface' },
            { text: 'Roadmap', link: '/roadmap' },
          ],
        },
        {
          text: 'Пакеты',
          items: [
            { text: 'Скиллы — skiller', link: '/skiller/guide/' },
            { text: 'Окружение — harness', link: '/harness/' },
            { text: 'Память и граф — maind', link: '/maind/' },
            { text: 'Обучение — analyst', link: '/analyst/' },
            { text: 'Фундамент — core', link: '/core/' },
            { text: 'Интент-команды — task', link: '/task/' },
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
