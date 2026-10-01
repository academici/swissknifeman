<!-- Source: anonymized production Laravel project -->
<!-- Inertia-page: resources/js/pages/Documents/Edit.vue -->
<!-- Thin: layout + domain components + composable; logic - in useDocumentForm. -->

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
        <Head :title="`Document: ${props.document.title}`" />

        <!-- Navigation via ONLY <Link>, not <a href> -->
        <Link :href="documentsIndex.url()" class="text-sm text-gray-500">← To the list</Link>

        <h1 class="text-xl font-semibold">{{ props.document.title }}</h1>
        <DocumentStatusBadge :status="props.document.status" />

        <!-- Form via useForm: status, errors and processing — from helper -->
        <form class="mt-6 space-y-4" @submit.prevent="submit">
            <div>
                <label for="title">Title</label>
                <input id="title" v-model="form.title" type="text" />
                <p v-if="form.errors.title" class="text-red-600">{{ form.errors.title }}</p>
            </div>

            <button type="submit" :disabled="form.processing">Save</button>
        </form>
    </AppLayout>
</template>
