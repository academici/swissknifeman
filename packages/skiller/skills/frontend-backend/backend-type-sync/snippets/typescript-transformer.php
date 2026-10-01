<?php

// Source: anonymized production Laravel project (config/typescript-transformer.php)
// Generates resources/js/types/generated.d.ts from annotated #[TypeScript] PHP-classes.

declare(strict_types=1);

return [
    /*
     * Scan paths. Namespace PHP-class under these paths specifies
     * namespace TS: App\Enums\Order\OrderStatus -> App.Enums.Order.OrderStatus.
     */
    'auto_discover_types' => [
        app_path(),
    ],

    /*
     * DefaultCollector catches classes with the attribute #[TypeScript] (and legacy @typescript).
     */
    'collectors' => [
        Spatie\TypeScriptTransformer\Collectors\DefaultCollector::class,
    ],

    /*
     * Include only actually used transformers:
     *  - EnumTransformer        — native PHP backed-enum -> App.Enums.*
     *  - SpatieEnumTransformer  — enum package spatie/enum (if applicable)
     *  - DtoTransformer         — Spatie-Data DTO -> App.Data.* / App.Dto.*
     *  - SpatieStateTransformer — Spatie States (if applicable)
     */
    'transformers' => [
        Spatie\LaravelTypeScriptTransformer\Transformers\SpatieStateTransformer::class,
        Spatie\TypeScriptTransformer\Transformers\EnumTransformer::class,
        Spatie\TypeScriptTransformer\Transformers\SpatieEnumTransformer::class,
        Spatie\LaravelTypeScriptTransformer\Transformers\DtoTransformer::class,
    ],

    /*
     * On the wire datetime — this JSON-lines. We give them away as string,
     * otherwise we get unreadable at the front/any type.
     */
    'default_type_replacements' => [
        DateTimeImmutable::class => 'string',
        Carbon\CarbonInterface::class => 'string',
        Carbon\CarbonImmutable::class => 'string',
        Carbon\Carbon::class => 'string',
    ],

    /*
     * Single output file. Commits to the repository; must be included
     * in "include" tsconfig.json.
     */
    'output_file' => resource_path('js/types/generated.d.ts'),

    /*
     * Recording format. Default TypeDefinitionWriter (declare namespace App).
     * Can be replaced with ModuleWriter or custom writer.
     */
    'writer' => Spatie\TypeScriptTransformer\Writers\TypeDefinitionWriter::class,

    /*
     * Optional output formatter (for example, PrettierFormatter). null — without formatting.
     */
    'formatter' => null,

    /*
     * false — enum like union lines/numbers (type). true — native TS-enum
     * (need runtime values). Keep selections consistent throughout the project.
     */
    'transform_to_native_enums' => false,

    /*
     * false — nullable like union with null (field: T | null).
     * true  — nullable as an optional field (field?: T).
     */
    'transform_null_to_optional' => false,
];
