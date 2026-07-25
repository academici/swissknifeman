# Instruction contract remediation — post-audit design

**Дата:** 2026-07-19  
**Основание:** `brief/00-brief.md`, `brief/01-refinements.md`, `journal.jsonl` — последняя
запись `item_id="design"`, `result="audit-red"`; repo-grounded механизмы
`core/block.py`, `packages/skiller/scripts/generate-hub.sh`,
`packages/maind/lib/maind/{health.py,provision/sync.py}`.

## Owner refinement

`AGENTS.md` является семантическим Codex-аналогом `CLAUDE.md` на root и package
уровнях. Оба provider-файла строятся из одного канона общих правил; байтовая
идентичность не требуется. Provider-specific дополнения разрешены только как явно
помеченные extensions и не могут отменять common rule без owner-approved superseding D#.
RAG:— (owner-grounded: remediation brief 2026-07-19)

## Executable carrier

| Слой | Единственный carrier | Обязанность |
|:--|:--|:--|
| Frozen semantics | `root/contracts/provider-instruction-contract.md` | scopes, semantic section IDs, projection rules, extension precedence, compatibility и diagnostics |
| Common source | `packages/harness/configs/common/instructions/catalog.json` + `packages/harness/configs/common/instructions/{root,packages/<package>}/{common,claude-code,codex}.md` | explicit ordered root/package inventory; `common.md` — общий канон, provider-файлы — только extensions |
| Renderer | `packages/harness/lib/harness/instructions.py` | pure catalog validation + independent `claude-code`/`codex` render plans через P2 artifact API |
| Managed targets | root `CLAUDE.md`/`AGENTS.md`; `packages/{skiller,harness,maind,analyst,task}/CLAUDE.md`/`AGENTS.md` | два раздельных managed blocks: common projection и provider extension; bytes вне markers user-owned |
| Provenance | P2 lock carrier `.swissknifeman/provider-artifacts.lock.json`, artifact kind `instruction-projection` | contract/catalog/fragment full source SHA-256, adapter ID/version, target, rendered SHA-256, managed marker IDs |
| Deploy/repair | P6.2 provider-aware onboard/sync provisioner | plan/check/apply/update/repair только по matching lock+markers; no implicit adoption |
| Independent gates | P5.7 conformance → P6.5 integrated checkpoint → P6.6 cold restart → P7.2 self-host → P7.3 cleanup → P7.4 audit | semantic parity, drift classes, repair boundary, legacy Claude compatibility и release evidence |

RAG:— (repo-grounded: `core/block.py` уже даёт marker/hash/upsert primitive;
`generate-hub.sh` уже умеет root-files `CLAUDE.md`/`AGENTS.md`; `maind` сейчас пишет
только Claude target и потому должен потребить provider projection в P6.2)

## Contract invariants

1. Для каждого explicit target scope exact set common semantic IDs одинаков в Claude
   и Codex projections; сравниваются IDs + normalized meaning, не bytes.
2. Provider extension имеет свой ID/owner/source и не маскируется под common section.
   Extension не может удалить/ослабить common rule; конфликт до write даёт diagnostic.
3. Managed block markers несут scope/provider/section-set identity; lock несёт full
   canonical source hash и rendered hash. Короткий content hash сам по себе недостаточен
   как provenance.
4. Existing path без matching marker+lock является unmanaged. Update не усыновляет его;
   repair меняет только managed blocks, сохраняет bytes вне markers и пишет backup по
   frozen artifact/instruction contracts.
5. Initial Claude migration проходит independent pre-change semantic inventory:
   обязательные правила, команды, package links и compatibility literals должны
   сохраниться. Provider-specific Claude content переезжает в `claude-code.md`, common —
   в `common.md`; fixtures не обновляются из actual render.
6. Root/package `AGENTS.md` обязан покрывать тот же common inventory и Codex-native
   extensions. Отсутствующий package AGENTS target, missing/extra/duplicate common ID,
   stale source hash, local managed drift или extension conflict делают conformance non-GREEN.
7. P7 не определяет schema/markers/hash/repair заново: он только вызывает public
   P5/P6 plan/check/apply/repair и проверяет evidence.

## Phase propagation

- **P5.6** замораживает contract и source layout до package implementation.
- **P5.7** реализует catalog/renderer, root+five-package projections в temp fixtures,
  provenance и independent semantic-parity/backward-compatibility conformance.
- **P6.2** заменяет Claude-only health/plan-convention writers на semantic intents,
  делегированные P5.7, и экспортирует provider-aware plan/check/apply/repair.
- **P6.5/P6.6** включают hashes, drift/repair proof и чтение root/package projections
  в durable checkpoint/cold-session proof.
- **P7.2/P7.3/P7.4** self-host, cleanup и release-аудит используют уже созданный механизм.

## Pre-mortem

| План провалился через 6–12 месяцев потому что… | Ранний сигнал | Mitigation / owner |
|:--|:--|:--|
| common IDs у Claude/Codex совпадают формально, но provider extension ослабил правило | extension повторяет/отрицает common ID, parity checker сравнивает только presence | P5.6 conflict semantics + negative goldens; P5.7 normalized meaning/override rejection; Owner утверждает contract |
| repair перезаписал ручной package guide или bytes вне markers | target существует без matching lock либо diff выходит за managed block | P5.6 unmanaged-by-default; P5.7/P6.2 outside-marker fixtures; P7.2 live owner D# + rollback |
| P7 подогнал schema/expected set под фактический self-host output | новый marker/hash/parser появляется впервые в P7 diff | P5.6/P5.7/P6.2 producer gates; P7 Code Guidance запрещает mechanism design; P7.4 independent expected inventory |
| restart прошёл только благодаря chat/bootstrap root AGENTS | checkpoint не содержит catalog/render hashes или P6.6 читает live file вместо committed evidence | P6.5 запекает source/render hashes и temp conformance artifact; P6.6 starts new session from disk+mAInd checkpoint |

RAG:— (repo-grounded: current managed writers и audit-red failure scenario)

## Audit/lifecycle residual

Design remediation не запускает `plan-lint` по прямому запрету владельца и не заявляет
GREEN. Историческая audit-row 11 содержит non-canonical free-form `friction`; append-only
правило запрещает её переписывать. Journal получает каноническую compensating
`audit-red` запись с `friction:["red-audit","deviation"]`; повторный аудит обязан
опубликовать текущий anchored lint count и отдельно оценить, принимает ли действующий
lint compensating semantics или сохраняет residual ERROR. RAG:— (repo-grounded:
`packages/task/lib/task/journal.py`, plan-journal contract §1/§2.1)

## Проверка (verification status)

- Repo-grounding: existing managed-block, dual-root-file hub и Claude-only maind writers
  прочитаны; carrier/phase mapping задан конкретными paths и predecessors.
- Внешних capability claims не добавлено; RAG не требовался.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: фактический anchored plan-lint count — сознательно
  не запускался в этом design remediation по ограничению владельца.
