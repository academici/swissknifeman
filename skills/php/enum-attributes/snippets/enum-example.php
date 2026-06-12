<?php

// Source: anonymized production Laravel project

declare(strict_types=1);

namespace App\Enums\Order;

use App\Attributes\Common\Color;
use App\Attributes\Common\Description;
use App\Attributes\Common\Label;
use App\Attributes\Order\Stage;
use App\Concerns\Enums\HasColorAttribute;
use App\Concerns\Enums\HasDescriptionAttribute;
use App\Concerns\Enums\HasLabelAttribute;
use App\Enums\Order\Workflow\OrderStage;
use EmreYarligan\EnumConcern\EnumConcern;
use Filament\Support\Contracts\HasLabel;
use ReflectionEnum;

/**
 * Обогащённый enum: метаданные кейсов декларативно в атрибутах,
 * методы getLabel()/getColor()/getDescription() — из Concern-трейтов.
 * EnumConcern добавляет коллекционные операции (all/values/...).
 * HasLabel (Filament) удовлетворяется методом getLabel() из трейта.
 */
enum OrderStatus: string implements HasLabel
{
    use EnumConcern;
    use HasColorAttribute;
    use HasDescriptionAttribute;
    use HasLabelAttribute;

    #[Stage(OrderStage::Intake)]
    #[Color('#6c757d')]
    #[Description('Черновик заказа, оформление не завершено.')]
    #[Label('Черновик')]
    case Draft = 'draft';

    #[Stage(OrderStage::Processing)]
    #[Color('#3786EB')]
    #[Description('Заказ зарегистрирован и передан в обработку.')]
    #[Label('Зарегистрирован')]
    case Registered = 'registered';

    #[Stage(OrderStage::Processing)]
    #[Color('#F9AA4B')]
    #[Description('Заказ обрабатывается ответственным менеджером.')]
    #[Label('В работе')]
    case InProgress = 'in_progress';

    #[Stage(OrderStage::Finalization)]
    #[Color('#18B797')]
    #[Description('Заказ выполнен и закрыт.')]
    #[Label('Завершён')]
    case Finished = 'finished';

    // Кейс без Color: трейт вернёт дефолт '#6c757d'.
    #[Description('Служебный отменённый статус вне stage-графа.')]
    #[Label('Отменён')]
    case Canceled = 'canceled';

    /**
     * Выборка кейсов по доменному атрибуту через reflection.
     *
     * @return self[]
     */
    public static function allForStage(OrderStage $stage): array
    {
        $reflection = new ReflectionEnum(self::class);
        $statuses = [];

        foreach ($reflection->getCases() as $case) {
            $attributes = $case->getAttributes(Stage::class);

            if ($attributes !== [] && $attributes[0]->newInstance()->stage === $stage) {
                $statuses[] = $case->getValue();
            }
        }

        return $statuses;
    }
}

// --- Использование ---
//
// OrderStatus::InProgress->getLabel();        // 'В работе'
// OrderStatus::InProgress->getColor();        // '#F9AA4B'
// OrderStatus::Canceled->getColor();          // '#6c757d' (дефолт из трейта)
// OrderStatus::allForStage(OrderStage::Processing); // [Registered, InProgress]
