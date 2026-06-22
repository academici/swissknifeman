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
 * Контроллер с декларативной авторизацией через #[CheckPermission].
 *
 * Атрибуты читает middleware CheckAccess (см. CheckAccess.php). Сам
 * контроллер про авторизацию ничего не знает — никаких $this->authorize()
 * и Gate-вызовов в теле экшена.
 *
 * Чтобы это сработало, маршруты группы должны проходить через middleware
 * 'check-access' (см. регистрацию в SKILL.md).
 */
final class OrderController
{
    // Без аргументов: право без привязки к модели (например, доступ к списку).
    #[CheckPermission(Permission::ViewAnyOrder)]
    public function index(): View
    {
        return view('orders.index');
    }

    // arguments: ['order'] — параметр маршрута {order} (Model через
    // route-model binding) уйдёт в Gate::allows('order.view', [$order]).
    #[CheckPermission(Permission::ViewOrder, arguments: ['order'])]
    public function show(Order $order): View
    {
        return view('orders.show', ['order' => $order]);
    }

    // Несколько повторяющихся атрибутов — все проверки должны пройти.
    // Разный status: первая ветка → 403, вторая маскирует чужой ресурс под 404.
    #[CheckPermission(Permission::UpdateOrder, arguments: ['order'])]
    #[CheckPermission(
        Permission::AccessCompany,
        arguments: ['order'],
        status: 404,
        message: 'Order not found.',
    )]
    public function update(Order $order): RedirectResponse
    {
        // ... обновление ...

        return redirect()->route('orders.show', ['order' => $order]);
    }
}
