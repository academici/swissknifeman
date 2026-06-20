// Source: anonymized production project
//
// Точка входа приложения (например app.ts). Ключевая строка для темы —
// вызов initializeTheme() ДО маунта: класс `.dark` ставится до первого кадра,
// поэтому чисто клиентский рендер не мигает светлой темой.
//
// Каркас createApp/mount показан для контекста — адаптируй под свой стек
// (Inertia / Vue Router / голый createApp). Важно лишь, ЧТО и КОГДА вызывается.

import { createApp, h } from 'vue';

import { initializeTheme } from '@/composables/useDarkMode';
// import App from '@/App.vue';

// Применяем тему до создания/маунта приложения — нет вспышки на клиенте.
initializeTheme();

const app = createApp({ render: () => h(/* App */ 'div') });

// ...тут регистрация плагинов: app.use(router), app.use(pinia) и т.п.

app.mount('#app');

// Для SSR-приложения одного initializeTheme() мало: между отдачей HTML и
// стартом этого бандла браузер уже рисует кадр. Корректный класс должен
// прийти из сервера — см. no-flash-init.html (cookie + inline-скрипт).
