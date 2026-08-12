# P2 quality remediation design — 2026-08-11

## Design boundary

P2 — successor, а не продолжение исчерпанного P1 repair budget. Stable P1 specs, state, closed
carrier и оба audit verdict не меняются. Новая фаза исправляет только воспроизведённые defects,
сначала у Task owner, затем у Harness owner, после чего root canary заново квалифицирует итог.

## Execution sequence

`P2.1 Task green → P2.2 Harness green → P2.3 root live requalification → phase candidate audit`

Последовательность обязательна: Harness integration fixtures должны потреблять уже исправленный
Task fail-closed verifier, а canary не имеет смысла до зелёных package validators.

## Red-first acceptance matrix

| Case | До исправления | Требуемый outcome |
|:--|:--|:--|
| clean checkout без `docs/<pkg>` | `docs-sync --check` red | green, потому что expected tree успешно собран и materialized cache отсутствует |
| существующий stale aggregate | red | red с точным package path |
| v2 terminal state без write-site после cutoff | lint пропускает | ERROR; `Updated` берётся из journal owner model |
| phase resolver недоступен | citations возвращает clean | non-zero fail-closed diagnostic |
| v1 Harness fixture без required plan meta | secondary `ROUTING-UNRESOLVED` | fixture валиден; проверяется intended route outcome |
| v2 item-state без `Next`, handoff с semantic Next | driver unresolved | driver читает handoff и выбирает только допустимые item IDs |
| final canary с observed blocked/retry rows | часть строк исключается | каждая строка имеет class, reproduction, scope/delta, action, outcome |

## Anti-shortcuts

- Не ослаблять Task linter, verifier, Harness fail-safe routing или full validators ради green.
- Не добавлять `Next` в layout-v2 state и не копировать parser logic в Harness.
- Не признавать отсутствующий generated aggregate обязательным committed artifact: он gitignored;
  проверять owner generator, а stale существующий cache — отклонять.
- Не hand-edit provider projections, locks, golden commands, status/state/bundles/decision views.
- Не переписывать P1 evidence и не включать unrelated ARTIFEX/root-roadmap dirty files.

## Requalification

P2.3 фиксирует новый git/tree anchor, запускает Task, Harness и Skiller validators, provider/docs/
registry/plan checks и повторяет один live path. GO разрешён только если required checks green,
все observed stops классифицированы, `procedural_terminalization=0`, recovered procedural signal
остаётся same-attempt, а реальный material stop остаётся terminal в test/scorecard evidence.
