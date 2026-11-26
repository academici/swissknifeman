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
 * Model with media: MANDATORY implements HasMedia + use InteractsWithMedia.
 * One trait without an interface is not enough (type-hints package waiting HasMedia).
 */
class Document extends Model implements HasMedia
{
    use InteractsWithMedia;

    public function registerMediaCollections(): void
    {
        // Single file: A new download replaces the previous one.
        $this->addMediaCollection('cover')
            ->singleFile()
            ->useFallbackUrl('/images/default-cover.jpg');

        // Restricted gallery MIME.
        $this->addMediaCollection('images')
            ->acceptsMimeTypes(['image/jpeg', 'image/png', 'image/webp']);

        // Attachments on a separate disk.
        // Disk - from config, NOT env(): env() is empty when the config is cached.
        $this->addMediaCollection('attachments')
            ->useDisk(config('media-library.disk_name', 'public'));
    }

    /**
     * Signature strictly ?Media $media = null — package calls method
     * both with and without an instance.
     */
    public function registerMediaConversions(?Media $media = null): void
    {
        // nonQueued: preview is needed immediately after loading, without queue worker.
        $this->addMediaConversion('thumb')
            ->fit(Fit::Contain, 300, 300)
            ->nonQueued();

        // Difficult conversion - queued (queued default).
        $this->addMediaConversion('preview')
            ->fit(Fit::Crop, 800, 600)
            ->performOnCollections('images', 'cover');

        // Conditional conversion based on the properties of a specific file.
        if ($media?->mime_type === 'application/pdf') {
            $this->addMediaConversion('pdf-preview')
                ->pdfPageNumber(1)
                ->fit(Fit::Contain, 400, 400);
        }
    }
}
