// Source: anonymized production Laravel project
// Fragment eslint.config.cjs (flat config): semantic boundaries of imports.
// Idea: domain Vue-components are not included in @/wayfinder/routes/* directly -
// only through layer actions/composables. Spot whitelist for legitimate exceptions.

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
                                'In domain Vue-components use actions/composables-layer instead of straight lines wayfinder-imports.',
                        },
                    ],
                },
            ],
            // Disallow string literals instead of generated ones enum:
            'no-restricted-syntax': [
                'error',
                {
                    selector:
                        "SwitchCase > Literal[value='approved'], Property[key.name='status'] > Literal[value='approved']",
                    message: 'Use App.Enums.Document.Status.Approved instead of a string literal.',
                },
                {
                    selector:
                        "SwitchCase > Literal[value='rejected'], Property[key.name='status'] > Literal[value='rejected']",
                    message: 'Use App.Enums.Document.Status.Rejected instead of a string literal.',
                },
            ],
        },
    },
    // Whitelist comes AFTER the bounding block - flat config applies the rules in order:
    {
        files: documentWayfinderImportWhitelist,
        rules: {
            'no-restricted-imports': 'off',
        },
    },
];
