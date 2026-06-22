<?php

// Source: anonymized production Laravel project
// Создание Data из запроса с валидацией и отдача в API/Inertia.
// Контроллер тонкий: from(request) -> сервис -> Data наружу.

declare(strict_types=1);

namespace App\Http\Controllers;

use App\Data\OrderData;
use App\Services\OrderService;
use Illuminate\Http\Request;
use Illuminate\Http\JsonResponse;
use Inertia\Inertia;
use Inertia\Response as InertiaResponse;

class OrderController extends Controller
{
    public function __construct(
        private readonly OrderService $orders,
    ) {}

    // POST /orders
    public function store(Request $request): JsonResponse
    {
        // from() сам собирает правила валидации из типов и #[Validation]-атрибутов
        // свойств OrderData, валидирует вход и бросает ValidationException при ошибке.
        // Никакого дублирующего $request->validate() и ручной сборки массива.
        $data = OrderData::from($request);

        // Сервис принимает и возвращает Data — бизнес-логика живёт там, не в Data и не в контроллере.
        $order = $this->orders->create($data);

        // Возврат Data: Laravel сериализует через toArray()/toResponse().
        // Ключи — по правилам маппинга класса (snake_case), включая computed-поля.
        return $order->toResponse($request)->setStatusCode(201);
    }

    // GET /orders/{id} — отдача в Inertia
    public function show(Request $request, int $id): InertiaResponse
    {
        $order = $this->orders->find($id); // -> OrderData

        // Фронт получает ровно ту форму, что описана в OrderData (и в App.Data.OrderData на TS).
        return Inertia::render('Order/Show', [
            'order' => $order,
        ]);
    }

    // Пример явного toArray() (например для логов/очереди) — выход по правилам трансформеров.
    public function snapshot(int $id): array
    {
        return $this->orders->find($id)->toArray();
    }
}

// --- Источники для from() взаимозаменяемы ---
// OrderData::from($request);            // HTTP-запрос (с валидацией)
// OrderData::from($orderModel);         // Eloquent-модель
// OrderData::from(['reference' => ...]) // массив
// OrderData::from($anotherOrderData);   // другой Data
