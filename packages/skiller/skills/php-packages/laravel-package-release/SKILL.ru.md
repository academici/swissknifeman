> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: laravel-package-release
bucket: php-packages
version: 0.3.0
description: "Use this skill when preparing Laravel package releases: generated release notes, GitHub release workflows, version checks, tags, release validation, or release automation changes. Never publish autonomously."
risk: write
persona: oss-dev
tags: ["php", "laravel", "package-dev"]
requires: []
produces_for: []
outputs: []
adapters: [claude, cursor, fable]
upstream: WendellAdriel/laravel-expressive
license: MIT
sha256: ""
---

# Релиз пакета

## Главная цель

Подготовить безопасный чеклист релиза пакета и его реализацию, не создавая тег, не делая push и не публикуя релиз, пока пользователь явно не одобрит это действие.

## Рабочий процесс

1. Просмотреть конфигурацию генерируемых заметок к релизу (release notes), GitHub-воркфлоу релиза, открытый diff и ожидающие изменения пакета.
2. Проверить состояние релиза командой `composer test` перед тем, как рекомендовать релиз.
3. Уточнить, нужно ли менять метаданные версии; многие Laravel-пакеты полагаются на Git-теги, а не на жёстко прописанную версию пакета.
4. Проверить именование тега, релизную ветку и поведение GitHub-воркфлоу релиза перед любой командой релиза.
5. Не создавать тег, не делать push и не публиковать без явного одобрения пользователя.

## Справочные файлы

- `.github/release.yml`
- `.github/workflows/tests.yml`
- `composer.json`

## Примеры

- Подготовить релиз: подтвердить категории генерируемых заметок к релизу, запустить `composer test` и составить черновик команды создания тега для одобрения пользователем.
- Обновить группировку заметок к релизу в `.github/release.yml`, когда добавлено новое соглашение об именовании меток (labels).

## Антипаттерны

- Создание тегов, push веток или публикация релизов без явного одобрения.
- Пропуск `composer test` перед рекомендацией о релизе.
- Изменение релизных воркфлоу без проверки поддерживаемой матрицы в `.github/workflows/tests.yml`.
