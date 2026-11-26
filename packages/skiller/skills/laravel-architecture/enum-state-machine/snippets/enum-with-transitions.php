<?php

// Source: generalized from a domain status enum with a transition graph (anonymized)
// The edge graph is the only source of truth. from/to — cases enum; other keys
// (guard/action/label/...) — edge metadata for authorization, execution and UI.

declare(strict_types=1);

namespace App\Enums;

use App\Actions\Order\PayOrderAction;
use App\Actions\Order\ShipOrderAction;
use App\Actions\Order\CompleteOrderAction;
use App\Actions\Order\CancelOrderAction;

enum OrderStatus: string
{
    case Draft = 'draft';
    case AwaitingPayment = 'awaiting_payment';
    case Paid = 'paid';
    case Shipped = 'shipped';
    case Completed = 'completed';
    case Cancelled = 'cancelled';

    /**
     * A single graph of valid transitions. No parallel copies in services/policies.
     *
     * @return list<array{
     *     from: self, to: self,
     *     guard?: string, action?: class-string, label?: string
     * }>
     */
    public static function transitionDefinitions(): array
    {
        return [
            ['from' => self::Draft,           'to' => self::AwaitingPayment, 'guard' => 'canSubmit',   'action' => PayOrderAction::class,      'label' => 'Checkout'],
            ['from' => self::AwaitingPayment, 'to' => self::Paid,            'guard' => 'canPay',      'action' => PayOrderAction::class,      'label' => 'Pay'],
            ['from' => self::Paid,            'to' => self::Shipped,         'guard' => 'canShip',     'action' => ShipOrderAction::class,     'label' => 'Ship'],
            ['from' => self::Shipped,         'to' => self::Completed,       'guard' => 'canComplete', 'action' => CompleteOrderAction::class, 'label' => 'Finish'],

            // Cancellation is available from several statuses - it's just a few edges.
            ['from' => self::Draft,           'to' => self::Cancelled,       'guard' => 'canCancel',   'action' => CancelOrderAction::class,   'label' => 'Cancel'],
            ['from' => self::AwaitingPayment, 'to' => self::Cancelled,       'guard' => 'canCancel',   'action' => CancelOrderAction::class,   'label' => 'Cancel'],
            ['from' => self::Paid,            'to' => self::Cancelled,       'guard' => 'canCancel',   'action' => CancelOrderAction::class,   'label' => 'Cancel'],
        ];
    }
}
