// Source: anonymized production project
//
// Типобезопасное имя иконки. Цель: автокомплит в шаблонах и ловля опечаток
// в name на этапе сборки, а не в рантайме. Два подхода — выбери один.

import * as icons from 'lucide-vue-next';

// --- Подход A: весь набор -------------------------------------------------
// Любая иконка набора допустима. Имена — ровно так, как экспортирует набор
// (для lucide это PascalCase: 'ArrowRight', 'Plus', ...). Если в Icon.vue
// нормализуешь имя из lower/kebab, отрази это в собственном Lowercase-типе.
export type IconNameFromSet = keyof typeof icons;

// --- Подход B: явное подмножество ----------------------------------------
// Фиксируешь только реально используемые иконки. Плюс: меньше шума в
// автокомплите и явный «реестр» иконок приложения; минус — список ведёшь руками.
// Имена в том регистре, в каком приходят из данных/шаблона (нормализуются в Icon.vue).
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

// Рантайм-гард: проверить строку из API/конфига перед передачей в <Icon>.
export function isIconName(value: string): value is IconName {
    return (ICON_NAMES as readonly string[]).includes(value);
}
