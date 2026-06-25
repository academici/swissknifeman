// Source: anonymized production Laravel project
// Доменный composable: resources/js/composables/document/useDocumentForm.ts
// Инкапсулирует форму и навигацию домена; компоненты не трогают wayfinder напрямую.

import { computed } from 'vue';
import { router, useForm } from '@inertiajs/vue3';
import { store, update } from '@/actions/App/Http/Controllers/DocumentController';
import { show as documentShow } from '@/routes/documents';

interface DocumentPayload {
    title: string;
    status: string;
}

export function useDocumentForm(initial?: Partial<DocumentPayload> & { id?: number }) {
    const form = useForm<DocumentPayload>({
        title: initial?.title ?? '',
        status: initial?.status ?? 'draft',
    });

    const isEditing = computed(() => Boolean(initial?.id));

    function submit() {
        if (initial?.id) {
            form.patch(update.url(initial.id), {
                onSuccess: () => openDocument(initial.id as number),
            });
            return;
        }

        form.post(store.url());
    }

    function openDocument(documentId: number) {
        router.visit(documentShow.url(documentId));
    }

    return { form, isEditing, submit, openDocument };
}
