// Source: anonymized production Vue 3 + TS project (eslint.config.js, flat config, ESLint 9+)
// Frame: defineConfigWithVueTs (wrapper over typescript-eslint) + eslint-plugin-vue,
// @stylistic for structural rules, eslint-plugin-import for the order and boundaries of imports,
// eslint-config-prettier LATEST (resolves conflicts with Prettier).
//
// WHAT (style values Spatie) — in skill frontend/js-code-style; here WHAT/HOW it is turned on.

import stylistic from '@stylistic/eslint-plugin';
import { defineConfigWithVueTs, vueTsConfigs } from '@vue/eslint-config-typescript';
import prettier from 'eslint-config-prettier/flat'; // /flat — option for flat config
import importPlugin from 'eslint-plugin-import';
import vue from 'eslint-plugin-vue';

// --- padding-line-between-statements: we generate pairs instead of writing them out by hand ---
const controlStatements = ['if', 'return', 'for', 'while', 'do', 'switch', 'try', 'throw'];

const paddingAroundControl = controlStatements.flatMap((stmt) => [
    { blankLine: 'always', prev: '*', next: stmt },
    { blankLine: 'always', prev: stmt, next: '*' },
]);

// --- semantic boundaries of imports (link with feature-layers inertia-vue) ---
// Domain Vue-components do not import generated wayfinder-routes directly,
// only via actions/composables-layer. Border pattern - in skill frontend/wayfinder.
const documentVueFiles = [
    'resources/js/components/document/**/*.vue',
    'resources/js/pages/Documents/**/*.vue',
];

// Files that are directly wayfinder-import allowed deliberately (tables, aggregator forms):
const documentWayfinderImportWhitelist = [
    'resources/js/components/document/DocumentForm.vue',
    'resources/js/components/document/DocumentTable.vue',
    'resources/js/pages/Documents/List.vue',
];

export default defineConfigWithVueTs(
    vue.configs['flat/essential'],
    vueTsConfigs.recommended,

    // --- TypeScript + import: rules and alias resolver ---
    {
        plugins: {
            import: importPlugin,
        },
        settings: {
            'import/resolver': {
                typescript: {
                    alwaysTryTypes: true,
                    project: './tsconfig.json', // to @/... were allowed
                },
                node: true,
            },
        },
        rules: {
            'vue/multi-word-component-names': 'off', // List.vue / Show.vue — normal
            '@typescript-eslint/no-explicit-any': 'off',
            '@typescript-eslint/consistent-type-imports': [
                'error',
                { prefer: 'type-imports', fixStyle: 'separate-type-imports' },
            ],
            '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
            'no-unused-vars': 'off', // do not duplicate native on top TS-versions
            'import/order': [
                'error',
                {
                    groups: ['builtin', 'external', 'internal', 'parent', 'sibling', 'index'],
                    alphabetize: { order: 'asc', caseInsensitive: true },
                    // 'newlines-between': 'always', // enable if desired
                },
            ],
            'import/consistent-type-specifier-style': ['error', 'prefer-top-level'],
        },
    },

    // --- @stylistic: just what it does NOT do Prettier ---
    {
        plugins: {
            '@stylistic': stylistic,
        },
        rules: {
            '@stylistic/brace-style': ['error', '1tbs', { allowSingleLine: false }],
            '@stylistic/padding-line-between-statements': ['error', ...paddingAroundControl],
        },
    },

    // --- import boundaries: bounding box ---
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
                                'In domain Vue-components use actions/composables-layer instead of straight lines wayfinder-imports.',
                        },
                    ],
                },
            ],
        },
    },
    // whitelist comes AFTER the bounding block - flat config applies the rules in order:
    {
        files: documentWayfinderImportWhitelist,
        rules: {
            'no-restricted-imports': 'off',
        },
    },

    // --- that we don’t lint: autogen, UI-kit, build configs ---
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

    prettier, // LAST: extinguishes everything ESLint-rules that conflict with Prettier

    // block after prettier is only valid for rules that do NOT conflict with the formatter:
    {
        rules: {
            curly: ['error', 'all'],
        },
    },
);
