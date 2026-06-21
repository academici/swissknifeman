// Source: anonymized production project
// components/ui/button/index.ts
// cva-набор вариантов + тип VariantProps + реэкспорт компонента.
// Паттерн универсален: тот же скелет для Badge, Alert, Toggle и любого
// компонента, у которого есть оси внешнего вида (variant/size/...).

import type { VariantProps } from "class-variance-authority"
import { cva } from "class-variance-authority"

// Реэкспорт самого компонента, чтобы импорт шёл из @/components/ui/button
export { default as Button } from "./Button.vue"

export const buttonVariants = cva(
  // base: классы, общие для всех экземпляров — раскладка, типографика,
  // состояния disabled:/focus-visible:/aria-invalid: (последние читают
  // атрибуты, которые примитив выставляет сам).
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-all outline-none shrink-0 disabled:pointer-events-none disabled:opacity-50 focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:border-destructive aria-invalid:ring-destructive/20",
  {
    variants: {
      // Ось «вид»: ключ = значение пропа variant, значение = Tailwind-классы.
      // Цвета берутся из токенов темы (bg-primary, text-*-foreground),
      // поэтому смена темы не требует правки компонента.
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        destructive: "bg-destructive text-white hover:bg-destructive/90 focus-visible:ring-destructive/20",
        outline: "border bg-background shadow-xs hover:bg-accent hover:text-accent-foreground",
        secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost: "hover:bg-accent hover:text-accent-foreground",
        link: "text-primary underline-offset-4 hover:underline",
      },
      // Ось «размер»: высота, отступы, иконочные квадраты.
      size: {
        "default": "h-9 px-4 py-2 has-[>svg]:px-3",
        "sm": "h-8 gap-1.5 rounded-md px-3 has-[>svg]:px-2.5",
        "lg": "h-10 rounded-md px-6 has-[>svg]:px-4",
        "icon": "size-9",
      },
    },
    // Значения по умолчанию для каждой оси: можно вызвать buttonVariants()
    // без аргументов и получить осмысленный результат.
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
)

// Выведенный тип объединяет литералы всех осей: даёт строго типизированные
// пропы (variant?: "default" | "destructive" | ...) без ручного перечисления.
export type ButtonVariants = VariantProps<typeof buttonVariants>
