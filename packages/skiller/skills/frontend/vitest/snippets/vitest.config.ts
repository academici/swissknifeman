// Source: anonymized production Laravel project
// Vitest-конфиг для Laravel + Inertia + Vue. Алиасы дублируют vite.config.js.

import { defineConfig } from 'vitest/config';
import vue from '@vitejs/plugin-vue';
import { resolve } from 'path';

export default defineConfig({
    plugins: [
        vue({
            // Те же опции, что в vite.config.js, — иначе шаблоны рендерятся иначе, чем в сборке.
            template: {
                transformAssetUrls: {
                    base: null,
                    includeAbsolute: false,
                },
            },
        }),
    ],
    resolve: {
        alias: {
            // Порядок важен: специфичный '@/routes' раньше общего '@'.
            '@/routes': resolve(__dirname, 'resources/js/wayfinder/routes'),
            '@': resolve(__dirname, 'resources/js'),
        },
    },
    test: {
        environment: 'jsdom', // DOM-API для mount() компонентов
        globals: true, // describe/it/expect без импортов
        include: ['resources/js/tests/**/*.{test,spec}.{ts,js}'],
        coverage: {
            provider: 'v8',
            reporter: ['text', 'html', 'lcov'],
            include: ['resources/js/**/*.{ts,vue}'],
            // ОБЯЗАТЕЛЬНО исключить автоген и сами тесты — иначе coverage бессмысленен:
            exclude: [
                'resources/js/tests/**',
                'resources/js/app.ts',
                'resources/js/bootstrap.ts',
                'resources/js/actions/**', // автоген Wayfinder
                'resources/js/routes/**', // автоген Wayfinder
                'resources/js/wayfinder/**', // автоген Wayfinder
            ],
            reportsDirectory: 'coverage',
        },
    },
});
