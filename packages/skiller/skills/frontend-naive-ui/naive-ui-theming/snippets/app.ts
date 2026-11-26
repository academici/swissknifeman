// Source: anonymized production project (Vue + Naive UI entry point)
// Entry point: connecting theme, locale, dark mode and providers Naive UI.
// Key: NConfigProvider wraps providers message/modal — otherwise them
// popup nodes will not receive theme and locale.

import { computed, createApp, h } from 'vue';
import {
    darkTheme,
    dateRuRU,
    NConfigProvider,
    NDialogProvider,
    NMessageProvider,
    NModalProvider,
    ruRU,
} from 'naive-ui';
import App from '@/App.vue';
import { theme, darkThemeOverrides } from '@/config/naive-ui';

// Dark mode is tied to the same flag as Tailwind: class .dark on <html>.
// So one switch controls both utility classes and theme Naive.
const isDark = computed(() =>
    document.documentElement.classList.contains('dark'),
);

const messageOptions = { placement: 'top-right', max: 2 } as const;

createApp({
    render: () =>
        h(
            NConfigProvider,
            {
                // Topic Naive: darkTheme in dark mode, built-in light (null) otherwise.
                theme: isDark.value ? darkTheme : null,
                // themeOverrides is applied on top of both themes.
                themeOverrides: isDark.value
                    ? { ...theme, ...darkThemeOverrides }
                    : theme,
                // Locale next to topic - single point of global configuration UI-whale.
                locale: ruRU,
                dateLocale: dateRuRU,
            },
            // Message Providers/modalok/dialogues - INSIDE config-provider.
            () =>
                h(NModalProvider, () =>
                    h(NDialogProvider, () =>
                        h(NMessageProvider, messageOptions, () => h(App)),
                    ),
                ),
        ),
}).mount('#app');
