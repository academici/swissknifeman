<!-- Source: anonymized production project (binding FilePond upload refs to an Inertia form + laravel-filepond server processing) -->

# Linking uploaded files to the form and server processing

Field `FilePondField.vue` via `v-model` gives off **list of links**
`{ id?, serverId? }[]`. This list is placed in the form like a regular field and left
in payload. Server by `serverId` takes a temporary file from the store laravel-filepond
and binds to the domain model.

## 1. Frontend — put the list in Inertia-form

```vue
<script lang="ts" setup>
import { useForm } from "@inertiajs/vue3";
import FilePondField, {
  type UploadedFileRef,
  type ExistingFile,
} from "@/components/forms/FilePondField.vue";

const props = defineProps<{ existingFiles: ExistingFile[] }>();

// attachment_files — normal form field; FilePond it is controlled through v-model.
const form = useForm<{ title: string; attachment_files: UploadedFileRef[] }>({
  title: "",
  attachment_files: props.existingFiles.map((file) => ({ id: file.id })),
});

function submit() {
  // On submit and saved ones fly away { id }, and new { serverId }.
  form.post("/orders");
}
</script>

<template>
  <form @submit.prevent="submit">
    <input v-model="form.title" />

    <FilePondField
      v-model="form.attachment_files"
      name="attachment_files"
      :files="existingFiles"
      multiple
      accepted-file-types="image/*,application/pdf"
      max-file-size="10MB"
    />
    <span v-if="form.errors.attachment_files">{{ form.errors.attachment_files }}</span>

    <button :disabled="form.processing">Save</button>
  </form>
</template>
```

Key: the field component does not know about the form, the form does not know about FilePond.
Communication - only via serializable `UploadedFileRef[]`. The field does this
portable between forms and projects.

## 2. (Optional) composable: existing vs pending

If you need logic on top of the list (meters, separate sections «saved» /
«waiting to load»), take it out to composable, and not into the component:

```ts
// useFileUpload.ts
import { computed, ref } from "vue";
import type { UploadedFileRef } from "@/components/forms/FilePondField.vue";

export function useFileUpload(initial: UploadedFileRef[]) {
  const files = ref<UploadedFileRef[]>([...initial]);

  const persisted = computed(() => files.value.filter((f) => f.id != null));
  const pending = computed(() => files.value.filter((f) => f.serverId != null));

  return { files, persisted, pending };
}
```

## 3. Backend — laravel-filepond: process/revert and binding by serverId

`rahulhaque/laravel-filepond` registers one route `/filepond`,
serving all callbacks FilePond:

| FilePond callback | HTTP             | What it does                                              |
|:------------------|:-----------------|:--------------------------------------------------------|
| `process`         | `POST /filepond` | accepts a temporary file, returns `serverId`         |
| `revert`          | `DELETE /filepond` | deletes the temporary file by `serverId` (cancel download) |
| `patch`           | `PATCH /filepond`  | receiving chunks when `chunk-uploads`                       |
| `restore`/`load`  | `GET /filepond`    | returns the previously saved/temporary file for poster    |

The package controller is connected by its service provider - do not write the route manually
needed. On the application side `serverId` take the file with the facade `Filepond`:

```php
<?php

declare(strict_types=1);

namespace App\Actions\Order;

use App\Models\Order;
use RahulHaque\Filepond\Facades\Filepond;

final readonly class SyncOrderAttachments
{
    /**
     * @param array<int, array{id?: int|string, serverId?: string}> $payload
     */
    public function handle(Order $order, array $payload): void
    {
        $items = collect($payload);

        // 1. Saved files (yes id) — leave as is / synchronized.
        $keepIds = $items
            ->filter(fn (array $item): bool => isset($item['id']))
            ->pluck('id');
        // ... remove from the collection everything that is not in $keepIds (depends on media-layer)

        // 2. New temporary files (yes serverId) — take from the store FilePond
        //    and bind it to the model. After getFile() temporary file is cleared.
        $items
            ->filter(fn (array $item): bool => isset($item['serverId']))
            ->each(function (array $item) use ($order): void {
                $uploaded = Filepond::field($item['serverId']);
                $file = $uploaded->getFile();           // UploadedFile

                $order
                    ->addMedia($file)                   // spatie/media-library etc.
                    ->toMediaCollection('attachments');
            });
    }
}
```

Useful Facade Techniques (see README package): `Filepond::field($serverId)`,
then `->getFile()` (get `UploadedFile`), `->getDto()` (metadata),
`->validate([...])` (rules Laravel-validator), `->delete()` (cancel).
For multiple fields, pass an array serverId — `getFile()` will return an array.

## Binding checklist

- [ ] The field is controlled via `v-model` list `{ id?, serverId? }[]`, form about FilePond doesn't know.
- [ ] B payload go away and saved `{ id }`, and new `{ serverId }`.
- [ ] On the back `serverId` processed via `Filepond::field()->getFile()`, temporary files do not leak.
- [ ] Type/size is also validated on the client (plugins), and on the server (`->validate()`).
