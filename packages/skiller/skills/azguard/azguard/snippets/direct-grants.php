<?php

// Source: azguard package docs (package: azguard/azguard)

declare(strict_types=1);

namespace App\Models;

use AzGuard\Concerns\HasAzGuard;
use AzGuard\Concerns\HasDirectGrants;
use Illuminate\Foundation\Auth\User as Authenticatable;

/**
 * Direct Grants — EXCEPTION mechanism, not the main pattern.
 * Default: rights → roles → users. Direct grant - when alone
 * user needs temporary/one-time right, not suitable for the role.
 * Grant the same thing 5+ users - it's time to create a role.
 *
 * HasDirectGrants expands hasPermission(): are now checked
 * roles AND direct grants - no other code changes needed.
 */
class User extends Authenticatable
{
    use HasAzGuard;
    use HasDirectGrants;
}

// ── Issue (fluent API) ─────────────────────────────────────────────────────
//
// use AzGuard\Facades\AzGuard;
// use App\AzGuard\App\Permissions\DocumentsPermission;
//
// // Indefinitely
// AzGuard::forUser($user)
//     ->on('app')
//     ->give(DocumentsPermission::Export);
//
// // C TTL 1 hour
// AzGuard::forUser($user)
//     ->on('app')
//     ->ttl(3600)
//     ->give(DocumentsPermission::Export);
//
// // Shortcut
// AzGuard::grantDirect($user, DocumentsPermission::Export, 'app', ttl: 3600);
//
// give() idempotent: calling again updates expires_at without duplicates.
//
// ── Review ───────────────────────────────────────────────────────────────────
//
// AzGuard::forUser($user)->on('app')->revoke(DocumentsPermission::Export);
// AzGuard::revokeDirect($user, DocumentsPermission::Export, 'app');
// AzGuard::forUser($user)->on('app')->revokeAll();   // all panel grants
//
// ── Verification / list ───────────────────────────────────────────────────────
//
// $user->hasDirectGrant(DocumentsPermission::Export, 'app');     // bool
// Gate::allows('direct-grant', [DocumentsPermission::Export, 'app']);
// $grants = AzGuard::activeGrants($user, 'app');                 // Collection
//
// ── Route middleware (line is inevitable) ─────────────────────────────────────
//
// Route::get('/export', ExportController::class)
//     ->middleware('az.grant:' . DocumentsPermission::Export->value . ',app');
// // 401 — not authenticated; 403 - the grant is not available or has expired.
//
// ── TTL and cleaning ───────────────────────────────────────────────────────────
//
// Grant with expires_at < now() is inactive in all checks.
// Cleaning up expired records - in scheduler (bootstrap/app.php):
//
// ->withSchedule(function (Schedule $schedule) {
//     $schedule->command('az-guard:prune-grants')->daily();
// })
//
// ── Events ─────────────────────────────────────────────────────────────────
//
// GrantGiven   — after each give()
// GrantRevoked — after each revoke() / revokeAll()
//
// Event::listen(GrantGiven::class, fn (GrantGiven $e) =>
//     Log::info("Grant [{$e->permissionKey}] issued to user #{$e->user->getAuthIdentifier()}"));
