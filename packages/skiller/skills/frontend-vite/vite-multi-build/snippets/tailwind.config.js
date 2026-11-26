// Source: anonymized production Laravel project
// Tailwind-MAIN application config: custom theme, content does not intersect with Filament.

import defaultTheme from 'tailwindcss/defaultTheme';
import forms from '@tailwindcss/forms';

/** @type {import('tailwindcss').Config} */
export default {
    content: [
        './vendor/laravel/framework/src/Illuminate/Pagination/resources/views/*.blade.php',
        './storage/framework/views/*.php',
        './resources/views/**/*.blade.php',
        './resources/js/**/*.vue',
    ],

    theme: {
        extend: {
            fontFamily: {
                sans: ['Manrope Variable', ...defaultTheme.fontFamily.sans],
            },
        },
    },

    plugins: [forms],
};
