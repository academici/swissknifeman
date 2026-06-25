// Source: anonymized production Laravel project
// Паттерны использования Laravel Wayfinder на фронтенде (Vue/Inertia).

// --- Импорты: ТОЛЬКО именованные (tree-shaking) -------------------------

// Controller actions:
import { show, store, update, destroy } from '@/actions/App/Http/Controllers/DocumentController';

// Именованные роуты (alias при коллизиях):
import { show as documentShow } from '@/routes/documents';

// ПЛОХО: default-импорт тянет весь сгенерированный модуль в бандл
// import DocumentController from '@/actions/App/Http/Controllers/DocumentController';

// --- Базовые методы ------------------------------------------------------

show(1); // { url: '/documents/1', method: 'get' }
show.url(1); // '/documents/1' — строка для axios/fetch
show.get(1); // явный HTTP-метод
store.post(); // { url: '/documents', method: 'post' }
update.patch(1); // { url: '/documents/1', method: 'patch' }
destroy.delete(1); // { url: '/documents/1', method: 'delete' }

// Атрибуты для HTML-формы (генерация с флагом --with-form):
store.form(); // { action: '/documents', method: 'post' }
update.form(1); // { action: '/documents/1', method: 'post' } + spoofed _method

// Query-параметры:
show(1, { query: { page: 1, filter: 'active' } }); // '/documents/1?page=1&filter=active'

// Route model binding — передавать объект с ключом, а не «голый» id, если роут ждёт модель:
show({ document: 1 });

// --- Inertia: <Form> и router --------------------------------------------

// <script setup lang="ts">
// import { Form } from '@inertiajs/vue3';
// import { store } from '@/actions/App/Http/Controllers/DocumentController';
// </script>
//
// <template>
//     <Form v-bind="store.form()">
//         <input name="title" />
//         <button type="submit">Сохранить</button>
//     </Form>
// </template>

// router.visit с wayfinder вместо строки:
// router.visit(show.url(documentId));

// --- Слой composable: компоненты не трогают wayfinder напрямую -----------

// resources/js/composables/document/useDocumentNavigation.ts
import { router } from '@inertiajs/vue3';

export function useDocumentNavigation() {
    function openDocument(documentId: number) {
        router.visit(show.url(documentId));
    }

    return { openDocument };
}
