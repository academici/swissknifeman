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
 * Привязка класса настроек к Filament-форме.
 *
 * Требует плагин filament/spatie-laravel-settings-plugin.
 *
 * Ключевое:
 * - extends SettingsPage;
 * - $settings = OrderSettings::class — связывает страницу с классом;
 * - name(...) КАЖДОГО поля == имя public-свойства класса
 *   (пакет сам читает значения при открытии и сохраняет в группу при submit);
 * - валидация и условные required() — на полях; ничего сохранять вручную не нужно.
 *
 * Для НЕ-Filament форм: на сохранении присвоить свойства резолвнутому объекту
 * и вызвать $settings->save() самостоятельно.
 */
final class ManageOrderSettings extends SettingsPage
{
    protected static string $settings = OrderSettings::class;

    protected static ?string $title = 'Настройки заказов';

    protected static ?string $navigationLabel = 'Заказы';

    #[Override]
    public function form(Schema $schema): Schema
    {
        return $schema
            ->schema([
                Section::make()
                    ->columnSpanFull()
                    ->description(description: 'При выключенном флаге применяются дефолты.')
                    ->columns(columns: 2)
                    ->schema([
                        Toggle::make(name: 'enabled')
                            ->label(label: 'Включить рантайм-переопределение')
                            ->columnSpanFull(),

                        TextInput::make(name: 'max_items_per_order')
                            ->label(label: 'Макс. позиций в заказе')
                            ->integer()
                            ->minValue(value: 1)
                            // required только когда включён флаг — условие читает значение поля enabled:
                            ->required(fn (Get $get): bool => (bool) $get(path: 'enabled')),

                        TextInput::make(name: 'default_discount_rate')
                            ->label(label: 'Скидка по умолчанию')
                            ->numeric()
                            ->minValue(value: 0)
                            ->maxValue(value: 1),

                        TextInput::make(name: 'support_email')
                            ->label(label: 'Email поддержки')
                            ->email()
                            ->maxLength(length: 255),

                        Select::make(name: 'allowed_currencies')
                            ->label(label: 'Разрешённые валюты')
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
