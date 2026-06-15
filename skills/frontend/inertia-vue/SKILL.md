---
name: inertia-vue
bucket: frontend
version: 0.3.0
description: "Inertia + Vue в Laravel: страницы, формы, навигация и слоистая организация resources/js (pages, layouts, components, composables, stores, features, events, types, actions/wayfinder)."
risk: write
persona: oss-dev
tags: [inertia, vue, laravel, frontend, architecture, structure]
requires: []
produces_for: []
outputs: []
snippets: [structure.md, composable-example.ts, page-example.vue, feature-structure.md]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Inertia + Vue development

## Контекст

Разработка Inertia + Vue фронтенда в Laravel-приложении: страницы, компоненты, формы, навигация — и слоистая организация `resources/js/`, чтобы каждый новый файл попадал в правильный слой, а не в свалку. Применять при любой правке под `resources/js/` и при вопросе «куда положить этот файл».

**Laravel Boost**: версионные основы Inertia (формы, навигация, API) — Boost-скилл inertia-vue-development; здесь — слоистая организация resources/js и проектные конвенции. Пакет: https://github.com/laravel/boost (скиллы — `vendor/laravel/boost/.ai/`).

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

## Доменные срезы `features/<домен>/`

Крупный домен (заявка, заказ, документ) собирается не в глобальных `components/` и `composables/`, а в один вертикальный срез `resources/js/features/<домен>/` со слоями фиксированных ролей:

```
features/order/
├── actions/       # единственный слой с импортом @/wayfinder/routes/* (обёртки над роутами + execute())
├── composables/   # use*-функции домена; импортируют ТОЛЬКО ../actions
├── model/         # оркестрация уровня страницы: собирает composables в один useShowPage
└── config/        # доменные константы, дефолты, карты статусов/вкладок
```

**Правило границ импортов** — зависимости строго в одну сторону, снаружи внутрь:

```
Vue-компонент / page  →  composables (или model)  →  actions  →  @/wayfinder/routes/*
```

1. **Только `actions/` знает про wayfinder**: все импорты `@/wayfinder/routes/*` живут в `features/<домен>/actions/` и нигде больше.
2. **Компоненты и страницы НЕ дёргают wayfinder-роуты напрямую** — они вызывают `use*`-функции из `composables/` (или `model/`), а те идут в `actions/`.
3. **`composables/` импортируют только `../actions`**, не `@/wayfinder/routes/*`: бизнес-логика отвязана от того, как именно вызывается backend.
4. **Каждый слой реэкспортит публичное API через `index.ts`** — наружу видны только реэкспортированные функции.

Граница держится не на доверии, а **enforced ESLint flat-config** через `no-restricted-imports`: паттерн `@/wayfinder/routes/*` запрещён в доменных Vue-файлах, точечный whitelist выводит из-под правила немногие легаси-файлы. Настройка ESLint flat-config и правила-границы — в скилле `frontend/js-code-style`; полное дерево среза, пример доменного composable и конфиг границы — в `snippets/feature-structure.md`.

## Когда какой сниппет открывать

| Ситуация | Файл |
|:---|:---|
| «Куда положить файл?» — полная карта слоёв с примерами путей | `snippets/structure.md` |
| Написать доменный composable (use*-функция, форма, навигация) | `snippets/composable-example.ts` |
| Создать новую Inertia-страницу с layout, формой и `<Link>` | `snippets/page-example.vue` |
| Завести доменный срез `features/<домен>/` с границей импортов | `snippets/feature-structure.md` |

## Чеклист качества

- [ ] Навигация через `<Link>`/`router.visit()`, формы через `useForm`/`<Form>`
- [ ] Файл лежит в правильном слое и доменной подпапке (таблица выше)
- [ ] `actions/`, `routes/`, `wayfinder/` не редактировались руками
- [ ] Логика вынесена в composables/features, компонент тонкий
- [ ] Общие компоненты/composables — в `shared/`, а не скопированы между доменами
- [ ] Тест нового модуля лежит в зеркальной подпапке `tests/`
- [ ] Импорты `@/wayfinder/routes/*` есть только в `features/<домен>/actions/`; компоненты/composables домена идут через `actions`-слой
- [ ] Граница импортов домена закреплена `no-restricted-imports` в ESLint flat-config, а не «на словах»

## Ссылки

- https://inertiajs.com/
- https://vuejs.org/guide/reusability/composables
- Связанные скиллы: `frontend/wayfinder`, `frontend/vitest`, `frontend/vue-composition-api`, `frontend/js-code-style`
