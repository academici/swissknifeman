// Source: anonymized production Laravel project
// Фрагмент eslint.config.cjs (flat config): семантические границы импортов.
// Идея: доменные Vue-компоненты не ходят в @/wayfinder/routes/* напрямую —
// только через слой actions/composables. Точечный whitelist для легитимных исключений.

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

module.exports = [
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
            // Запрет строковых литералов вместо сгенерированных enum:
            'no-restricted-syntax': [
                'error',
                {
                    selector:
                        "SwitchCase > Literal[value='approved'], Property[key.name='status'] > Literal[value='approved']",
                    message: 'Используйте App.Enums.Document.Status.Approved вместо строкового литерала.',
                },
                {
                    selector:
                        "SwitchCase > Literal[value='rejected'], Property[key.name='status'] > Literal[value='rejected']",
                    message: 'Используйте App.Enums.Document.Status.Rejected вместо строкового литерала.',
                },
            ],
        },
    },
    // Whitelist идёт ПОСЛЕ ограничивающего блока — flat config применяет правила по порядку:
    {
        files: documentWayfinderImportWhitelist,
        rules: {
            'no-restricted-imports': 'off',
        },
    },
];
