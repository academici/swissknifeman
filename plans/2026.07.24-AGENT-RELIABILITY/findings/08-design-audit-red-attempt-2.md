# Design audit — 2026.07.24-AGENT-RELIABILITY — заход 2/2

**Дата:** 2026-07-24
**Режим:** fresh cold-context adversarial pre-exec design audit
**Вердикт: RED**

`AUDIT-CAP: design — 2/2, решение за владельцем.` Этот отчёт не назначает
remediation, третий design audit или P0.1.

## Anchor, preflight и deterministic gates

- `HEAD`: `454ea86d4ee381e0ff16c6c624a87fbc888343cc`.
- Audit-input plan snapshot до разрешённых audit writes:
  `sha256:f6cf58b45df0c5f8d5c253e4c9ca345b0977ebd1fa7fdbd07920692d7826be9e`.
  Команда:
  `find plans/2026.07.24-AGENT-RELIABILITY -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum`.
- Post-bookkeeping lint-input snapshot, исключающий только этот self-referential
  report carrier:
  `sha256:32e663b387f9a9b8906c7c79ae9f764079c28dc758a4f4f331a26d6aa43d115c`.
- Worktree до аудита уже содержал user-owned изменения:
  `CHANGELOG.md`, `docs/reference.md`, `plans/ACTIVE.md`, новый каталог этого
  плана и `tmp/`; аудит их не исправлял и не очищал.
- Live preflight: `codex doctor --json` = overall `ok`, effective
  `gpt-5.6-sol`, approval `Never`, filesystem unrestricted; все четыре
  effective global/project Codex hook commands существуют и executable;
  synthetic project `SessionStart` probe exit `0`; `maind health --cwd --json`
  = connected, memory roundtrip green. `codex plugin list --json` подтверждает
  enabled `core@0.4.0` и `task@0.3.0`.
- Source bundle: `verify`, `map-state`, `verify-results`,
  `verify-claim-inventory` завершились с exit `0`: 20 manifest entries, семь
  journal snapshots, пять cases, corrected stored denominators/control и
  восемь claim ranges.
- Scoped command
  `python3 packages/task/scripts/plan-lint.py plans/2026.07.24-AGENT-RELIABILITY`
  до и после audit bookkeeping: **0 ERROR / 0 WARN**, exit `0`.
- Current package conflict scan: `skiller registry --check` green;
  `packages/task/scripts/validate.sh` green (`228/228` tests);
  `packages/skiller/scripts/validate.sh` green (`418/418` tests, existing
  warning debt only); `git diff --check` exit `0`.

## Findings

### F1 — P0.1 требует семантическую проверку от immutable verifier, который её не выполняет

- **Severity:** Blocker
- **Label:** issue
- **Item:** P0.1 / D25 source-evidence contract
- **Evidence:** `phases/P0.md:30,33,35,37`;
  `artifacts/source-evidence/verify_source_bundle.py:26-95,102-111`;
  `artifacts/source-evidence/manifests/bundle-manifest.json:25`.
- **Failure scenario:** P0.1 утверждает, что именно
  `verify_source_bundle.py verify` валидирует provenance/redaction/selection
  полей и frozen corrected denominator/dedup/corpus/baseline invariants.
  Фактический `verify()` проверяет hashes/sizes/line counts, required key
  presence, exact case IDs и только stored `completed_turns=952` плюс число
  snapshots. Отдельный `verify_results()` лишь сравнивает ещё три сохранённые
  константы (`591`, `550`, `135110000`) и наличие control; он не пересчитывает
  их из семи journals и не вызывается P0.1 Validation. Значения provenance,
  selectors, timestamps, confidence и sanitization semantics не валидируются.
  Поэтому hash-green bundle может дать заявленный green, не доказав
  load-bearing semantic invariants, после чего P0.2/P0.3 заморозят контракт и
  acceptance на непроверенном основании.
- **Почему item неисполним как написан:** verifier сам hash-pinned в bundle,
  P0.1 Files не разрешает менять verifier/manifest, а Implementation Rules
  запрещают editing bundle bytes. Новый `write_verification_report.py` может
  добавить другую проверку, но не может сделать истинным точное обещание о
  существующем `verify` command без выхода за Files/contract.

### F2 — у 13 thin root adapters нет canonical sources и нет owning generator path

- **Severity:** Blocker
- **Label:** issue
- **Item:** P1.1/P1.2, D6/D27/D28
- **Evidence:** `AGENTS.md:10-11`; `packages/skiller/CLAUDE.md:9,61,87-99`;
  `phases/P1.md:28-38,47-57`; `phases/P2.md:55-57`;
  `packages/skiller/lib/skiller/registry.py:425-465`;
  `packages/skiller/lib/skiller/skillset.py:767-774,818-853`.
- **Failure scenario:** P1.2 обязуется заменить 13 manual full copies
  (`cross-project-optimizer`, `decision-verification`, `docs-maintenance`,
  `ecosystem-integration`, `ecosystem-mcp`, `ecosystem-setup`,
  `field-feedback-loop`, `harness-operations`, `maind-overview`,
  `package-architecture`, `project-tooling-runbook`, `release-discipline`,
  `skill-authoring`) на deterministically generated pointer/provenance-only
  adapters. Механический поиск дал **0/13** canonical
  `packages/skiller/skills/**/<name>/SKILL.md`. Root `AGENTS.md` запрещает
  canonical content вне `packages/skiller/skills/`/`packages/task/commands/`.
  P1.1 создаёт только contracts/maps; P1.2 Files не включает ни одного
  canonical skill source и исключает canonical skill text.
- Названный P1.2 registry writer генерирует skiller registry/index,
  package-local `core`/`skm` publications и marketplaces, но не пишет root
  `.agents/skills`. Единственный существующий Codex vendor writer находится в
  `skillset.py`, который отсутствует в P1.2 Files; даже он выбирает identities
  из skiller registry, где этих 13 names нет. Required Reads P1.2 и P2.2
  дополнительно требуют несуществующий
  `packages/skiller/skills/general/skill-authoring/SKILL.md`.
- **Итог:** исполнитель вынужден либо вручную переписать 13 adapters, нарушив
  D27 и root invariant, либо расширить Files/public seams/canonical content без
  P1.1-approved ownership/SemVer contract. P1.4 не может доказать generator
  closure постфактум, если producer отсутствует.

## Покрытие brief и проверено без дополнительных находок

| Brief/refinement thread | Исполнительный carrier | Результат audit |
|:--|:--|:--|
| portable evidence, corrected telemetry, falsifiable RCA, acceptance-before-mutation | P0.1–P0.3, D25/D26, committed source-evidence bundle | carrier есть; F1 делает первый item неисполняемым |
| hook lifecycle, cached/live path, rollback | P0.4 | порядок после G0, exact reads/files/validation согласованы |
| one semantic identity, provider projection, immutable version/tree, exact 12 deletions | P1.1–P1.4, D27/D28 | exact deletions/cold exactly-once carrier есть; F2 ломает 13-adapter producer closure |
| checked task outcome, fresh sequential dispatch, bounded review, real route evidence | P2.1–P2.5 | contract→implementation→conformance order согласован; P2.2 sole canonical edit, P2.3 runtime-only publication split сохранён |
| unified traces, metrics, eval gate, self-host proof | P3.1–P3.5 | producer order и terminal independent audit согласованы |
| architectural hypotheses, effective-source doctor, docs/release authority | P4.1–P4.3 | accept/reject/unknown и read-only P4.3 generated closure сохранены; G1 не исполняет rollout |

- Structural sweep: **21/21** item headings; scoped lint confirms required item
  schema/DoR. Routing = **21/21**; roadmap solo rows = **21/21**; semantic
  `Next`, `command.subagents` capability rows и native Codex commands =
  **21/21** each.
- Routing↔roadmap model class/effort, `plan-exec` versus manual
  `task:plan-run`, Review tier and dependency order agree. Каждый solo объясняет
  non-batching; no undeclared batch/workflow was found.
- Meta `Design Passes: 3/3` is backed by three design-pass lifecycle records
  plus append-only reconciliation; aborted pre-verdict inspection is not counted
  as a completed audit. This file is the second actual verdict.
- D26 is carried through P0 contract design, P2.1/P2.2 compiler/lint,
  P2.5/P3.3 conformance and P4.3 docs. External host/chat/mAInd/`tmp` paths are
  provenance/advisory rather than declared execution inputs.
- D27 version-first owner tuples, full generated trees/locks/marketplaces,
  no-op second checks and exact diff-scope guards are consistently assigned.
  P4.3 runs render/registry checks read-only and reopens the owning item on
  drift.
- D28 names exact six core plus six task root deletions after generated proof;
  P1.4 requires actual cold generated install/discovery and exactly-once
  resolution, not source counting or suppression.
- Contribution governance is required before new shared seams; P1.1/P2.1 freeze
  consumers, alternatives, ADR/SemVer and fail closed on Rule-of-Three-negative
  records.
- Only G0 and G1 remain Owner gates. P3.4 uses a task-specific `mktemp`
  disposable detached worktree, exact mutation allowlist, per-case commits and
  binary patches, clean switch rollback, non-force cleanup refusal on dirt,
  explicit native Codex flags, and no `HOME`/`CODEX_HOME`, reset/stash or
  main-worktree cleanup.

## Что запускать

`AUDIT-CAP: design — заход 2/2, решение за владельцем; P0.1, remediation и
третий audit не назначены.`

| Параметр | Значение |
|:--|:--|
| Model class | `frontier` |
| Effort | `xhigh` |
| Capabilities | `—` |
| Plan context | `cold-start — plan-step` |
| Model | `gpt-5.6-sol` |
| Thinking | `xhigh` |
| Approval policy | `never` |
| Sandbox | `danger-full-access` |
| Cwd | `/home/vostrikov/projects/packages/swissknifeman` |
| Context | `NEW SESSION` |
| Суть | Только Owner decision: остановить план либо явно расширить authority/cap для redesign и последующего independent audit |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="xhigh"' -a never -s danger-full-access 'NEW SESSION Owner decision boundary for 2026.07.24-AGENT-RELIABILITY after final design audit attempt 2/2 RED. Do not execute P0.1, do not repair the plan, and do not start a third design audit. Read AGENTS.md, CLAUDE.md, plans/2026.07.24-AGENT-RELIABILITY/findings/08-design-audit-red-attempt-2.md, plan.md, phases/P0.md, phases/P1.md and handoff.md. Present Dmitry Vostrikov only the exact capped choice: (A) stop/kill this plan, or (B) explicitly override the two-audit cap and grant new authority for a redesigned executable contract plus a later independent audit. Record no package, docs, plan-item, FOREMAN, fleet or consumer changes until the owner chooses.'
```
