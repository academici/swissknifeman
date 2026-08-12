import { defineConfig } from 'vitepress'
import { withMermaid } from 'vitepress-plugin-mermaid'

export default withMermaid(defineConfig({
  lang: 'ru-RU',
  title: 'Task',
  description: 'Команды задач и executable plan protocol',
  base: '/task/',
  lastUpdated: true,
  ignoreDeadLinks: [/^\/harness\//, /^\/develop/],
  themeConfig: {
    nav: [{ text: 'Обзор', link: '/' }, { text: 'Методология', link: '/methodology' }],
    sidebar: {
      '/': [{
        text: 'Task',
        items: [
          { text: 'Обзор', link: '/' },
          { text: 'Методология', link: '/methodology' },
          { text: 'Структура плана', link: '/plan-structure' },
          { text: 'Миграция v1 → v2', link: '/plan-migration-runbook' },
          { text: 'Шаблоны', link: '/templates' },
          { text: 'Workflow', link: '/workflows' },
          { text: 'Контракт read-budget', link: '/reference/read-budget-contract' },
        ],
      }],
    },
    search: { provider: 'local' },
    outline: { label: 'На этой странице' },
    docFooter: { prev: 'Назад', next: 'Вперёд' },
  },
}))
