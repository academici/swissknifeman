// Source: anonymized production Laravel project
// Tailwind-ADMIN config: hard preset Filament, content — only Filament-files.
// Do not add application theme here: preset Filament is not compatible with arbitrary overrides.

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
