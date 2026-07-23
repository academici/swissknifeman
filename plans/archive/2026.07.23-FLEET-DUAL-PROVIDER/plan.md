# 2026.07.23-FLEET-DUAL-PROVIDER — Fleet rollout двух провайдеров

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | 2026.07.23-FLEET-DUAL-PROVIDER |
| Title | Последовательная двухпровайдерная настройка проектов |
| Version | 0.9.1 |
| Status | 🟠 Done with deviations |
| Document Type | Executable Master Plan |
| Authoring Model | frontier |
| Design Passes | 3/3 — ecosystem-core fleet change: initial design, RED remediation, final cross-phase reconciliation |
| Last Updated | 2026-07-23 |
| Repository | swissknifeman |
| Related Packages | skiller · harness · maind |
| Execution Mode | phase-first |
| Target Operator Classes | implementation (exec) · frontier (design/audit) |
| Approval Owner | Dmitry Vostrikov — пользовательский запрос от 2026-07-23 |
| Home | repo:plans/2026.07.23-FLEET-DUAL-PROVIDER |

## 1. Context

Реализация dual-provider завершена, но первый fleet dry-run выявил, что connect
канал не может доставить Codex в consumer-репозитории. Требуется устранить этот
разрыв без неявной глобальной установки и без перезаписи user/managed drift.
После механизма раскатка идёт строго по одному зарегистрированному проекту,
фиксируя каждый сбой в плане и возвращаясь к owning source. Пропавшие временные
записи не являются целью автоматического удаления. RAG:— (repo-grounded:
findings/00-fleet-dry-run-2026-07-23.md).
P1 закрывает только synthetic/disposable conformance MVP. P2 сохранил D5–D7
evidence и internal owning fixes, но D14 вывел незавершённую раскатку по live
external consumers из terminal scope: она требует отдельного будущего
owner-authorized carrier и продолжает подчиняться D5–D7.

## 2. Execution Rules

- Каждый проект применяется только после его dry-run и проверяется health/managed locks.
- `--repair` применяется лишь к подтверждённому managed-drift; чужие конфликты не перезаписывать.
- Любой новый fleet-отказ сначала воспроизводится тестом и исправляется в owning package.
- Временные отсутствующие реестровые пути пропускать с явной находкой, не удалять автоматически.
- Один item за раз; после terminal item обновлять status, journal и handoff.

## 3. Routing

| Items | Model class/effort | Exec | Почему |
|:--|:--|:--|:--|
| P0.1 | frontier/high | manual | открытый fleet-contract carrier для внешнего Codex connect consumer |
| P0.2 | implementation/high | manual | меняет eligibility/failure semantics fleet sync |
| P1.1 | implementation/medium | plan-exec | детерминированный existing conformance CLI пишет только disposable roots и plan artifact |
| P1.2 | implementation/high | manual | conditional owning repair требует high verification |
| P2.1 | implementation/medium | plan-exec | plan-only commit→item/lint traceability с детерминированными git/lint gates |
| P2.2 | frontier/high | manual | D12-authorized consumer remediation: exact ownership/provider decisions и live external state |

## 4. Phase Index & Status Board

| Phase | Title | Items 🟢/всего | Status |
|:--|:--|:--|:--|
| P0 | Устранить блокер connect-проекции | 1/2 | 🟠 Done with deviations |
| P1 | Пилот и стабилизация | 1/2 | 🟢 Done |
| P2 | Последовательный fleet rollout | 1/2 | 🟠 Done with deviations |

## 5. Decision Log

| D# | Дата | Решение | Почему |
|:--|:--|:--|:--|
| D1 | 2026-07-23 | P1/P2 полностью детализированы до первого exec; carrier implementation остаётся P0 input. | Исполнимый fleet порядок и retry boundary должны быть проверяемы до provider writes. RAG:— (repo-grounded: findings/00-fleet-dry-run-2026-07-23.md) |
| D2 | 2026-07-23 | Drift остаётся fail-closed, repair — только явный. | Иначе автоматизация может стереть локальную работу. RAG:— (repo-grounded: packages/skiller/lib/skiller/skillset.py:857) |
| D3 | 2026-07-23 | Внешний Codex connect consumer получает repo-contained marketplace и self-contained selected plugin bundles под существующим artifact lock; self-host остаётся thin, install/cache/enable — отдельное user-level действие. | Официальный Codex manual подтверждает repo marketplace и contained local sources, frozen publication contract запрещает внешний thin path и implicit native install. RAG:✅ 2026-07-23 (`findings/P0.1-codex-connect-carrier-verification.md`, Build plugins). |
| D4 | 2026-07-23 | P0.1 включает owning generated Codex bundle, его conformance test, существующую CLI-документацию и `[Unreleased]`; внешняя копия обязана получать runtime tree уже из self-contained generated source. | Attempt 2 audit доказал, что downstream carrier не может восстановить runtime files, отсутствующие в generated `core`; repo `docs-maintenance`/`release-discipline` требуют синхронных user-facing docs и changelog. Spec синхронизирован до attempt 3; поздняя синхронизация docs/CHANGELOG в attempt 2 остаётся process deviation. RAG:— (`findings/P0.1-attempt2-independent-audit.md`). |
| D5 | 2026-07-23 | Owner directed P1.1 to skip `sibintek-insiders`: the actively worked consumer must not be mutated; redesign the pilot selection before retry. | P1.1 dry-run found unmanaged root instruction ownership and package-target absence; `--repair`/`--force` are outside scope. RAG:— (`findings/P1.1-pilot.md`). |
| D6 | 2026-07-23 | Consumer instruction scope is topology-derived: `root` always; each package scope only for its exact real package directory, preserving frozen order. Ordinary consumers do not receive synthetic swissknifeman package targets. | Existing mAInd broadens every request to all scopes while harness already accepts an ordered subset; this resolves the topology conflict without relaxing ownership or changing the harness contract. RAG:— (`research/01-pilot-selection-contract.md`). |
| D7 | 2026-07-23 | Replacement pilot is the first registry-order external candidate passing the complete no-write eligibility/provider/worktree/instruction preflight; D5 target and self-host are excluded. No match blocks without writes; repair/force stay forbidden. | Committed evidence does not prove a named next candidate, so deterministic selection is the only non-guessing carrier. RAG:— (`research/01-pilot-selection-contract.md`). |
| D8 | 2026-07-23 | Owner directed rollout to continue: P1.1 reopens as a fresh manual execution beginning with a new live registry-order D7 scan, not a pre-named candidate or a deferral. Exactly one normal apply remains conditional on one candidate passing the complete preflight. | Eligibility is live external state; the owner authorizes a new evidence pass but does not relax D5–D7, permit repair/force, or authorize overwriting dirty/unmanaged bytes. RAG:— (repo-grounded: `brief/01-refinements.md`). |
| D9 | 2026-07-23 | После двух зафиксированных пустых D7 scans P1.1 прекращает повторять registry scan и выбирает ровно один synthetic/disposable local temp-root dual-provider conformance carrier. Green закрывает только минимальный conformance MVP; red передаёт concrete owning defect в P1.2. Live external rollout остаётся P2 debt, а live consumers не являются target P1.1. | Owner разрешил минимальный disposable fixture без остановки; existing `maind sync --conformance` выполняет dual-provider apply/check и полный provider/provisioner dry-run только в `TemporaryDirectory`. Его внутренний temp-only repair case — safety control, не consumer repair и не разрешение CLI `--repair`. D5–D7 не ослабляются: `sibintek-insiders`, self-host, dirty/unmanaged bytes, `--repair` и `--force` остаются запрещены. RAG:— (repo-grounded: `brief/01-refinements.md`; `research/01-pilot-selection-contract.md`; `packages/maind/lib/maind/provision/sync.py:683-934`). |
| D10 | 2026-07-23 | P2 принимает D9 synthetic GREEN только как precondition, сначала закрывает plan-only P1.1 traceability carrier, затем заново применяет D5–D7 к каждому live consumer точными public per-project командами. | Disposable temp-root не доказывает eligibility или safety live consumer; audit P1 требует восстановить commit→item/lint traceability до первого consumer access, не реопеняя P1 и не переписывая append-only историю. RAG:— (repo-grounded: `phases/P1.md`, блок `Audit P1 — 2026-07-23`; D5–D9). |
| D11 | 2026-07-23 | После committed zero D7-set P2.2 прекращает omnibus scan и предлагает owner-gated read-only remediation diagnosis ровно для `azguard`; proposal не разрешает доступ. До отдельной Owner Approval записи D12 запрещены live inspection, dry-run, mutation и apply; после D12 diagnosis заканчивается preimage classification и новым mutation proposal, а не consumer write. | Dirty/non-Git/stale registry классы требуют project/registry authority; из committed clean roots только `azguard`/`botkit` имеют consumer-owned provider/MCP/instruction conflicts. Названный узкий diagnosis создаёт owning carrier без ослабления D5–D7. RAG:— (repo-grounded: `findings/P2.2-rollout.md`; `research/02-p2.2-remediation-boundary.md`). |
| D12 | 2026-07-23 | Owner одобрил автономное разрешение P2.2 consumer conflicts до terminal item без промежуточных micro-gates. Агент вправе диагностировать и минимально исправлять exact clean-consumer targets, затем выполнять D7 apply/health/no-op; новый повторяемый automation defect исправляется в owning source. D5–D7, `sibintek-insiders`, self-host, dirty worktrees, registry cleanup, `--repair` и `--force` остаются frozen exclusions. | Прямое распоряжение владельца «конфликты разруливай сам до полного завершения пункта» даёт authority на in-scope remediation, но не на стирание чужой работы или обход fail-closed gates. RAG:— (repo-grounded: `brief/01-refinements.md`, P2.2 Owner Approval). |
| D13 | 2026-07-23 | P2.2 сначала исправляет mAInd provider-context defect: exact registered root's regular `.swissknife.json#/providers` подаётся в существующий shared resolver как project layer; missing carrier сохраняет fleet/default behavior, unsafe/invalid carrier fail-closed до write. После green tests повторяется тот же `azguard` D7 dry-run. | `azguard` tracked carrier выбирает Claude+Codex, но `provider_projection_context` не передаёт project layer и наблюдаемо возвращает только fleet-default Claude. Shared resolver уже владеет precedence/schema; новый параллельный parser запрещён. RAG:— (repo-grounded: `findings/P2.2-azguard-remediation-diagnosis.md`; `packages/maind/lib/maind/provision/deploy.py:62-81`; `packages/maind/lib/maind/config.py:416-438`). |
| D14 | 2026-07-23 | Owner сузил P2.2 до внутренних swissknifeman fixes и запретил любой дальнейший доступ к live consumer repositories в этом item. D13, safe exact adoption и устранение duplicate Codex vendor carrier закрываются внутри пакетов; live consumer rollout, fleet dry-run и consumer commits отложены в отдельный будущий authority carrier. D5–D7, запрет `--repair`/`--force` и все frozen exclusions сохраняются. | Прямое owner scope change после обнаружения duplicate `.agents/skills` channel требует завершить owning automation fixes без продолжения внешней мутации. Это supersede только live-execution части D12 для P2.2, а не ослабление safety contract. RAG:— (repo-grounded: `brief/01-refinements.md`, P2.2 D14; `findings/P2.2-rollout.md`, Attempt 2). |
| D15 | 2026-07-23 | Owner потребовал завершить terminal plan без новых launch prompts: plan-only audit remediation, archive, push существующей ветки и ожидание CI выполняются в одном прогоне; P2 не реопеняется. | Все audit findings относятся к evidence/accounting, а не к сломанному product deliverable. Authority не включает consumer access, rollout, FOREMAN или merge PR #147. RAG:— (repo-grounded: `brief/01-refinements.md`, Terminal completion; `phases/P2.md`, Audit P2). |

## 6. Update Log

| Дата | Кто (role/model) | Что |
|:--|:--|:--|
| 2026-07-23 | issue-planner/frontier | Design pass 1/3: initial fleet dry-run converted into P0 carrier/eligibility design. |
| 2026-07-23 | issue-planner/frontier | Design pass 2/3: RED audit-1 разобран; добавлены parity acceptance, retry и полная карта rollout. |
| 2026-07-23 | issue-planner/frontier | Design pass 3/3: cross-phase reconciliation audit-2 — JIT removed, routing/files/budget reconciled. |
| 2026-07-23 | task-plan-run / gpt-5.6-sol/high | P0.1 закрыт: project-scoped Codex connect carrier публикует contained selected bundles с Claude parity — детали см. phases/P0.md P0.1 Completion Notes. |
| 2026-07-23 | root-review / gpt-5.6-sol/high | P0.1 переоткрыт, attempt 2: внешний bundle терял runtime support files (`snippets/`, `references/`, scripts/assets), поэтому claim self-contained не подтверждён. |
| 2026-07-23 | task-plan-run / gpt-5.6-sol/high | P0.1 закрыт attempt 2: runtime support tree доставляется с consumer exclusions и symlink-containment preflight — детали см. phases/P0.md P0.1 Completion Notes. |
| 2026-07-23 | independent-audit / gpt-5.6-sol/high | P0.1 attempt 2 RED: generated `core` остаётся thin; item переоткрыт attempt 3, spec синхронизирован D4. |
| 2026-07-23 | task-plan-run / gpt-5.6-sol/high | P0.1 закрыт attempt 3: owning generator публикует canonical runtime tree в generated `core` и внешний carrier — детали см. phases/P0.md P0.1 Completion Notes. |
| 2026-07-23 | independent-audit / gpt-5.6-sol/high | P0.1 attempt 3 GREEN: canonical → generated → external runtime transfer, exclusions, containment и commit topology подтверждены без findings. |
| 2026-07-23 | task-plan-run / gpt-5.6-terra/high | P0.2 закрыт с deviations: unavailable registry paths стали provider-qualified skips; no-write fleet rerun классифицировал consumer blockers — детали см. phases/P0.md P0.2 Completion Notes. |
| 2026-07-23 | task-plan-run / gpt-5.6-terra/high | P1.1 skipped by owner decision: `sibintek-insiders` не изменялся после fail-closed instruction dry-run — детали см. phases/P1.md P1.1 Completion Notes. |
| 2026-07-23 | task-plan-design / gpt-5.6-sol/xhigh | P1.1 redesigned and reopened by D6/D7: topology-derived instruction scopes plus deterministic replacement selection; item spec commit `7df01cbc`. |
| 2026-07-23 | task-plan-run / gpt-5.6-terra/high | P1.1 blocked: D6 repair is validated, but D7 selected no compatible external candidate — details in `phases/P1.md` P1.1 Completion Notes. |
| 2026-07-23 | task-plan-design / gpt-5.6-terra/high | P1.1 reopened by D8: rollout continues with a fresh non-named registry-order D7 scan and one conditional normal apply. |
| 2026-07-23 | task-plan-run / gpt-5.6-terra/high | P1.1 blocked: fresh D8 D7 scan found no dual-provider external candidate; no consumer write — details in `phases/P1.md` P1.1 Completion Notes. |
| 2026-07-23 | task-plan-design / frontier/high | P1.1 redesigned by D9: exhausted live selection replaced with one disposable temp-root conformance pilot; D5–D7 remain frozen. |
| 2026-07-23 | task-plan-exec / gpt-5.6/medium | P1.1 закрыт: D9 disposable dual-provider conformance carrier GREEN без live consumer/registry access — детали см. phases/P1.md P1.1 Completion Notes. |
| 2026-07-23 | task-plan-close / implementation/low | P1.2 пропущен по D9: conditional remediation не применима после GREEN P1.1 — детали см. phases/P1.md P1.2 Completion Notes. |
| 2026-07-23 | task-plan-close / implementation/low | P1 закрыта: disposable dual-provider conformance MVP подтверждён, conditional remediation пропущена по D9 — детали см. phases/P1.md Phase Handoff. |
| 2026-07-23 | task-plan-design / gpt-5.6-sol/high | P2 reconciled after P1 ATTENTION: добавлен plan-only traceability prerequisite и live rollout восстановлен по D5–D7 exact per-consumer commands; P1 не реопенялась. |
| 2026-07-23 | task-plan-exec / gpt-5.6-terra/medium | P2.1 закрыт: закреплён append-only P1.1 commit→item/lint carrier — детали см. phases/P2.md P2.1 Completion Notes. |
| 2026-07-23 | task-plan-run / gpt-5.6-terra/high | P2.2 заблокирован: live D7-set исчерпан без apply; per-consumer evidence и owning remediation — в findings/P2.2-rollout.md. |
| 2026-07-23 | task-plan-design / gpt-5.6-sol/high | P2.2 перепроектирован по D11: proposed `azguard` read-only diagnosis ждёт отдельного D12 Owner Approval; live consumer access не выполнялся. |
| 2026-07-23 | owner / Dmitry Vostrikov | D12: P2.2 получил authority на автономное conflict remediation до terminal item без ослабления D5–D7. |
| 2026-07-23 | task-plan-design / gpt-5.6-sol/high | D13: azguard diagnosis локализовал project-provider layer defect в mAInd; точный test-first owning repair добавлен в P2.2. |
| 2026-07-23 | owner / Dmitry Vostrikov | D14: P2.2 сужен до внутренних owning fixes; любой дальнейший live consumer access запрещён, rollout отложен без ослабления D5–D7. |
| 2026-07-23 | task-plan-run / gpt-5.6-sol/high | P2.2 закрыт по D14: project provider layer, exact managed adoption и canonical contained Codex carrier исправлены и провалидированы; live rollout deferred — детали см. phases/P2.md P2.2 Completion Notes. |
| 2026-07-23 | independent-acceptance / root | P2.2 reopened: already-desired exact adoption оставлял все actions NOOP и не записывал ownership lock. |
| 2026-07-23 | task-plan-run / gpt-5.6-sol/high | P2.2 закрыт fix-forward: already-desired adoption теперь атомарно переносит ownership и проходит ordinary no-op planning — детали см. phases/P2.md P2.2 Completion Notes. |
| 2026-07-23 | review-fix / gpt-5.6-sol/high | `24b4d080` устранил ruff regression в declared `provider_deploy.py` перед PR head `a86cf425`. |
| 2026-07-23 | task-plan-close / gpt-5.6-sol | P2 закрыта с D14 material deviation: internal fixes и evidence сверены до `a86cf425`; independent audit carrier подготовлен, live rollout не возобновлён. |
| 2026-07-23 | task-plan-audit / gpt-5.6-sol/xhigh | P2 audit ATTENTION: product validation GREEN; найдены шесть evidence/accounting defects — детали см. phases/P2.md Audit P2. |
| 2026-07-23 | task-plan-close / gpt-5.6-sol/xhigh | D15 terminal reconciliation: шесть audit findings закрыты plan-only carrier'ом; consumer boundary сохранён — детали см. findings/P2-audit-remediation.md. |
