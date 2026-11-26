// Source: anonymized production Laravel project
// Test examples: Vue-component via @vue/test-utils and composable as a pure function.
// The location mirrors the sources:
//   components/document/DocumentStatusBadge.vue -> tests/components/document/DocumentStatusBadge.test.ts
//   composables/document/useDocumentFilters.ts  -> tests/composables/document/useDocumentFilters.test.ts

import { mount } from '@vue/test-utils';
import { ref } from 'vue';
// globals: true — describe/it/expect are available without importing from 'vitest'

// --- Component test --------------------------------------------------------

import DocumentStatusBadge from '@/components/document/DocumentStatusBadge.vue';

describe('DocumentStatusBadge', () => {
    it('displays the readable status of the document', () => {
        const wrapper = mount(DocumentStatusBadge, {
            props: { status: 'approved' },
        });

        expect(wrapper.text()).toContain('Approved');
        expect(wrapper.classes()).toContain('badge-success');
    });

    it('emits an event when clicked', async () => {
        const wrapper = mount(DocumentStatusBadge, {
            props: { status: 'approved' },
        });

        await wrapper.trigger('click');

        expect(wrapper.emitted('select')).toHaveLength(1);
    });
});

// --- Test composable ---------------------------------------------------------

import { useDocumentFilters } from '@/composables/document/useDocumentFilters';

describe('useDocumentFilters', () => {
    it('filters documents by status', () => {
        const documents = ref([
            { id: 1, status: 'approved' },
            { id: 2, status: 'rejected' },
        ]);

        const { filteredDocuments, setStatusFilter } = useDocumentFilters(documents);

        setStatusFilter('approved');

        expect(filteredDocuments.value).toHaveLength(1);
        expect(filteredDocuments.value[0].id).toBe(1);
    });
});

// Composable with lifecycle-hooks (onMounted, inject) wrap in a carrier component:
// const TestHost = defineComponent({ setup: () => useDocumentFilters(ref([])), template: '<div />' });
// mount(TestHost);
