// Source: anonymized production project
//
// Composable dark theme light | dark | system for Vue 3.
// - source of truth: localStorage (client) + cookie (for SSR);
// - class `.dark` on <html> via classList.toggle;
// - matchMedia('(prefers-color-scheme: dark)') for mode system + listener change;
// - all calls to window/document/localStorage under SSR-guard.
//
// updateTheme / initializeTheme are exported separately: they are called from the entry point
// BEFORE application mount (see bootstrap-init.ts), and not just from components.

import type { ComputedRef, Ref } from 'vue';
import { computed, onMounted, ref } from 'vue';

export type ResolvedAppearance = 'light' | 'dark';
export type Appearance = ResolvedAppearance | 'system';

export type UseDarkModeReturn = {
    appearance: Ref<Appearance>;
    resolvedAppearance: ComputedRef<ResolvedAppearance>;
    updateAppearance: (value: Appearance) => void;
};

// One name for localStorage and cookie. If you change it, change it SSR-template.
const STORAGE_KEY = 'appearance';
const COOKIE_MAX_AGE_DAYS = 365;

// --- low-level helpers (all SSR-safe) -------------------------------

const isClient = (): boolean => typeof window !== 'undefined';

const prefersDark = (): boolean =>
    isClient() && window.matchMedia('(prefers-color-scheme: dark)').matches;

const systemMediaQuery = (): MediaQueryList | null =>
    isClient() ? window.matchMedia('(prefers-color-scheme: dark)') : null;

const getStoredAppearance = (): Appearance | null =>
    isClient() ? (localStorage.getItem(STORAGE_KEY) as Appearance | null) : null;

const setCookie = (name: string, value: string, days = COOKIE_MAX_AGE_DAYS): void => {
    if (typeof document === 'undefined') {
        return;
    }

    const maxAge = days * 24 * 60 * 60;

    document.cookie = `${name}=${value};path=/;max-age=${maxAge};SameSite=Lax`;
};

// --- theme application (clean, no storage) --------------------------------

// Sets/removes class `.dark` on <html>. For 'system' resolves via matchMedia.
export function updateTheme(value: Appearance): void {
    if (!isClient()) {
        return;
    }

    const isDark = value === 'system' ? prefersDark() : value === 'dark';

    document.documentElement.classList.toggle('dark', isDark);
}

// --- boot: call at the entry point BEFORE the mount (see bootstrap-init.ts) ----------

const handleSystemThemeChange = (): void => {
    // System change affects the screen only while selected 'system'.
    updateTheme(getStoredAppearance() ?? 'system');
};

export function initializeTheme(): void {
    if (!isClient()) {
        return;
    }

    // Immediately apply the saved selection (or system) — before the first frame.
    updateTheme(getStoredAppearance() ?? 'system');

    // Reaction to changing the system theme on the fly.
    systemMediaQuery()?.addEventListener('change', handleSystemThemeChange);
}

// --- composable for components ------------------------------------------

// Modular ref: is experiencing repeated calls useDarkMode in different components.
const appearance = ref<Appearance>('system');

export function useDarkMode(): UseDarkModeReturn {
    onMounted(() => {
        // Synchronization after SSR-hydration: on server ref was defaulted.
        const saved = getStoredAppearance();

        if (saved) {
            appearance.value = saved;
        }
    });

    const resolvedAppearance = computed<ResolvedAppearance>(() =>
        appearance.value === 'system'
            ? prefersDark()
                ? 'dark'
                : 'light'
            : appearance.value,
    );

    function updateAppearance(value: Appearance): void {
        appearance.value = value;

        // The source of truth is on the client.
        localStorage.setItem(STORAGE_KEY, value);
        // Server copy: localStorage is not available to the server.
        setCookie(STORAGE_KEY, value);

        updateTheme(value);
    }

    return { appearance, resolvedAppearance, updateAppearance };
}
