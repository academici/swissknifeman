# Sharp Edge: XSS in Blade

## Search patterns

```bash
grep -rnE '\{!!' resources/views/
grep -rnE '@js\(|Js::from\(' resources/views/ app/
grep -rnE 'v-html=' resources/js/ resources/views/
grep -rnE 'href="\{\{|\:href="' resources/views/ resources/js/
```

## What is considered a vulnerability

```blade
{{-- VULNERABLE: Unescaped output of user data --}}
{!! $comment->body !!}

{{-- SAFE: auto-escaping --}}
{{ $comment->body }}

{{-- VULNERABLE: custom URL in href — javascript: schema --}}
<a href="{{ $user->website }}">

{{-- VULNERABLE: data in an inline script without Js::from --}}
<script>const config = {!! json_encode($userData) !!};</script>
{{-- SAFE --}}
<script>const config = {{ Js::from($userData) }};</script>
```

## What to look for during verification

- `{!! !!}` justified only for trusted HTML (yours WYSIWYG after
  sanitization, render markdown via library with purify). Ask:
  who writes in this field?
- User input in HTML-attributes without quotes - escaping
  Blade does not prevent the attribute from being exited.
- `v-html` in Vue-components - the same `{!! !!}`.
- `json_encode` in `<script>` without flags `JSON_HEX_TAG|JSON_HEX_APOS` —
  closing tag `</script>` data string.

## Severity

- `{!! !!}` with a field that the user fills in - **high/critical**
  (critical, if the page is visible to other users - stored XSS).
- Custom URL in href/src without schema validation - **medium/high**.
- `{!! !!}` with constant/trusted source is not a godsend.
