"""run — драйвер exec-волны (P4.2–P4.6, root/contracts/driver-plan-protocol-v2.md).

Четыре модуля, каждый со своим item'ом: `plan_reader` (очередь фазы, P4.2),
`worker` (запуск воркера, P4.3), `gate` (вердикт, P4.4), `journal` (журнал +
сводка волны, P4.5). CLI-склейка (`cmd_run`) — P4.6."""
