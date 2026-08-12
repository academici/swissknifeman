# P2 final RED — owner outcome and P3 contract synthesis

## Входы

- финальный `Audit P2 — 2026-08-11`, заход 2, fingerprint
  `72d1c1ef97d96cd647766b0f350f4fb785309bec5e2112315a08e09002ffba7c`;
- D17 bounded audit cap и D18 successor pattern;
- явное owner approval D23;
- current Task sources `commands/plan-run.md`, `lib/task/route_evidence.py`,
  `lib/task/plan_bundle.py` и reproduced `docs-sync.sh --check` red.

Все выводы repo-grounded; внешних факт-классов в решении нет. RAG:—.

## F1–F6 → owning contract

| Finding | Класс | Owner outcome | Successor proof |
|:--|:--|:--|:--|
| F1: product writes внутри report-only P2.4 | material scope/acceptance | не back-attribute и не менять P2.4 spec | P3.2 квалифицирует полный `ba882c9f..P3.1` anchor и пишет только report |
| F2: `provider-config` принят как actual | fail-closed/public protocol | static config не доказательство текущего thread | P3.1 удаляет config fallback/allowlist; unknown останавливает dispatch до journal |
| F3: `docs-sync --check` red | acceptance | GO P2.4 не используется | P3.1 регенерирует aggregate; P3.2 повторяет check на новом anchor |
| F4: нет write-site в state | evidence integrity | post-hoc prose не заменяет terminal event | P3.2 закрывается только с exact `allow/allow` в journal/state |
| F5: stale under-routed handoff | owner navigation | прежний Next запрещён | D23 handoff указывает только P3 waiting/run |
| F6: duplicate D22 bundle read | generator/read budget | waiver отклонён | P3.1 dedupe + focused regression + fresh P2.3/P3 bundles |

## Контрактная граница

P3.1 владеет только Task source/generated/docs/ledger paths, перечисленными в его `Files`.
Provider-bound route telemetry не реализуется в этом плане: если provider API не отдаёт обе оси
активного thread, фактический route остаётся unknown и execution не стартует. Static config,
CLI selector, actor и owner prose не являются fallback. RAG:— (repo-grounded:
`roadmap/2026.08.11-codex-effective-route-observability.md`,
`packages/task/lib/task/route_evidence.py:41-46`, `packages/task/commands/plan-run.md:51-79`).

P3.2 — новый root canary, а не второй product repair. Он принимает terminal P3.1, перечисляет
каждый commit/path post-P2.3 anchor, повторяет все required gates и при любом red выдаёт ADJUST
без product write. P1/P2 audit history остаётся immutable.

## Outcome-projection limitation

Owner-approved `🟠` смысл P2 нельзя материализовать штатным `plan-close P2.4`: current compiler
возвращает `block:LOOP_BUDGET_EXCEEDED`/`n/a` после audit attempt 2. Generated state вручную не
редактируется и journal bypass не выполняется. До отдельного канонического owner-outcome carrier
решение D23 и handoff маркируют P2 `🟢` row как non-authoritative для qualification; это named
process limitation, не основание ослаблять P3 acceptance.
