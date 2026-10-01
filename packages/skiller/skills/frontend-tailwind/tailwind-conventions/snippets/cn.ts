// Source: anonymized production project
//
// cn() — single point for conditional and dynamic classes Tailwind.
//   clsx       — collects classes from strings/objects/arrays, discards falsy.
//   tailwind-merge — resolves conflicts Tailwind-utilities: last one wins
//                    ("px-2 px-4" -> "px-4", "text-sm text-lg" -> "text-lg").
//
// Without twMerge conditional classes accumulate conflicts and produce unpredictable results.
// Always wrap dynamic class sets in cn(), and not glue the lines by hand.

import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]): string {
    return twMerge(clsx(inputs));
}

// --- Usage examples --------------------------------------------------
//
// Condition object:
//   cn('rounded-md px-3 py-2', {
//       'bg-primary text-primary-foreground': variant === 'primary',
//       'bg-secondary text-secondary-foreground': variant === 'secondary',
//       'opacity-50 pointer-events-none': disabled,
//   })
//
// Merge prop class with basic (component remains overridable):
//   const props = defineProps<{ class?: string }>()
//   const classes = computed(() => cn('inline-flex items-center gap-2', props.class))
//   // <button :class="classes">  — props.class='px-8' will correctly override the default padding
//
// V .prettierrc cn is listed in tailwindFunctions, therefore prettier-plugin-tailwindcss
// sorts classes and inside cn(...) too (see snippets/.prettierrc).
