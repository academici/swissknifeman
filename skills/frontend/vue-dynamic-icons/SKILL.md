---
name: vue-dynamic-icons
bucket: frontend
version: 0.1.0
description: "Vue: один компонент-иконка, выбирающий SVG по строковому имени из набора (lucide-vue-next и др.) через <component :is>; активировать при словах динамическая иконка, icon by name, component is icon, проброс size/strokeWidth/color, типобезопасное имя иконки, замена набора иконок."
risk: write
persona: oss-dev
tags: [vue, icons, dynamic-component, lucide, typescript, frontend]
requires: []
produces_for: []
outputs: []
snippets: [Icon.vue, icon-name.type.ts]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Vue dynamic icon component

## Контекст

Нужен **один** переиспользуемый компонент `<Icon name="...">`, который рендерит SVG-иконку по строковому имени из набора (например `lucide-vue-next`, `@heroicons/vue`, собственный реестр), пробрасывает `size` / `strokeWidth` / `color` / `class` и не требует ручного импорта каждой иконки на каждой странице.

**Когда активировать:**
- В шаблоне просят иконку «по имени из данных/конфига» (`type`, `status`, `category` приходят строкой с backend).
- Видишь россыпь `import { Plus, Trash, ... } from 'lucide-vue-next'` в десятках компонентов — пора централизовать.
- Звучит «динамическая иконка», «icon by name», «`<component :is>` для иконки», «типобезопасное имя иконки», «как поменять набор иконок».

Паттерн **универсален** и не привязан к конкретному набору: набор — это любой модуль, экспортирующий Vue-компоненты-иконки по именам. Сменить набор = поменять один `import * as icons` и (опционально) источник union-типа имён.

## Алгоритм

1. **Создай единый компонент** `components/shared/Icon.vue` (`<script setup lang="ts">`). Все остальные места используют только его, не импортируя иконки напрямую.
2. **Импортируй набор как namespace**: `import * as icons from '<icon-set>'` — получаешь словарь `{ ИмяИконки: Component }`. Это единственная точка привязки к набору.
3. **Объяви пропсы** через `defineProps<Props>` + `withDefaults`:
   - `name: IconName` — имя иконки (типобезопасный union, см. шаг 6; на старте допустимо `string`);
   - `size?: number | string` (дефолт, напр. `16`), `strokeWidth?: number | string` (дефолт `2`), `color?: string`, `class?: string`.
4. **Нормализуй имя под соглашение набора.** В `lucide-vue-next` экспорт в PascalCase (`ArrowRight`), а данные часто в kebab/lower (`arrow-right`, `plus`). Приведи имя к нужному регистру в `computed`, а не в шаблоне. Простейший случай (lower → Pascal первой буквы) показан в сниппете; для kebab-case добавь конвертацию каждого сегмента.
5. **Выбирай компонент лениво через `computed`** — резолв иконки пересчитывается только при смене `name`:
   ```ts
   const icon = computed(() => (icons as Record<string, Component>)[normalize(props.name)]);
   ```
   Никаких сетов `if/switch` по именам — словарь набора и есть карта.
6. **Сделай имя типобезопасным.** Выведи union допустимых имён из самого набора (`keyof typeof icons`) или объяви явный `IconName` для подмножества используемых иконок (см. `snippets/icon-name.type.ts`). Это даёт автокомплит и ловит опечатки в имени на этапе сборки, а не в рантайме.
7. **Обработай промах.** Если `icons[name]` не найден — `<component :is>` с `undefined` ничего не рендерит. По желанию: верни фолбэк-иконку (`HelpCircle`/`Square`) или выведи `console.warn` в dev. Типобезопасный `name` (шаг 6) убирает большинство промахов заранее.
8. **Пробрось пропсы в `<component :is="icon">`**: `:size`, `:stroke-width`, `:color`, `:class`. `class` мерджи с базовыми классами (`cn(...)` / `clsx` / ручная конкатенация), чтобы вызывающий мог дополнять, а не затирать стиль.
9. **Используй везде одинаково**: `<Icon :name="row.icon" :size="20" class="text-muted" />`. Имя может приходить из props/стора/ответа API.

## Замена набора иконок

Чтобы перейти на другой набор, меняешь **только Icon.vue**, контракт `<Icon name size ...>` остаётся:

| Шаг | Что меняешь |
|:---|:---|
| Импорт набора | `import * as icons from '@heroicons/vue/24/outline'` вместо `lucide-vue-next` |
| Нормализация имени | под соглашение нового набора (suffix `Icon`, kebab→Pascal, и т.п.) |
| Союз-тип имён | `IconName = keyof typeof icons` пересчитается сам, либо обнови явный список |
| Пробрасываемые пропсы | у разных наборов разный API (lucide — `strokeWidth`; heroicons — без него): пробрось то, что поддерживает набор |

Поскольку набор изолирован в одном файле, цена миграции — один компонент, а не правка всех мест вызова.

## Чеклист качества

- [ ] Иконки нигде не импортируются вручную, кроме единственного `Icon.vue` (`import * as icons`)
- [ ] Выбор компонента — ленивый `computed` по `name`, без `if/switch`-цепочек
- [ ] Имя приводится к соглашению набора в `computed`/функции, а не в шаблоне
- [ ] `name` типобезопасен (`IconName` из `keyof typeof icons` или явный union), а не голый `string`
- [ ] Пробрасываются `size`, `strokeWidth`, `color` с дефолтами через `withDefaults`
- [ ] `class` мерджится с базовыми классами, вызывающий может дополнять стиль
- [ ] Есть стратегия на промах имени (фолбэк-иконка или dev-warn)
- [ ] Смена набора затрагивает только `Icon.vue`, контракт `<Icon>` не меняется

## Ссылки

- https://vuejs.org/guide/essentials/component-basics#dynamic-components
- https://lucide.dev/guide/packages/lucide-vue-next
- `snippets/Icon.vue`, `snippets/icon-name.type.ts`
- Связанные скиллы: `frontend/inertia-vue`, `frontend/vue-composition-api`
