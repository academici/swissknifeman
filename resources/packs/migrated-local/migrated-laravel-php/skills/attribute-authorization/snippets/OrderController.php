<?php

// Source: anonymized production project

declare(strict_types=1);

namespace App\Http\Controllers;

use App\Attributes\CheckPermission;
use App\Enums\Permission;
use App\Models\Order;
use Illuminate\Http\RedirectResponse;
use Illuminate\View\View;

/**
 * Controller with declarative authorization via #[CheckPermission].
 *
 * Attributes reads middleware CheckAccess (see CheckAccess.php). Himself
 * controller does not know anything about authorization - no $this->authorize()
 * and Gate-calls in the action body.
 *
 * For this to work, the group's routes must go through middleware
 * 'check-access' (see registration in SKILL.md).
 */
final class OrderController
{
    // No arguments: right without model binding (for example, access to a list).
    #[CheckPermission(Permission::ViewAnyOrder)]
    public function index(): View
    {
        return view('orders.index');
    }

    // arguments: ['order'] — route parameter {order} (Model via
    // route-model binding) will go to Gate::allows('order.view', [$order]).
    #[CheckPermission(Permission::ViewOrder, arguments: ['order'])]
    public function show(Order $order): View
    {
        return view('orders.show', ['order' => $order]);
    }

    // Several duplicate attributes - all checks must pass.
    // Various status: first thread → 403, the second disguises someone else's resource as 404.
    #[CheckPermission(Permission::UpdateOrder, arguments: ['order'])]
    #[CheckPermission(
        Permission::AccessCompany,
        arguments: ['order'],
        status: 404,
        message: 'Order not found.',
    )]
    public function update(Order $order): RedirectResponse
    {
        // ... update...

        return redirect()->route('orders.show', ['order' => $order]);
    }
}
