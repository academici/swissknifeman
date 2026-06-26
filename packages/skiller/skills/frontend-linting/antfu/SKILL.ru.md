> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: antfu
description: Anthony Fu's opinionated tooling and conventions for JavaScript/TypeScript projects. Use when setting up new projects, configuring ESLint/Prettier alternatives, monorepos, library publishing, or when the user mentions Anthony Fu's preferences.
metadata:
  author: Anthony Fu
  version: "2026.05.01"
---

## Практики написания кода

### Организация кода

- **Единая ответственность**: у каждого исходного файла должна быть чёткая, сфокусированная область/цель
- **Дробление больших файлов**: разбивайте файлы, когда они становятся большими или начинают решать слишком много задач
- **Отделение типов**: всегда выносите типы и интерфейсы в `types.ts` или `types/*.ts`
- **Вынос констант**: переносите константы в отдельный файл `constants.ts`

### Среда выполнения (runtime)

- **Предпочитайте изоморфный код**: пишите runtime-агностичный код, работающий в Node, браузере и воркерах, везде где это возможно
- **Явные указатели среды**: когда код привязан к конкретной среде, добавьте комментарий в начало файла:

```ts
// @env node
// @env browser
```

### TypeScript

- **Явные типы возврата**: объявляйте типы возвращаемых значений явно, когда это возможно
- **Избегайте сложных inline-типов**: выносите сложные типы в отдельные объявления `type` или `interface`

### Комментарии

- **Избегайте ненужных комментариев**: код должен быть самодокументируемым
- **Объясняйте «почему», а не «как»**: комментарии должны описывать причину или замысел, а не то, что делает код

### Тестирование (Vitest)

- Файлы тестов: `foo.ts` → `foo.test.ts` (в том же каталоге)
- Используйте API `describe`/`it` (не `test`)
- Используйте `toMatchSnapshot` для сложных выводов
- Используйте `toMatchFileSnapshot` с явным путём для снимков, специфичных для конкретного языка

---

## Выбор инструментов

### Команды @antfu/ni

| Команда | Описание |
|---------|-------------|
| `ni` | Установить зависимости |
| `ni <pkg>` / `ni -D <pkg>` | Добавить зависимость / dev-зависимость |
| `nr <script>` | Запустить скрипт |
| `nu` | Обновить зависимости |
| `nun <pkg>` | Удалить зависимость |
| `nci` | Чистая установка (`pnpm i --frozen-lockfile`) |
| `nlx <pkg>` | Выполнить пакет (`npx`) |

### Проверка версий npm-пакетов

Используйте [`fast-npm-meta`](https://github.com/antfu/fast-npm-meta) для поиска последней версии пакета — он запрашивает небольшой метаданные-эндпоинт вместо скачивания полного payload реестра (который может занимать мегабайты на пакет).

```bash
nlx fast-npm-meta version vite              # 7.3.1
nlx fast-npm-meta version "nuxt@^3.5"       # 3.5.22 — с учётом диапазона
nlx fast-npm-meta version vite nuxt vue     # несколько сразу
nlx fast-npm-meta version vite --json       # JSON для скриптов
nlx fast-npm-meta full vite                 # полный список версий + dist-tags
```

Предпочитайте это вместо `npm view <pkg> version`, когда вам нужна только последняя версия, и вместо чтения `package.json` напрямую из реестра.

### Конфигурация TypeScript

```json
{
  "compilerOptions": {
    "target": "ESNext",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true
  }
}
```

### Настройка ESLint

```js
// eslint.config.mjs
import antfu from '@antfu/eslint-config'

export default antfu()
```


По завершении задач запускайте `pnpm run lint --fix`, чтобы отформатировать код и исправить стиль написания.

Подробные опции конфигурации: [antfu-eslint-config](references/antfu-eslint-config.md)

### Git-хуки

```json
{
  "simple-git-hooks": {
    "pre-commit": "pnpm i --frozen-lockfile --ignore-scripts --offline && npx lint-staged"
  },
  "lint-staged": { "*": "eslint --fix" },
  "scripts": {
    "prepare": "npx simple-git-hooks"
  }
}
```

### Каталоги pnpm (catalogs)

Используйте именованные каталоги в `pnpm-workspace.yaml` для управления версиями:

| Каталог | Назначение |
|---------|-------------|
| `prod` | Продакшен-зависимости |
| `inlined` | Зависимости, инлайнящиеся бандлером |
| `dev` | Dev-инструменты (линтер, бандлер, тестирование) |
| `frontend` | Фронтенд-библиотеки |

Избегайте каталога по умолчанию (default). Имена каталогов можно подстраивать под нужды конкретного проекта.

---

## Справочные материалы (References)

| Тема | Описание | Ссылка |
|-------|-------------|-----------|
| ESLint Config | Поддержка фреймворков, форматтеры, переопределения правил, настройки VS Code | [antfu-eslint-config](references/antfu-eslint-config.md) |
| Project Setup | .gitignore, GitHub Actions, расширения VS Code | [setting-up](references/setting-up.md) |
| App Development | Соглашения и паттерны Vue/Nuxt/UnoCSS | [app-development](references/app-development.md) |
| Library Development | Бандлинг через tsdown, публикация pure ESM | [library-development](references/library-development.md) |
| Monorepo | pnpm workspaces, централизованный alias, Turborepo | [monorepo](references/monorepo.md) |
