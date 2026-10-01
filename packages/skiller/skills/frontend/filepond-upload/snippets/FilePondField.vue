<!-- Source: anonymized production project (FilePond field with laravel-filepond process/revert + v-model) -->
<!--
  Reused loading field. Encapsulates:
    - server-config on endpoints laravel-filepond (process/revert on /filepond, CSRF);
    - v-model: list of links { id?, serverId? } — is what goes into the form;
    - restore already saved files as local-posters (defaultFiles);
    - binding serverId when processfile and cleaning when removefile.

  Model contract (neutral, suitable for any domain Order/Document/Article):
    { id?: number|string }   — file already saved on the server (Media/Attachment);
    { serverId: string }     — temporary file uploaded FilePond, is not linked yet.
-->
<script lang="ts" setup>
import type { FilePondServerConfigProps, FilePondFile } from "filepond";
import { ref, type Ref } from "vue";
// Factory from snippets/register-filepond.ts (vue-filepond or local wrapper).
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
  maxFileSize?: string; // e.g. "10MB" — plugin file-validate-size
}>();

// Model-list of links: this is what the parent puts in payload forms.
const model = defineModel<UploadedFileRef[]>({ default: () => [] });

// Initialize the model with already saved files (them id), so that when submitting
// the server understood which records to leave and which to add serverId.
model.value = files.map((file) => ({ id: file.id }));

// server-config laravel-filepond: one URL /filepond serves
// process (POST), revert (DELETE), restore/load (GET) and patch (chunk).
// CSRF and X-Requested-With are required - otherwise Laravel will return 419/redirect.
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

// We show already saved files as posters (type: "local"), source = them id.
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

// processfile: FilePond gave serverId temporary file - add to the model.
function onProcessFile(_error: unknown, file: FilePondFile): void {
  const serverId = String(file.serverId ?? "").trim();
  if (!serverId) return;
  model.value = [...model.value, { serverId }];
}

// removefile: remove the link and id (saved), and by serverId (temporary).
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
    label-idle="Drag and drop file or click to select"
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
