<?php

// Source: anonymized production project

declare(strict_types=1);

namespace App\Filament\Pages\Settings;

use App\Settings\Order\OrderSettings;
use Filament\Forms\Components\Select;
use Filament\Forms\Components\TextInput;
use Filament\Forms\Components\Toggle;
use Filament\Pages\SettingsPage;
use Filament\Schemas\Components\Section;
use Filament\Schemas\Components\Utilities\Get;
use Filament\Schemas\Schema;
use Override;

/**
 * Binding a settings class to Filament-form.
 *
 * Requires plugin filament/spatie-laravel-settings-plugin.
 *
 * Key:
 * - extends SettingsPage;
 * - $settings = OrderSettings::class — associates a page with a class;
 * - name(...) EACH field == name public-class properties
 *   (the package itself reads the values when opening and saves it to the group when submit);
 * - validation and conditionals required() — in the margin; There is no need to save anything manually.
 *
 * For NOT-Filament forms: when saving, assign properties to the resolved object
 * and call $settings->save() yourself.
 */
final class ManageOrderSettings extends SettingsPage
{
    protected static string $settings = OrderSettings::class;

    protected static ?string $title = 'Order settings';

    protected static ?string $navigationLabel = 'Orders';

    #[Override]
    public function form(Schema $schema): Schema
    {
        return $schema
            ->schema([
                Section::make()
                    ->columnSpanFull()
                    ->description(description: 'When the flag is disabled, defaults are applied.')
                    ->columns(columns: 2)
                    ->schema([
                        Toggle::make(name: 'enabled')
                            ->label(label: 'Enable runtime override')
                            ->columnSpanFull(),

                        TextInput::make(name: 'max_items_per_order')
                            ->label(label: 'Max. items in the order')
                            ->integer()
                            ->minValue(value: 1)
                            // required only when the flag is enabled - the condition reads the field value enabled:
                            ->required(fn (Get $get): bool => (bool) $get(path: 'enabled')),

                        TextInput::make(name: 'default_discount_rate')
                            ->label(label: 'Default discount')
                            ->numeric()
                            ->minValue(value: 0)
                            ->maxValue(value: 1),

                        TextInput::make(name: 'support_email')
                            ->label(label: 'Email support')
                            ->email()
                            ->maxLength(length: 255),

                        Select::make(name: 'allowed_currencies')
                            ->label(label: 'Allowed currencies')
                            ->multiple()
                            ->options(options: [
                                'USD' => 'USD',
                                'EUR' => 'EUR',
                                'GBP' => 'GBP',
                            ]),
                    ]),
            ]);
    }
}
