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
- [Task launch-block parity](2026.09.13-task-final-launch-block-parity.md): `continue-root`
  продолжает ready batch в том же root; cold-start/wait final получает один native launch-block,
  а delivery не рекомендует design для уже детализированной фазы.
- [CoreX B-P3 local resource efficiency](2026.09.15-corex-p3-local-resource-efficiency.md):
  ограниченные repairs Task/Harness выполнены и выпущены в `v0.18.0`; измерение полного
  resource-effect остаётся отдельным условным исследованием.
- [Open-run final admission](2026.09.15-task-open-run-final-admission-regression.md):
  session-bound guard реализован и выпущен в `v0.18.0`; full transport acceptance не заявлен.

Machine-local receipt находится в `~/.swissknifeman/receipts/delivery/v0.16.0/`.
Он отдельно фиксирует успешные и заблокированные targets; публикация тега не означает GREEN delivery.
