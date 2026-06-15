// Source: anonymized production project
//
// cn() — единая точка для условных и динамических классов Tailwind.
//   clsx       — собирает классы из строк/объектов/массивов, отбрасывает falsy.
//   tailwind-merge — разрешает конфликты Tailwind-утилит: последняя побеждает
//                    ("px-2 px-4" -> "px-4", "text-sm text-lg" -> "text-lg").
//
// Без twMerge условные классы накапливают конфликты и дают непредсказуемый результат.
// Всегда оборачивай динамические наборы классов в cn(), а не клей строки руками.

import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]): string {
    return twMerge(clsx(inputs));
}

// --- Примеры использования --------------------------------------------------
//
// Объект-условия:
//   cn('rounded-md px-3 py-2', {
//       'bg-primary text-primary-foreground': variant === 'primary',
//       'bg-secondary text-secondary-foreground': variant === 'secondary',
//       'opacity-50 pointer-events-none': disabled,
//   })
//
// Слияние пропсового class с базовым (компонент остаётся переопределяемым):
//   const props = defineProps<{ class?: string }>()
//   const classes = computed(() => cn('inline-flex items-center gap-2', props.class))
//   // <button :class="classes">  — props.class='px-8' корректно перебьёт дефолтный паддинг
//
// В .prettierrc cn перечислен в tailwindFunctions, поэтому prettier-plugin-tailwindcss
// сортирует классы и внутри cn(...) тоже (см. snippets/.prettierrc).
