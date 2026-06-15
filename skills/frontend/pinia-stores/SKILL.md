---
name: pinia-stores
bucket: frontend
version: 0.1.0
description: "Pinia (Vue 3) — глобальное состояние: setup-сторы (defineStore с функцией), ref=state/computed=getters/function=actions, именование use*Store, композиция сторов, доступ к стору вне компонента, hydration из props, persist. Активировать при создании/правке файла под resources/js/stores/**, defineStore, useXxxStore, при вопросах «как хранить глобальное состояние / шарить данные между компонентами / куда вынести состояние из компонента»."
risk: write
persona: oss-dev
tags: [pinia, vue, frontend, state-management, store, architecture]
requires: []
produces_for: []
outputs: []
snippets: [useExampleStore.ts, store-in-component.vue, store-composition.ts]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Pinia stores (Vue 3)

## Контекст

Глобальное (разделяемое между компонентами) состояние Vue 3 на Pinia: счётчики, текущий пользователь, корзина, открытые модалки, кэш справочников — всё, что переживает размонтирование одного компонента и читается из нескольких мест.

**Когда активировать:**
- создаётся или правится файл под `resources/js/stores/**` (или `src/stores/**`);
- в коде есть `defineStore(...)`, импорт `from 'pinia'`, вызов `useXxxStore()`;
- вопрос «как шарить данные между несвязанными компонентами», «куда вынести состояние из компонента», «как обратиться к состоянию из обычного `.ts`-модуля (вне компонента)».

**ГРАНИЦА со скиллом `frontend/vue-composition-api`:** там — `<script setup>`, локальное состояние **одного** компонента (`ref`/`computed`/`watch` внутри компонента). Здесь — **глобальное** состояние, живущее в Pinia и доступное отовсюду. Если состояние нужно только текущему компоненту — это НЕ стор, оставляй `ref` в компоненте или выноси в composable. Стор заводят, когда состояние читают/меняют минимум из двух несвязанных мест либо оно должно пережить навигацию.

## Алгоритм

1. **Регистрация Pinia (один раз на приложение).** В точке старта (`app.ts`/`main.ts`): `const pinia = createPinia()` и `app.use(pinia)`. Без этого любой `useXxxStore()` упадёт. Один экземпляр `pinia` на приложение; на сервере (SSR) — новый экземпляр на каждый запрос.
2. **Только setup-сторы.** `defineStore('id', () => { ... })` с функцией-сетапом — единый стиль (как `<script setup>`). Option-store (`defineStore('id', { state, getters, actions })`) не использовать в новом коде.
3. **Внутри сетапа — три роли по типу значения:**
   - `ref()`/`reactive()` → **state** (реактивные данные стора);
   - `computed()` → **getters** (производные значения; кэшируются);
   - обычная `function` → **actions** (мутации state и асинхронные операции).
4. **Возвращай из сетапа всё публичное.** Стор отдаёт наружу объект со всем, что должно быть доступно: `return { count, doubleCount, increment }`. Что не вернул — приватно (например, внутренний таймер `let pulseTimer`). State-`ref` обязан попасть в `return`, иначе Pinia не подхватит его как состояние (важно для devtools/SSR/persist).
5. **Именование.** Файл и фабрика — `use<Domain>Store` (`useCartStore`, `useNotificationsStore`); первый аргумент `defineStore` — стабильный строковый `id` (`'cart'`, `'notifications'`) — он же ключ в devtools и в persisted-хранилище, менять его нельзя бездумно.
6. **Один стор — один домен.** Не сваливай несвязанные сущности в «global»-стор. Дроби по доменам (`useAuthStore`, `useCartStore`, `useUiStore`); файлы — в `resources/js/stores/`, при росте — доменные подпапки.
7. **Использование в компоненте.** `const store = useXxxStore()` в `<script setup>`. Вызывать **методы** прямо со стора (`store.increment()`). Для **деструктуризации state/getters с сохранением реактивности** — `storeToRefs(store)` (обычная деструктуризация `const { count } = store` рвёт реактивность). Actions деструктурировать можно как есть — они не реактивны.
8. **Доступ вне компонента (`.ts`-модули, шина событий, ws-адаптеры).** Вызывай `useXxxStore()` **внутри функции/обработчика**, а не на верхнем уровне модуля — на момент импорта модуля Pinia может быть ещё не установлена. Передавать конкретный `pinia` первым аргументом нужно только в коде до `app.use(pinia)` или на сервере вне жизненного цикла запроса.
9. **Hydration / инициализация от сервера.** Не дублируй то, что уже отрендерил backend. Сервер отдаёт начальное значение через props/initial-state — компонент-владелец сидит на нём через `onMounted(() => store.init(props.initialValue))` (или эквивалент). Стор держит метод `init(payload)` / `setX(...)`, который сеет state; дальше живые обновления (события, ws) идут через actions.
10. **SSR-нюанс.** При серверном рендере создавай `createPinia()` на каждый запрос (общий синглтон-стор протёк бы между пользователями). Начальное состояние сериализуется на сервере и регидрируется на клиенте — на клиенте не перезатирай его повторным фетчем, если значение уже пришло.
11. **persist — только по необходимости.** Сохранение в `localStorage`/`sessionStorage` подключают плагином `pinia-plugin-persistedstate` и опцией `persist` в `defineStore`. Персистить только то, что реально должно пережить перезагрузку (UI-предпочтения, черновик); токены/чувствительное и серверный кэш — не персистить.
12. **Композиция сторов (стор внутри стора).** Внутри сетапа одного стора можно вызвать `useOtherStore()` и читать его state/getters / дёргать его actions — так строят производное состояние без дублирования. Избегай взаимных циклов (A зависит от B и B от A); выноси общее в третий стор или в action-параметр.

## Анатомия setup-стора

```ts
export const useCounterStore = defineStore('counter', () => {
  // state
  const count = ref(0)
  // getter
  const doubleCount = computed(() => count.value * 2)
  // приватное (НЕ в return) — недоступно снаружи
  let timer: ReturnType<typeof setTimeout> | null = null
  // action
  function increment() { count.value++ }

  return { count, doubleCount, increment } // всё публичное
})
```

Правила, которые легко нарушить:
- **State-`ref` не попал в `return`** → он не считается состоянием стора (нет в devtools/SSR/persist). Возвращай его.
- **`const { count } = store`** в компоненте → потеря реактивности. Бери `storeToRefs(store)` для state/getters.
- **`useStore()` на верхнем уровне обычного `.ts`-модуля** → «getActivePinia() was called but there was no active Pinia». Вызывай внутри функции.
- **Меняешь state напрямую снаружи** (`store.count = 5` из компонента) технически можно, но мутации концентрируй в actions — иначе логику не переиспользовать и не оттестировать.

## Когда какой сниппет открывать

| Ситуация | Файл |
|:---|:---|
| Написать новый setup-стор (state/getters/actions, приватное поле, init от сервера) | `snippets/useExampleStore.ts` |
| Подключить стор в компоненте: `storeToRefs`, вызов actions, hydration в `onMounted` | `snippets/store-in-component.vue` |
| Композиция: один стор использует другой + доступ к стору вне компонента | `snippets/store-composition.ts` |

## Чеклист качества

- [ ] `createPinia()` создан и `app.use(pinia)` вызван один раз (на сервере — на каждый запрос)
- [ ] Стор — setup-форма `defineStore('id', () => {...})`, не option-форма
- [ ] `ref`=state, `computed`=getters, `function`=actions; всё публичное в `return`
- [ ] Имя `use<Domain>Store`, стабильный строковый `id`; один стор — один домен
- [ ] В компоненте state/getters берутся через `storeToRefs`, мутации — через actions
- [ ] Вне компонента `useXxxStore()` вызывается внутри функции, не на верхнем уровне модуля
- [ ] Начальное состояние от сервера сеется через `init/setX` и не перезатирается повторным фетчем
- [ ] `persist` подключён только там, где состояние реально должно пережить перезагрузку
- [ ] Нет взаимных циклов между сторами при композиции

## Ссылки

- https://pinia.vuejs.org/core-concepts/ (setup stores, getters, actions)
- https://pinia.vuejs.org/cookbook/composing-stores.html
- https://pinia.vuejs.org/ssr/ (hydration, per-request instance)
- https://prazdevs.github.io/pinia-plugin-persistedstate/
- Связанные скиллы: `frontend/vue-composition-api` (локальное состояние компонента), `frontend/inertia-vue` (где `stores/` в слоистой `resources/js`)
