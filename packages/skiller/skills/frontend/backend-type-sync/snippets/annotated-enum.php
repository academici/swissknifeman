<?php

// Source: anonymized production Laravel project (app/Enums + app/Data)
// Два типичных источника типов: backed-enum -> App.Enums.*, Spatie-Data DTO -> App.Data.*.
// Атрибут #[TypeScript] включает класс в генерацию.

declare(strict_types=1);

namespace App\Enums\Order;

use Spatie\TypeScriptTransformer\Attributes\TypeScript;

// --- 1) Backed-enum -> App.Enums.Order.OrderStatus ---------------------------
// Внутреннее устройство enum (Label/Priority-атрибуты, методы) — зона скилла
// php/enum-attributes. Здесь добавляем только #[TypeScript] поверх готового enum.

#[TypeScript]
enum OrderStatus: string
{
    case Draft = 'draft';
    case Pending = 'pending';
    case Paid = 'paid';
    case Cancelled = 'cancelled';
}
// generated.d.ts:
//   namespace App { namespace Enums { namespace Order {
//     export type OrderStatus = 'draft' | 'pending' | 'paid' | 'cancelled';
//   }}}


namespace App\Data\Order;

use App\Enums\Order\OrderStatus;
use Spatie\LaravelData\Data;
use Spatie\TypeScriptTransformer\Attributes\TypeScript;

// --- 2) Spatie-Data DTO -> App.Data.Order.OrderListItem ----------------------
// Поля DTO становятся полями TS-объекта. Вложенные enum/DTO (OrderStatus,
// CustomerView) должны быть ТОЖЕ аннотированы #[TypeScript], иначе -> any.

#[TypeScript]
final class OrderListItem extends Data
{
    /**
     * Коллекции типизируй PHPDoc, иначе array -> any[].
     *
     * @param  OrderLineView[]  $lines
     */
    public function __construct(
        public int $id,
        public ?string $number,
        public OrderStatus $status,        // -> App.Enums.Order.OrderStatus
        public ?CustomerView $customer,    // -> App.Data.Order.CustomerView | null
        public array $lines,               // -> App.Data.Order.OrderLineView[]
        public string $created_at,         // Carbon на бэке -> string (см. replacements)
    ) {}
}
// generated.d.ts:
//   namespace App { namespace Data { namespace Order {
//     export type OrderListItem = {
//       id: number,
//       number: string | null,
//       status: App.Enums.Order.OrderStatus,
//       customer: App.Data.Order.CustomerView | null,
//       lines: App.Data.Order.OrderLineView[],
//       created_at: string,
//     };
//   }}}
