---
name: vite-multi-build
bucket: frontend
version: 0.1.0
description: "Две независимые Vite-сборки в одном Laravel-проекте: основное приложение и Filament-админка с раздельными конфигами Vite/Tailwind, hotfile и build-директориями."
risk: write
persona: oss-dev
tags: [vite, laravel, filament, tailwind, build, multi-config]
requires: []
produces_for: []
outputs: []
snippets: [vite.config.js, vite.admin.config.js, tailwind.config.js, tailwind-admin.config.js, package-scripts.json]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Vite multi-build (приложение + Filament-админка)

## Контекст

Один Laravel-проект — два независимых фронтенда: основное Inertia/Vue-приложение и Filament-админка. У Filament жёсткий Tailwind-пресет; смешивание его с кастомной темой приложения в одном конфиге ломает стили обеих сторон. Решение — полностью раздельные пары конфигов Vite + Tailwind, отдельные build-директории и hotfile.

Применять когда: в Laravel-проект добавляется Filament с кастомной темой, либо нужен любой второй изолированный фронтенд-бандл (виджет, embed, лендинг).

## Алгоритм

1. **Основная сборка** — `vite.config.js`: входы `resources/js/app.ts` + sass/tailwind css, выход по умолчанию `public/build`, hotfile `public/hot`. Плагины: `wayfinder()`, `laravel()`, `vue()`, `tailwindcss()`. `APP_URL` и `VITE_PORT` читать через `loadEnv(mode, process.cwd(), '')` — для CORS/HMR в Docker.
2. **Админская сборка** — `vite.admin.config.js`: единственный вход `resources/filament/admin/theme.sass`; у `laravel()` задать `buildDirectory: 'filament'` (выход `public/filament`) и `hotFile: 'public/filament.hot'` — иначе обе сборки перетирают один hotfile.
3. **Два Tailwind-конфига**: `tailwind.config.js` — кастомная тема приложения (content: blade + vue, свои шрифты/цвета, plugin forms); `tailwind-admin.config.js` — `presets: [filament preset]`, content только Filament-файлы. В админском vite-конфиге указать `tailwindcss({ config: './tailwind-admin.config.js' })`.
4. **Скрипты package.json**: `dev`/`build` — основная сборка; `dev:admin`/`build:admin` — с флагом `--config vite.admin.config.js`. CI/деплой запускает обе build-команды.
5. **Blade-сторона**: основная — обычный `@vite([...])`; админка регистрирует тему через Filament (`->viteTheme('resources/filament/admin/theme.sass', 'filament')` или аналог) с указанием buildDirectory.

## Когда НЕ применять

- Второй бандл не требует изоляции стилей (общая тема) — достаточно добавить вход в существующий конфиг.
- SPA без Laravel — паттерн hotfile/buildDirectory специфичен для laravel-vite-plugin.

## Когда какой сниппет открывать

| Ситуация | Файл |
|:---|:---|
| Настроить основную сборку: входы, loadEnv, HMR/CORS для Docker, алиасы | `snippets/vite.config.js` |
| Настроить админскую сборку: hotFile, buildDirectory, отдельный tailwind-конфиг | `snippets/vite.admin.config.js` |
| Tailwind-тема основного приложения | `snippets/tailwind.config.js` |
| Tailwind с пресетом Filament для админки | `snippets/tailwind-admin.config.js` |
| Скрипты dev/build для обеих сборок | `snippets/package-scripts.json` |

## Чеклист качества

- [ ] У админской сборки свой `hotFile` (`public/filament.hot`) и `buildDirectory` (`public/filament`) — сборки не перетирают друг друга
- [ ] Tailwind-конфиги не пересекаются по `content` (тема приложения не сканирует Filament и наоборот)
- [ ] Админский vite-конфиг явно указывает `tailwind-admin.config.js`
- [ ] `APP_URL`/`VITE_PORT` читаются через `loadEnv`, а не захардкожены
- [ ] В package.json есть все четыре скрипта: `dev`, `build`, `dev:admin`, `build:admin`
- [ ] CI/деплой выполняет обе build-команды; `public/filament` попадает в артефакт

## Ссылки

- https://laravel.com/docs/vite
- https://filamentphp.com/docs (раздел про кастомные темы / vite theme)
- Связанные скиллы: `frontend/wayfinder` (плагин в основной сборке); версионные гайдлайны Tailwind — Boost-скилл `tailwindcss` (v3/v4)
