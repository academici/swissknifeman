# Острая грань: XSS в Blade

## Паттерны поиска

```bash
grep -rnE '\{!!' resources/views/
grep -rnE '@js\(|Js::from\(' resources/views/ app/
grep -rnE 'v-html=' resources/js/ resources/views/
grep -rnE 'href="\{\{|\:href="' resources/views/ resources/js/
```

## Что считается уязвимостью

```blade
{{-- УЯЗВИМО: неэкранированный вывод пользовательских данных --}}
{!! $comment->body !!}

{{-- БЕЗОПАСНО: автоэкранирование --}}
{{ $comment->body }}

{{-- УЯЗВИМО: пользовательский URL в href — javascript: схема --}}
<a href="{{ $user->website }}">

{{-- УЯЗВИМО: данные в инлайн-скрипт без Js::from --}}
<script>const config = {!! json_encode($userData) !!};</script>
{{-- БЕЗОПАСНО --}}
<script>const config = {{ Js::from($userData) }};</script>
```

## На что смотреть при верификации

- `{!! !!}` оправдан только для доверенного HTML (свой WYSIWYG после
  санитизации, рендер markdown через библиотеку с purify). Спросить:
  кто пишет в это поле?
- Пользовательский ввод в HTML-атрибутах без кавычек — экранирование
  Blade не спасает от выхода из атрибута.
- `v-html` во Vue-компонентах — тот же `{!! !!}`.
- `json_encode` в `<script>` без флагов `JSON_HEX_TAG|JSON_HEX_APOS` —
  закрытие тега `</script>` строкой данных.

## Severity

- `{!! !!}` с полем, которое заполняет пользователь, — **high/critical**
  (critical, если страница видна другим пользователям — stored XSS).
- Пользовательский URL в href/src без валидации схемы — **medium/high**.
- `{!! !!}` с константой/доверенным источником — не находка.
