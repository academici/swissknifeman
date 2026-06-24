---
paths:
  - "**/api/**"
  - "**/routers/**"
  - "**/views/**"
---

Эндпоинты ({{WEB_FRAMEWORK}}):

- Тонкий handler: валидация на границе (pydantic-модель / DRF-serializer), логика в service,
  доступ к данным в repository/ORM.
- Версионирование API; явные коды ответов и схемы ошибок.
- Без бизнес-логики во view; без прямого ORM в handler без слоя.
- SQL параметризован (нет f-string SQL); секреты из окружения.
