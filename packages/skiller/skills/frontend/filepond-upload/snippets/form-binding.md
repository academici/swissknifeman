<!-- Source: anonymized production project (binding FilePond upload refs to an Inertia form + laravel-filepond server processing) -->

# Привязка загруженных файлов к форме и серверная обработка

Поле `FilePondField.vue` через `v-model` отдаёт наружу **список ссылок**
`{ id?, serverId? }[]`. Этот список кладётся в форму как обычное поле и уходит
в payload. Сервер по `serverId` забирает временный файл из стора laravel-filepond
и привязывает к доменной модели.

## 1. Frontend — кладём список в Inertia-форму

```vue
<script lang="ts" setup>
import { useForm } from "@inertiajs/vue3";
import FilePondField, {
  type UploadedFileRef,
  type ExistingFile,
} from "@/components/forms/FilePondField.vue";

const props = defineProps<{ existingFiles: ExistingFile[] }>();

// attachment_files — обычное поле формы; FilePond им управляет через v-model.
const form = useForm<{ title: string; attachment_files: UploadedFileRef[] }>({
  title: "",
  attachment_files: props.existingFiles.map((file) => ({ id: file.id })),
});

function submit() {
  // На submit улетают и сохранённые { id }, и новые { serverId }.
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

    <button :disabled="form.processing">Сохранить</button>
  </form>
</template>
```

Ключевое: компонент-поле не знает про форму, форма не знает про FilePond.
Связь — только через сериализуемый `UploadedFileRef[]`. Это делает поле
переносимым между формами и проектами.

## 2. (Опционально) composable: existing vs pending

Если нужна логика поверх списка (счётчики, раздельные секции «сохранённые» /
«ожидают загрузки»), вынесите её в composable, а не в компонент:

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

## 3. Backend — laravel-filepond: process/revert и привязка по serverId

`rahulhaque/laravel-filepond` регистрирует один маршрут `/filepond`,
обслуживающий все колбэки FilePond:

| FilePond callback | HTTP             | Что делает                                              |
|:------------------|:-----------------|:--------------------------------------------------------|
| `process`         | `POST /filepond` | принимает временный файл, возвращает `serverId`         |
| `revert`          | `DELETE /filepond` | удаляет временный файл по `serverId` (отмена загрузки) |
| `patch`           | `PATCH /filepond`  | приём чанков при `chunk-uploads`                       |
| `restore`/`load`  | `GET /filepond`    | отдаёт ранее сохранённый/временный файл для постера    |

Контроллер пакета подключается его сервис-провайдером — руками роут писать не
нужно. На стороне приложения по `serverId` забираем файл фасадом `Filepond`:

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

        // 1. Сохранённые файлы (есть id) — оставляем как есть / синхронизируем.
        $keepIds = $items
            ->filter(fn (array $item): bool => isset($item['id']))
            ->pluck('id');
        // ... удалить из коллекции всё, чего нет в $keepIds (зависит от media-слоя)

        // 2. Новые временные файлы (есть serverId) — забираем из стора FilePond
        //    и привязываем к модели. После getFile() временный файл очищается.
        $items
            ->filter(fn (array $item): bool => isset($item['serverId']))
            ->each(function (array $item) use ($order): void {
                $uploaded = Filepond::field($item['serverId']);
                $file = $uploaded->getFile();           // UploadedFile

                $order
                    ->addMedia($file)                   // spatie/media-library и т.п.
                    ->toMediaCollection('attachments');
            });
    }
}
```

Полезные методы фасада (см. README пакета): `Filepond::field($serverId)`,
затем `->getFile()` (получить `UploadedFile`), `->getDto()` (метаданные),
`->validate([...])` (правила Laravel-валидатора), `->delete()` (отмена).
Для множественного поля передавайте массив serverId — `getFile()` вернёт массив.

## Чеклист привязки

- [ ] Поле управляется через `v-model` списком `{ id?, serverId? }[]`, форма про FilePond не знает.
- [ ] В payload уходят и сохранённые `{ id }`, и новые `{ serverId }`.
- [ ] На бэке `serverId` обработан через `Filepond::field()->getFile()`, временные файлы не утекают.
- [ ] Тип/размер валидируются и на клиенте (плагины), и на сервере (`->validate()`).
