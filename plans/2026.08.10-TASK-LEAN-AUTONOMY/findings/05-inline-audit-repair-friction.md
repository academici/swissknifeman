# Field feedback — non-material audit repair must stay inline

Дата наблюдения: 2026-08-11.

## Наблюдение

Финальный design audit обнаружил единственный детерминированный bookkeeping-дефект: freshness date
`index.md` предшествовала уже перечисленному carrier от следующего дня. Executor path, item specs,
Routing, bundles и acceptance не были затронуты, однако первоначальная реакция сформировала
`ATTENTION` handoff вместо немедленного исправления одной строки. Владелец остановил этот путь как
точное воспроизведение проблемы плана: процедурная мелочь затормозила рабочий поток.

## Требуемая семантика

Текущий authoritative root исправляет non-material deterministic plan-bookkeeping defect inline,
регенерирует только owner-generated carriers, один раз повторяет детерминированные gates и завершает
тот же attempt. Новый audit/design pass/session не создаётся. Material/spec/acceptance и authority/
safety defects не попадают в этот envelope.

RAG:— (repo-grounded: `brief/01-refinements.md`, audit заход 4 и фактическая правка `index.md`).
