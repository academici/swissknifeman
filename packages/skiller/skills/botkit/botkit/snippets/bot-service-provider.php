<?php

// Source: botkit/core (anonymized)

declare(strict_types=1);

namespace App\Bots;

use App\Bots\Support\AbstractBotPackageServiceProvider;

final class BotAssistantServiceProvider extends AbstractBotPackageServiceProvider
{
    protected function definitionClass(): string
    {
        return AssistantBotDefinition::class;
    }

    protected function migrationPath(): ?string
    {
        return __DIR__.'/../database/migrations';
    }
}
