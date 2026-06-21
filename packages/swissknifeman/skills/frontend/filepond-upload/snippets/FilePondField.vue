<!-- Source: anonymized production project (FilePond field with laravel-filepond process/revert + v-model) -->
<!--
  Переиспользуемое поле загрузки. Инкапсулирует:
    - server-конфиг на endpoints laravel-filepond (process/revert на /filepond, CSRF);
    - v-model: список ссылок { id?, serverId? } — это то, что уходит в форму;
    - восстановление уже сохранённых файлов как local-постеров (defaultFiles);
    - привязку serverId при processfile и очистку при removefile.

  Контракт модели (нейтральный, подходит под любой домен Order/Document/Article):
    { id?: number|string }   — уже сохранённый на сервере файл (Media/Attachment);
    { serverId: string }     — временный файл, загруженный FilePond, ещё не привязан.
-->
<script lang="ts" setup>
import type { FilePondServerConfigProps, FilePondFile } from "filepond";
import { ref, type Ref } from "vue";
// Фабрика из snippets/register-filepond.ts (vue-filepond или локальная обёртка).
import { FilePond } from "@/components/forms/filepond";
import { getCsrfToken } from "@/utils/csrf";

export interface UploadedFileRef {
  id?: number | string;
  serverId?: string;
}

export interface ExistingFile {
  id: number | string;
  file_name?: string | null;
  size?: number | null;
  mime_type?: string | null;
}

const {
  files = [],
  name = "files",
  multiple = false,
  acceptedFileTypes = undefined,
  maxFileSize = undefined,
} = defineProps<{
  name?: string;
  files?: ExistingFile[];
  multiple?: boolean;
  acceptedFileTypes?: string;
  maxFileSize?: string; // напр. "10MB" — плагин file-validate-size
}>();

// Модель-список ссылок: именно его родитель кладёт в payload формы.
const model = defineModel<UploadedFileRef[]>({ default: () => [] });

// Инициализируем модель уже сохранёнными файлами (их id), чтобы при сабмите
// сервер понимал, какие записи оставить, а какие добавить по serverId.
model.value = files.map((file) => ({ id: file.id }));

// server-конфиг laravel-filepond: один URL /filepond обслуживает
// process (POST), revert (DELETE), restore/load (GET) и patch (chunk).
// CSRF и X-Requested-With обязательны — иначе Laravel вернёт 419/redirect.
const server: FilePondServerConfigProps["server"] = {
  url: "/filepond",
  process: "/filepond",
  revert: "/filepond",
  patch: "/filepond",
  withCredentials: true,
  headers: {
    "X-CSRF-TOKEN": getCsrfToken(),
    "X-Requested-With": "XMLHttpRequest",
  },
};

interface FilePondLocalFile {
  source: string;
  options: { type: "local"; file?: { name: string; size: number; type: string } };
}

// Уже сохранённые файлы показываем как постеры (type: "local"), source = их id.
const defaultFiles: Ref<FilePondLocalFile[]> = ref(
  files.map((file) => ({
    source: String(file.id),
    options: {
      type: "local",
      file: {
        name: file.file_name ?? "",
        size: file.size ?? 0,
        type: file.mime_type ?? "",
      },
    },
  })),
);

// processfile: FilePond отдал serverId временного файла — добавляем в модель.
function onProcessFile(_error: unknown, file: FilePondFile): void {
  const serverId = String(file.serverId ?? "").trim();
  if (!serverId) return;
  model.value = [...model.value, { serverId }];
}

// removefile: убираем ссылку и по id (сохранённый), и по serverId (временный).
function onRemoveFile(_error: unknown, file: FilePondFile): void {
  const id = String(file.id ?? "").trim();
  const serverId = String(file.serverId ?? "").trim();
  model.value = model.value.filter(
    (item) => String(item.id ?? "") !== id && String(item.serverId ?? "") !== serverId,
  );
}
</script>

<template>
  <FilePond
    :name="name"
    label-idle="Перетащите файл или нажмите для выбора"
    :allow-multiple="multiple"
    :accepted-file-types="acceptedFileTypes"
    :max-file-size="maxFileSize"
    :files="defaultFiles"
    :server="server"
    :allow-file-poster="true"
    :credits="false"
    :chunk-uploads="true"
    @processfile="onProcessFile"
    @removefile="onRemoveFile"
  />
</template>
