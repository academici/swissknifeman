// Source: anonymized production project (vue-filepond + filepond plugins registration)
//
// Registration FilePond once per application: factory vue-filepond + plugins + CSS.
// Connects at the entry point (resources/js/app.ts) BEFORE mounting Vue,
// or locally in the field component - see both options below.

// --- Option A: published-package vue-filepond (recommended, most portable) ---

import vueFilePond from "vue-filepond";

// We connect only those plugins that are really needed - each one adds weight to the bundle.
import FilePondPluginFileValidateType from "filepond-plugin-file-validate-type";
import FilePondPluginFileValidateSize from "filepond-plugin-file-validate-size";
import FilePondPluginImagePreview from "filepond-plugin-image-preview";
import FilePondPluginFilePoster from "filepond-plugin-file-poster";

// CSS kernels + CSS of every plugin that has it (image-preview, file-poster).
// Import of styles is required - preview without it/poster will not be rendered.
import "filepond/dist/filepond.min.css";
import "filepond-plugin-image-preview/dist/filepond-plugin-image-preview.min.css";
import "filepond-plugin-file-poster/dist/filepond-plugin-file-poster.min.css";

// vueFilePond(...plugins) inside calls registerPlugin(...) and returns
// Vue-component. We register globally so that the templates can be seen <file-pond>.
export const FilePond = vueFilePond(
  FilePondPluginFileValidateType,
  FilePondPluginFileValidateSize,
  FilePondPluginImagePreview,
  FilePondPluginFilePoster,
);

// app.use(plugin)/createApp(...) ... .component("FilePond", FilePond)

// --- Option B: local factory (if you need strict type checking/SSR) ---
//
// If the project contains its own resources/js/components/forms/VueFilePond.ts
// (thin typed wrapper over `filepond` core: create/supported/registerPlugin),
// import the factory from it and pass the plugins in the same way:
//
//   import vueFilePond from "@/components/forms/VueFilePond";
//   const FilePond = vueFilePond(FilePondPluginFileValidateType, FilePondPluginImagePreview);
//
// Behavior is identical to option A; only the factory source changes.
