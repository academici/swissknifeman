<?php

// Source: anonymized production Laravel project (app/Enums + app/Data)
// Two typical type sources: backed-enum -> App.Enums.*, Spatie-Data DTO -> App.Data.*.
// Attribute #[TypeScript] includes the class in the generation.

declare(strict_types=1);

namespace App\Enums\Order;

use Spatie\TypeScriptTransformer\Attributes\TypeScript;

// --- 1) Backed-enum -> App.Enums.Order.OrderStatus ---------------------------
// Internal structure enum (Label/Priority-attributes, methods) — skill zone
// php/enum-attributes. Here we add only #[TypeScript] on top of the finished one enum.

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
// Fields DTO become fields TS-object. Nested enum/DTO (OrderStatus,
// CustomerView) must ALSO be annotated #[TypeScript], otherwise -> any.

#[TypeScript]
final class OrderListItem extends Data
{
    /**
     * Type collections PHPDoc, otherwise array -> any[].
     *
     * @param  OrderLineView[]  $lines
     */
    public function __construct(
        public int $id,
        public ?string $number,
        public OrderStatus $status,        // -> App.Enums.Order.OrderStatus
        public ?CustomerView $customer,    // -> App.Data.Order.CustomerView | null
        public array $lines,               // -> App.Data.Order.OrderLineView[]
        public string $created_at,         // Carbon on the back -> string (see replacements)
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
