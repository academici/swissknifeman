<?php

// Source: anonymized production project

declare(strict_types=1);

use Spatie\LaravelSettings\Migrations\SettingsMigration;

/**
 * Settings-миграция: задаёт значения по умолчанию для класса настроек.
 *
 * Расположение: database/settings/ (путь из config/settings.php → migrations_paths).
 * Генерация: php artisan make:settings-migration CreateOrderSettings
 * Запуск:    php artisan migrate (settings-миграции прогоняются вместе с обычными).
 *
 * ВАЖНО: каждое public-свойство класса ДОЛЖНО иметь соответствующий add(),
 * иначе при первом чтении упадёт Spatie\LaravelSettings\Exceptions\MissingSettings.
 * Ключ = "group.property" (точно как group() + имя свойства).
 */
return new class extends SettingsMigration
{
    public function up(): void
    {
        $this->migrator->add(property: 'order.enabled', value: false);
        $this->migrator->add(property: 'order.max_items_per_order', value: 50);
        $this->migrator->add(property: 'order.default_discount_rate', value: 0.0);
        $this->migrator->add(property: 'order.support_email', value: null);
        $this->migrator->add(property: 'order.allowed_currencies', value: ['USD', 'EUR']);

        // Чувствительные значения — шифрованным хранилищем, а не открытым add():
        // $this->migrator->addEncrypted(property: 'order.api_token', value: null);
    }
};

/*
 * ЭВОЛЮЦИЯ СХЕМЫ — отдельной миграцией (синхронно с правкой свойств класса):
 *
 * return new class extends SettingsMigration
 * {
 *     public function up(): void
 *     {
 *         // новое свойство (после добавления его в класс):
 *         $this->migrator->add(property: 'order.auto_archive_days', value: 30);
 *
 *         // переименование (и свойство в классе переименовать тем же коммитом):
 *         $this->migrator->rename(from: 'order.support_email', to: 'order.contact_email');
 *
 *         // удаление (свойство убрать из класса):
 *         $this->migrator->delete(property: 'order.legacy_flag');
 *     }
 * };
 */
