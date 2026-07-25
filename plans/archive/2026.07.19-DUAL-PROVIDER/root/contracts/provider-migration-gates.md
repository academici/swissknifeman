# Provider migration gates

**Version:** v1.0.0

**Status:** frozen

**Approval Owner:** Dmitry Vostrikov

**Approval:** D59, 2026-07-20

**Inputs:** frozen D55 capability/artifact contracts and accepted ADR-0001

## Purpose

Этот контракт задаёт fail-closed preconditions для поэтапной dual-provider
migration, self-hosting `swissknifeman`, отдельного FOREMAN reconcile и будущей
fleet wave. Он не считает рабочую Codex-сессию, memory checkpoint, TODO,
draft или незакоммиченный output release evidence.

Каждый gate ниже называет exact producer item, evidence carrier, owner,
pass/fail rule и failure action. Отсутствующее, draft, stale, uncommitted,
unknown-major или невоспроизводимое evidence равно `fail`, а не `pending-pass`.

## Normative gate rules

1. Gate имеет ровно один outcome: `pass` или `fail`; неполный набор evidence
   классифицируется как `fail` для зависимого перехода.
2. Evidence MUST быть committed, tree-anchored и воспроизводимым названной
   командой. Prose `migration готова` не является evidence.
3. Producer не может сам заменить явный Approval Owner D# или independent audit.
4. Красный audit автоматически запускает D58 fix-forward в owning item/phase,
   после чего gate повторяется. Owner нужен только для frozen-contract
   change, новой authority или genuine owner fork.
5. `plans/2026.07.18-FOREMAN/**`, `plans/ACTIVE.md` и внешние fleet roots являются
   protected paths до того gate, который явно разрешает отдельную operation.

## Preconditions

| Gate | Transition | Exact producer item / verifier | Evidence path | Owner | Pass rule | failure action |
|:--|:--|:--|:--|:--|:--|:--|
| G01 | Начать P1.1 | P0.3, P0.4; `/task:plan-audit 2026.07.19-DUAL-PROVIDER P0` | `root/contracts/provider-{capability,artifact,migration-gates}.md`; `root/adr/0001-provider-adapter-architecture.md`; `phases/P0.md` `## Audit P0`; `plan.md` D55 + P0.4 approval D# | Approval Owner + independent P0 auditor | Три P0 contracts frozen v1.0.0, ADR accepted, P0 items terminal, audit literal GREEN, protected delta 0 | P1 остаётся `⬜ Not started`; reopen/fix-forward P0 и повторить audit |
| G02 | Начать P2.1 | P1.1–P1.4; `/task:plan-audit 2026.07.19-DUAL-PROVIDER P1` | `root/contracts/provider-config-contract.md`; `artifacts/P1-provider-compatibility-matrix.md`; `phases/P1.md` `## Audit P1` | P1.1 Approval Owner + independent P1 auditor | Config contract frozen v1.0.0; P1 items terminal; compatibility/no-write matrix green; audit GREEN; protected delta 0 | P2 не стартует; fix-forward P1, при contract change новый Owner D# |
| G03 | Перейти от skills publication к command work | P3.2, P3.5; `/task:plan-audit 2026.07.19-DUAL-PROVIDER P3` | `artifacts/P3-skill-publication-conformance.md`; `phases/P3.md` `## Audit P3` | P3.1 contract owner + independent P3 auditor | Claude marketplace/skills compatibility goldens зелёны; Codex catalog exact-set green; canonical skill IDs/parity совпадают; audit GREEN | P4.1 не стартует; repair P3 без manual dual-tree fork |
| G04 | Перейти от command work к harness | P4.3, P4.5; `/task:plan-audit 2026.07.19-DUAL-PROVIDER P4` | `root/contracts/provider-command-routing-contract.md`; `artifacts/P4-command-parity-conformance.md`; `phases/P4.md` `## Audit P4` | P4.1 Approval Owner + independent P4 auditor | Stable command IDs/routing frozen; Claude bodies/literals прошли compatibility; Codex native invocation и neutral routing fail-closed; audit GREEN | P5.1 не стартует; fix-forward P4, не downgrade provider semantics |
| G05 | Перейти от harness/instructions к deploy | P5.2, P5.5, P5.7; `/task:plan-audit 2026.07.19-DUAL-PROVIDER P5` | `root/contracts/provider-{harness,instruction}-contract.md`; `artifacts/P5-{harness,instruction}-conformance.md`; `phases/P5.md` `## Audit P5` | P5.1/P5.6 Approval Owner + independent P5 auditor | Claude compatibility green; Codex trust/approval/sandbox axes разделены; implicit full access отклоняется; root/package common IDs паритетны; audit GREEN | P6.1 не стартует; security regression чинится в P5 до deploy |
| G06 | Перейти к release/self-host phase | P6.5, P6.6; `/task:plan-audit 2026.07.19-DUAL-PROVIDER P6` | `artifacts/P6-integrated-conformance.md`; `artifacts/P6-bootstrap-checkpoint.md`; `artifacts/P6-cold-restart-evidence.md`; `phases/P6.md` `## Audit P6` | P6 independent auditor | Committed checkpoint повторён в cold session; both provider rows, instruction hashes, MCP/memory/analytics probes green; protected delta 0; audit GREEN | P7.1 не стартует; fix-forward P6 и новый cold proof |
| G07 | Начать self-host E2E | P7.1 | `artifacts/P7-provider-docs-conformance.md`; committed README/docs generated blocks | P7.1 executor, checked by P7.4 auditor | Capability/docs exact-set green, contract/catalog hashes указаны, Claude/Codex native examples валидны, full access не описан как default | P7.2 не начинает apply; repair docs/catalog projection |
| G08 | Перейти от isolated к live self-host install/update/drift/repair | P7.2 isolated stage | `artifacts/P7-self-host-e2e.md`; `findings/P7-self-host-probes-2026-07-19.md`; exact live path/action proposal | P7.2 Approval Owner | На anchored tree isolated Claude-only, Codex-only и dual matrices прошли plan→check(no-write)→apply→clean→second-noop→drift→repair→clean→rollback; explicit D# утверждает exact live scope | Live target не меняется; P7.2 остаётся in-progress до repair/re-approval |
| G09 | Начать bootstrap cleanup/release assembly | P7.2, then P7.3 inventory stage | `artifacts/P7-self-host-e2e.md`; `artifacts/P7-bootstrap-cleanup.md`; `artifacts/P7-release-manifest.md`; exact cleanup path/action proposal | P7.3 Approval Owner | Live self-host E2E green; every cleanup target имеет bootstrap ownership, generated replacement ID/hash, rollback bytes и post-removal dual smoke; explicit D# утверждает inventory | Cleanup остаётся read-only; unknown/user-owned/Claude-compatible path не удаляется |
| G10 | Открыть отдельный FOREMAN reconcile, не исполнять P1.4 | P7.4 cold adversarial audit | `artifacts/P7-release-audit.md`; `artifacts/P7-release-manifest.md`; `artifacts/P7-{self-host-e2e,bootstrap-cleanup}.md`; `artifacts/P6-cold-restart-evidence.md`; frozen bundle ниже; read-only donor `plans/2026.07.18-FOREMAN/plan.md` Status Board row `P1` и `handoff.md` | Independent P7.4 auditor + Approval Owner | Literal `P7.4 **Вердикт: GREEN**`, explicit Owner D#, committed clean release scope, both providers GREEN, rollback reproducible, donor FOREMAN delta 0 | `plans/2026.07.18-FOREMAN` остаётся paused; ATTENTION/RED маршрутизируется D58 fix-forward |
| G11 | Сохранить fleet no-write и открыть только future rollout-plan design | P7.4 final verifier; future rollout не является item этого плана | `artifacts/P7-release-audit.md` protected-path delta; future owner-approved separate fleet plan | Approval Owner future fleet plan | В DUAL-PROVIDER external fleet delta 0. Future plan допустим только после G10, terminal/audited provider-neutral FOREMAN reconcile и с cohorts, backups, rollback, provider selection, canary/stop rules | Любой fleet write в этом плане отклоняется; без separate approved plan outcome — no-op |

Gates срабатывают последовательно. Later GREEN не компенсирует
failed earlier gate, а регрессия после pass снова закрывает зависимый переход.

## Security profiles and independent knobs

Project Trust, Approval Policy и Sandbox Boundary являются тремя независимыми
inputs. `approval_policy=never` не доказывает trust и не расширяет sandbox.

| Semantic profile | Project Trust | Approval Policy | Sandbox Boundary | Full access rule |
|:--|:--|:--|:--|:--|
| `observe` | Не активирует project-owned executable surfaces | Provider-native read/check confirmation policy | Read-only/no-write boundary | Запрещён |
| `workspace-contained` | Explicit trusted project | Provider-native, может быть interactive или `never` | Только declared workspace/managed targets; external paths/network не расширяются из approval | Запрещён |
| `trusted-full-access` | Explicit trusted repository | Explicit operation value; не выводится из trust | Provider-native full-access boundary | Только explicit operation + named target + Approval Owner там, где gate этого требует; не наследуется из defaults/project/fleet |

Provider adapters MAY use native names and richer controls, but MUST preserve these
independent axes and fail closed when a requested boundary is unavailable or ambiguous.

## No-write and rollback invariants

- `plan`, `check`, `doctor` and `dry-run` MUST NOT change target, lock, backup, project config,
  FOREMAN, `plans/ACTIVE.md` or fleet roots.
- Before any P7.2/P7.3 live mutation, evidence records exact target/action set, pre-hashes,
  ownership, managed boundary, expected post-hashes, backup/rollback location and stop rule.
- Rollback is rehearsed on isolated roots before live apply. It restores only declared managed
  targets from captured bytes and MUST NOT overwrite user-owned bytes or bytes outside markers.
- Partial provider failure makes the aggregate non-GREEN. Success of one Provider never masks
  failure, unsupported requirement, untrusted state or drift conflict of another required Provider.
- After mutation, a second apply MUST be an empty diff and check MUST classify every required
  artifact `clean`; otherwise rollback remains available and the dependent gate fails.
- Bootstrap cleanup is not `rm stale paths`: it requires ownership, replacement identity/hash,
  dual-provider smoke, captured rollback bytes and exact Owner-approved action inventory.

## Exact FOREMAN handoff bundle

G10 opens only a separate provider-neutral reconcile. It does not edit or execute FOREMAN and
does not authorize P1.4 directly. The cold-start bundle MUST contain:

1. frozen `provider-capability-contract.md`, `provider-artifact-contract.md` and this contract,
   with Approval D# and ADR-0001;
2. frozen `provider-command-routing-contract.md` from P4.1 and the P4 parity conformance report;
3. P6 cold-restart evidence proving durable provider/instruction/MCP/memory/analytics state;
4. P7 docs conformance, self-host E2E, bootstrap-cleanup, release manifest and adversarial audit;
5. a version/hash table for every downstream frozen contract referenced by the release manifest;
6. the read-only donor snapshot: `plans/2026.07.18-FOREMAN` Status Board row `P1` and handoff
   waiting condition, with before/after delta 0;
7. a self-contained reconcile launch payload naming inputs, allowed scope and anti-scope.
8. a donor command-surface correction: read-only FOREMAN D35/P4.4 still names obsolete
   `maind memory store`; reconcile MUST replace it with effective CLI
   `maind memory remember` or native MCP `maind_memory_store` before P4.4 execution.

The reconcile must decide how FOREMAN consumes neutral command/routing and provider invocation.
Until that separate decision is committed and audited, the donor handoff condition remains unmet.
P0.4 records this defect but MUST NOT repair the paused donor in place.

## Fleet boundary

This plan has no fleet-write operation. G11 proves a no-op over external projects; it does not
pre-approve rollout. A later fleet plan is a new authority boundary and MUST define cohorts,
canary order, backups, tested rollback, per-project provider selection, protected/user-owned
surfaces, failure thresholds and stop/resume rules after the FOREMAN reconcile is terminal.

## Compatibility and notification

- **major:** changes a gate transition, pass/fail meaning, owner authority, protected boundary,
  security-axis independence, rollback invariant, FOREMAN bundle or fleet no-write rule;
- **minor:** adds a fail-closed gate/evidence field without weakening existing transitions;
- **patch:** clarifies wording or diagnostics without changing required evidence/outcome.

Unknown major fails closed. After freeze or later SemVer change, the donor Contracts row and
all same-root consumers are updated in one bookkeeping cycle; cross-repo consumers receive an
explicit mAInd/open-risk notification.

## Validation

Validation MUST prove:

1. gate IDs are unique and every row has transition, exact producer/verifier, evidence, owner,
   pass rule and failure action;
2. P1/P2 entry, Claude compatibility, Codex security, self-host install/update/drift/repair,
   bootstrap cleanup, P7.4/FOREMAN and fleet no-write are all represented;
3. the frozen D55 contracts/ADR are inputs and no Rendered Artifact becomes source;
4. trust, approval and sandbox remain independent and full access is explicit only;
5. every check/dry-run and protected-path comparison is no-write;
6. G10 requires literal P7.4 GREEN plus Owner D# and leaves FOREMAN byte-identical;
7. G11 requires a separate fleet plan and cannot authorize rollout from this contract.

## Approved Owner decision set (D59)

D59 freezes v1.0.0 and approves together:

1. G01–G11 transitions, producers, evidence carriers, owners, pass/fail rules and failure actions;
2. independent Project Trust / Approval Policy / Sandbox Boundary and explicit-only full access;
3. no-write, rollback, partial-provider and bootstrap-cleanup invariants;
4. the exact G10 FOREMAN handoff bundle and its reconcile-only authority;
5. fleet no-op in this plan and the separate post-FOREMAN rollout-plan condition;
6. pre-mortem traceability in `research/03-p0-design-and-premortem.md`;
7. no permission to edit/execute FOREMAN, fleet or future package implementation in P0.4.
