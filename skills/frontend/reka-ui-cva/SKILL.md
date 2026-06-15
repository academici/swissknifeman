---
name: reka-ui-cva
bucket: frontend
version: 0.1.0
description: "Библиотека UI-компонентов на headless-примитивах Reka UI + варианты class-variance-authority (cva). Активировать при добавлении/правке компонента в components/ui/, при заведении cva-вариантов, обёртке reka-ui примитива в свой компонент, составном Root/Trigger/Content (Dialog/Dropdown/Tooltip), слиянии классов cn() и связке с Tailwind."
risk: write
persona: oss-dev
tags: [reka-ui, cva, vue, tailwind, headless, components, variants, design-system]
requires: []
produces_for: []
outputs: []
snippets: [button-variants.ts, Button.vue, dialog-composite.md]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: UI-компоненты на Reka UI + cva

## Контекст

Построение собственной библиотеки UI-компонентов поверх headless-примитивов **Reka UI** (доступность, фокус, ARIA, состояния `data-[state]`) с системой вариантов **class-variance-authority (cva)** и слиянием классов через `cn()` (clsx + tailwind-merge). Каждый компонент — тонкая обёртка примитива: поведение берётся из Reka UI, внешний вид задаётся cva-вариантами и Tailwind-классами.

**Когда активировать:**
- добавляешь или правишь компонент в `components/ui/<name>/` (Button, Badge, Dialog, Dropdown и т. п.);
- заводишь cva-набор вариантов (`variant`, `size`, ...) и тип `VariantProps`;
- оборачиваешь примитив `reka-ui` в свой Vue-компонент (`Primitive`/`asChild`, форвардинг пропов);
- собираешь составной компонент из частей `Root` / `Trigger` / `Content` (Dialog, Popover, Tooltip, DropdownMenu);
- сливаешь служебные и пользовательские классы через `cn()`.

**Laravel Boost**: за Boost — серверные Blade-компоненты с готовым видом (Boost-UI / Flux); Reka UI — клиентские unstyled-примитивы для Vue, где вид вы задаёте сами через cva + Tailwind. Это **ours-only** скилл: Reka UI не входит в Laravel Boost (нет `.ai/`-каталога в пакете), границы с Boost-скиллом нет и upstream не нужен — паттерн описан целиком.

## Входные данные

- Стек проекта: Vue 3, Tailwind, и зависимости `reka-ui`, `class-variance-authority`, `clsx`, `tailwind-merge` в `package.json`.
- Утилита `cn()` (обычно `@/lib/utils`); если её нет — создать (см. шаг 1).
- Существующие компоненты в `components/ui/` как образец конвенций (data-slot, форвардинг, структура папки).

## Алгоритм

1. **Утилита `cn()`** — единая точка слияния классов. `clsx` собирает условные классы, `tailwind-merge` снимает конфликты Tailwind (последний `px-*` побеждает):
   ```ts
   import { clsx, type ClassValue } from "clsx"
   import { twMerge } from "tailwind-merge"
   export function cn(...inputs: ClassValue[]) {
     return twMerge(clsx(inputs))
   }
   ```
   Все классы в компонентах прогоняй только через `cn()`, никогда не конкатенируй строки руками.

2. **Структура компонента** — папка на компонент: `components/ui/<name>/`. Внутри:
   - `index.ts` — реэкспорт компонента(ов) и, если есть варианты, `cva`-набор + тип `VariantProps`;
   - `<Name>.vue` — обёртка примитива;
   - для составных — по файлу на каждую часть (`Dialog.vue`, `DialogTrigger.vue`, `DialogContent.vue`, ...).

3. **cva-варианты** (`index.ts`) — `cva(base, { variants, defaultVariants })`:
   - первый аргумент — **base**: классы, общие для всех экземпляров (раскладка, типографика, состояния `disabled:`, `focus-visible:`, `aria-invalid:`);
   - `variants` — карты осей (`variant`, `size`): ключ = значение пропа, значение = Tailwind-классы;
   - `defaultVariants` — значения по умолчанию для каждой оси;
   - экспортируй сам набор (`export const buttonVariants = cva(...)`) и выведенный тип `export type ButtonVariants = VariantProps<typeof buttonVariants>` — он даёт строго типизированные пропы без ручного перечисления литералов.

4. **Обёртка примитива** (`<Name>.vue`) — для интерактивных листовых элементов используется `Primitive` из `reka-ui`:
   - пропы расширяют `PrimitiveProps` (даёт `as` и `asChild`) и добавляют оси вариантов (`variant?: ButtonVariants["variant"]`) + `class?: HTMLAttributes["class"]`;
   - `withDefaults(defineProps<Props>(), { as: "button" })` — дефолтный тег;
   - в шаблоне `:class="cn(buttonVariants({ variant, size }), props.class)"` — сначала вычисленные варианты, затем пользовательский `class` (он перекрывает за счёт tailwind-merge);
   - ставь `data-slot="<name>"` для адресации из CSS и тестов; контент пробрасывай через `<slot />`.

5. **`asChild` / полиморфизм** — `Primitive` рендерит тег `as` (по умолчанию свой), а `:as-child="asChild"` сливает поведение/классы в единственный дочерний элемент вместо обёртки. Это даёт «кнопку, которая на самом деле ссылка»: `<Button as-child><Link .../></Button>` — стили кнопки получает `<Link>`. Тот же приём — для `Trigger`-частей примитивов.

6. **Форвардинг пропов в составных компонентах** — части Reka UI (`DialogRoot`, `DialogContent`, ...) принимают свои пропы/эмиты; прокидывай их прозрачно:
   - чистый проброс без классов — `useForwardPropsEmits(props, emits)` (или `useForwardProps` без эмитов), затем `v-bind="forwarded"`;
   - если у части есть свой `class`, **исключи** его из форварда: `const delegated = reactiveOmit(props, "class")`, и слей отдельно `:class="cn('<base>', props.class)"` — иначе `class` уйдёт в примитив дважды;
   - для частей с порталом/оверлеем ставь `inheritAttrs: false` и пробрасывай `{ ...$attrs, ...forwarded }`.

7. **Композиция Root/Trigger/Content** — составной компонент собирается из частей, каждая обёрнута отдельно и реэкспортирована из `index.ts`:
   - `Root` (`Dialog.vue`) — управление открытием, форвард пропов/эмитов, слот;
   - `Trigger` — тонкая обёртка `DialogTrigger`, обычно с `asChild` под свою кнопку;
   - `Content` — портал + оверлей + контейнер с cva/base-классами и состояниями `data-[state=open]:` для анимаций;
   - структурные части (`Header`, `Footer`, `Title`, `Description`) — простые `div`/примитивы с `cn('<base>', props.class)`.
   Использование: `<Dialog> <DialogTrigger as-child>...</DialogTrigger> <DialogContent>...</DialogContent> </Dialog>`.

8. **Связка с Tailwind** — все варианты и base — это Tailwind-утилиты; токены (`bg-primary`, `text-foreground`, `ring-ring`) задаются темой Tailwind, поэтому смена темы не требует правки компонентов. Состояния примитива читаются селекторами `data-[state=open]:`, `data-[side=top]:`, `aria-invalid:` — Reka UI выставляет эти атрибуты сама.

9. **Реэкспорт** — `index.ts` каждой папки реэкспортит публичное API (`export { default as Button } from "./Button.vue"` + `export const buttonVariants`/`export type ...`), чтобы импорт шёл из `@/components/ui/<name>`, а не из конкретных файлов.

## Когда какой сниппет открывать

| Ситуация | Файл |
|:---|:---|
| Завести cva-набор вариантов (`variant`/`size`) + тип `VariantProps`, реэкспорт | `snippets/button-variants.ts` |
| Обернуть примитив `Primitive`/`asChild`, слить классы `cn()`, дефолтный тег | `snippets/Button.vue` |
| Собрать составной компонент Root/Trigger/Content с форвардингом и `reactiveOmit(class)` | `snippets/dialog-composite.md` |

## Чеклист качества

- [ ] Компонент — тонкая обёртка примитива Reka UI; поведение/доступность не реализованы руками
- [ ] Все классы слиты через `cn()`, пользовательский `class` идёт **последним** аргументом
- [ ] cva: `base` + `variants` + `defaultVariants`; экспортирован набор и тип `VariantProps`
- [ ] Пропы вариантов типизированы через `ButtonVariants["variant"]`, не строковыми литералами вручную
- [ ] `Primitive` + `asChild`/`as` для полиморфных/интерактивных элементов
- [ ] В составных частях с собственным `class` он исключён из форварда (`reactiveOmit`), чтобы не дублировался
- [ ] Форвардинг пропов/эмитов через `useForwardPropsEmits`/`useForwardProps`, а не ручной перебор
- [ ] `data-slot` проставлен; `index.ts` реэкспортит публичное API папки
- [ ] Цвета/радиусы взяты из Tailwind-токенов темы, а не захардкожены

## Ссылки

- https://reka-ui.com/
- https://cva.style/docs
- https://github.com/dcastil/tailwind-merge
- Связанные скиллы: `frontend/inertia-vue`, `frontend/js-code-style`
