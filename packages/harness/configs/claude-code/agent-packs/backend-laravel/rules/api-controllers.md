---
paths:
  - "**/Http/Controllers/**"
  - "**/routes/api.php"
  - "**/routes/web.php"
---

Canon access-layer (depth - skill `php:repositories`). Risk-layer: **data-integrity**
(authorization/access). On the review of this layer, turn on HTTP-checklist: authorization in policy/gate
(not in controller); per domain exception - HTTP-mapping (404/403/422/429);
contract test throws exception in script.

- Controller **thin**: read via `*Repository`, entry via Action; none
  `Model::query()/::create()/::where()/::all()/::find()` in the controller.
- Validation - FormRequest (not raw `request()->input()`); authorization — policy/gate
  or attribute, not inline.
- Recoil - Resource/Data (spatie/laravel-data), not `toArray()` models.
