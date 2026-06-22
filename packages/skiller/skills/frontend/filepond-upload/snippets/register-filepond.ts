// Source: anonymized production project (vue-filepond + filepond plugins registration)
//
// Регистрация FilePond один раз на приложение: фабрика vue-filepond + плагины + CSS.
// Подключается в точке входа (resources/js/app.ts) ДО монтирования Vue,
// либо локально в компоненте-поле — см. оба варианта ниже.

// --- Вариант A: published-пакет vue-filepond (рекомендуется, самый переносимый) ---

import vueFilePond from "vue-filepond";

// Плагины подключаем только те, что реально нужны — каждый добавляет вес в бандл.
import FilePondPluginFileValidateType from "filepond-plugin-file-validate-type";
import FilePondPluginFileValidateSize from "filepond-plugin-file-validate-size";
import FilePondPluginImagePreview from "filepond-plugin-image-preview";
import FilePondPluginFilePoster from "filepond-plugin-file-poster";

// CSS ядра + CSS каждого плагина, у которого он есть (image-preview, file-poster).
// Импорт стилей обязателен — без него превью/постер не отрисуются.
import "filepond/dist/filepond.min.css";
import "filepond-plugin-image-preview/dist/filepond-plugin-image-preview.min.css";
import "filepond-plugin-file-poster/dist/filepond-plugin-file-poster.min.css";

// vueFilePond(...plugins) внутри вызывает registerPlugin(...) и возвращает
// Vue-компонент. Регистрируем глобально, чтобы шаблоны видели <file-pond>.
export const FilePond = vueFilePond(
  FilePondPluginFileValidateType,
  FilePondPluginFileValidateSize,
  FilePondPluginImagePreview,
  FilePondPluginFilePoster,
);

// app.use(plugin)/createApp(...) ... .component("FilePond", FilePond)

// --- Вариант B: локальная фабрика (если нужен строгий контроль типов/SSR) ---
//
// Если в проекте лежит собственный resources/js/components/forms/VueFilePond.ts
// (тонкая типизированная обёртка над `filepond` core: create/supported/registerPlugin),
// импортируйте фабрику из него и так же передавайте плагины:
//
//   import vueFilePond from "@/components/forms/VueFilePond";
//   const FilePond = vueFilePond(FilePondPluginFileValidateType, FilePondPluginImagePreview);
//
// Поведение идентично варианту A; меняется только источник фабрики.
