// Source: anonymized production Laravel project
// Примеры тестов: Vue-компонент через @vue/test-utils и composable как чистая функция.
// Расположение зеркалит исходники:
//   components/document/DocumentStatusBadge.vue -> tests/components/document/DocumentStatusBadge.test.ts
//   composables/document/useDocumentFilters.ts  -> tests/composables/document/useDocumentFilters.test.ts

import { mount } from '@vue/test-utils';
import { ref } from 'vue';
// globals: true — describe/it/expect доступны без импорта из 'vitest'

// --- Тест компонента --------------------------------------------------------

import DocumentStatusBadge from '@/components/document/DocumentStatusBadge.vue';

describe('DocumentStatusBadge', () => {
    it('отображает читаемый статус документа', () => {
        const wrapper = mount(DocumentStatusBadge, {
            props: { status: 'approved' },
        });

        expect(wrapper.text()).toContain('Approved');
        expect(wrapper.classes()).toContain('badge-success');
    });

    it('эмитит событие при клике', async () => {
        const wrapper = mount(DocumentStatusBadge, {
            props: { status: 'approved' },
        });

        await wrapper.trigger('click');

        expect(wrapper.emitted('select')).toHaveLength(1);
    });
});

// --- Тест composable ---------------------------------------------------------

import { useDocumentFilters } from '@/composables/document/useDocumentFilters';

describe('useDocumentFilters', () => {
    it('фильтрует документы по статусу', () => {
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

// Composable с lifecycle-хуками (onMounted, inject) оборачивать в компонент-носитель:
// const TestHost = defineComponent({ setup: () => useDocumentFilters(ref([])), template: '<div />' });
// mount(TestHost);
