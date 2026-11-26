// Source: anonymized production project
//
// Type-safe icon name. Goal: autocomplete in templates and catching typos
// in name at the build stage, and not at runtime. Two approaches - choose one.

import * as icons from 'lucide-vue-next';

// --- Approach A: whole set -------------------------------------------------
// Any set icon is acceptable. Names - exactly as the set exports
// (for lucide this PascalCase: 'ArrowRight', 'Plus', ...). If in Icon.vue
// normalize the name from lower/kebab, reflect this in your own Lowercase-type.
export type IconNameFromSet = keyof typeof icons;

// --- Approach B: explicit subset ----------------------------------------
// You only record actually used icons. Plus: less noise in
// autocomplete and explicit «registry» application icons; The downside is that you make the list by hand.
// Names in the case in which they come from the data/template (are normalized to Icon.vue).
export const ICON_NAMES = [
    'plus',
    'pencil',
    'trash',
    'check',
    'x',
    'arrowRight',
    'chevronDown',
    'search',
    'settings',
    'helpCircle',
] as const;

export type IconName = (typeof ICON_NAMES)[number];

// Runtime guard: check line from API/config before transferring to <Icon>.
export function isIconName(value: string): value is IconName {
    return (ICON_NAMES as readonly string[]).includes(value);
}
