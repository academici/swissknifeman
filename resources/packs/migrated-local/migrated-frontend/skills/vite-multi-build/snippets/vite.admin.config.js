// Source: anonymized production Laravel project
// Admin build (Filament-topic). Completely isolated from the main one:
// your entrance, your buildDirectory (public/filament), yours hotfile (public/filament.hot),
// yours tailwind-config with preset Filament.
// Launch: vite --config vite.admin.config.js

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
            // Critical: without separate hotFile assemblies are frayed public/hot each other.
            hotFile: 'public/filament.hot',
            buildDirectory: 'filament',
            input: laravelAdminInput,
        }),
        tailwindcss({
            // Explicit config with preset Filament — should not be mixed with the application theme.
            config: './tailwind-admin.config.js',
        }),
    ],
});
