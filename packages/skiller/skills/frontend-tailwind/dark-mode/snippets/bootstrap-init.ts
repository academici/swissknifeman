// Source: anonymized production project
//
// Application entry point (for example app.ts). The key line for the topic is
// call initializeTheme() BEFORE mount: class `.dark` is placed before the first frame,
// so the purely client render does not flash the light theme.
//
// Frame createApp/mount shown for context - adapt to your stack
// (Inertia / Vue Router / naked createApp). All that matters is WHAT is called and WHEN.

import { createApp, h } from 'vue';

import { initializeTheme } from '@/composables/useDarkMode';
// import App from '@/App.vue';

// Applying a theme before creating/application mount - no flash on the client.
initializeTheme();

const app = createApp({ render: () => h(/* App */ 'div') });

// ...here is the registration of plugins: app.use(router), app.use(pinia) etc.

app.mount('#app');

// For SSR-applications of one initializeTheme() little: between recoil HTML and
// by the start of this bundle, the browser is already drawing a frame. The correct class should
// come from the server - see. no-flash-init.html (cookie + inline-script).
