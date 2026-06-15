---
name: tailwind-conventions
bucket: frontend
version: 0.1.0
description: "Конвенции Tailwind CSS v4 для Laravel/Vue: CSS-first конфиг (@import tailwindcss, @theme-токены вместо tailwind.config.js), дизайн-токены, тёмная тема (.dark + dark:* + useAppearance), cn() (clsx+tailwind-merge), prettier-plugin-tailwindcss + tailwindFunctions, дисциплина отступов. Активировать при правке *.vue/*.css с Tailwind, настройке tailwind/postcss/prettier под Tailwind, работе с тёмной темой."
risk: write
persona: oss-dev
tags: [tailwind, tailwindcss-v4, css, vue, laravel, dark-mode, design-tokens, prettier]
requires: []
produces_for: []
outputs: []
snippets: [app.css, cn.ts, .prettierrc]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Tailwind CSS conventions

## Контекст

Конвенции Tailwind CSS **v4** для фронтенда Laravel + Vue. Активировать, когда:

- правишь стили в `*.vue`/`*.blade.php` с Tailwind-утилитами или в `*.css` с `@theme`/`@apply`/`@import 'tailwindcss'`;
- настраиваешь сборку Tailwind (vite.config с `@tailwindcss/vite`, миграция `tailwind.config.js` → CSS-first, PostCSS);
- настраиваешь Prettier под Tailwind (сортировка классов, `tailwindFunctions`);
- работаешь с тёмной темой (класс `.dark`, утилиты `dark:*`, composable переключения темы);
- пишешь условные/динамические классы и нужно `cn()`.

Ключевой сдвиг v4: **конфиг живёт в CSS**, а не в `tailwind.config.js`. Движок подключается Vite-плагином `@tailwindcss/vite`, токены и тема описываются директивами `@theme`, `@source`, `@custom-variant`.

**Laravel Boost**: версионные основы Tailwind в Laravel-стартерах — Boost-скилл `tailwindcss-development`; здесь — проектные конвенции v4, токены, тёмная тема и дисциплина классов. Контент авторский, из проектных конфигов.

## Алгоритм

1. **Определи версию.** Открой входной CSS (`resources/css/app.css`). Если там `@import 'tailwindcss'` — это **v4**, конфиг CSS-first, `tailwind.config.js` обычно отсутствует. Если три `@tailwind base/components/utilities` и есть `tailwind.config.js` — это **v3**. Не смешивай подходы; для нового кода — v4.

2. **Конфиг и токены — в CSS (v4).** Правь токены только в `app.css`, не создавай `tailwind.config.js` без необходимости (см. `snippets/app.css`):
   - `@import 'tailwindcss';` — вместо трёх `@tailwind`-директив v3;
   - `@source '...';` — добавить пути сканирования классов вне стандартных (заменяет `content: [...]`);
   - `@theme { --color-*, --spacing-*, --radius-*, --font-* }` — дизайн-токены; имена с префиксами генерируют утилиты (`--color-brand` → `bg-brand`/`text-brand`/`border-brand`);
   - `@plugin '@tailwindcss/forms';` — вместо `plugins: [require(...)]`.

3. **Дизайн-токены — семантические, не «сырые» цвета.** Заводи токены ролей (`--color-background`, `--color-foreground`, `--color-primary`, `--color-muted`, `--color-border`…), ссылающиеся на CSS-переменные `:root`. В разметке используй семантические утилиты (`bg-background`, `text-muted-foreground`, `border-border`), а не `bg-white`/`text-gray-900` напрямую — иначе тёмная тема не подхватится.

4. **Тёмная тема — через класс, а не media-query:**
   - в CSS: `@custom-variant dark (&:is(.dark *));` — утилиты `dark:*` срабатывают, когда `.dark` есть на любом предке;
   - значения токенов задаются дважды: светлые в `:root`, тёмные в `.dark` (одни имена переменных — две палитры; утилиты не дублируются);
   - класс `.dark` на `<html>` ставит/снимает composable `useAppearance` (см. раздел «Тёмная тема»);
   - предпочитай семантические токены `dark:`-вариантам в разметке: смена темы должна идти через переменные, точечный `dark:bg-…` — только для исключений.

5. **Условные/динамические классы — только через `cn()`** (см. `snippets/cn.ts`):
   - `cn(...inputs)` = `twMerge(clsx(inputs))`; `clsx` собирает классы из строк/объектов/массивов, `tailwind-merge` разрешает конфликты утилит (последняя побеждает: `px-2 px-4` → `px-4`);
   - никогда не клей классы шаблонными строками вручную — конфликты Tailwind не разрешатся;
   - для переопределяемых компонентов сливай базовые классы с `props.class` через `cn('base…', props.class)`.

6. **Prettier — авто-сортировка классов** (см. `snippets/.prettierrc`):
   - `plugins: ["prettier-plugin-tailwindcss"]` — сортирует классы в каноническом порядке;
   - `tailwindFunctions: ["clsx", "cn", "cva", "tv"]` — чтобы классы внутри `cn(...)`/`cva(...)` тоже сортировались;
   - в v4 укажи `tailwindStylesheet` (путь к входному CSS с `@theme`), а не `tailwindConfig`;
   - плагин Tailwind должен идти последним в массиве `plugins`.

7. **Дисциплина отступов** (см. раздел ниже): отступы между элементами — через `gap`/`space-*` на контейнере, не через внешние `margin` детей; единая шкала `spacing` (кратные шага токенов), без «магических» `px`-значений.

8. **Длинные списки классов организуй** (см. раздел ниже): порядок групп, перенос статичных классов в `@apply`/компонент при повторении, динамика — в `cn()`.

## Тёмная тема и useAppearance

Класс `.dark` управляется composable; токены переключаются автоматически.

- Тип состояния: `'light' | 'dark' | 'system'`. `system` читает `matchMedia('(prefers-color-scheme: dark)')`.
- `updateAppearance(value)`: сохраняет выбор в `localStorage` (клиент) и в cookie (для SSR), затем зовёт `updateTheme(value)`.
- `updateTheme(value)`: ставит/снимает класс `dark` на `document.documentElement` (`<html>`) — `classList.toggle('dark', isDark)`.
- При `system` навешивается слушатель `change` на media-query, чтобы тема следовала за ОС.
- Инициализация (`initializeTheme`) вызывается до маунта приложения (в SSR — из cookie), чтобы избежать «вспышки» неправильной темы.

В компонентах не дёргай `document.documentElement.classList` напрямую — только через `useAppearance().updateAppearance()`. Цвета берутся из семантических токенов, поэтому переключение `.dark` перекрашивает UI без `dark:`-утилит в каждом классе.

## Дисциплина отступов

- **Отступы между элементами — на контейнере, не на детях.** Внутри flex/grid используй `gap-*` (`flex gap-4`, `grid gap-6`); для вертикальных стопок без flex — `space-y-*`. Внешние `margin` на детях (`mt-*`/`mb-*`) создают «схлопывание» и зависимость от порядка — избегай.
- **Единая шкала spacing.** Только значения из шкалы токенов (`p-2`, `p-4`, `gap-6`…). Произвольные `p-[13px]`/`mt-[7px]` — только как осознанное исключение; повторяющееся значение заведи токеном `--spacing-*`.
- **Padding на контейнере, gap для зазоров.** Внешнюю «рамку» делает `padding` секции, расстояние между элементами — `gap`. Не смешивай обе роли в `margin`.

## Организация длинных списков классов

- **Порядок групп** (плагин Prettier приведёт к канону автоматически — но держи логический порядок при письме): layout/позиционирование → display/flex/grid → box (w/h/p/m/gap) → typography → визуал (bg/border/rounded/shadow) → состояния (`hover:`/`focus:`/`dark:`) → анимации.
- **Повторяющийся статичный набор → компонент или `@apply`.** Если один и тот же длинный набор копируется в 3+ местах — вынеси в Vue-компонент (кнопка, карточка) либо в `@layer components { .btn { @apply … } }`. Не плоди копии.
- **Статика и динамика раздельно.** Постоянные классы — строкой в шаблоне; условные — через `cn()` объектом. Не вмешивай тернарники в общую строку класса.
- **Варианты — через `cva`/`tv`** (если используются в проекте): они в `tailwindFunctions`, классы внутри тоже сортируются.

## Чеклист качества

- [ ] Версия определена: для v4 — `@import 'tailwindcss'`, конфиг в CSS, без лишнего `tailwind.config.js`
- [ ] Цвета/радиусы/шрифты заведены токенами в `@theme`; в разметке — семантические утилиты, не «сырые» `bg-white`/`text-gray-*`
- [ ] Тёмная тема: `@custom-variant dark (&:is(.dark *))`, значения в `:root` и `.dark`, класс ставит `useAppearance` (не ручной `classList`)
- [ ] Условные/динамические классы — через `cn()` (twMerge+clsx), а не склейка строк
- [ ] `.prettierrc`: `prettier-plugin-tailwindcss` последним в `plugins`, `tailwindFunctions` включает `cn`/`clsx`/`cva`/`tv`, в v4 задан `tailwindStylesheet`
- [ ] Отступы между элементами — `gap`/`space-*` на контейнере, не внешние `margin` детей; значения из единой шкалы spacing
- [ ] Повторяющийся длинный набор классов вынесен в компонент/`@apply`, а не скопирован
- [ ] Классы отсортированы Prettier (включая внутри `cn(...)`/`cva(...)`)

## Ссылки

- snippets/app.css — CSS-first конфиг v4: токены, тёмная тема, отличия v4↔v3
- snippets/cn.ts — утилита `cn()` (clsx + tailwind-merge)
- snippets/.prettierrc — Prettier с плагином и `tailwindFunctions`
- https://tailwindcss.com/docs/upgrade-guide — гайд миграции v3 → v4
- https://tailwindcss.com/docs/theme — директива `@theme` и токены
- Связанные скиллы: `frontend/inertia-vue`, `frontend/vue-composition-api`, `frontend/js-code-style`
