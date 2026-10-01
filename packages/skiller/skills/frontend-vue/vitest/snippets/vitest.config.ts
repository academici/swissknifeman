// Source: anonymized production Laravel project
// Vitest-config for Laravel + Inertia + Vue. Aliases are duplicated vite.config.js.

import { defineConfig } from 'vitest/config';
import vue from '@vitejs/plugin-vue';
import { resolve } from 'path';

export default defineConfig({
    plugins: [
        vue({
            // Same options as in vite.config.js, — otherwise templates are rendered differently than in the assembly.
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
            // Order is important: specific '@/routes' before general '@'.
            '@/routes': resolve(__dirname, 'resources/js/wayfinder/routes'),
            '@': resolve(__dirname, 'resources/js'),
        },
    },
    test: {
        environment: 'jsdom', // DOM-API for mount() components
        globals: true, // describe/it/expect without imports
        include: ['resources/js/tests/**/*.{test,spec}.{ts,js}'],
        coverage: {
            provider: 'v8',
            reporter: ['text', 'html', 'lcov'],
            include: ['resources/js/**/*.{ts,vue}'],
            // MUST exclude autogen and the tests themselves - otherwise coverage is meaningless:
            exclude: [
                'resources/js/tests/**',
                'resources/js/app.ts',
                'resources/js/bootstrap.ts',
                'resources/js/actions/**', // autogen Wayfinder
                'resources/js/routes/**', // autogen Wayfinder
                'resources/js/wayfinder/**', // autogen Wayfinder
            ],
            reportsDirectory: 'coverage',
        },
    },
});
