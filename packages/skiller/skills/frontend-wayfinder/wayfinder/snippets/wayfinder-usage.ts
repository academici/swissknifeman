// Source: anonymized production Laravel project
// Usage patterns Laravel Wayfinder on the frontend (Vue/Inertia).

// --- Imports: named ONLY (tree-shaking) -------------------------

// Controller actions:
import { show, store, update, destroy } from '@/actions/App/Http/Controllers/DocumentController';

// Named routes (alias for collisions):
import { show as documentShow } from '@/routes/documents';

// BAD: default-import pulls the entire generated module into a bundle
// import DocumentController from '@/actions/App/Http/Controllers/DocumentController';

// --- Basic methods -------------------------------------------------------------

show(1); // { url: '/documents/1', method: 'get' }
show.url(1); // '/documents/1' — line for axios/fetch
show.get(1); // explicit HTTP-method
store.post(); // { url: '/documents', method: 'post' }
update.patch(1); // { url: '/documents/1', method: 'patch' }
destroy.delete(1); // { url: '/documents/1', method: 'delete' }

// Attributes for HTML-forms (generation with flag --with-form):
store.form(); // { action: '/documents', method: 'post' }
update.form(1); // { action: '/documents/1', method: 'post' } + spoofed _method

// Query-parameters:
show(1, { query: { page: 1, filter: 'active' } }); // '/documents/1?page=1&filter=active'

// Route model binding — pass an object with a key, rather than «naked» id, if the route is waiting for the model:
show({ document: 1 });

// --- Inertia: <Form> and router --------------------------------------------

// <script setup lang="ts">
// import { Form } from '@inertiajs/vue3';
// import { store } from '@/actions/App/Http/Controllers/DocumentController';
// </script>
//
// <template>
//     <Form v-bind="store.form()">
//         <input name="title" />
//         <button type="submit">Save</button>
//     </Form>
// </template>

// router.visit with wayfinder instead of the line:
// router.visit(show.url(documentId));

// --- Layer composable: components are not touched wayfinder directly -----------

// resources/js/composables/document/useDocumentNavigation.ts
import { router } from '@inertiajs/vue3';

export function useDocumentNavigation() {
    function openDocument(documentId: number) {
        router.visit(show.url(documentId));
    }

    return { openDocument };
}
