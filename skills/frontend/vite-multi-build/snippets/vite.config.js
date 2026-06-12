// Source: anonymized production Laravel project
// Основная сборка: Inertia/Vue-приложение. Выход — public/build, hotfile — public/hot (дефолты).

import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig, loadEnv } from 'vite';
import laravel from 'laravel-vite-plugin';
import tailwindcss from '@tailwindcss/vite';
import vue from '@vitejs/plugin-vue';
import { wayfinder } from '@laravel/vite-plugin-wayfinder';

const projectRoot = path.dirname(fileURLToPath(import.meta.url));

const laravelInput = [
    'resources/sass/tailwind.css',
    'resources/sass/app.sass',
    'resources/js/app.ts',
];

export default defineConfig(({ mode }) => {
    // Третий аргумент '' — читать все переменные, не только VITE_*.
    const env = loadEnv(mode, process.cwd(), '');
    const vitePort = Number(env.VITE_PORT) || 5173;
    const appOrigin = env.APP_URL || 'http://localhost:8080';

    return {
        // Docker: слушаем 0.0.0.0 внутри контейнера; HMR ходит через localhost;
        // CORS — origin приложения из APP_URL.
        server: {
            host: '0.0.0.0',
            port: vitePort,
            strictPort: true,
            hmr: {
                host: 'localhost',
                port: vitePort,
            },
            cors: {
                origin: appOrigin,
                credentials: true,
            },
        },
        build: {
            rollupOptions: {
                input: laravelInput,
            },
        },
        plugins: [
            wayfinder(),
            laravel({
                input: laravelInput,
                refresh: true,
            }),
            vue({
                template: {
                    transformAssetUrls: {
                        base: null,
                        includeAbsolute: false,
                    },
                },
            }),
            tailwindcss(), // использует ./tailwind.config.js (тема приложения)
        ],
        resolve: {
            alias: {
                '@/routes': path.join(projectRoot, 'resources/js/wayfinder/routes'),
                '@': path.join(projectRoot, 'resources/js'),
            },
        },
    };
});
