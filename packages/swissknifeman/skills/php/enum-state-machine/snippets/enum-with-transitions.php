<?php

// Source: generalized from a domain status enum with a transition graph (anonymized)
// Граф рёбер — единственный источник истины. from/to — кейсы enum; остальные ключи
// (guard/action/label/...) — метаданные ребра для авторизации, исполнения и UI.

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
     * Единый граф допустимых переходов. Никаких параллельных копий в сервисах/политиках.
     *
     * @return list<array{
     *     from: self, to: self,
     *     guard?: string, action?: class-string, label?: string
     * }>
     */
    public static function transitionDefinitions(): array
    {
        return [
            ['from' => self::Draft,           'to' => self::AwaitingPayment, 'guard' => 'canSubmit',   'action' => PayOrderAction::class,      'label' => 'Оформить'],
            ['from' => self::AwaitingPayment, 'to' => self::Paid,            'guard' => 'canPay',      'action' => PayOrderAction::class,      'label' => 'Оплатить'],
            ['from' => self::Paid,            'to' => self::Shipped,         'guard' => 'canShip',     'action' => ShipOrderAction::class,     'label' => 'Отгрузить'],
            ['from' => self::Shipped,         'to' => self::Completed,       'guard' => 'canComplete', 'action' => CompleteOrderAction::class, 'label' => 'Завершить'],

            // Отмена доступна из нескольких статусов — это просто несколько рёбер.
            ['from' => self::Draft,           'to' => self::Cancelled,       'guard' => 'canCancel',   'action' => CancelOrderAction::class,   'label' => 'Отменить'],
            ['from' => self::AwaitingPayment, 'to' => self::Cancelled,       'guard' => 'canCancel',   'action' => CancelOrderAction::class,   'label' => 'Отменить'],
            ['from' => self::Paid,            'to' => self::Cancelled,       'guard' => 'canCancel',   'action' => CancelOrderAction::class,   'label' => 'Отменить'],
        ];
    }
}
