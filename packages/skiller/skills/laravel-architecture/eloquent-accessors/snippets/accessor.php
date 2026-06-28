<?php

declare(strict_types=1);

// Source: {project}/app/Models/* (anonymized)
// Эталоны современных Eloquent accessors/mutators через Attribute::make().

namespace App\Models;

use Illuminate\Database\Eloquent\Casts\Attribute;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;

final class User extends Model
{
    protected $fillable = ['first_name', 'last_name', 'middle_name', 'email'];

    // ── Relations ─────────────────────────────────────────────
    public function posts(): HasMany
    {
        return $this->hasMany(related: Post::class);
    }

    // ── Attributes (после relations, перед scopes) ────────────

    /** Только getter, стрелочная функция — для простого вычисления. */
    protected function fullName(): Attribute
    {
        return Attribute::make(
            get: fn ($value, $attributes): string => trim("{$this->first_name} {$this->last_name}"),
        );
    }

    /** Getter + setter: нормализация email при записи и чтении. */
    protected function email(): Attribute
    {
        return Attribute::make(
            get: fn (?string $value): ?string => $value === null ? null : mb_strtolower($value),
            set: fn (?string $value): ?string => $value === null ? null : mb_strtolower(trim($value)),
        );
    }

    /** Многострочный аксессор: сборка из нескольких атрибутов. */
    protected function fullAddress(): Attribute
    {
        return Attribute::make(
            get: function ($value, array $attributes): string {
                $parts = [
                    $attributes['postal_code'] ?? null,
                    $attributes['city'] ?? null,
                    $attributes['street'] ?? null,
                ];

                return implode(', ', array_filter($parts));
            },
        );
    }

    // ── Scopes ────────────────────────────────────────────────
    // public function scopeActive($query) { ... }
}

/*
 * ── Миграция legacy-аксессора ──────────────────────────────
 *
 * ❌ Было (legacy):
 *     public function getFullNameAttribute(): string
 *     {
 *         return $this->first_name . ' ' . $this->last_name;
 *     }
 *
 * ✅ Стало (modern):
 *     protected function fullName(): Attribute
 *     {
 *         return Attribute::make(
 *             get: fn () => $this->first_name . ' ' . $this->last_name,
 *         );
 *     }
 *
 * Шаги: удалить getXxxAttribute(); добавить protected xxx(): Attribute;
 * добавить use ...Casts\Attribute; прогнать тест на эквивалентность.
 */
