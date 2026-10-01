<?php

// Source: anonymized production project

declare(strict_types=1);

use Spatie\LaravelSettings\Migrations\SettingsMigration;

/**
 * Settings-migration: Sets default values for a settings class.
 *
 * Location: database/settings/ (path from config/settings.php → migrations_paths).
 * Generation: php artisan make:settings-migration CreateOrderSettings
 * Launch:    php artisan migrate (settings-migrations are run along with regular ones).
 *
 * IMPORTANT: every public-class property MUST have a corresponding add(),
 * otherwise it will crash on the first reading Spatie\LaravelSettings\Exceptions\MissingSettings.
 * Key = "group.property" (exactly like group() + property name).
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

        // Sensitive values - encrypted storage, not open add():
        // $this->migrator->addEncrypted(property: 'order.api_token', value: null);
    }
};

/*
 * SCHEME EVOLUTION - separate migration (synchronously with editing class properties):
 *
 * return new class extends SettingsMigration
 * {
 *     public function up(): void
 *     {
 *         // new property (after adding it to the class):
 *         $this->migrator->add(property: 'order.auto_archive_days', value: 30);
 *
 *         // renaming (and rename the property in the class with the same commit):
 *         $this->migrator->rename(from: 'order.support_email', to: 'order.contact_email');
 *
 *         // deletion (remove property from class):
 *         $this->migrator->delete(property: 'order.legacy_flag');
 *     }
 * };
 */
