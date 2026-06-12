// Source: anonymized production Laravel project
// Tailwind-конфиг АДМИНКИ: жёсткий пресет Filament, content — только Filament-файлы.
// Не добавлять сюда тему приложения: пресет Filament несовместим с произвольными overrides.

import preset from './vendor/filament/filament/tailwind.config.preset';

/** @type {import('tailwindcss').Config} */
export default {
    presets: [preset],
    content: [
        './app/Filament/**/*.php',
        './resources/views/filament/**/*.blade.php',
        './vendor/filament/**/*.blade.php',
    ],
};
