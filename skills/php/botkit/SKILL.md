---
name: botkit
bucket: php
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

## Контекст

Паттерны для Laravel bot-пакетов на базе Botkit: определение бота, регистрация через ServiceProvider, приём webhook.

## Алгоритм

1. Реализуй `BotDefinition` с уникальным slug
2. Наследуй `AbstractBotPackageServiceProvider` в пакете
3. Добавь webhook route с верификацией подписи
4. Зарегистрируй бота в `BotDefinitionRegistry`

## Чеклист качества

- [ ] slug уникален и lowercase-hyphenated
- [ ] capabilities объявлены явно
- [ ] webhook валидирует подпись провайдера
