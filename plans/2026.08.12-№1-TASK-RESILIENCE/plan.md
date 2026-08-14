# 2026.08.12-№1-TASK-RESILIENCE — План №1 — Continue-first Task

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | 2026.08.12-№1-TASK-RESILIENCE |
| Title | План №1 — Continue-first Task |
| Layout | v2 |
| Document Type | Executable Master Plan |
| Authoring Model | frontier/high |
| Repository | swissknifeman |
| Related Packages | task · skiller · harness · maind |
| Execution Mode | phase-first, continue-root, acceptance-led |
| Target Operator Classes | implementation (exec) · economy (mechanical checks) · frontier (design/audit) |
| Approval Owner | repository owner |
| Home | repo:swissknifeman |
| Design Passes | 3/3 — pass 3 оформил owner-authorized постархивное P7-продолжение по pinned working-tree и roadmap snapshots |
| visibility | private |
| Paused By | — |

## 1. Context

Task слишком рано превращает route/tool/projection/local repair signal в terminal
`Blocked`, escalation, новый design pass или преждевременный `final`. Это создаёт петлю:
задача не началась, но уже терминальна, поэтому её нельзя безопасно продолжить.
План построил continue-first контур P0–P6: evidence baseline, cutover v1→v2,
идентичность плана, nonterminal observations/local repair, подтверждение
реальной блокировки, terminal delivery и release/rollout. Уже написанный код
считается лишь release candidate: каждая фаза отдельно сверяет его с ТЗ и
чинит расхождения до релиза. Phase audit завершает этот контур как audit-fixer:
находит и сам исправляет безопасные in-scope отклонения в одном свежем root. RAG:✅ 2026-08-12 (Perplexity Web: Temporal,
Microsoft Durable Functions; synthesis и URLs —
`findings/02-rag-resilience-and-schema-cutover-2026-08-12.md`).

После архивирования владелец авторизовал P7 как узкое постархивное продолжение: принять уже
существующий working-tree candidate, сохранить использованные roadmap-источники с проверяемой
диспозицией, довести Task runtime/canon/projections до зелёных package gates и снова вернуть план
в архив. P0–P6, локальные `v0.13.0`/`v0.13.1`/`v0.13.2`, release evidence и rollout immutable;
P7 не получает authority на новый tag, push, GitHub release или повторный rollout. RAG:—
(repo-grounded: D32, `findings/29-P7-postarchive-working-tree-inventory.md`,
`research/11-P7-postarchive-continuation-design.md`).

## 2. Execution Rules

- P0–P6 терминальны и не переисполняются; единственный live execution scope — P7.0 → P7.5, статус берётся только из generated state.
- Каждый P7 item запускается отдельной свежей owner-сессией; после terminal handoff текущий root не продолжает следующий item молча.
- Внутри фазы запускать stable Batch из §3 целиком; каждый item всё равно проходит собственные validation/commit/state/receipt. Phase audit/close — жёсткая граница группы.
- P1 сначала мигрирует все active v1 plans, затем удаляет v1 execution schema/path; обратный порядок запрещён.
- Любой failure signal проходит `observe → minimal reproduce → classify → act → verify`.
- Procedural/transient/dependency/tool-noise/stale projection и bounded local reversible defect чинятся inline; это nonterminal `local-repair`.
- Route rejection, pending decision, local repair и block candidate не меняют item status/attempt.
- Внешний block candidate обязан иметь verified RAG; покрытие external-класса — 100%.
- Если план требует Perplexity Web, пустой/недоступный ответ после bounded retry пишет
  nonterminal `rag-pending`: fallback не закрывает item/phase и не разрешает terminal verdict.
- Terminal `Blocked`/escalation до одного свежего isolated reviewer verdict `JUSTIFIED` запрещены.
- `AVOIDABLE` возвращает root в repair; `INSUFFICIENT_EVIDENCE` — в сбор evidence; reviewer не даёт authority.
- Phase audit — audit-fixer: все безопасные in-scope находки чинятся, валидируются и перепривязываются к candidate в одном audit root; отдельный repair-run/второй audit не создаются.
- Сложность, объём validation, generator drift, unrelated dirty tree и незапущенный downstream consumer — nonterminal; останавливают только доказанные authority/safety/public/frozen/acceptance boundaries.
- Material safety/authority/frozen/public/acceptance boundary не автофиксится.
- Generated provider/docs/registry/state/bundle носители менятся только owning generator.
- Кодовая/docstring/PR/review ссылка на item: `2026.08.12-№1-TASK-RESILIENCE Pn.m`; bare `Pn.m` — только внутри этого плана.
- Каждый item получает product commit и отдельный bookkeeping commit; посторонний дифф не стейджить.
- Tag `v0.13.0` создаётся только после terminal P6.1; rollout — только по уже зарегистрированным project/channel.
- Push/GitHub release без отдельного owner instruction не выполнять.
- После terminal P7, GREEN phase audit и `task:plan-close P7` выполнить отдельный `task:plan-close archive 2026.08.12-№1-TASK-RESILIENCE`; до этого active-path сохраняется.

## 3. Routing

| Batch | Items | Model class/effort | Exec | Review | Почему |
|:--|:--|:--|:--|:--|:--|
| B-P0-EVIDENCE | P0.1 | frontier/high | manual | full | общий gap→acceptance producer chain; закрыто |
| B-P0-EVIDENCE | P0.2 | frontier/high | manual | full | reuse gap matrix и acceptance boundary; закрыто |
| solo | P0.3 | frontier/high | manual | full | отдельная Perplexity capability и mandatory evidence checkpoint |
| B-P1-MIGRATOR | P1.1 | frontier/high | manual | full | closed inventory producer питает compatibility/policy в той же fleet context |
| B-P1-MIGRATOR | P1.2 | implementation/high | manual | full | узкая Routing-нормализация переиспользует 15-target rehearsal и migrator tests |
| B-P1-MIGRATOR | P1.3 | frontier/high | manual | full | frozen migration policy и dry-run admission всех 15 targets делят тот же migrator/matrix context |
| B-P1-FLEET | P1.4 | implementation/high | manual | full | отдельная external-write boundary: применить approved previews и доказать zero-live |
| B-P1-FLEET | P1.5 | implementation/high | manual | full | removal сразу после zero-live ledger, без повторной fleet reconnaissance |
| B-P2-IDENTITY | P2.1 | implementation/high | manual | full | общий PLAN-ID parser/linter/canon context |
| B-P2-IDENTITY | P2.2 | implementation/high | manual | full | qualified refs потребляют identity grammar и provider surface |
| B-P3-CONTINUE | P3.1 | implementation/high | manual | full | state semantics питают command repair flow |
| B-P3-CONTINUE | P3.2 | implementation/high | manual | full | общие Task commands/tests и nonterminal contract |
| B-P3-CONTINUE | P3.3 | implementation/high | manual | light | узкий lint predicate использует тот же false-stop/plan canon context |
| B-P4-BLOCK | P4.1 | implementation/high | manual | full | candidate schema/reducer — producer confirmer flow |
| B-P4-BLOCK | P4.2 | frontier/high | manual | full | reuse block/RAG fixtures; batch route повышается до frontier/high |
| solo | P5.1 | implementation/high | manual | full | item уже терминален до D24 redesign; его frozen receipt evidence не переиспользует execution context в recovery P5.2 |
| solo | P5.2 | implementation/high | manual | full | historical terminal block и D24 redesign требуют отдельный recovery launch; P5.1 уже терминален, а P5.3 — другая package-scope boundary |
| solo | P5.3 | implementation/high | manual | full | package-scope restart в `packages/skiller` и cross-package owning generators/docs — hard context boundary после canonical P5.2 producer |
| solo | P6.1 | implementation/high | manual | full | clean committed release-tree gate перед side effect |
| solo | P6.2 | implementation/high | manual | full | owner-authorized frozen-release recovery требует нового exact v0.13.2 candidate с byte-fresh carriers; старые tags immutable |
| solo | P6.3 | implementation/medium | plan-exec | full | irreversible annotated-tag boundary отделена от release requalification |
| solo | P6.4 | implementation/high | manual | full | external registered-project rollout после verified tag capsule |
| solo | P7.0 | implementation/high | manual | full | bootstrap hard boundary: current candidate linter applies new terminal/audit rules to immutable historical rows, so repair must precede ordinary Task dispatch |
| solo | P7.1 | implementation/high | manual | full | отдельный fresh-root/commit boundary для route, journal и terminal-state runtime core; owner запретил смешивать с последующими срезами |
| solo | P7.2 | implementation/high | manual | full | delivery/lint потребляют уже запечатанный P7.1 state contract и имеют собственный fail-closed regression surface |
| solo | P7.3 | implementation/high | manual | full | schema/rubric/reducer и material phase fingerprint образуют отдельную audit/block safety boundary |
| solo | P7.4 | implementation/high | manual | full | canonical commands и owning generators меняются только после стабилизации runtime; cross-package generated-output boundary |
| solo | P7.5 | implementation/high | manual | full | aggregate package/docs/roadmap closeout и staged deletion set проверяются в отдельном fresh root перед phase audit |

## 5. Decision Log

Каталог решений: `decisions/`; собрать:
`python3 packages/task/scripts/plan-views.py decisions --plan-dir plans/2026.08.12-№1-TASK-RESILIENCE`.

## 7. Contracts

### Exported

| Контракт | Версия | Статус | Потребители | Уведомлены |
|:--|:--|:--|:--|:--|
| numbered-plan-identity | v1.0.0 | candidate | plan-protocol, plan-lint, Task provider commands | P2/P5 |
| plan-layout-v2-only-execution | v1.0.0 | candidate | Task readers, commands, active plan fleet | P1/P5/P6 |
| continue-first-block-policy | v1.0.0 | candidate | Task commands, journal/state, provider adapters | P3/P4/P5 |
| terminal-delivery-receipt | v1.0.0 | candidate | Task commands and provider delivery seam | P5 |
| phase-audit-fixer | v1.0.0 | candidate | Task audit/close, plan-protocol, provider adapters | P5/P6 |

## Проверка (verification status)

- RAG: до ремонта моста `perplexity-web` x7 → 1 ответ, 6 `No answer found`; после
  `perplexity-web-mcp` commit `d77ce0e` повторены `search`/`advanced`/`deep` → 660/1192/8462
  символов, у basic/deep есть official sources. Выжимка и URLs — в findings/02.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: ничего; обязательный Perplexity gate закрыт успешным rerun,
  а не WebSearch fallback.
- Обходки/[POSSIBLE-DEFECT]: нет; временная DOM-диагностика удалена, bridge regression покрыт
  51 passed + 1 skipped package tests и тремя живыми MCP-вызовами.
- P7: execution ещё не начиналось; DoR опирается только на pinned working-tree/snapshot evidence,
  а зелёные runtime/package/docs verdicts обязаны появиться в terminal evidence P7.1–P7.5.
