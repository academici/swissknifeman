> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: namespace-refactor-safety
bucket: php
version: 0.1.0
description: "Дисциплина крупных namespace/move-рефакторингов в PHP/Laravel: три фазы — alias → обновление use-стейтментов → hard-rename; ловушка префиксных коллизий find-replace (якорься на FQN, не на голый токен); контракт на границе — phpstan ловит дрейф имплементера; arch-тесты на паритет слоёв; breaking move = мажор. Активировать: namespace refactor, move class, rename namespace, domain restructure, mass rename, breaking change, arch test."
risk: write
persona: oss-dev
tags: ["php", "refactor", "namespace", "safety"]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Namespace / Move Refactor Safety

Крупные переносы namespace ломаются молча. Делай поэтапно.

## Три фазы (не схлопывать)

1. **Alias.** Добавь `class_alias` / реэкспорт по старому FQN, чтобы ничего не сломалось во время переноса.
2. **Обнови `use`-стейтменты** по всем call-site (механический, ревьюабельный дифф).
3. **Hard-rename / убрать alias**, когда все ссылки указывают на новый FQN.

## Ловушки

- **Префиксные коллизии find-replace.** `Channel` — подстрока `ChannelMember`; `Message` — `MessageNotFound`.
  Слепой `sed s/Message/Chat\Message/` искорёжит `MessageNotFound`. Якорись на FQN / строку `use`, не на голый токен.
- **Контракт как граница.** Объяви/держи интерфейс на границе — `phpstan` тогда ловит каждый дрейфующий
  имплементер (типизированный seam лучше grep).
- **Arch-тесты на паритет.** Pest/PHPUnit arch-тест «namespace зеркалит каталог / слой X зависит только от Y»
  ловит недоделанный перенос.

## Версионирование

- Перенос ПУБЛИЧНОГО FQN класса — breaking change → мажор + миграционная заметка (или держать alias один minor
  как deprecation).

## Связанные

- `php:laravel-structure`, `php:static-analysis` (phpstan-seam).
