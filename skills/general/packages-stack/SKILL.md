---
name: packages-stack
bucket: general
version: 0.1.0
description: "Реестр используемых внешних NPM и Composer пакетов. Опирайся на официальную документацию этих пакетов при написании кода."
risk: read
persona: oss-dev
tags: [dependencies, conventions]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Стек внешних зависимостей (Packages Stack)

Во всех проектах используются стандартизированные библиотеки и пакеты. При работе с этими технологиями **не нужно выдумывать велосипеды** — используй встроенные методы из этих пакетов.

Если у тебя (ИИ) нет в базе знаний актуальной информации по пакету — **обязательно** сходи в веб-поиск и почитай их официальную документацию перед написанием кода.

## 📦 Backend (Composer / Laravel)

1. **`nwidart/laravel-modules`**
   - **Для чего:** Построение модульной архитектуры (DDD-подход).
   - **Правило:** Все новые фичи создаются внутри папки `Modules/`, а не в `app/`.
   - **Сайт:** https://nwidart.com/laravel-modules/

2. **`spatie/laravel-medialibrary`**
   - **Для чего:** Работа с файлами, загрузками, прикрепление картинок к моделям.
   - **Правило:** Никаких ручных `Storage::put()`, если сущность можно сохранить через `$model->addMedia()`.
   - **Сайт:** https://spatie.be/docs/laravel-medialibrary

3. **`filament/filament`** (v3.x)
   - **Для чего:** Построение админ-панелей и внутренних дашбордов.
   - **Правило:** Использовать Filament Resources и Forms вместо написания кастомных CRUD контроллеров.
   - **Сайт:** https://filamentphp.com/

4. **`spatie/laravel-data`** (если используется DTO)
   - **Для чего:** Строгая типизация данных, замена стандартным FormRequests и API Resources.

## 📦 Frontend (NPM / Vue / Build)

1. **`vue`** (v3.x - Composition API)
   - **Правило:** Использовать `<script setup>`, `ref()`, `computed()`.

2. **`pinia`**
   - **Для чего:** State-менеджер (вместо Vuex).

3. **`tailwindcss`**
   - **Для чего:** Стилизация компонентов.
   - **Правило:** Не писать кастомный CSS без крайней необходимости, использовать utility-классы.

4. **`@inertiajs/vue3`**
   - **Для чего:** Связка Laravel и Vue без написания API.
   - **Правило:** Использовать компонент `<Link>` для переходов.

5. **`vite`**
   - Сборщик фронтенда. Конфигурируется в `vite.config.ts`.
