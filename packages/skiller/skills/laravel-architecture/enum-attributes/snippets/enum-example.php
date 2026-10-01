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
 * Enriched enum: case metadata declaratively in attributes,
 * methods getLabel()/getColor()/getDescription() — from Concern-traits.
 * EnumConcern adds collection operations (all/values/...).
 * HasLabel (Filament) is satisfied by the method getLabel() from the trait.
 */
enum OrderStatus: string implements HasLabel
{
    use EnumConcern;
    use HasColorAttribute;
    use HasDescriptionAttribute;
    use HasLabelAttribute;

    #[Stage(OrderStage::Intake)]
    #[Color('#6c757d')]
    #[Description('Draft order, registration is not completed.')]
    #[Label('Draft')]
    case Draft = 'draft';

    #[Stage(OrderStage::Processing)]
    #[Color('#3786EB')]
    #[Description('The order has been registered and submitted for processing.')]
    #[Label('Registered')]
    case Registered = 'registered';

    #[Stage(OrderStage::Processing)]
    #[Color('#F9AA4B')]
    #[Description('The order is being processed by the responsible manager.')]
    #[Label('In progress')]
    case InProgress = 'in_progress';

    #[Stage(OrderStage::Finalization)]
    #[Color('#18B797')]
    #[Description('The order has been completed and closed.')]
    #[Label('Completed')]
    case Finished = 'finished';

    // Case without Color: trait will return default '#6c757d'.
    #[Description('Service canceled status out stage-column.')]
    #[Label('Canceled')]
    case Canceled = 'canceled';

    /**
     * Selection of cases by domain attribute via reflection.
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

// --- Usage ---
//
// OrderStatus::InProgress->getLabel();        // 'In progress'
// OrderStatus::InProgress->getColor();        // '#F9AA4B'
// OrderStatus::Canceled->getColor();          // '#6c757d' (default from trait)
// OrderStatus::allForStage(OrderStage::Processing); // [Registered, InProgress]
