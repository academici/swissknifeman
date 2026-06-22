<?php

// Source: botkit/core (anonymized)

declare(strict_types=1);

namespace App\Http\Controllers;

use App\Bots\BotDefinitionRegistry;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

final class BotWebhookController
{
    public function __construct(
        private BotDefinitionRegistry $registry,
    ) {}

    public function __invoke(Request $request, string $botType): JsonResponse
    {
        if (! $this->verifySignature($request)) {
            return response()->json(['error' => 'Invalid signature'], 401);
        }

        $definition = $this->registry->get($botType);
        $payload = $request->all();

        // Dispatch to bot handler
        return response()->json(['status' => 'ok', 'bot' => $definition->name()]);
    }

    private function verifySignature(Request $request): bool
    {
        $secret = config('bots.webhook_secret');
        $signature = $request->header('X-Webhook-Signature', '');
        $expected = hash_hmac('sha256', $request->getContent(), (string) $secret);

        return hash_equals($expected, $signature);
    }
}
