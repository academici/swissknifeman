// Source: anonymized production project (Vue + Naive UI entry point)
// Точка входа: подключение темы, локали, тёмного режима и провайдеров Naive UI.
// Ключевое: NConfigProvider оборачивает провайдеры message/modal — иначе их
// всплывающие узлы не получат тему и локаль.

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

// Тёмный режим завязан на тот же флаг, что и Tailwind: класс .dark на <html>.
// Так один переключатель управляет и утилитарными классами, и темой Naive.
const isDark = computed(() =>
    document.documentElement.classList.contains('dark'),
);

const messageOptions = { placement: 'top-right', max: 2 } as const;

createApp({
    render: () =>
        h(
            NConfigProvider,
            {
                // Тема Naive: darkTheme в тёмном режиме, встроенная светлая (null) иначе.
                theme: isDark.value ? darkTheme : null,
                // themeOverrides применяется поверх обеих тем.
                themeOverrides: isDark.value
                    ? { ...theme, ...darkThemeOverrides }
                    : theme,
                // Локаль рядом с темой — единая точка глобальной конфигурации UI-кита.
                locale: ruRU,
                dateLocale: dateRuRU,
            },
            // Провайдеры сообщений/модалок/диалогов — ВНУТРИ config-provider.
            () =>
                h(NModalProvider, () =>
                    h(NDialogProvider, () =>
                        h(NMessageProvider, messageOptions, () => h(App)),
                    ),
                ),
        ),
}).mount('#app');
