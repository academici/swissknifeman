---
name: livewire-blade-attributes
description: "Livewire 3 Blade-component attribute delta gotchas. Activate when a tag attribute must be conditional/dynamic: never put @if/@endif/@js() inside the attribute list (breaks parsing). Fix: pre-build via ComponentAttributeBag (->merge, ->class) in @php, spread as one expression. Triggers: parse/render error, conditional wire:model/wire:sortable/step/disabled, @js() in an attribute, unstable wire:key in a loop"
---

Advisory scope: conditional/dynamic Blade-component attribute gotchas in Livewire 3. Control directives *inside a tag's attribute list* break parsing (attribute lost or component renders with error). Rule: no logic between tag attributes — pre-build all conditional/dynamic attributes in a `@php` block via `Illuminate\View\ComponentAttributeBag` (`->merge([...])`, `->class([...])`) and spread as one `{{ $bag }}`. Laravel Boost (`livewire/*`) owns versioned Livewire 2/3/4 rules; this skill is only the Blade-attribute deltas not in Boost.

## Activate when

- Writing/reviewing Livewire Blade markup where a tag attribute must be conditional or dynamic.
- `@if`/`@endif`, `@js()`, ternary, or concatenation **inside the attribute list** of `<x-...>` or a plain tag with `wire:` attributes.
- Component parse/render error, "eaten" or duplicated attribute.
- Conditional `wire:model`/`wire:sortable`/`step`/`disabled`/`class`.
- Loop with `wire:model`/`wire:key` where DOM desyncs after reorder/delete.

Do NOT activate: static attributes without conditions; Livewire lifecycle/binding/validation questions — that's Boost (`livewire/*`).

## Algorithm

1. Find logic in attributes. Any `@if/@endif`, `@js()`, ternary, or interpolation *between* tag attributes is a candidate to extract. Attribute value via `{{ }}` or `:attr="$expr"` is fine; a block-opening/closing directive between attributes is not.
2. Lift assembly into a `@php` block before the tag. Start from a base set as array or `new \Illuminate\View\ComponentAttributeBag([...])`.
3. Conditional attributes via `->merge([...])` (or add the key to the array before the Bag constructor). One `if` = one `merge`/key.
4. Classes via `->class([...])` with conditional keys (`'font-semibold' => $isActive`), not string concatenation in `class="..."`.
5. Spread the Bag as one expression: `<x-ui.input {{ $inputAttributes }} />`. No directives after it inside the tag.
6. Boolean/optional attribute via plain PHP, not `@js()`: `:disabled="$disabled"`; "present/absent" → `:disabled="$disabled ? true : null"` (`null` value → attribute omitted entirely).
7. `wire:model` modifiers go in the attribute name (`wire:model.live.debounce.300ms="..."`), not assembled via conditional directives inside the string.
8. `wire:key` static and stable: type prefix + immutable model id (`wire:key="order-{{ $order->id }}"`), not the loop index — else reorder/delete breaks DOM binding.

## Anti-patterns → replacement

| Anti-pattern in attributes | Replacement |
|---|---|
| `@if ($step) step="{{ $step }}" @endif` | `->merge(['step' => $step])` in `@php` |
| `@if ($sortable) wire:sortable="..." @endif` | conditional array key → `ComponentAttributeBag` |
| `:disabled="@js($disabled)"` | `:disabled="$disabled"` |
| string class concatenation in `class="..."` | `->class(['base', 'active' => $isActive])` |
| `wire:model="@if($live) live @endif='...'"` | `wire:model.live="..."` (modifier in name) |
| `wire:key="row-{{ $loop->index }}"` | `wire:key="order-{{ $order->id }}"` |

## Which snippet

| Situation | File |
|---|---|
| Conditional/dynamic attribute, classes, wire:model, wire:key — before/after pairs | `snippets/blade-attributes.blade.php` |

## Quality checklist

- [ ] No `@if/@endif`, `@js()`, or block directives inside the tag's attribute list
- [ ] Conditional attributes built in `@php` via `ComponentAttributeBag` (`->merge`) and spread as one `{{ $bag }}`
- [ ] Conditional classes via `->class([...])`, not string concatenation
- [ ] Boolean attribute `:attr="$expr"`; "present/absent" via ternary with `null`, no `@js()`
- [ ] `wire:model` modifiers (`.live`, `.debounce`) in the attribute name
- [ ] `wire:key` unique, stable, not based on loop index
- [ ] Component renders without parse errors

## Links

- https://livewire.laravel.com/docs/components
- https://laravel.com/docs/blade#default-merged-attributes (ComponentAttributeBag, `merge`, `class`)
- Laravel Boost (`livewire/*`) — versioned Livewire 2/3/4 rules; not duplicated here.
- `snippets/blade-attributes.blade.php` — before/after pairs.
- Related skills: `laravel-filament/filament` (Livewire-based UI — same Blade components), `frontend-backend/laravel-echo-client` (realtime frontend when Livewire is augmented with websockets).
