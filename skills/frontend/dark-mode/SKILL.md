---
name: dark-mode
bucket: frontend
version: 0.1.0
description: "Тёмная тема light|dark|system на Vue 3: composable useDarkMode (matchMedia prefers-color-scheme, localStorage + cookie для SSR, toggle класса .dark на documentElement, слушатель change для system), инициализация до маунта без вспышки темы, мини-переключатель. Активировать при добавлении переключения темы, борьбе со вспышкой светлой темы (FOUC), синхронизации темы с системой или восстановлении темы при SSR."
risk: write
persona: oss-dev
tags: [dark-mode, theme, vue, composable, ssr, tailwind, matchmedia, localstorage]
requires: [tailwind-conventions]
produces_for: []
outputs: []
snippets: [useDarkMode.ts, bootstrap-init.ts, no-flash-init.html, ThemeToggle.vue]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Тёмная тема (light | dark | system)

## Контекст

Переключение оформления приложения между тремя состояниями — `light`, `dark` и `system` (следовать системной настройке ОС). Тёмное состояние выражается классом `.dark` на корневом `<html>` (`document.documentElement`); Tailwind и дизайн-токены реагируют на этот класс (см. `frontend/tailwind-conventions`). Выбор пользователя сохраняется и переживает перезагрузку.

**Когда активировать:**
- добавляешь переключатель темы или пункт настроек «оформление»;
- борешься со вспышкой светлой темы при загрузке (FOUC — страница мигает белым, потом темнеет);
- нужно, чтобы тема следовала за системой и реагировала на смену системной темы на лету;
- настраиваешь восстановление темы при SSR / server-side рендере, чтобы сервер отдавал правильный класс с первого байта;
- видишь самописный код с `matchMedia('(prefers-color-scheme: dark)')`, ручным `classList.add('dark')` и хочешь привести его к единому паттерну.

**Два слоя, оба обязательны:**
1. **Runtime (Vue)** — composable: реактивное состояние, переключение, сохранение в `localStorage` + `cookie`, подписка на системную тему.
2. **Boot (до маунта)** — синхронная инициализация класса `.dark` ДО первого рендера, иначе пользователь увидит вспышку. На клиенте — вызов `initializeTheme()` в точке входа; при SSR — короткий inline-скрипт в шаблоне страницы, читающий значение из cookie/системы.

Без слоя 2 любой composable бесполезен: к моменту маунта Vue браузер уже отрисовал светлый кадр.

## Архитектура состояния

| Понятие | Тип / значение | Где живёт |
|:---|:---|:---|
| `Appearance` | `'light' \| 'dark' \| 'system'` | выбор пользователя, хранится |
| `ResolvedAppearance` | `'light' \| 'dark'` | что реально на экране (`system` → разрешён через matchMedia) |
| Класс `.dark` | присутствует ⟺ resolved === `'dark'` | `document.documentElement` |
| Ключ хранения | одно строковое имя, напр. `'appearance'` | `localStorage` **и** `cookie` |

**Правила:**
- Никогда не хранить `ResolvedAppearance`. Хранится только выбор пользователя (`Appearance`), включая литерал `'system'` — иначе теряется намерение «следовать за системой».
- `localStorage` — источник правды на клиенте. `cookie` — копия для сервера (localStorage серверу недоступен). Пишутся обе на каждое изменение, одним значением.
- Модуль обязан быть SSR-безопасным: каждое обращение к `window`/`document`/`localStorage` под охраной `typeof window === 'undefined'` (или `document`) — иначе сборка SSR падает.

## Алгоритм

1. **Определи типы** `Appearance` и `ResolvedAppearance`. Состояние `appearance` — модульный `ref<Appearance>('system')` со значением по умолчанию `'system'` (новый пользователь следует за ОС).
2. **`updateTheme(value)`** — чистая функция применения класса, без побочного хранения:
   - SSR-guard в начале (`typeof window === 'undefined' → return`);
   - если `value === 'system'` — разрешить через `matchMedia('(prefers-color-scheme: dark)').matches`;
   - `document.documentElement.classList.toggle('dark', isDark)` — именно `toggle` со вторым аргументом, не пара add/remove.
3. **Персистентность** — на каждое изменение писать в оба хранилища одним значением:
   - `localStorage.setItem(KEY, value)` (клиент);
   - `cookie` `KEY=value;path=/;max-age=<год>;SameSite=Lax` (сервер). Обе записи под SSR-guard.
4. **`initializeTheme()`** (клиентский boot, вызывается из точки входа ДО/около маунта):
   - прочитать сохранённое значение из `localStorage`, при отсутствии — `'system'`;
   - `updateTheme(saved)` — выставить класс немедленно;
   - подписаться на системную тему: `matchMedia(...).addEventListener('change', handler)`, где `handler` перечитывает сохранённое значение и зовёт `updateTheme` — переключение ОС влияет на экран только пока выбран `'system'`.
5. **`useDarkMode()`** (composable для компонентов):
   - в `onMounted` синхронизировать модульный `ref` с `localStorage` (на случай SSR-гидрации, когда модуль инициализировался на сервере);
   - `resolvedAppearance` — `computed<ResolvedAppearance>`: для `'system'` вернуть `prefersDark() ? 'dark' : 'light'`, иначе само значение;
   - `updateAppearance(value)`: записать `ref`, сохранить в localStorage + cookie (шаг 3), вызвать `updateTheme(value)`;
   - вернуть `{ appearance, resolvedAppearance, updateAppearance }`.
6. **Boot без вспышки** — критичный шаг, см. ниже. На клиенте — `initializeTheme()` в точке входа до маунта. При SSR — inline-скрипт в `<head>` шаблона.
7. **Разметка** реагирует на `.dark` через семантические токены / `dark:*`-утилиты Tailwind — это зона `frontend/tailwind-conventions`, здесь только переключаем класс.

## Инициализация без вспышки темы (FOUC)

Вспышка возникает, когда браузер успевает отрисовать кадр со светлой темой до того, как JS навесит `.dark`. Лечится тем, что класс ставится **синхронно, как можно раньше**, до первого рендера.

**Клиент (SPA, без SSR):** вызвать `initializeTheme()` в точке входа (`app.ts`) до или сразу около монтирования приложения — `updateTheme` отработает до того, как Vue нарисует контент. Достаточно для чисто клиентского рендера: пустой `#app` светлым не мигает.

**SSR / server-side render:** сервер должен отдать корректный класс уже в HTML, иначе вспышка вернётся между отдачей страницы и стартом JS. Два связанных приёма:
- сервер кладёт сохранённый `Appearance` из cookie в страницу (Blade/шаблон): `<html class="dark">` сразу, если cookie === `dark`;
- если cookie === `system` (или пуст), класс на сервере поставить нельзя — система известна только браузеру. Тогда **синхронный inline-скрипт** в `<head>` (до загрузки бандла и до контента) читает `matchMedia` и ставит `.dark` ещё до первого кадра. Опционально — inline-`<style>` с фоном `html`/`html.dark`, чтобы даже фон страницы не мигал.

Принцип: cookie закрывает явный выбор `light`/`dark` на сервере, inline-скрипт закрывает `system` на клиенте до маунта. Снаружи отдаётся `app.ts` (клиент) и фрагмент шаблона (SSR) — оба в снипетах.

## Связь с Tailwind

**Laravel Boost**: версионные основы тёмной темы из Tailwind/Inertia стартер-кита (базовый `useAppearance`, инициализация) идут из Boost-скиллов `tailwindcss-development` / `inertia-vue-development`; здесь — авторский трёхрежимный composable, boot без вспышки и SSR-инициализация через cookie. Пакет: https://github.com/laravel/boost (скиллы — `vendor/laravel/boost/.ai/`).

Этот скилл только владеет классом `.dark` и состоянием. То, как `.dark` влияет на цвета — `frontend/tailwind-conventions`:
- Tailwind v4: `@custom-variant dark (&:is(.dark *));` — `dark:*`-утилиты и токены срабатывают по классу `.dark` на предке.
- Предпочитай семантические токены (значения переменных переопределяются в `.dark`) точечным `dark:bg-…` в разметке.
- Имя класса (`dark`) и контракт «класс на `<html>`» — общие для обоих скиллов; не расходись.

## Когда какой сниппет открывать

| Ситуация | Файл |
|:---|:---|
| Сам composable: типы, updateTheme, persist, initializeTheme, useDarkMode | `snippets/useDarkMode.ts` |
| Подключить инициализацию в точке входа (app.ts), клиент | `snippets/bootstrap-init.ts` |
| Убрать вспышку при SSR: класс из cookie + inline-скрипт в шаблоне | `snippets/no-flash-init.html` |
| Готовый мини-переключатель light/dark/system | `snippets/ThemeToggle.vue` |

## Чеклист качества

- [ ] Состояние `'light' | 'dark' | 'system'`; по умолчанию `'system'`; хранится только выбор, не resolved
- [ ] Класс ставится через `documentElement.classList.toggle('dark', isDark)`, а не парой add/remove
- [ ] Значение пишется одновременно в `localStorage` и в `cookie` (SameSite=Lax, длинный max-age)
- [ ] Каждое обращение к `window`/`document`/`localStorage` под SSR-guard — сборка SSR не падает
- [ ] `initializeTheme()` вызван в точке входа ДО маунта — клиентской вспышки нет
- [ ] При SSR класс приходит из cookie + inline-скрипт в `<head>` закрывает режим `system` — серверной вспышки нет
- [ ] Подписка `matchMedia change` обновляет тему только когда выбран `system`
- [ ] Имя класса и контракт `.dark`-на-`<html>` совпадают с `frontend/tailwind-conventions`; цвета не хардкодятся, идут через токены/`dark:*`

## Ссылки

- https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-color-scheme
- https://developer.mozilla.org/en-US/docs/Web/API/Window/matchMedia
- https://vuejs.org/guide/reusability/composables
- Связанные скиллы: `frontend/tailwind-conventions`, `frontend/inertia-vue`, `frontend/vue-composition-api`
