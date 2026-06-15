// Source: anonymized production project (Vue + Naive UI)
// Единый источник правды темы: resources/js/config/naive-ui.ts
// Сначала common (наследуется всеми компонентами), затем точечные пер-компонентные блоки.

import type { GlobalThemeOverrides } from 'naive-ui';

// Бренд-палитра вынесена в CSS-переменные на :root (и переопределена под .dark),
// чтобы Naive UI и Tailwind ссылались на ОДИН источник цвета. Подставляем те же
// переменные сюда — переключение класса .dark на <html> перекрашивает оба слоя.
export const theme: GlobalThemeOverrides = {
    common: {
        // Типографика и геометрия
        fontFamily: 'Inter, system-ui, sans-serif',
        fontSizeMedium: '14px',
        fontSizeLarge: '16px',
        heightMedium: '40px',
        borderRadius: '8px',

        // Палитра (через CSS-переменные — общий источник с Tailwind)
        primaryColor: 'var(--color-primary)',
        primaryColorHover: 'var(--color-primary-hover)',
        primaryColorPressed: 'var(--color-primary-pressed)',
        successColor: 'var(--color-success)',
        infoColor: 'var(--color-info)',
        warningColor: 'var(--color-warning)',
        errorColor: 'var(--color-error)',

        // Поверхности и границы
        bodyColor: 'var(--color-body)',
        borderColor: 'var(--color-border)',
        placeholderColor: 'var(--color-placeholder)',
    },

    // Пер-компонентные блоки — только то, чего недостаточно в common.
    Button: {
        heightMedium: '40px',
        paddingMedium: '5px 16px',
        fontSizeMedium: '14px',
        fontWeight: 500,
    },
    Card: {
        paddingMedium: '20px 24px',
        paddingSmall: '16px',
        borderRadius: '8px',
        titleFontSizeMedium: '16px',
        fontSizeMedium: '14px',
    },
    Form: {
        labelFontSizeTopMedium: '12px',
        feedbackFontSizeMedium: '12px',
        feedbackHeightMedium: '24px',
        blankHeightMedium: '40px',
    },
    Input: {
        borderRadius: '8px',
    },
    Tag: {
        borderRadius: '6px',
        fontSizeMedium: '12px',
        heightMedium: '28px',
        padding: '4px 10px',
        fontWeightStrong: '600',
    },
    Tabs: {
        tabFontSizeMedium: '14px',
        tabFontWeightActive: '600',
        panePaddingMedium: '0px',
    },
};

// Опционально: переопределения, валидные только в тёмном режиме.
// Применяются ПОВЕРХ darkTheme при isDark (см. snippets/app.ts).
export const darkThemeOverrides: GlobalThemeOverrides = {
    common: {
        bodyColor: 'var(--color-body-dark)',
        borderColor: 'var(--color-border-dark)',
    },
};
