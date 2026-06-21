// Source: anonymized production Laravel project
// Админская сборка (Filament-тема). Полностью изолирована от основной:
// свой вход, свой buildDirectory (public/filament), свой hotfile (public/filament.hot),
// свой tailwind-конфиг с пресетом Filament.
// Запуск: vite --config vite.admin.config.js

import { defineConfig } from 'vite';
import laravel from 'laravel-vite-plugin';
import tailwindcss from '@tailwindcss/vite';

const laravelAdminInput = ['resources/filament/admin/theme.sass'];

/** @type {import('vite').UserConfig} */
export default defineConfig({
    build: {
        rollupOptions: {
            input: laravelAdminInput,
        },
    },
    plugins: [
        laravel({
            // Критично: без отдельного hotFile сборки перетирают public/hot друг друга.
            hotFile: 'public/filament.hot',
            buildDirectory: 'filament',
            input: laravelAdminInput,
        }),
        tailwindcss({
            // Явный конфиг с пресетом Filament — не смешивать с темой приложения.
            config: './tailwind-admin.config.js',
        }),
    ],
});
