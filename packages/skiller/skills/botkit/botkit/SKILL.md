---
name: botkit
bucket: botkit
version: 0.2.0
description: "Bot framework patterns: BotDefinition contract, package service provider, webhook handling"
risk: write
persona: oss-dev
tags: [php, laravel, bots, botkit]
requires: [laravel]
produces_for: []
outputs: []
snippets:
  - bot-definition.php
  - bot-service-provider.php
  - webhook-controller.php
adapters: [claude, cursor, fable]
sha256: ""
---

Laravel Botkit bot-package patterns: bot definition, ServiceProvider registration, webhook intake.

Steps:
1. Implement `BotDefinition` with unique slug.
2. Extend `AbstractBotPackageServiceProvider` in the package.
3. Add webhook route with signature verification.
4. Register bot in `BotDefinitionRegistry`.

Quality checklist:
- slug unique, lowercase-hyphenated.
- capabilities declared explicitly.
- webhook validates provider signature.

Refs:
- `php/laravel` — architectural patterns (actions, resources) bot logic builds on.
- `php-packages/laravel-packages` — package scaffold, ServiceProvider, resource publishing.
- `php/laravel-structure` — placement of bot classes in the project tree.

<!-- ru-source-sha256: 44c4e0db7dc7edd8875869556a134e6a7e0536b8bb413af88ad6fd4c03f31126 -->
