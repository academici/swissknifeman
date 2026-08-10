# 2026-08-09 — RED-аудит P5: реопен по §3

**Вход владельца:** `$ task:plan-design 2026.08.07-PLAN-ECONOMY P5` после RED-аудита уже
терминальной фазы. Первым источником служит блок `phases/P5/P5.md` →
`## Audit P5 — 2026-08-09`.

**Обязательный результат:** реоткрыть P5 по четырёхшаговому протоколу и довести remediation до
исполняемого ТЗ. Очередь обязана валидировать frozen request/response/auto-answer contract на
каждом ingress; только outcome `apply` вправе возобновить root, а `park`/`reject`/`escalate`
сохраняют fail-closed состояние и свежие item/status projections. Приёмка должна создавать события
реальными producer paths, покрыть policy auto-answer и owner `continue`/`park`/`reject`, а затем
воспроизводиться на названном item tree с явным bootstrap и committed report.

**Границы:** не менять frozen `decision-request` v1, `authority-frame` v1 и owner hash D143;
не менять P4 fingerprint/packet/`same_return_max`, reader-contract carrier paths, P6 и
`packages/artifex`. Finding о write-scope самой команды `plan-audit` остаётся отдельным
протокольным долгом и не является основанием расширять P5.
