# Open Questions — 2026.07.15-TELEMETRY-OPT

Трекер незакрытого (plan-protocol §3). Закрытое перемещается в Decision Log плана (D#).

| # | Вопрос | Статус | Владелец | Разрешение |
|:--|:--|:--|:--|:--|
| OQ-1 | Гранулярность P3-аудита: по task-командам (A) vs по phase-токенам (B, блокируется telemetry-gap) | Exploration | plan-design (при детализации P3) | — (см. plan.md ## Обсуждение №1) |
| OQ-2 | Контролируем ли мы ядро Workflow-тула CC для профилактики релончей, или только детекция+guidance | Resolved → D7 | P1.1 recon | Ядро — вне патча (не трогаем), но НЕ баг: async_launched + `<task-notification>` — документированный контракт, `resumeFromRunId` — санкционированный resume. Профилактика — детекция+guidance, см. findings/P1-workflow-rootcause.md |
| OQ-3 | Нужен ли добавочный хук-сигнал категоризации churn (not-read-first/edit-fail/reread) в run-report, сверх сырья `tool_failures`, или дисциплины anti-drift достаточно | Decision pending | P2.1 recon | дефолт D6 — дисциплина-first, хук-сигнал отложен; P2.1 подтверждает по данным (доминирующий драйвер + ценность категоризации для analyst) |
