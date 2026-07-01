---
paths:
  - "**/Http/Controllers/**"
  - "**/routes/api.php"
  - "**/routes/web.php"
---

Канон access-layer (глубина — скилл `php:repositories`). Risk-слой: **data-integrity**
(авторизация/access). На ревью этого слоя включай HTTP-чек-лист: авторизация в policy/gate
(не в контроллере); на каждое доменное исключение — HTTP-маппинг (404/403/422/429);
контрактный тест бросает исключение в сценарии.

- Контроллер **тонкий**: чтение через `*Repository`, запись через Action; никаких
  `Model::query()/::create()/::where()/::all()/::find()` в контроллере.
- Валидация — FormRequest (не сырой `request()->input()`); авторизация — policy/gate
  или атрибут, не инлайн.
- Отдача — Resource/Data (spatie/laravel-data), не `toArray()` модели.
