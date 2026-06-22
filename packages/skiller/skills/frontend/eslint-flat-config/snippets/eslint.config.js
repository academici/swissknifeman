// Source: anonymized production Vue 3 + TS project (eslint.config.js, flat config, ESLint 9+)
// Каркас: defineConfigWithVueTs (обёртка над typescript-eslint) + eslint-plugin-vue,
// @stylistic для структурных правил, eslint-plugin-import для порядка и границ импортов,
// eslint-config-prettier ПОСЛЕДНИМ (гасит конфликты с Prettier).
//
// ЧТО (значения стиля Spatie) — в скилле frontend/js-code-style; здесь ЧЕМ/КАК это включается.

import stylistic from '@stylistic/eslint-plugin';
import { defineConfigWithVueTs, vueTsConfigs } from '@vue/eslint-config-typescript';
import prettier from 'eslint-config-prettier/flat'; // /flat — вариант для flat config
import importPlugin from 'eslint-plugin-import';
import vue from 'eslint-plugin-vue';

// --- padding-line-between-statements: генерируем пары, а не выписываем руками ---
const controlStatements = ['if', 'return', 'for', 'while', 'do', 'switch', 'try', 'throw'];

const paddingAroundControl = controlStatements.flatMap((stmt) => [
    { blankLine: 'always', prev: '*', next: stmt },
    { blankLine: 'always', prev: stmt, next: '*' },
]);

// --- семантические границы импортов (связка с feature-слоями inertia-vue) ---
// Доменные Vue-компоненты не импортируют сгенерированные wayfinder-роуты напрямую,
// только через actions/composables-слой. Паттерн границы — в скилле frontend/wayfinder.
const documentVueFiles = [
    'resources/js/components/document/**/*.vue',
    'resources/js/pages/Documents/**/*.vue',
];

// Файлы, которым прямой wayfinder-импорт разрешён осознанно (таблицы, формы-агрегаторы):
const documentWayfinderImportWhitelist = [
    'resources/js/components/document/DocumentForm.vue',
    'resources/js/components/document/DocumentTable.vue',
    'resources/js/pages/Documents/List.vue',
];

export default defineConfigWithVueTs(
    vue.configs['flat/essential'],
    vueTsConfigs.recommended,

    // --- TypeScript + import: правила и резолвер алиасов ---
    {
        plugins: {
            import: importPlugin,
        },
        settings: {
            'import/resolver': {
                typescript: {
                    alwaysTryTypes: true,
                    project: './tsconfig.json', // чтобы @/... разрешались
                },
                node: true,
            },
        },
        rules: {
            'vue/multi-word-component-names': 'off', // List.vue / Show.vue — норма
            '@typescript-eslint/no-explicit-any': 'off',
            '@typescript-eslint/consistent-type-imports': [
                'error',
                { prefer: 'type-imports', fixStyle: 'separate-type-imports' },
            ],
            '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
            'no-unused-vars': 'off', // не дублировать нативное поверх TS-версии
            'import/order': [
                'error',
                {
                    groups: ['builtin', 'external', 'internal', 'parent', 'sibling', 'index'],
                    alphabetize: { order: 'asc', caseInsensitive: true },
                    // 'newlines-between': 'always', // включить при желании
                },
            ],
            'import/consistent-type-specifier-style': ['error', 'prefer-top-level'],
        },
    },

    // --- @stylistic: только то, чего НЕ делает Prettier ---
    {
        plugins: {
            '@stylistic': stylistic,
        },
        rules: {
            '@stylistic/brace-style': ['error', '1tbs', { allowSingleLine: false }],
            '@stylistic/padding-line-between-statements': ['error', ...paddingAroundControl],
        },
    },

    // --- границы импортов: ограничивающий блок ---
    {
        files: documentVueFiles,
        rules: {
            'no-restricted-imports': [
                'error',
                {
                    patterns: [
                        {
                            group: ['@/wayfinder/routes/*'],
                            message:
                                'В доменных Vue-компонентах используйте actions/composables-слой вместо прямых wayfinder-импортов.',
                        },
                    ],
                },
            ],
        },
    },
    // whitelist идёт ПОСЛЕ ограничивающего блока — flat config применяет правила по порядку:
    {
        files: documentWayfinderImportWhitelist,
        rules: {
            'no-restricted-imports': 'off',
        },
    },

    // --- что не линтуем: автоген, UI-кит, конфиги сборки ---
    {
        ignores: [
            'vendor',
            'node_modules',
            'public',
            'bootstrap/ssr',
            'tailwind.config.js',
            'vite.config.ts',
            'resources/js/actions/**',
            'resources/js/routes/**',
            'resources/js/wayfinder/**',
            'resources/js/components/ui/*',
        ],
    },

    prettier, // ПОСЛЕДНИМ: гасит все ESLint-правила, конфликтующие с Prettier

    // блок после prettier допустим только для правил, НЕ конфликтующих с форматтером:
    {
        rules: {
            curly: ['error', 'all'],
        },
    },
);
