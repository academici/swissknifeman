<?php
// Source: anonymized production project

declare(strict_types=1);

/*
 * Связка: кастомные #[Label]/#[Priority] (домен) + #[TypeScript] (экспорт на фронт).
 * Один enum несёт и человекочитаемые метаданные для бэка (через concern-резолвер),
 * и контракт типа для TS (через spatie/laravel-typescript-transformer).
 *
 * Три части в одном файле для наглядности — в проекте это три файла:
 *   app/Attributes/Common/Label.php
 *   app/Concerns/Enums/HasLabelAttribute.php
 *   app/Enums/User/UserRole.php
 */

namespace App\Attributes\Common;

use Attribute;

// 1) Доменный атрибут метаданных. target = TARGET_CLASS_CONSTANT (покрывает enum-кейсы).
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

// 2) Concern резолвит атрибут на каждый case через reflection-резолвер.
//    Резолвер: ReflectionEnum->getCase($this->name)->getAttributes(Label::class)->newInstance().
//    См. snippets/concern-trait.php — там сам EnumCaseAttributeResolver.
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

// 3) Enum со стэком атрибутов:
//    #[TypeScript] на классе  -> DefaultCollector подхватит его и экспортирует тип в .d.ts;
//    #[Label]/#[Priority] на кейсах -> доменные метаданные, читаемые concern-ами на бэке;
//    implements HasLabel + getLabel() из трейта -> совместимость с Filament-селектами.
//
// Конфликта нет: #[TypeScript] и кастомные атрибуты живут на разных уровнях
// (класс vs константа) и обрабатываются разными механизмами.
#[TypeScript]
enum UserRole: string implements HasLabel
{
    use EnumConcern;          // коллекционные операции: ::values(), ::all()
    use HasLabelAttribute;    // getLabel() из #[Label]

    #[Label('Администратор')]
    case Admin = 'admin';

    #[Label('Секретарь')]
    #[Priority(forOrder: 1)]
    case Secretary = 'secretary';

    #[Label('Регистратор')]
    #[Priority(forOrder: 2)]
    case Registrar = 'registrar';

    #[Label('Утверждающий')]
    #[Priority(forOrder: 3)]
    case Approving = 'approving';

    /** Системная роль, не рабочая роль приложения. Метку несёт, но в выборках не участвует. */
    #[Label('Суперадминистратор')]
    case SuperAdmin = 'super_admin';
}

/*
 * Конфиг экспорта: config/typescript-transformer.php
 * --------------------------------------------------
 * return [
 *     'auto_discover_types' => [app_path()],
 *     'collectors' => [
 *         // DefaultCollector ищет классы с #[TypeScript] (и @typescript) и отдаёт их трансформерам.
 *         Spatie\TypeScriptTransformer\Collectors\DefaultCollector::class,
 *     ],
 *     'transformers' => [
 *         Spatie\TypeScriptTransformer\Transformers\EnumTransformer::class,
 *         // ...DtoTransformer и пр.
 *     ],
 *     'output_file' => resource_path('types/generated.d.ts'),
 *     'transform_to_native_enums' => false, // enum -> union-тип (а не native TS enum)
 * ];
 *
 * Команда генерации:  php artisan typescript:transform
 *
 * Результат в resources/types/generated.d.ts:
 *   declare namespace App.Enums.User {
 *       export type UserRole = 'admin' | 'secretary' | 'registrar' | 'approving' | 'super_admin';
 *   }
 *
 * Фронт потребляет App.Enums.* как union-типы — frontend-сторона синка
 * (см. связанный скилл frontend/backend-type-sync).
 *
 * Важно: #[TypeScript] экспортирует ТОЛЬКО backing-значения кейсов.
 * Метки из #[Label] на фронт НЕ попадают — если нужны label'ы в UI,
 * отдавайте их отдельной мапой (DTO/ресурс) либо своим writer-ом.
 */
