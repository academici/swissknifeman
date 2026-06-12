---
name: inertia-vue
bucket: frontend
version: 0.2.0
description: "Inertia + Vue в Laravel: страницы, формы, навигация и слоистая организация resources/js (pages, layouts, components, composables, stores, features, events, types, actions/wayfinder)."
risk: write
persona: oss-dev
tags: [inertia, vue, laravel, frontend, architecture, structure]
requires: []
produces_for: []
outputs: []
snippets: [structure.md, composable-example.ts, page-example.vue]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Inertia + Vue development

## Контекст

Разработка Inertia + Vue фронтенда в Laravel-приложении: страницы, компоненты, формы, навигация — и слоистая организация `resources/js/`, чтобы каждый новый файл попадал в правильный слой, а не в свалку. Применять при любой правке под `resources/js/` и при вопросе «куда положить этот файл».

## Алгоритм

1. **Навигация**: только `<Link>` / `router.visit()` — никаких `<a href>` и `window.location` внутри приложения.
2. **Формы**: Inertia form-хелперы — `useForm` или компонент `<Form>` (с wayfinder `store.form()`); ошибки и состояние отправки берутся из хелпера, не дублируются вручную.
3. **Новый файл — определить слой** по таблице:

| Слой | Что кладём |
|:---|:---|
| `pages/` | Роутабельные Inertia-страницы; доменные подпапки (`Documents/`, `Orders/`) |
| `layouts/` | Layout-компоненты страниц |
| `components/` | Vue-компоненты: доменные подпапки (`document/`, `order/`) + `shared/` для переиспользуемых |
| `composables/` | `use*`-функции; доменные подпапки + `shared/` |
| `stores/` | Pinia-сторы |
| `features/` | Фичеспецифичная логика, не влезающая в один composable (доменные подпапки) |
| `events/` | Шина событий + `adapters/`, `sideEffects/`, `plugins/` |
| `types/` | TS-типы и декларации |
| `actions/`, `routes/`, `wayfinder/` | **Автоген Wayfinder — не редактировать руками** |
| `shared/` | Кросс-доменные модули, не являющиеся компонентами/composables |
| `utils/` | Чистые функции-хелперы без состояния |
| `config/` | Конфигурационные константы фронтенда |
| `tests/` | Vitest-тесты, **зеркало структуры исходников** |

4. **Доменная организация внутри слоя**: внутри `components/`, `composables/`, `features/`, `pages/` — подпапки по домену (`document/`, `order/`, `auth/`, `notifications/`); общее — в `shared/`.
5. **Границы**: страницы и доменные компоненты ходят к backend через composables/actions-слой (см. скилл `frontend/wayfinder`); логика — в composables/features, компоненты остаются тонкими.

## Когда какой сниппет открывать

| Ситуация | Файл |
|:---|:---|
| «Куда положить файл?» — полная карта слоёв с примерами путей | `snippets/structure.md` |
| Написать доменный composable (use*-функция, форма, навигация) | `snippets/composable-example.ts` |
| Создать новую Inertia-страницу с layout, формой и `<Link>` | `snippets/page-example.vue` |

## Чеклист качества

- [ ] Навигация через `<Link>`/`router.visit()`, формы через `useForm`/`<Form>`
- [ ] Файл лежит в правильном слое и доменной подпапке (таблица выше)
- [ ] `actions/`, `routes/`, `wayfinder/` не редактировались руками
- [ ] Логика вынесена в composables/features, компонент тонкий
- [ ] Общие компоненты/composables — в `shared/`, а не скопированы между доменами
- [ ] Тест нового модуля лежит в зеркальной подпапке `tests/`

## Ссылки

- https://inertiajs.com/
- https://vuejs.org/guide/reusability/composables
- Связанные скиллы: `frontend/wayfinder`, `frontend/vitest`, `frontend/vue-composition-api`, `frontend/js-code-style`
