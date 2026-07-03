## Планы проекта — конвенция plan-protocol

Мастер-планы живут в `plans/<PLAN-ID>/` (`plan.md` + `phases/` + `handoff.md`) по протоколу
plan-protocol; плоский `.md` в `plans/` (кроме `ACTIVE.md`/`README.md`) — черновик plan mode,
разверни его: `/task:plan-design from-draft <файл>`. Активный план — `plans/ACTIVE.md`
(нет файла — единственный план 🟡). Статусы обновляются В ФАЙЛАХ плана, не в чате — работа
без обновления не завершена. Цикл: item/фаза закрыты → `handoff.md` перезаписан →
рекомендован `/clear`. Команды: `/task:plan-{design,exec,close,audit}`.
