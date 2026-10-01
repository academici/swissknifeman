{{-- Source: anonymized production project --}}
{{--
    Delta gochizy Livewire 3: conditional/dynamic attributes Blade-components.
    Universal pattern - neutral domains (Order/Article/Document),
    component `<x-ui.input>` / `<x-ui.button>` — replace with yours UI-kit.
--}}

{{-- ============================================================= --}}
{{-- BAD: directives and @js() INSIDE the tag attribute list --}}
{{-- The component parser breaks: the attribute is not parsed, rendering crashes --}}
{{-- ============================================================= --}}

{{-- ❌ @if/@endif between attributes --}}
<x-ui.input
    wire:model="form.quantity"
    @if ($step) step="{{ $step }}" @endif
    placeholder="Quantity"
/>

{{-- ❌ Conditional wire:-attribute on a regular tag --}}
<div class="flex flex-col gap-2" @if ($sortable) wire:sortable="reorderItems" @endif>
    {{-- ... --}}
</div>

{{-- ❌ @js() in the attribute value --}}
<x-ui.button :disabled="@js($disabled)">Save</x-ui.button>

{{-- ❌ Conditional modifier inside an attribute name wire:model --}}
<input wire:model="@if ($live) live @endif='form.title'">


{{-- ============================================================= --}}
{{-- GOOD: attributes are collected in advance in @php-block via --}}
{{-- ComponentAttributeBag, then unfold in one {{ $bag }}  --}}
{{-- ============================================================= --}}

{{-- ✅ Conditional attribute via ->merge([...]) --}}
@php
    $inputAttributes = new \Illuminate\View\ComponentAttributeBag([
        'wire:model' => 'form.quantity',
        'placeholder' => 'Quantity',
    ]);

    if ($step) {
        $inputAttributes = $inputAttributes->merge(['step' => $step]);
    }
@endphp

<x-ui.input {{ $inputAttributes }} />

{{-- ✅ Same result via array + one constructor Bag --}}
@php
    $row = ['class' => 'flex flex-col gap-2'];

    if ($sortable) {
        $row['wire:sortable'] = 'reorderItems';
    }
@endphp

<div {{ new \Illuminate\View\ComponentAttributeBag($row) }}>
    {{-- ... --}}
</div>

{{-- ✅ Classes - via ->class([...]) with conditional keys --}}
@php
    $cellAttributes = (new \Illuminate\View\ComponentAttributeBag([]))
        ->class([
            'px-3 py-2',
            'font-semibold' => $isActive,
            'text-muted' => ! $isActive,
        ]);
@endphp

<td {{ $cellAttributes }}>{{ $order->title }}</td>

{{-- ✅ Boolean attribute - normal PHP-expression, without @js() --}}
<x-ui.button :disabled="$disabled">Save</x-ui.button>

{{-- ✅ "Attribute exists / no attribute" — ternary with null --}}
{{--    value null => Blade does not output the attribute at all --}}
<x-ui.button :disabled="$disabled ? true : null">Save</x-ui.button>


{{-- ============================================================= --}}
{{-- wire:model and wire:key — correct use --}}
{{-- ============================================================= --}}

{{-- ✅ wire:key is static in the markup and unique within a loop. --}}
{{--    Prefix by type + stable id models - experiencing --}}
{{--    reordering/deleting lines without out of sync DOM.       --}}
@foreach ($orders as $order)
    <div wire:key="order-{{ $order->id }}" class="border-b">
        {{-- modifiers wire:model are written directly in the attribute name, --}}
        {{-- not via conditional directives inside a line --}}
        <x-ui.input wire:model.live.debounce.300ms="form.titles.{{ $order->id }}" />
    </div>
@endforeach

{{-- ❌ wire:key from the loop index - breaks the binding when reorder/delete --}}
@foreach ($orders as $i => $order)
    <div wire:key="row-{{ $i }}">{{-- ... --}}</div>
@endforeach
