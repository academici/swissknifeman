# Целевая operating model

## Жёсткий каркас

До исполнения должны быть ясны: intent, acceptance, scope, запрещённые изменения, authority
gates, зависимости и следующий исполнимый срез. Неопределённость в одном из этих полей —
причина доработать контракт до старта.

## Свободный execution loop

Исполнитель может без перепроектирования:

- менять порядок независимых действий;
- объединять соседние пункты одной причинной области;
- исправлять найденный дефект в заявленных файлах и acceptance;
- выбирать focused validation и глубину review по фактическому риску diff;
- продолжать в текущей owning-сессии, пока контекст достаточен.

Это не разрешает менять acceptance, public/frozen semantics, security posture, authority,
необратимые действия или разрастаться в другую подсистему без решения владельца.

## Repair envelope

Локальный repair допустим, если он обратим, находится в заявленном scope, сохраняет acceptance
и не пересекает material boundary. Ориентир — одна-две причинно разные попытки. Это не
механический лимит: очевидный новый фикс по новому evidence может быть выполнен дальше.
Повтор того же fingerprint без нового evidence вызывает один scoped independent review.
После него продолжается исправление вперёд либо фиксируется реальный no-progress/material gate;
автоматической серии re-audit нет.

## Review trigger

| Ситуация | Действие |
|:--|:--|
| Low-risk, scope прежний, focused checks green | принять без отдельного аудита |
| Minor/nit finding | исправить и отметить в текущей сессии |
| Material diff или новый риск | один scoped review до acceptance |
| Scope/SHA/risk не изменились после review | переиспользовать verdict |
| Тот же failure fingerprint повторён | сменить тактику / один независимый review |
| Authority, security, irreversible, acceptance change | остановить и запросить владельца |

Для plan-audit детерминированный non-material bookkeeping defect является частным случаем первой
строки: repair и один gate rerun происходят в том же attempt; новый verdict cycle не создаётся.
Material/spec/authority finding остаётся за пределами этого envelope. RAG:— (repo-grounded: D11).

До любого stop/retry исполнитель применяет D12: наблюдает actual process/diff, минимально
воспроизводит сигнал, классифицирует его и только затем действует. Procedural/transient/
dependency-not-ready/unrelated-pre-existing не меняют product status; acceptance/safety/authority
останавливают только затронутый item. Unknown outcome non-idempotent write fail-closed до
reconciliation. RAG:✅ 2026-08-11 (`findings/06-cross-project-execution-telemetry.md`,
`research/07-adaptive-failure-and-telemetry-synthesis.md`).

## Группировка и сессии

Roadmap предлагает causal groups, но не создаёт cursor/lease/manifest. Owning-agent вправе
объединить или разделить соседние ready items, если зависимости и acceptance остаются
наблюдаемыми. Новая сессия нужна из-за реальной нехватки контекста/способности или
независимости проверки, а не потому, что закончился пункт.

## Field evidence

Основные признаки улучшения: сколько было сессий, design/audit passes, reopens, owner
interruptions и повторных чтений; смог ли агент закрыть малые отклонения сам; сохранились ли
границы. Автотесты проверяют синтаксис и критические переходы, но не объявляют UX протокола
успешным без живого canary.

Canary также измеряет control-plane stop tax: routing blocks, audit/retry loops, duplicate
terminals, cold starts, same-attempt recoveries и journal↔run join. D13 использует существующие
journal/run-report carriers; отсутствие optional telemetry остаётся coverage gap, а не новым
product gate.
