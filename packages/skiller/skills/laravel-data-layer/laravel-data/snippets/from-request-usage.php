<?php

// Source: anonymized production Laravel project
// Creation Data from a request with validation and return to API/Inertia.
// Thin controller: from(request) -> service -> Data out.

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
        // from() itself collects validation rules from types and #[Validation]-attributes
        // properties OrderData, validates the input and throws ValidationException on error.
        // No duplicate $request->validate() and manual assembly of the array.
        $data = OrderData::from($request);

        // The service accepts and returns Data — business logic lives there, not in Data and not in the controller.
        $order = $this->orders->create($data);

        // Return Data: Laravel serializes via toArray()/toResponse().
        // Keys - according to class mapping rules (snake_case), including computed-fields.
        return $order->toResponse($request)->setStatusCode(201);
    }

    // GET /orders/{id} — return to Inertia
    public function show(Request $request, int $id): InertiaResponse
    {
        $order = $this->orders->find($id); // -> OrderData

        // The front gets exactly the shape described in OrderData (and in App.Data.OrderData on TS).
        return Inertia::render('Order/Show', [
            'order' => $order,
        ]);
    }

    // Example of explicit toArray() (for example for logs/queues) — exit according to the rules of transformers.
    public function snapshot(int $id): array
    {
        return $this->orders->find($id)->toArray();
    }
}

// --- Sources for from() are interchangeable ---
// OrderData::from($request);            // HTTP-request (with validation)
// OrderData::from($orderModel);         // Eloquent-model
// OrderData::from(['reference' => ...]) // array
// OrderData::from($anotherOrderData);   // other Data
