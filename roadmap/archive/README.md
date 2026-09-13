# Архив реализованных полевых инцидентов

Оригинальные carrier сохранены без изменения текста. Их прежние статусы описывают момент
наблюдения; результат реализации — исходники, проверки и релиз `v0.16.0`.
Относительные ссылки внутри оригиналов относятся к их прежнему расположению в `roadmap/`.

- [Task opt-in routing](2026.09.12-task-opt-in-routing-not-mandatory-hub.md): текущий выбор
  владельца определяет маршрут; обычная разработка не создаёт план.
- [Interrupted predecessor](2026.09.13-task-interrupted-predecessor-recovery.md): typed diagnosis,
  durable start/resume и delayed successor bundle после terminal producer.
- [Owner authority/calendar](2026.09.11-plan-run-owner-authority-and-calendar-resume.md):
  finite declared grant из текущего owner message и typed external checkpoint.
- [Release-to-runtime](2026.09.11-release-to-runtime-attestation-and-recovery.md): immutable
  version gate, owner-union lock, проверка cache и явная delivery-команда с recovery/readback receipt.

Machine-local receipt находится в `~/.swissknifeman/receipts/delivery/v0.16.0/`.
Он отдельно фиксирует успешные и заблокированные targets; публикация тега не означает GREEN delivery.
