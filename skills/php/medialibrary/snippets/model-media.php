<?php

// Source: anonymized production Laravel project

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Spatie\Image\Enums\Fit;
use Spatie\MediaLibrary\HasMedia;
use Spatie\MediaLibrary\InteractsWithMedia;
use Spatie\MediaLibrary\MediaCollections\Models\Media;

/**
 * Модель с медиа: ОБЯЗАТЕЛЬНО implements HasMedia + use InteractsWithMedia.
 * Одного трейта без интерфейса недостаточно (type-hints пакета ждут HasMedia).
 */
class Document extends Model implements HasMedia
{
    use InteractsWithMedia;

    public function registerMediaCollections(): void
    {
        // Одиночный файл: новая загрузка заменяет предыдущую.
        $this->addMediaCollection('cover')
            ->singleFile()
            ->useFallbackUrl('/images/default-cover.jpg');

        // Галерея с ограничением по MIME.
        $this->addMediaCollection('images')
            ->acceptsMimeTypes(['image/jpeg', 'image/png', 'image/webp']);

        // Вложения на отдельном диске.
        // Диск — из config, НЕ env(): env() пуст при закешированном конфиге.
        $this->addMediaCollection('attachments')
            ->useDisk(config('media-library.disk_name', 'public'));
    }

    /**
     * Сигнатура строго ?Media $media = null — пакет вызывает метод
     * и с экземпляром, и без него.
     */
    public function registerMediaConversions(?Media $media = null): void
    {
        // nonQueued: превью нужно сразу после загрузки, без queue worker.
        $this->addMediaConversion('thumb')
            ->fit(Fit::Contain, 300, 300)
            ->nonQueued();

        // Тяжёлая конверсия — в очередь (queued по умолчанию).
        $this->addMediaConversion('preview')
            ->fit(Fit::Crop, 800, 600)
            ->performOnCollections('images', 'cover');

        // Условная конверсия по свойствам конкретного файла.
        if ($media?->mime_type === 'application/pdf') {
            $this->addMediaConversion('pdf-preview')
                ->pdfPageNumber(1)
                ->fit(Fit::Contain, 400, 400);
        }
    }
}
