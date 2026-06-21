<?php

// Source: anonymized production Laravel project
// Data-класс заказа: вложенная DataCollection позиций, касты/трансформеры,
// computed-итог, маппинг имён camelCase<->snake_case и экспорт в TypeScript.

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

// #[TypeScript] -> попадёт в generated.d.ts как App.Data.OrderData (см. frontend/backend-type-sync).
// Классовый #[MapName(SnakeCaseMapper)] -> свойства camelCase в PHP, ключи snake_case в JSON/во входе.
#[TypeScript]
#[MapName(SnakeCaseMapper::class)]
class OrderData extends Data
{
    public function __construct(
        // Простое типизированное свойство + правила валидации прямо на свойстве.
        #[Required, Max(64)]
        public string $reference,

        // Enum кастуется автоматически по типу свойства (вход) и сериализуется как backed value (выход).
        public OrderStatus $status,

        // Каст применяется на входе (from()), трансформер — на выходе (toArray()).
        // Строка "2026-01-31" -> CarbonImmutable -> ISO-строка в JSON.
        #[WithCast(DateTimeInterfaceCast::class)]
        #[WithTransformer(DateTimeInterfaceTransformer::class)]
        public ?CarbonImmutable $dueAt,

        // Одиночный вложенный DTO — просто тип-свойство.
        public ?CustomerData $customer,

        // Список дочерних DTO: DataCollection + ОБЯЗАТЕЛЬНЫЙ тип элемента.
        // Без #[DataCollectionOf] пакет не знает, во что разворачивать массив.
        /** @var DataCollection<ItemData> */
        #[DataCollectionOf(ItemData::class)]
        public DataCollection $items,
    ) {
        // Computed-свойство инициализируется в конструкторе из других полей.
        $this->total = $this->items->toCollection()->sum('amount');
    }

    // Computed-свойство: вычисляется из items, попадает в toArray() и в TS-тип,
    // но НЕ ожидается во входных данных (не присутствует в from()-источнике).
    #[Computed]
    public int $total;
}
