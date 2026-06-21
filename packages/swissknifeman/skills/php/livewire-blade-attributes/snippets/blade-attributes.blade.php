{{-- Source: anonymized production project --}}
{{--
    Дельта-гочизы Livewire 3: условные/динамические атрибуты Blade-компонентов.
    Универсальный паттерн — домены нейтральные (Order/Article/Document),
    компонент `<x-ui.input>` / `<x-ui.button>` — замените на свой UI-kit.
--}}

{{-- ============================================================= --}}
{{-- ПЛОХО: директивы и @js() ВНУТРИ списка атрибутов тега           --}}
{{-- Ломает парсер компонента: атрибут не разбирается, рендер падает --}}
{{-- ============================================================= --}}

{{-- ❌ @if/@endif между атрибутами --}}
<x-ui.input
    wire:model="form.quantity"
    @if ($step) step="{{ $step }}" @endif
    placeholder="Quantity"
/>

{{-- ❌ Условный wire:-атрибут на обычном теге --}}
<div class="flex flex-col gap-2" @if ($sortable) wire:sortable="reorderItems" @endif>
    {{-- ... --}}
</div>

{{-- ❌ @js() в значении атрибута --}}
<x-ui.button :disabled="@js($disabled)">Save</x-ui.button>

{{-- ❌ Условный модификатор внутри имени атрибута wire:model --}}
<input wire:model="@if ($live) live @endif='form.title'">


{{-- ============================================================= --}}
{{-- ХОРОШО: атрибуты собираются заранее в @php-блоке через         --}}
{{-- ComponentAttributeBag, затем разворачиваются одним {{ $bag }}  --}}
{{-- ============================================================= --}}

{{-- ✅ Условный атрибут через ->merge([...]) --}}
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

{{-- ✅ Тот же результат через массив + один конструктор Bag --}}
@php
    $row = ['class' => 'flex flex-col gap-2'];

    if ($sortable) {
        $row['wire:sortable'] = 'reorderItems';
    }
@endphp

<div {{ new \Illuminate\View\ComponentAttributeBag($row) }}>
    {{-- ... --}}
</div>

{{-- ✅ Классы — через ->class([...]) с условными ключами --}}
@php
    $cellAttributes = (new \Illuminate\View\ComponentAttributeBag([]))
        ->class([
            'px-3 py-2',
            'font-semibold' => $isActive,
            'text-muted' => ! $isActive,
        ]);
@endphp

<td {{ $cellAttributes }}>{{ $order->title }}</td>

{{-- ✅ Булев атрибут — обычное PHP-выражение, без @js() --}}
<x-ui.button :disabled="$disabled">Save</x-ui.button>

{{-- ✅ "Атрибут есть / атрибута нет" — тернарник с null --}}
{{--    значение null => Blade вообще не выводит атрибут --}}
<x-ui.button :disabled="$disabled ? true : null">Save</x-ui.button>


{{-- ============================================================= --}}
{{-- wire:model и wire:key — корректное использование               --}}
{{-- ============================================================= --}}

{{-- ✅ wire:key статичен в разметке и уникален в пределах цикла.    --}}
{{--    Префикс по типу + стабильный id модели — переживает         --}}
{{--    переупорядочивание/удаление строк без рассинхрона DOM.       --}}
@foreach ($orders as $order)
    <div wire:key="order-{{ $order->id }}" class="border-b">
        {{-- модификаторы wire:model пишутся прямо в имени атрибута,  --}}
        {{-- не через условные директивы внутри строки               --}}
        <x-ui.input wire:model.live.debounce.300ms="form.titles.{{ $order->id }}" />
    </div>
@endforeach

{{-- ❌ wire:key из индекса цикла — рвёт привязку при reorder/delete --}}
@foreach ($orders as $i => $order)
    <div wire:key="row-{{ $i }}">{{-- ... --}}</div>
@endforeach
