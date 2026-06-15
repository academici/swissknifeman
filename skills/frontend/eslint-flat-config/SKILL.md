---
name: eslint-flat-config
bucket: frontend
version: 0.1.0
description: "ESLint flat config (eslint.config.js) для Vue 3 + TypeScript: defineConfigWithVueTs/typescript-eslint + eslint-plugin-vue, @stylistic, import/order и границы импортов, padding-line-between-statements, цепочка Prettier (eslint-config-prettier + tailwindcss + organize-imports), скрипты lint/lint:fix. Триггеры: настройка/правка eslint или prettier, новый Vue/TS проект."
risk: write
persona: oss-dev
tags: [eslint, prettier, flat-config, vue, typescript, stylistic, tooling]
requires: []
produces_for: []
outputs: []
snippets: [eslint.config.js, prettierrc.json, package-scripts.json]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: ESLint flat config (Vue 3 + TypeScript)

## Контекст

Сборка и правка тулинга линтинга/форматирования для Vue 3 + TypeScript проекта: файл `eslint.config.js` (flat config, ESLint 9+), `.prettierrc` с цепочкой плагинов и npm-скрипты `lint`/`lint:fix`. Активировать при: настройке или правке `eslint.config.*` / `.prettierrc`, бутстрапе нового Vue/TS проекта, добавлении/обновлении ESLint- или Prettier-плагина, появлении конфликта правил ESLint vs Prettier.

**Граница с `frontend/js-code-style`** — разделение жёсткое:

| | Скилл | Отвечает на вопрос |
|:---|:---|:---|
| **ЧТО** | `frontend/js-code-style` | какие правила стиля (Spatie): 4 пробела, ширина 120, одинарные кавычки, `const`-first, `===`, `function` для именованных |
| **ЧЕМ/КАК** | `eslint-flat-config` (этот) | каким тулингом это включается: flat-config структура, набор плагинов, цепочка Prettier, скрипты |

То есть значения `tabWidth`/`printWidth`/`singleQuote` берутся из `js-code-style`, а *куда* их записать и *чем* проверять — здесь. Не дублируй обоснование стиля — ссылайся на `js-code-style`.

**Laravel Boost**: версионные основы Vite/Inertia/Tailwind стартер-кита идут из Boost; здесь — авторская сборка flat-config поверх проектных конвенций. Пакет: https://github.com/laravel/boost.

## Алгоритм

1. **Базовый каркас flat config**. `eslint.config.js` как ES-модуль (`export default`). Собрать через `defineConfigWithVueTs` из `@vue/eslint-config-typescript` — это обёртка над `typescript-eslint`, правильно настраивающая `vue-eslint-parser` + `@typescript-eslint/parser` для блоков `<script>` в `.vue`. Подключить пресеты `vue.configs['flat/essential']` (из `eslint-plugin-vue`) и `vueTsConfigs.recommended`.
   - Если стек **без `@vue/eslint-config-typescript`** (legacy / минимальный) — собрать массив руками: `@eslint/js` recommended → блок с `vue-eslint-parser` (`parserOptions.parser = @typescript-eslint/parser`) → плагин `@typescript-eslint`. Эту форму использовать только когда обёртка недоступна.

2. **TypeScript-правила**. `@typescript-eslint/no-explicit-any` обычно `off` (проект прагматичный) или `warn`. Включить `@typescript-eslint/consistent-type-imports` (`prefer: 'type-imports'`, `fixStyle: 'separate-type-imports'`) — типовые импорты отделяются автоматически. `@typescript-eslint/no-unused-vars` с `argsIgnorePattern: '^_'`; парный нативный `no-unused-vars` выключить, чтобы не дублировался.

3. **Vue-правила**. `vue/multi-word-component-names: 'off'` (страницы вроде `List.vue`, `Show.vue` — норма в Inertia-проектах). Прочие отключения (`vue/no-multiple-template-root`, `vue/no-v-model-argument`) — только по реальной необходимости стека.

4. **`@stylistic` — структурные правила, которых нет в Prettier**. Плагин `@stylistic/eslint-plugin`. Здесь — то, что Prettier не делает: `padding-line-between-statements` (пустые строки вокруг управляющих конструкций — генерируется хелпером, см. п. 6), `brace-style: ['1tbs', { allowSingleLine: false }]`, при желании `curly: ['error', 'all']`. Не дублируй форматирование, которое уже делает Prettier (отступы/кавычки) — это зона Prettier (п. 7), иначе правила конфликтуют.

5. **`import/order` и границы импортов** (`eslint-plugin-import`).
   - `import/order`: группы `['builtin', 'external', 'internal', 'parent', 'sibling', 'index']`, `alphabetize: { order: 'asc', caseInsensitive: true }`, опционально `newlines-between: 'always'`.
   - `import/consistent-type-specifier-style: 'prefer-top-level'` — связка с `consistent-type-imports` из п. 2.
   - Резолвер: `settings['import/resolver'].typescript = { alwaysTryTypes: true, project: './tsconfig.json' }` (пакет `eslint-import-resolver-typescript`), чтобы алиасы `@/...` разрешались.
   - **Семантические границы** через `no-restricted-imports` для конкретных `files`-глобов: например доменные Vue-компоненты не импортируют `@/wayfinder/routes/*` напрямую — только через actions/composables-слой (связка с `frontend/inertia-vue` feature-слоями). Точечный whitelist легитимных исключений — **отдельным блоком ПОСЛЕ** ограничивающего (flat config применяет блоки по порядку). Сам паттерн границы wayfinder — см. скилл `frontend/wayfinder`.

6. **`padding-line-between-statements`**. Не выписывать руками десятки пар — сгенерировать: список управляющих конструкций (`if/return/for/while/do/switch/try/throw`) развернуть в пары `{ blankLine: 'always', prev: '*', next: stmt }` и обратную через `flatMap`. См. `snippets/eslint.config.js`.

7. **Интеграция с Prettier — порядок критичен**. `eslint-config-prettier` (импорт `eslint-config-prettier/flat` для flat config) подключается **последним** в массиве конфигов — он гасит все ESLint-правила, конфликтующие с Prettier. ESLint форматированием не занимается; форматирует Prettier. Если после `prettier` нужен ещё блок со `@stylistic`-правилами (например `curly`, `brace-style`) — он идёт после `prettier`, т.к. эти правила не конфликтуют с форматтером.

8. **Цепочка плагинов Prettier** (`.prettierrc`). Порядок плагинов в массиве `plugins` имеет значение:
   - `prettier-plugin-organize-imports` — сортировка/чистка импортов на уровне форматтера (TS language service);
   - `prettier-plugin-tailwindcss` — **строго последним** (требование плагина: должен идти после всех остальных), сортирует Tailwind-классы. Указать `tailwindFunctions: ['clsx', 'cn', 'cva']` и `tailwindStylesheet` (путь к `app.css`) для Tailwind v4.
   - Значения форматирования (`tabWidth`, `printWidth`, `singleQuote`, `semi`) — из `frontend/js-code-style`. `overrides` для `*.yml` → `tabWidth: 2`.

9. **npm-скрипты**. В `package.json` (`"type": "module"`):
   - `"lint": "eslint . --fix"` (или явно `"lint:fix"`),
   - `"lint:check": "eslint ."`,
   - `"format": "prettier --write resources/"`, `"format:check": "prettier --check resources/"`,
   - `"types:check": "vue-tsc --noEmit"`.
   Закрепить devDependencies: `eslint`, `@eslint/js`, `typescript-eslint`, `@vue/eslint-config-typescript`, `eslint-plugin-vue`, `@stylistic/eslint-plugin`, `eslint-plugin-import`, `eslint-import-resolver-typescript`, `eslint-config-prettier`, `prettier`, `prettier-plugin-tailwindcss`, `prettier-plugin-organize-imports`.

10. **`ignores`**. Отдельным блоком: `vendor`, `node_modules`, `public`, `bootstrap/ssr`, генерируемые `resources/js/{actions,routes,wayfinder}/**`, UI-китовые `resources/js/components/ui/*`, конфиги сборки (`vite.config.ts`, `tailwind.config.js`). Автоген руками не линтуем (связка с `frontend/wayfinder` и `frontend/inertia-vue`).

## Когда какой сниппет открывать

| Ситуация | Файл |
|:---|:---|
| Собрать/поправить весь `eslint.config.js` (каркас, плагины, границы, padding-хелпер, порядок prettier) | `snippets/eslint.config.js` |
| Настроить `.prettierrc` с цепочкой плагинов (organize-imports → tailwindcss последним) | `snippets/prettierrc.json` |
| Прописать npm-скрипты lint/format/types и devDependencies | `snippets/package-scripts.json` |

## Чеклист качества

- [ ] `eslint.config.js` — flat config (ESM `export default`), Vue+TS через `defineConfigWithVueTs` (или ручной каркас с `vue-eslint-parser`, если обёртки нет)
- [ ] Подключены `vue.configs['flat/essential']` и `vueTsConfigs.recommended`
- [ ] `consistent-type-imports` + `import/consistent-type-specifier-style` согласованы
- [ ] `import/order` с группами и `alphabetize`; TS-резолвер настроен на `tsconfig.json`
- [ ] `@stylistic` покрывает только то, чего нет в Prettier (padding/brace), без дублей форматирования
- [ ] `padding-line-between-statements` сгенерирован хелпером, а не выписан вручную
- [ ] `eslint-config-prettier` (`/flat`) — последним в массиве; ESLint не форматирует
- [ ] В `.prettierrc` `prettier-plugin-tailwindcss` — последний плагин; `organize-imports` перед ним
- [ ] Значения форматирования взяты из `frontend/js-code-style`, не переобоснованы здесь
- [ ] `ignores` исключает автоген (actions/routes/wayfinder), UI-кит и конфиги сборки
- [ ] Скрипты `lint`/`lint:check`/`format`/`types:check` и devDependencies прописаны

## Ссылки

- https://eslint.org/docs/latest/use/configure/configuration-files (flat config)
- https://github.com/vuejs/eslint-config-typescript
- https://typescript-eslint.io/
- https://eslint-stylistic.dev/
- https://github.com/prettier/eslint-config-prettier
- https://github.com/tailwindlabs/prettier-plugin-tailwindcss
- snippets/eslint.config.js, snippets/prettierrc.json, snippets/package-scripts.json
- Связанные скиллы: `frontend/js-code-style` (ЧТО — правила стиля), `frontend/wayfinder` (паттерн границ импортов), `frontend/inertia-vue` (feature-слои), `frontend/vitest`
