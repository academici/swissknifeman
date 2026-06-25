// Source: anonymized production project
//
// Composable тёмной темы light | dark | system для Vue 3.
// - source of truth: localStorage (клиент) + cookie (для SSR);
// - класс `.dark` на <html> через classList.toggle;
// - matchMedia('(prefers-color-scheme: dark)') для режима system + слушатель change;
// - все обращения к window/document/localStorage под SSR-guard.
//
// updateTheme / initializeTheme экспортируются отдельно: их зовут из точки входа
// ДО маунта приложения (см. bootstrap-init.ts), а не только из компонентов.

import type { ComputedRef, Ref } from 'vue';
import { computed, onMounted, ref } from 'vue';

export type ResolvedAppearance = 'light' | 'dark';
export type Appearance = ResolvedAppearance | 'system';

export type UseDarkModeReturn = {
    appearance: Ref<Appearance>;
    resolvedAppearance: ComputedRef<ResolvedAppearance>;
    updateAppearance: (value: Appearance) => void;
};

// Одно имя для localStorage и cookie. Меняешь — меняй и в SSR-шаблоне.
const STORAGE_KEY = 'appearance';
const COOKIE_MAX_AGE_DAYS = 365;

// --- низкоуровневые помощники (все SSR-safe) -------------------------------

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

// --- применение темы (чистое, без хранения) --------------------------------

// Ставит/снимает класс `.dark` на <html>. Для 'system' разрешает через matchMedia.
export function updateTheme(value: Appearance): void {
    if (!isClient()) {
        return;
    }

    const isDark = value === 'system' ? prefersDark() : value === 'dark';

    document.documentElement.classList.toggle('dark', isDark);
}

// --- boot: вызвать в точке входа ДО маунта (см. bootstrap-init.ts) ----------

const handleSystemThemeChange = (): void => {
    // Системная смена влияет на экран, только пока выбран 'system'.
    updateTheme(getStoredAppearance() ?? 'system');
};

export function initializeTheme(): void {
    if (!isClient()) {
        return;
    }

    // Немедленно применяем сохранённый выбор (или system) — до первого кадра.
    updateTheme(getStoredAppearance() ?? 'system');

    // Реакция на смену системной темы на лету.
    systemMediaQuery()?.addEventListener('change', handleSystemThemeChange);
}

// --- composable для компонентов --------------------------------------------

// Модульный ref: переживает повторные вызовы useDarkMode в разных компонентах.
const appearance = ref<Appearance>('system');

export function useDarkMode(): UseDarkModeReturn {
    onMounted(() => {
        // Синхронизация после SSR-гидрации: на сервере ref был дефолтным.
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

        // Источник правды на клиенте.
        localStorage.setItem(STORAGE_KEY, value);
        // Копия для сервера: localStorage серверу недоступен.
        setCookie(STORAGE_KEY, value);

        updateTheme(value);
    }

    return { appearance, resolvedAppearance, updateAppearance };
}
