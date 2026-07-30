---
name: botkit
bucket: botkit
version: 0.2.0
description: "Use when building bot framework features: BotDefinition contract, package service provider, webhook handling."
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

<!-- ru-source-sha256: 553d8a600c74f2c1f1d5775e73c71050b1ef0a60ee686001044bd217f16d9335 -->
