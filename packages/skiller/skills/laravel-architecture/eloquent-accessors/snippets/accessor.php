<?php

declare(strict_types=1);

// Source: {project}/app/Models/* (anonymized)
// Standards of modern Eloquent accessors/mutators via Attribute::make().

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

    // ── Attributes (after relations, before scopes) ────────────

    /** Only getter, arrow function - for simple calculations. */
    protected function fullName(): Attribute
    {
        return Attribute::make(
            get: fn ($value, $attributes): string => trim("{$this->first_name} {$this->last_name}"),
        );
    }

    /** Getter + setter: normalization email when writing and reading. */
    protected function email(): Attribute
    {
        return Attribute::make(
            get: fn (?string $value): ?string => $value === null ? null : mb_strtolower($value),
            set: fn (?string $value): ?string => $value === null ? null : mb_strtolower(trim($value)),
        );
    }

    /** Multi-line accessor: assembly of multiple attributes. */
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
 * ── Migration legacy-accessor ──────────────────────────────
 *
 * ❌ Was (legacy):
 *     public function getFullNameAttribute(): string
 *     {
 *         return $this->first_name . ' ' . $this->last_name;
 *     }
 *
 * ✅ Became (modern):
 *     protected function fullName(): Attribute
 *     {
 *         return Attribute::make(
 *             get: fn () => $this->first_name . ' ' . $this->last_name,
 *         );
 *     }
 *
 * Steps: delete getXxxAttribute(); add protected xxx(): Attribute;
 * add use ...Casts\Attribute; run an equivalence test.
 */
