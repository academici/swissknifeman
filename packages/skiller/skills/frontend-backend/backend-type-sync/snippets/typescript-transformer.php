<?php

// Source: anonymized production Laravel project (config/typescript-transformer.php)
// Генерирует resources/js/types/generated.d.ts из аннотированных #[TypeScript] PHP-классов.

declare(strict_types=1);

return [
    /*
     * Пути сканирования. Неймспейс PHP-класса под этими путями задаёт
     * неймспейс TS: App\Enums\Order\OrderStatus -> App.Enums.Order.OrderStatus.
     */
    'auto_discover_types' => [
        app_path(),
    ],

    /*
     * DefaultCollector ловит классы с атрибутом #[TypeScript] (и legacy @typescript).
     */
    'collectors' => [
        Spatie\TypeScriptTransformer\Collectors\DefaultCollector::class,
    ],

    /*
     * Включай только реально используемые трансформеры:
     *  - EnumTransformer        — нативные PHP backed-enum -> App.Enums.*
     *  - SpatieEnumTransformer  — enum пакета spatie/enum (если применяется)
     *  - DtoTransformer         — Spatie-Data DTO -> App.Data.* / App.Dto.*
     *  - SpatieStateTransformer — Spatie States (если применяются)
     */
    'transformers' => [
        Spatie\LaravelTypeScriptTransformer\Transformers\SpatieStateTransformer::class,
        Spatie\TypeScriptTransformer\Transformers\EnumTransformer::class,
        Spatie\TypeScriptTransformer\Transformers\SpatieEnumTransformer::class,
        Spatie\LaravelTypeScriptTransformer\Transformers\DtoTransformer::class,
    ],

    /*
     * На проводе datetime — это JSON-строки. Отдаём их как string,
     * иначе на фронте получим нечитаемый/любой тип.
     */
    'default_type_replacements' => [
        DateTimeImmutable::class => 'string',
        Carbon\CarbonInterface::class => 'string',
        Carbon\CarbonImmutable::class => 'string',
        Carbon\Carbon::class => 'string',
    ],

    /*
     * Единый выходной файл. Коммитится в репозиторий; должен входить
     * в "include" tsconfig.json.
     */
    'output_file' => resource_path('js/types/generated.d.ts'),

    /*
     * Формат записи. По умолчанию TypeDefinitionWriter (declare namespace App).
     * Можно подменить на ModuleWriter или собственный writer.
     */
    'writer' => Spatie\TypeScriptTransformer\Writers\TypeDefinitionWriter::class,

    /*
     * Опциональный форматтер вывода (например, PrettierFormatter). null — без форматирования.
     */
    'formatter' => null,

    /*
     * false — enum как union строк/чисел (тип). true — нативный TS-enum
     * (нужны рантайм-значения). Держи выбор единообразным по проекту.
     */
    'transform_to_native_enums' => false,

    /*
     * false — nullable как union с null (field: T | null).
     * true  — nullable как опциональное поле (field?: T).
     */
    'transform_null_to_optional' => false,
];
