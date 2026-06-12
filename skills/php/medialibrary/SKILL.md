---
name: medialibrary
bucket: php
version: 0.1.0
description: "spatie/laravel-medialibrary: привязка файлов к Eloquent-моделям, коллекции, конверсии, получение URL"
risk: write
persona: oss-dev
tags: ["php", "laravel", "media", "spatie", "uploads", "images"]
requires: []
produces_for: []
outputs: []
snippets:
  - model-media.php
  - media-usage.php
adapters: [claude, cursor, fable]
sha256: ""
---

## Контекст

`spatie/laravel-medialibrary` — привязка файлов к Eloquent-моделям: коллекции, конверсии изображений (через spatie/image), responsive images, разные диски. Скилл активируется при работе с загрузкой файлов, аватарами, превью, `HasMedia`/`InteractsWithMedia`.

## Алгоритм

1. **Установка**: `composer require spatie/laravel-medialibrary`, затем обязательно опубликовать миграции:
   `php artisan vendor:publish --provider="Spatie\MediaLibrary\MediaLibraryServiceProvider" --tag="medialibrary-migrations"` и `php artisan migrate`.
2. **Модель**: `implements HasMedia` + `use InteractsWithMedia` — интерфейс и трейт всегда вместе.
3. **Коллекции** в `registerMediaCollections()`: `addMediaCollection('avatar')->singleFile()`, `->useDisk('s3')`, `->acceptsMimeTypes([...])`, `->useFallbackUrl(...)`.
4. **Конверсии** в `registerMediaConversions(?Media $media = null)`: `addMediaConversion('thumb')->fit(Fit::Contain, 300, 300)->nonQueued()`. Fit — enum `Spatie\Image\Enums\Fit`.
5. **Добавление**: `$model->addMedia($file)->toMediaCollection('images')` — без завершающего `toMediaCollection()` файл НЕ сохранится. Варианты: `addMediaFromRequest()`, `addMediaFromUrl()`, `addMediaFromDisk()`.
6. **Получение**: `getFirstMediaUrl('collection')`, `getFirstMediaUrl('collection', 'conversion')`, `getMedia()`, `hasMedia()`.
7. Детали (FileAdder-опции, custom properties, responsive images, события, кастомные PathGenerator/FileNamer) — в `references/medialibrary-guide.md`.

## Когда какой сниппет открывать

| Ситуация | Файл |
|---|---|
| Настраиваю модель: коллекции + конверсии | `snippets/model-media.php` |
| Добавляю/получаю/удаляю медиа в контроллере или ресурсе | `snippets/media-usage.php` |
| Нужны редкие фичи: responsive, custom properties, события, конфиг | `references/medialibrary-guide.md` |

## Do / Don't

**Do:**
- Всегда `implements HasMedia` вместе с `use InteractsWithMedia`.
- Сигнатура конверсий строго `registerMediaConversions(?Media $media = null)`.
- `->nonQueued()` для конверсий, которые нужны сразу (по умолчанию они уходят в очередь).
- `->singleFile()` для коллекций с одним файлом (аватар) — новая загрузка заменяет старую.

**Don't:**
- Не забывать `vendor:publish` миграций перед `migrate` — без таблицы `media` ничего не работает.
- Не использовать `env()` для диска — только `config()` или `config/media-library.php` (env() пустой при закешированном конфиге).
- Не вызывать `addMedia()` без `toMediaCollection()` — медиа не сохранится.
- Не ссылаться на конверсии, которые не зарегистрированы в `registerMediaConversions()` — получите пустой URL.

## Чеклист качества

- [ ] Миграции опубликованы и применены, таблица `media` существует
- [ ] Модель: интерфейс + трейт, конверсии с `?Media $media = null`
- [ ] Каждая цепочка `addMedia()` завершается `toMediaCollection()`
- [ ] Диск задан через config, очередь учтена (`nonQueued()` или работающий worker)
- [ ] В API-ресурсах URL берутся через `getFirstMediaUrl()`, не руками из путей

## Ссылки

- `references/medialibrary-guide.md` — полный справочник по API пакета
- https://spatie.be/docs/laravel-medialibrary
