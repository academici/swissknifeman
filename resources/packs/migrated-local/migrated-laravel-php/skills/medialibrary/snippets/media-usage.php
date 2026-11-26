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
        // IMPORTANT: the chain must end toMediaCollection(),
        // otherwise the file will NOT be saved.
        $document->addMediaFromRequest('cover')
            ->toMediaCollection('cover');

        // With options FileAdder (everything is chained until toMediaCollection):
        $document->addMedia($request->file('image'))
            ->usingFileName('cover-'.$document->id.'.jpg')
            ->withCustomProperties(['alt' => $request->string('alt')->toString()])
            ->preservingOriginal() // copy, not move the source
            ->toMediaCollection('images');

        // Multiple files from one request field:
        $document->addMultipleMediaFromRequest(['images'])
            ->each(fn ($fileAdder) => $fileAdder->toMediaCollection('images'));

        return back();
    }

    public function show(Document $document): array
    {
        return [
            // Original and conversion. The conversion name should be
            // registered in registerMediaConversions(), otherwise empty URL.
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

        // Or clear the entire collection:
        // $document->clearMediaCollection('images');

        return back();
    }
}
