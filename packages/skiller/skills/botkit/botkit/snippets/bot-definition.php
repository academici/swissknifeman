<?php

// Source: botkit/core (anonymized)

declare(strict_types=1);

namespace App\Bots;

use App\Bots\Contracts\BotDefinition;

final class AssistantBotDefinition implements BotDefinition
{
    public function name(): string
    {
        return 'assistant';
    }

    public function label(): string
    {
        return 'AI Assistant';
    }

    public function description(): string
    {
        return 'General-purpose conversational bot.';
    }

    public function capabilities(): array
    {
        return ['chat', 'tools'];
    }

    public function syncDefaults(): array
    {
        return [
            'instructions' => 'You are a helpful assistant.',
            'tools' => [],
        ];
    }

    public function defaultPrompt(): ?string
    {
        return 'You are a helpful assistant.';
    }
}
