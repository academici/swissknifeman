// Source: anonymized production project (Vue + Naive UI)
// Single source of truth topic: resources/js/config/naive-ui.ts
// First common (is inherited by all components), then point per-component blocks.

import type { GlobalThemeOverrides } from 'naive-ui';

// The brand palette is placed in CSS-variables on:root (and redefined under .dark),
// to Naive UI and Tailwind referenced ONE color source. We substitute the same
// variables here - class switching.dark on <html> recolors both layers.
export const theme: GlobalThemeOverrides = {
    common: {
        // Typography and Geometry
        fontFamily: 'Inter, system-ui, sans-serif',
        fontSizeMedium: '14px',
        fontSizeLarge: '16px',
        heightMedium: '40px',
        borderRadius: '8px',

        // Palette (via CSS-variables - shared source with Tailwind)
        primaryColor: 'var(--color-primary)',
        primaryColorHover: 'var(--color-primary-hover)',
        primaryColorPressed: 'var(--color-primary-pressed)',
        successColor: 'var(--color-success)',
        infoColor: 'var(--color-info)',
        warningColor: 'var(--color-warning)',
        errorColor: 'var(--color-error)',

        // Surfaces and boundaries
        bodyColor: 'var(--color-body)',
        borderColor: 'var(--color-border)',
        placeholderColor: 'var(--color-placeholder)',
    },

    // Per-component blocks are just what is not enough in common.
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

// Optional: overrides valid only in dark mode.
// Apply OVER darkTheme when isDark (see snippets/app.ts).
export const darkThemeOverrides: GlobalThemeOverrides = {
    common: {
        bodyColor: 'var(--color-body-dark)',
        borderColor: 'var(--color-border-dark)',
    },
};
