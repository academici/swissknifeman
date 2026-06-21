<!-- Source: anonymized production Laravel project -->
<!-- Inertia-страница: resources/js/pages/Documents/Edit.vue -->
<!-- Тонкая: layout + доменные компоненты + composable; логика — в useDocumentForm. -->

<script setup lang="ts">
import { Head, Link } from '@inertiajs/vue3';
import AppLayout from '@/layouts/AppLayout.vue';
import DocumentStatusBadge from '@/components/document/DocumentStatusBadge.vue';
import { useDocumentForm } from '@/composables/document/useDocumentForm';
import { index as documentsIndex } from '@/routes/documents';

interface Props {
    document: {
        id: number;
        title: string;
        status: string;
    };
}

const props = defineProps<Props>();

const { form, submit } = useDocumentForm(props.document);
</script>

<template>
    <AppLayout>
        <Head :title="`Документ: ${props.document.title}`" />

        <!-- Навигация ТОЛЬКО через <Link>, не <a href> -->
        <Link :href="documentsIndex.url()" class="text-sm text-gray-500">← К списку</Link>

        <h1 class="text-xl font-semibold">{{ props.document.title }}</h1>
        <DocumentStatusBadge :status="props.document.status" />

        <!-- Форма через useForm: состояние, ошибки и processing — из хелпера -->
        <form class="mt-6 space-y-4" @submit.prevent="submit">
            <div>
                <label for="title">Название</label>
                <input id="title" v-model="form.title" type="text" />
                <p v-if="form.errors.title" class="text-red-600">{{ form.errors.title }}</p>
            </div>

            <button type="submit" :disabled="form.processing">Сохранить</button>
        </form>
    </AppLayout>
</template>
