<?php

// Source: azguard package docs (package: azguard/azguard)

declare(strict_types=1);

use App\AzGuard\App\Permissions\DocumentsPermission;
use App\Models\Document;
use App\Models\User;
use AzGuard\Grants\GrantBuilder;
use Illuminate\Support\Facades\Gate;

/**
 * Pest-patterns for AzGuard. Roles - PHP-classes: available without seeding.
 * Rules:
 *   - test both sides: for each «allowed» — test «prohibited»;
 *   - between state changes in one test - $user->flushPermissions();
 *   - assertForbidden(), not assertStatus(403);
 *   - in the test config az-guard.php: 'cache' => ['enabled' => false].
 */

// ── Roles and rights ────────────────────────────────────────────────────────────

it('allows editors to view documents', function () {
    $user = User::factory()->create();
    $user->assignRole('editor');

    expect($user->hasPermission(DocumentsPermission::View))->toBeTrue();
    expect($user->hasPermission(DocumentsPermission::Delete))->toBeFalse();
});

it('checks any/all permission sets', function () {
    $user = User::factory()->create();
    $user->assignRole('editor');

    expect($user->hasAnyPermission([
        DocumentsPermission::Edit,
        DocumentsPermission::Delete,
    ]))->toBeTrue();

    expect($user->hasAllPermissions([
        DocumentsPermission::Edit,
        DocumentsPermission::Delete,   // y editor no Delete
    ]))->toBeFalse();
});

// ── HTTP: 403 for a user without permission ────────────────────────────────────

it('returns 403 for users without permission', function () {
    $user = User::factory()->create();

    $this->actingAs($user)
        ->get(route('documents.index'))
        ->assertForbidden();
});

it('allows editor through the route', function () {
    $this->actingAs(User::factory()->editor()->create())
        ->get(route('documents.index'))
        ->assertOk();
});

// ── Gate with model (via policy) ─────────────────────────────────────────

it('routes gate checks through the policy', function () {
    $user = User::factory()->create();
    $document = Document::factory()->create(['owner_id' => $user->id]);
    $user->assignRole('editor');

    $this->actingAs($user);

    expect(Gate::allows(DocumentsPermission::Edit, $document))->toBeTrue();
    expect(Gate::allows(DocumentsPermission::Delete, $document))->toBeFalse();
});

// ── Direct grants ───────────────────────────────────────────────────────────

it('grants direct permission to a user', function () {
    $user = User::factory()->create();

    (new GrantBuilder($user))
        ->on('app')
        ->give(DocumentsPermission::Export);

    expect($user->hasPermission(DocumentsPermission::Export))->toBeTrue();
});

it('denies an expired grant', function () {
    $user = User::factory()->create();

    (new GrantBuilder($user))
        ->on('app')
        ->give(DocumentsPermission::Export)
        ->until(now()->subMinute());   // has already expired

    $user->flushPermissions();          // reset in-memory cache

    expect($user->hasPermission(DocumentsPermission::Export))->toBeFalse();
});

// ── Factory states — readable user training ──────────────────────
//
// // database/factories/UserFactory.php
// public function editor(): static
// {
//     return $this->afterCreating(fn (User $user) =>
//         $user->assignRole('editor', panel: 'app')
//     );
// }
//
// $editor = User::factory()->editor()->create();
//
// ── Unit-tests without database - AzGuardFake ─────────────────────────────────────────
//
// use AzGuard\Testing\AzGuardFake;
//
// beforeEach(fn () => AzGuardFake::install());   // in-memory resolver
//
// it('checks permission in a service', function () {
//     $user = User::factory()->make(['id' => 1]);
//     AzGuardFake::grantPermission($user, DocumentsPermission::View);
//     AzGuardFake::grantRole($user, 'editor');
//
//     expect(app(DocumentService::class)->canView($user, $document))->toBeTrue();
// });
