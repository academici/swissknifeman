---
name: medialibrary
description: "Use when attaching files to Eloquent models: spatie/laravel-medialibrary collections, conversions, URLs."
---

## Scope

`spatie/laravel-medialibrary`: attach files to Eloquent models — collections, image conversions (via spatie/image), responsive images, multiple disks. Trigger on file uploads, avatars, previews, `HasMedia`/`InteractsWithMedia`.

- Laravel Boost: when Boost is connected, spatie/laravel-medialibrary guidelines come from the package; this skill is self-sufficient without Boost. Package: https://github.com/laravel/boost (skills — `vendor/laravel/boost/.ai/`).

## Steps

1. Install: `composer require spatie/laravel-medialibrary`, then publish migrations (mandatory): `php artisan vendor:publish --provider="Spatie\MediaLibrary\MediaLibraryServiceProvider" --tag="medialibrary-migrations"` and `php artisan migrate`.
2. Model: `implements HasMedia` + `use InteractsWithMedia` — interface and trait always together.
3. Collections in `registerMediaCollections()`: `addMediaCollection('avatar')->singleFile()`, `->useDisk('s3')`, `->acceptsMimeTypes([...])`, `->useFallbackUrl(...)`.
4. Conversions in `registerMediaConversions(?Media $media = null)`: `addMediaConversion('thumb')->fit(Fit::Contain, 300, 300)->nonQueued()`. Fit — enum `Spatie\Image\Enums\Fit`.
5. Add: `$model->addMedia($file)->toMediaCollection('images')` — without trailing `toMediaCollection()` the file is NOT saved. Variants: `addMediaFromRequest()`, `addMediaFromUrl()`, `addMediaFromDisk()`.
6. Get: `getFirstMediaUrl('collection')`, `getFirstMediaUrl('collection', 'conversion')`, `getMedia()`, `hasMedia()`.
7. Details (FileAdder options, custom properties, responsive images, events, custom PathGenerator/FileNamer) — in `references/medialibrary-guide.md`.

## Which snippet

| Situation | File |
|---|---|
| Configure model: collections + conversions | `snippets/model-media.php` |
| Add/get/delete media in controller or resource | `snippets/media-usage.php` |
| Rare features: responsive, custom properties, events, config | `references/medialibrary-guide.md` |

## Do

- Always `implements HasMedia` together with `use InteractsWithMedia`.
- Conversion signature strictly `registerMediaConversions(?Media $media = null)`.
- `->nonQueued()` for conversions needed immediately (default = queued).
- `->singleFile()` for single-file collections (avatar) — new upload replaces old.

## Don't

- Don't skip `vendor:publish` of migrations before `migrate` — without `media` table nothing works.
- Don't use `env()` for disk — only `config()` or `config/media-library.php` (env() is empty when config is cached).
- Don't call `addMedia()` without `toMediaCollection()` — media not saved.
- Don't reference conversions not registered in `registerMediaConversions()` — yields empty URL.

## Quality checklist

- [ ] Migrations published and applied, `media` table exists
- [ ] Model: interface + trait, conversions with `?Media $media = null`
- [ ] Every `addMedia()` chain ends with `toMediaCollection()`
- [ ] Disk set via config, queue handled (`nonQueued()` or working worker)
- [ ] In API resources URLs taken via `getFirstMediaUrl()`, not built from paths by hand

## Links

- `references/medialibrary-guide.md` — full package API reference
- https://spatie.be/docs/laravel-medialibrary
- Related skills: `frontend/filepond-upload` (frontend file upload, server-side model binding), `laravel-testing/test-isolation-guard` (isolated `media-test` disk in tests), `laravel-data-layer/laravel-data` (media URLs in DTOs/resources), `laravel-filament/filament` (media fields in admin)
