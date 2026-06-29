---
paths:
<!-- pack:if IS_LARAVEL_PACKAGE -->  - "src/Http/Controllers/**"
<!-- pack:endif --><!-- pack:ifnot IS_LARAVEL_PACKAGE -->  - "app/Http/Controllers/**"
<!-- pack:endif -->  - "routes/api.php"
---

Канон access-layer (глубина — скилл `php:repositories`):

- Контроллер **тонкий**: чтение через `*Repository`, запись через Action; никаких
  `Model::query()/::create()/::where()/::all()/::find()` в контроллере.
- Валидация — FormRequest (не сырой `request()->input()`); авторизация — policy/gate
  или атрибут, не инлайн.
- Отдача — Resource/Data (spatie/laravel-data), не `toArray()` модели.
