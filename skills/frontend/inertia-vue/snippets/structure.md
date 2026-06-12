# Карта слоёв resources/js (Laravel + Inertia + Vue)

Source: anonymized production Laravel project.

```
resources/js/
├── app.ts                  # entrypoint
├── pages/                  # роутабельные Inertia-страницы
│   ├── Auth/
│   ├── Documents/          #   доменные подпапки: List.vue, Show.vue, Edit.vue
│   └── Notifications/
├── layouts/                # layout-компоненты (AppLayout.vue, GuestLayout.vue)
├── components/             # Vue-компоненты
│   ├── document/           #   доменные: DocumentTable.vue, DocumentForm.vue
│   ├── order/
│   └── shared/             #   переиспользуемые: Button.vue, Modal.vue
├── composables/            # use*-функции
│   ├── document/           #   useDocumentFilters.ts, useDocumentNavigation.ts
│   └── shared/             #   usePagination.ts, useDebounce.ts
├── stores/                 # Pinia-сторы (useUserStore.ts)
├── features/               # фичеспецифичная логика крупнее composable
│   └── document/           #   экспорт, мастера, мульти-шаговые сценарии
├── events/                 # шина событий
│   ├── adapters/           #   подключение транспортов (websocket и т.п.)
│   ├── sideEffects/        #   реакции на события (тосты, инвалидация)
│   └── plugins/
├── types/                  # TS-типы, .d.ts
├── actions/                # АВТОГЕН Wayfinder (controller actions) — не править
├── routes/                 # АВТОГЕН Wayfinder (именованные роуты) — не править
├── wayfinder/              # АВТОГЕН Wayfinder (внутренности) — не править
├── shared/                 # кросс-доменные модули (не компоненты и не composables)
├── utils/                  # чистые функции без состояния (formatDate.ts)
├── config/                 # константы фронтенда
└── tests/                  # Vitest, зеркало структуры:
    ├── components/document/
    ├── composables/document/
    └── events/
```

## Что куда кладём

| Хочу добавить | Слой | Пример пути |
|:---|:---|:---|
| Новую страницу со своим URL | `pages/<Домен>/` | `pages/Documents/Show.vue` |
| Обёртку страниц (шапка/сайдбар) | `layouts/` | `layouts/AppLayout.vue` |
| Компонент одного домена | `components/<домен>/` | `components/document/DocumentTable.vue` |
| Компонент для всех доменов | `components/shared/` | `components/shared/ConfirmModal.vue` |
| Переиспользуемую реактивную логику | `composables/<домен или shared>/` | `composables/document/useDocumentFilters.ts` |
| Глобальное состояние | `stores/` | `stores/useUserStore.ts` |
| Многошаговый сценарий / крупную фичу | `features/<домен>/` | `features/document/export/` |
| Реакцию на событие шины | `events/sideEffects/` | `events/sideEffects/showToastOnDocumentSaved.ts` |
| Тип/интерфейс | `types/` | `types/document.ts` |
| Функцию-хелпер без состояния | `utils/` | `utils/formatDate.ts` |
| Тест | `tests/` (зеркало) | `tests/composables/document/useDocumentFilters.test.ts` |

## Правила

- Доменные подпапки внутри каждого слоя; общее — `shared/`.
- `actions/`, `routes/`, `wayfinder/` генерируются `php artisan wayfinder:generate` / vite-плагином — любые ручные правки будут перезаписаны.
- Доменные компоненты не импортируют `@/wayfinder/routes/*` напрямую — через composables/actions (см. скилл `frontend/wayfinder`).
