---
name: vue-testing-best-practices
bucket: frontend-vue
version: 1.1.0
description: "Практики тестирования Vue 3-компонентов через Vitest + Vue Test Utils 2: mount vs shallowMount, изоляция композаблов, createTestingPinia, async/flushPromises, устойчивые data-testid, моки детей/слотов/эмитов и что НЕ тестировать."
risk: write
persona: oss-dev
tags: [vue, testing, vitest, vue-test-utils, pinia, composables, frontend]
requires: [vue, vitest]
produces_for: []
outputs: []
snippets: [component.spec.ts]
adapters: [claude, cursor, fable]
sha256: ""
license: MIT
author: github.com/vuejs-ai
---

# Skill: тестирование Vue-компонентов (Vitest + Vue Test Utils 2)

## Контекст

Скилл — про **что и как тестировать в Vue-компонентах**: чёрный ящик (вход = props/слоты/события
пользователя, выход = DOM/эмиты/вызовы стора), а не внутренности. Стек: Vitest как раннер
(`frontend/vitest`, `frontend/vitest-vue`), Vue Test Utils 2 (VTU) как монтировщик, опционально
`@testing-library/vue` для user-centric стиля. Пишем на Composition API (`<script setup lang="ts">`),
Pinia — через `@pinia/testing`, async — через `flushPromises`/`nextTick`.

Конфиг Vitest (jsdom, алиасы, coverage) — НЕ здесь, он в `frontend/vitest`. Общий API
expect/mock/vi — в `frontend/vitest-vue`. Этот скилл их не дублирует, а надстраивает Vue-специфику.

## Когда активировать

- Пишешь/чинишь `*.spec.ts`/`*.test.ts` для `.vue`-компонента или композабла (`useX`).
- Тесты ломаются при рефакторинге внутренностей, хотя поведение не менялось.
- «injection Symbol(pinia) not found», падает async-setup, не находится Teleport/модалка.
- Тест флакает на гонках (не дождались промиса/тика); снапшоты «зелёные» при сломанной фиче.
- Надо решить mount vs shallowMount, замокать ребёнка/глобал, проверить эмит или слот.

## Алгоритм

1. **Реши: компонент или композабл.**
   - Чистый `useX` без lifecycle/inject — тестируй как обычную функцию: вызови, дёрни методы,
     проверь `.value` рефов. Никакого mount.
   - `useX` с `onMounted`/`inject`/`provide` — оберни в компонент-носитель
     (`defineComponent({ setup: () => useX(), template: '<div/>' })`) и `mount`. См.
     `reference/testing-composables-helper-wrapper.md`.

2. **Выбери mount vs shallowMount.**
   - `mount` — по умолчанию: рендерит реальное дерево, проверяешь пользовательский сценарий.
   - `shallowMount` — заглушает всех детей; бери только когда ребёнок тяжёлый/внешний и его
     рендер мешает. Не используй shallowMount «на всякий случай» — он прячет интеграционные баги.
   - Точечная заглушка вместо тотальной: `global.stubs: { HeavyChild: true }`.

3. **Селекторы — устойчивые.** Ищи по `data-testid` (`wrapper.get('[data-testid="x"]')`), не по CSS-
   классам, тексту или позиции в дереве — иначе рефакторинг разметки ломает тесты на ровном месте.
   Стиль чёрного ящика — `reference/testing-component-blackbox-approach.md`.

4. **Подключи зависимости через `global`.**
   - Pinia: `global.plugins: [createTestingPinia({ createSpy: vi.fn })]`. По умолчанию действия
     застаблены (`stubActions: true`) — проверяешь, что действие вызвано. Нужна реальная логика
     действия — `stubActions: false`, а точечно подмени лишь действие на границе I/O (сетевой
     вызов) через `vi.spyOn(store, 'action').mockResolvedValue(...)`. См.
     `reference/testing-pinia-store-setup.md`.
   - Router/i18n/глобальные компоненты — `global.plugins`/`global.components`/`global.mocks`.

5. **Async — дожидайся явно.** После `trigger`/смены props/резолва промиса вызывай
   `await flushPromises()` (микротаски: промисы в действиях/watch) и/или `await nextTick()`
   (DOM-обновление после синхронного изменения реактивности). `trigger`/`setProps` уже возвращают
   промис — `await` их. См. `reference/testing-async-await-flushpromises.md`.

6. **Проверяй контракт наружу.**
   - Эмиты: `wrapper.emitted('eventName')` → массив вызовов; payload — `emitted('e')[0]`.
   - Слоты: `mount(C, { slots: { default: 'text', named: ComponentStub } })`, затем ассертить
     отрендеренное содержимое.
   - DOM/текст/классы видимого результата — не внутренние data().

7. **async setup / Suspense / Teleport / defineAsyncComponent** — особые случаи:
   `reference/testing-suspense-async-components.md`, `reference/async-component-testing.md`,
   `reference/teleport-testing-complexity.md`.

8. **`@testing-library/vue` как альтернатива** VTU, когда хочешь user-centric API
   (`render` + `screen.getByRole`/`getByText` + `@testing-library/user-event`): меньше доступа к
   внутренностям, тесты ближе к поведению пользователя. Не смешивай оба стиля в одном файле; для
   доступности/ролей `getByRole` нагляднее `data-testid`. Это альтернатива, а не замена — выбери одно.

## Что НЕ тестировать

- **Реактивность и сам Vue/Pinia/VTU** — что `ref` обновляется, `computed` пересчитывается,
  `watch` срабатывает: это уже протестировано фреймворком. Тестируй СВОЮ логику поверх.
- **Только снапшоты** как замена ассертам — большой снапшот «зелёный» при сломанной фиче и
  скрывает регрессии за шумом. Снапшот — для маленького стабильного вывода, не вместо проверок.
  См. `reference/testing-no-snapshot-only.md`.
- **Приватные внутренности** (`wrapper.vm.someInternal`, имена методов) — завязка на реализацию.
- **Вычисленные стили/реальные DOM-события браузера** в jsdom — для этого браузерный раннер
  (`@vitest/browser`/Playwright CT), см. `reference/testing-browser-vs-node-runners.md`. E2E —
  `reference/testing-e2e-playwright-recommended.md`.

## Когда какой сниппет открывать

| Ситуация | Файл |
|:---|:---|
| Нужен эталон спека: mount + Pinia + async + проверка эмитов + data-testid | `snippets/component.spec.ts` |
| Изолированный тест композабла (с lifecycle — через компонент-носитель) | `reference/testing-composables-helper-wrapper.md` |
| Ошибки injection pinia / выбор stubActions | `reference/testing-pinia-store-setup.md` |
| Флак на гонках, не дождался промиса/тика | `reference/testing-async-await-flushpromises.md` |
| Тесты ломаются при рефакторинге внутренностей | `reference/testing-component-blackbox-approach.md` |
| async setup / Suspense / defineAsyncComponent / Teleport не рендерятся | `reference/testing-suspense-async-components.md`, `reference/async-component-testing.md`, `reference/teleport-testing-complexity.md` |
| Нужны реальные стили/DOM-события или E2E | `reference/testing-browser-vs-node-runners.md`, `reference/testing-e2e-playwright-recommended.md` |

## Чеклист качества

- [ ] Тест проверяет поведение (DOM/эмиты/вызовы стора), а не внутренности (`vm.*`, имена методов)
- [ ] Выбран `mount` по умолчанию; `shallowMount`/`stubs` — только для тяжёлых/внешних детей с обоснованием
- [ ] Селекторы по `data-testid` (или ролям в testing-library), не по классам/тексту/позиции
- [ ] Pinia подключена через `createTestingPinia`; решено `stubActions` true/false осознанно
- [ ] Каждый async-переход дождан `await flushPromises()`/`await nextTick()`, нет «голых» промисов
- [ ] Эмиты проверены через `emitted()` с payload; слоты — через `slots`
- [ ] Нет тестов на реактивность Vue / только-снапшотов как единственной ассерты
- [ ] Композабл без lifecycle тестируется как функция; с lifecycle — через компонент-носитель
- [ ] Файл лежит зеркально исходнику; `vitest run` зелёный локально

## Ссылки

- `frontend/vitest` — конфиг Vitest именно для Laravel/Inertia/Vue (jsdom, алиасы, coverage exclude).
  Настройку раннера бери там, здесь — практики тестов.
- `frontend/vitest-vue` — generic справочник API Vitest (test/describe/expect/mock/vi, coverage).
  Общий API не дублируем — за ним туда.
- `frontend/vue` — Composition API / `<script setup>` / реактивность: что именно тестируем.
- `frontend/vue-best-practices` — архитектура (когда composable, когда store), влияет на тестируемость.
- `frontend/pinia` / `frontend/pinia-stores` — устройство сторов, которые мокаем через `createTestingPinia`.
- https://test-utils.vuejs.org/ · https://testing-library.com/docs/vue-testing-library/intro/ · https://pinia.vuejs.org/cookbook/testing.html
- `reference/` — детальные заметки по частным случаям (импорт из antfu/skills, см. `upstream.json`).
