<?php

// Source: anonymized production Laravel project

declare(strict_types=1);

namespace App\Http\Controllers;

use App\Models\Document;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;

class DocumentMediaController extends Controller
{
    public function store(Request $request, Document $document): RedirectResponse
    {
        // ВАЖНО: цепочка обязана заканчиваться toMediaCollection(),
        // иначе файл НЕ будет сохранён.
        $document->addMediaFromRequest('cover')
            ->toMediaCollection('cover');

        // С опциями FileAdder (всё чейнится до toMediaCollection):
        $document->addMedia($request->file('image'))
            ->usingFileName('cover-'.$document->id.'.jpg')
            ->withCustomProperties(['alt' => $request->string('alt')->toString()])
            ->preservingOriginal() // копировать, а не перемещать исходник
            ->toMediaCollection('images');

        // Несколько файлов из одного поля запроса:
        $document->addMultipleMediaFromRequest(['images'])
            ->each(fn ($fileAdder) => $fileAdder->toMediaCollection('images'));

        return back();
    }

    public function show(Document $document): array
    {
        return [
            // Оригинал и конверсия. Имя конверсии должно быть
            // зарегистрировано в registerMediaConversions(), иначе пустой URL.
            'cover' => $document->getFirstMediaUrl('cover'),
            'cover_thumb' => $document->getFirstMediaUrl('cover', 'thumb'),

            'has_images' => $document->hasMedia('images'),

            'images' => $document->getMedia('images')->map(fn ($media) => [
                'id' => $media->id,
                'url' => $media->getUrl(),
                'thumb' => $media->getUrl('thumb'),
                'alt' => $media->getCustomProperty('alt'),
                'size' => $media->size,
            ]),
        ];
    }

    public function destroy(Document $document, int $mediaId): RedirectResponse
    {
        $document->deleteMedia($mediaId);

        // Или очистить коллекцию целиком:
        // $document->clearMediaCollection('images');

        return back();
    }
}
