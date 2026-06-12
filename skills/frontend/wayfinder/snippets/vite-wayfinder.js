// Source: anonymized production Laravel project
// Подключение vite-плагина Wayfinder: автогенерация типов при изменении роутов в dev.

import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import laravel from 'laravel-vite-plugin';
import vue from '@vitejs/plugin-vue';
import { wayfinder } from '@laravel/vite-plugin-wayfinder';

const projectRoot = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
    plugins: [
        // wayfinder() ДО laravel(): следит за изменениями роутов/контроллеров
        // и перегенерирует resources/js/{actions,routes,wayfinder} автоматически.
        wayfinder(),
        laravel({
            input: ['resources/js/app.ts'],
            refresh: true,
        }),
        vue(),
    ],
    resolve: {
        alias: {
            // Алиас именованных роутов на автогенерённую папку — порядок важен:
            // более специфичный '@/routes' раньше общего '@'.
            '@/routes': path.join(projectRoot, 'resources/js/wayfinder/routes'),
            '@': path.join(projectRoot, 'resources/js'),
        },
    },
});

// Без плагина — регенерация вручную после изменения роутов:
//   php artisan wayfinder:generate --no-interaction
//   php artisan wayfinder:generate --with-form --no-interaction  # + form-хелперы
