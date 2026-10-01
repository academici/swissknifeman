<?php

// Source: anonymized production Laravel project
// Data-order class: nested DataCollection positions, castes/transformers,
// computed-summary, name mapping camelCase<->snake_case and export to TypeScript.

declare(strict_types=1);

namespace App\Data;

use App\Enums\OrderStatus;
use Carbon\CarbonImmutable;
use Spatie\LaravelData\Attributes\Computed;
use Spatie\LaravelData\Attributes\DataCollectionOf;
use Spatie\LaravelData\Attributes\MapName;
use Spatie\LaravelData\Attributes\WithCast;
use Spatie\LaravelData\Attributes\WithTransformer;
use Spatie\LaravelData\Attributes\Validation\Max;
use Spatie\LaravelData\Attributes\Validation\Required;
use Spatie\LaravelData\Casts\DateTimeInterfaceCast;
use Spatie\LaravelData\Data;
use Spatie\LaravelData\DataCollection;
use Spatie\LaravelData\Mappers\SnakeCaseMapper;
use Spatie\LaravelData\Transformers\DateTimeInterfaceTransformer;
use Spatie\TypeScriptTransformer\Attributes\TypeScript;

// #[TypeScript] -> will hit generated.d.ts like App.Data.OrderData (see frontend/backend-type-sync).
// Class #[MapName(SnakeCaseMapper)] -> properties camelCase in PHP, keys snake_case in JSON/in the input.
#[TypeScript]
#[MapName(SnakeCaseMapper::class)]
class OrderData extends Data
{
    public function __construct(
        // Simple typed property + validation rules directly on the property.
        #[Required, Max(64)]
        public string $reference,

        // Enum is cast automatically by property type (input) and is serialized as backed value (exit).
        public OrderStatus $status,

        // Cast is applied at the entrance (from()), transformer - at the output (toArray()).
        // String "2026-01-31" -> CarbonImmutable -> ISO-line in JSON.
        #[WithCast(DateTimeInterfaceCast::class)]
        #[WithTransformer(DateTimeInterfaceTransformer::class)]
        public ?CarbonImmutable $dueAt,

        // Single nested DTO — is just a property type.
        public ?CustomerData $customer,

        // List of children DTO: DataCollection + REQUIRED element type.
        // Without #[DataCollectionOf] package does not know what to expand the array into.
        /** @var DataCollection<ItemData> */
        #[DataCollectionOf(ItemData::class)]
        public DataCollection $items,
    ) {
        // Computed-property is initialized in the constructor from other fields.
        $this->total = $this->items->toCollection()->sum('amount');
    }

    // Computed-property: calculated from items, hits toArray() and in TS-type,
    // but is NOT expected in the input (is not present in from()-source).
    #[Computed]
    public int $total;
}
