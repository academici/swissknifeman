// Source: anonymized production project
// components/ui/button/index.ts
// cva-option set + type VariantProps + re-exporting a component.
// The pattern is universal: the same skeleton for Badge, Alert, Toggle and any
// component that has appearance axes (variant/size/...).

import type { VariantProps } from "class-variance-authority"
import { cva } from "class-variance-authority"

// Re-export the component itself so that the import comes from @/components/ui/button
export { default as Button } from "./Button.vue"

export const buttonVariants = cva(
  // base: classes common to all instances - layout, typography,
  // states disabled:/focus-visible:/aria-invalid: (last read
  // attributes that the primitive sets itself).
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-all outline-none shrink-0 disabled:pointer-events-none disabled:opacity-50 focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:border-destructive aria-invalid:ring-destructive/20",
  {
    variants: {
      // Axis «view»: key = prop value variant, value = Tailwind-classes.
      // Colors are taken from theme tokens (bg-primary, text-*-foreground),
      // so changing the theme does not require editing the component.
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        destructive: "bg-destructive text-white hover:bg-destructive/90 focus-visible:ring-destructive/20",
        outline: "border bg-background shadow-xs hover:bg-accent hover:text-accent-foreground",
        secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost: "hover:bg-accent hover:text-accent-foreground",
        link: "text-primary underline-offset-4 hover:underline",
      },
      // Axis «size»: height, padding, icon squares.
      size: {
        "default": "h-9 px-4 py-2 has-[>svg]:px-3",
        "sm": "h-8 gap-1.5 rounded-md px-3 has-[>svg]:px-2.5",
        "lg": "h-10 rounded-md px-6 has-[>svg]:px-4",
        "icon": "size-9",
      },
    },
    // Default values for each axis: can be called buttonVariants()
    // without arguments and get a meaningful result.
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
)

// The inferred type combines the literals of all axes: gives strongly typed
// props (variant?: "default" | "destructive" | ...) without manual enumeration.
export type ButtonVariants = VariantProps<typeof buttonVariants>
