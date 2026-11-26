<?php
// Source: anonymized production project

declare(strict_types=1);

/*
 * Bundle: custom #[Label]/#[Priority] (domain) + #[TypeScript] (export to front).
 * One enum also carries human-readable metadata for the back (via concern-resolver),
 * and the type contract for TS (via spatie/laravel-typescript-transformer).
 *
 * Three parts in one file for clarity - in the project these are three files:
 *   app/Attributes/Common/Label.php
 *   app/Concerns/Enums/HasLabelAttribute.php
 *   app/Enums/User/UserRole.php
 */

namespace App\Attributes\Common;

use Attribute;

// 1) Domain metadata attribute. target = TARGET_CLASS_CONSTANT (covers enum-cases).
#[Attribute(Attribute::TARGET_CLASS_CONSTANT)]
final readonly class Label
{
    public function __construct(
        public string $value,
    ) {}
}

namespace App\Concerns\Enums;

use App\Attributes\Common\Label;
use App\Support\Enums\EnumCaseAttributeResolver;

// 2) Concern resolves the attribute for each case via reflection-resolver.
//    Resolver: ReflectionEnum->getCase($this->name)->getAttributes(Label::class)->newInstance().
//    See snippets/concern-trait.php — there himself EnumCaseAttributeResolver.
/** @property-read string $name */
trait HasLabelAttribute
{
    public function getLabel(): string
    {
        $attribute = EnumCaseAttributeResolver::forCase($this, Label::class);

        if ($attribute instanceof Label) {
            return $attribute->value;
        }

        return '';
    }
}

namespace App\Enums\User;

use App\Attributes\Common\Label;
use App\Attributes\User\Role\Priority;
use App\Concerns\Enums\HasLabelAttribute;
use EmreYarligan\EnumConcern\EnumConcern;
use Filament\Support\Contracts\HasLabel;
use Spatie\TypeScriptTransformer\Attributes\TypeScript;

// 3) Enum with attribute stack:
//    #[TypeScript] on the class -> DefaultCollector will pick it up and export the type to .d.ts;
//    #[Label]/#[Priority] on cases -> domain metadata, readable concern-ami on back;
//    implements HasLabel + getLabel() from trait -> compatible with Filament-selects.
//
// No conflict: #[TypeScript] and custom attributes live at different levels
// (class vs constant) and are processed by different mechanisms.
#[TypeScript]
enum UserRole: string implements HasLabel
{
    use EnumConcern;          // collection operations: ::values(), ::all()
    use HasLabelAttribute;    // getLabel() from #[Label]

    #[Label('Administrator')]
    case Admin = 'admin';

    #[Label('Secretary')]
    #[Priority(forOrder: 1)]
    case Secretary = 'secretary';

    #[Label('Recorder')]
    #[Priority(forOrder: 2)]
    case Registrar = 'registrar';

    #[Label('Approver')]
    #[Priority(forOrder: 3)]
    case Approving = 'approving';

    /** System role, not application worker role. Bears the mark, but does not participate in the samples. */
    #[Label('Super Administrator')]
    case SuperAdmin = 'super_admin';
}

/*
 * Export config: config/typescript-transformer.php
 * --------------------------------------------------
 * return [
 *     'auto_discover_types' => [app_path()],
 *     'collectors' => [
 *         // DefaultCollector searches for classes with #[TypeScript] (and @typescript) and gives them to the Transformers.
 *         Spatie\TypeScriptTransformer\Collectors\DefaultCollector::class,
 *     ],
 *     'transformers' => [
 *         Spatie\TypeScriptTransformer\Transformers\EnumTransformer::class,
 *         // ...DtoTransformer etc.
 *     ],
 *     'output_file' => resource_path('types/generated.d.ts'),
 *     'transform_to_native_enums' => false, // enum -> union-type (and not native TS enum)
 * ];
 *
 * Generation command:  php artisan typescript:transform
 *
 * Result in resources/types/generated.d.ts:
 *   declare namespace App.Enums.User {
 *       export type UserRole = 'admin' | 'secretary' | 'registrar' | 'approving' | 'super_admin';
 *   }
 *
 * Front consumes App.Enums.* like union-types - frontend-sync side
 * (see related skill frontend/backend-type-sync).
 *
 * Important: #[TypeScript] exports ONLY backing-case values.
 * Tags from #[Label] do NOT go to the front - if needed label's in UI,
 * give them as a separate map (DTO/resource) or your writer-ohm.
 */
