# TASK-AUTHORITY-CARRIER-01 — Task Contract authority prerequisite

**State:** terminal
**Owner:** `packages/task` — Task Contract compiler and `plan-exec`/`plan-run` write-sites
**Blocks:** every Artifex execution item, beginning with P0.1
**Created from:** D64 defect · repeat `Audit design — 2026-08-03` F6 · D65 · third audit F7/F8 · D66
**Producer evidence:** pending
**Independent review artifact:** `artifacts/design/task-authority-carrier-01-review.md` (absent until the reviewer writes it)

This is the exact producer/carrier for the Task authority repair required before Artifex item
execution. It is not an Artifex product item and grants no owner transition. The carrier may move
from `waiting` to `terminal` only after the implementation commit and an independent review meet
every condition below; prose assurance, synthetic D#, caller-supplied authority kwargs or an
uncommitted diff cannot terminalize it.

## Required repair

1. Remove the plan-specific default `D50 (G-EXEC for self-host P0-P3)` from the live
   `task_contract.build()` authority path. No live Task runtime or canonical plan command may
   fabricate `authority.class`, `authority.granted` or `authority.granted_by` from that foreign
   plan decision.
2. Make the compiler resolve all three authority fields from a checked plan-native carrier.
   Routine continuation must identify its real plan/item carrier without inventing an owner
   grant. A requested protected transition must resolve an exact, non-revoked, scope-matching
   `[OWNER-GRANT:<gate-id>]` Decision Log record; missing, forged, revoked, ambiguous or
   wrong-scope carriers must fail closed with `block:AUTHORITY_BOUNDARY`.
3. Keep the two mandatory `plan-exec` boundaries and the inherited-route `plan-run` projection on
   the same resolver. Manual kwargs, a synthetic D-number and prose in this file are forbidden as
   production bypasses.
4. Preserve ordinary fleet compatibility: all 32 existing Artifex item specs must build and
   evaluate on their ordinary non-protected path without the foreign D50 provenance. The branch
   validators of P5.4/P6.1 remain authoritative for their conditional protected transitions;
   absent owner grants select refusal/NO-GO paths rather than blocking safe adjudication.

## Owned files and generation boundary

The producer owns only the minimum Task compiler/command/tests and their deterministic provider
projections required by the repair. Canonical sources are edited first; generated provider
artifacts are refreshed only through `python3 packages/task/scripts/render-provider-commands.py
--root .` and must pass the same command with `--check`. Existing unrelated dirty-worktree edits
are preserved and never reverted, stashed or bundled into the repair.

Expected source surface:

- `packages/task/lib/task/task_contract.py`
- `packages/task/commands/plan-exec.md`
- `packages/task/commands/plan-run.md`
- `packages/task/commands/plan-close.md` only if its shared pre-final call-site must change
- `packages/task/tests/test_task_contract.py`
- `packages/task/tests/test_canon_literals.py`
- deterministic outputs owned by `packages/task/scripts/render-provider-commands.py`
- `CHANGELOG.md` under `[Unreleased]`

Any required plan-schema or public-contract change outside that surface stops the producer and
returns to `task:plan-design`; it is not improvised inside the repair.

## Acceptance matrix

| Case | Required result |
|:--|:--|
| Ordinary Artifex item, all 32 existing IDs | build succeeds; both predicates allow under the routed actual route; `authority.granted_by` names the resolved current-plan carrier and never the foreign D50 |
| Exact later owner-grant marker, matching gate/branch/scope and not revoked | protected transition resolves deterministically and the authority predicate allows |
| Missing owner-grant marker | `pre_mutation = block:AUTHORITY_BOUNDARY` |
| Forged/synthetic D#, wrong gate, wrong branch or wrong scope | `pre_mutation = block:AUTHORITY_BOUNDARY` |
| Exact marker revoked by a later D# | `pre_mutation = block:AUTHORITY_BOUNDARY` |
| Caller attempts to restore the old D50 through manual authority kwargs | typed refusal or the checked carrier wins; never `allow` from the supplied string |
| Both command boundaries and `plan-run` inherited route | all invoke the same checked compiler/resolver; no prose-only or duplicated predicate |

## Terminal predicate

`State: terminal` is legal only when the carrier and its independent review artifact record all
of the following on committed trees:

- **Implementation commit:** a real commit hash whose scoped diff contains the repair and no
  unrelated worktree changes.
- **Removal check:** the live runtime/canonical command surface contains no foreign D50 default.
- **Positive/negative proof:** deterministic tests cover every row of the acceptance matrix.
- **Ordinary regression proof:** a repository script enumerates the 32 existing Artifex IDs,
  builds/evaluates each under its routed actual route, reports 32/32 allow for the ordinary path
  and zero foreign-D50 provenance.
- **Package checks:** `PYTHONPATH=packages/task/lib python3 -m unittest discover -s
  packages/task/tests -p 'test_task_contract.py'`, `PYTHONPATH=packages/task/lib python3 -m
  unittest discover -s packages/task/tests -p 'test_canon_literals.py'`, `python3
  packages/task/scripts/render-provider-commands.py --check --root .` and `bash
  packages/task/scripts/validate.sh` all exit 0.
- **Plan checks:** plan lint, `--conflicts` and strict citations remain green on the committed
  carrier update.
- **Independent verification:** a separately launched fresh frontier/xhigh reviewer writes
  `artifacts/design/task-authority-carrier-01-review.md`, records literal `GREEN`, the reviewed
  implementation commit, plan snapshot hash and exact positive/negative/32-build results, then
  updates the `Independent verification` section below. The producer cannot write that artifact,
  edit that section or change `State`; the reviewer cannot repair Task code while reviewing.

## Producer launch

**Next:** manual: implementation/high

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | repository-code-edit · task-contract-evaluate · provider-artifact-regenerate |
| Context | cold-start — plan-step |
| Суть | Исправить live Task authority carrier по точному контракту этого файла; Artifex items не исполнять |
| Команда | — |

```text
codex -C /home/vostrikov/projects/packages/swissknifeman/packages/task -m gpt-5.6-terra -c model_reasoning_effort="high" -a never -s danger-full-access

$ task:dev /home/vostrikov/projects/packages/swissknifeman/plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/design/task-authority-carrier-01.md

РЕЖИМ: отдельный implementation/high producer prerequisite, НЕ Artifex item execution и НЕ terminal review
ВХОД: абсолютный carrier path выше; /home/vostrikov/projects/packages/swissknifeman/plans/2026.08.03-ARTIFEX-SUPERVISOR/plan.md D64–D66 и последний Audit design (заход 3); AGENTS.md от repo root до packages/task
СКОУП: удалить чужой D50 default; вывести authority fields из проверяемого plan-native carrier; добавить acceptance-matrix и ordinary 32-build проверки; регенерировать только owned provider artifacts; прогнать package checks; создать scoped implementation commit; записать его hash и exact producer commands/results только в Producer evidence, сохранив State=waiting; завершить exact Reviewer/terminalizer launch ниже, но не запускать его в этой сессии
НЕ ТРОГАТЬ: State; Independent verification; task-authority-carrier-01-review.md; P0.1–P6.4 statuses/deliverables; Artifex product implementation; unrelated dirty worktree; provider/pilot/hook/package-home/docs/fleet/Brain/release state
```

## Producer evidence

**Status:** ready-for-review
**Implementation commit:** 635cbdb5717ce2438a17fa674338f7b8502cf0f7
**Producer route:** `gpt-5.6-terra/high`
**Commands/results:** Isolated detached worktree at implementation commit
`635cbdb5717ce2438a17fa674338f7b8502cf0f7` plus Artifex plan snapshot
`sha256:e052e6c840521aad1ec9397ad2210bea71793cb69b61102d56782599420c83f0`:
`python3 packages/task/scripts/render-provider-commands.py --check --root .` — exit 0/no-op;
`PYTHONPATH=packages/task/lib python3 -m unittest discover -s packages/task/tests -p
'test_task_contract.py'` — exit 0, 79 tests (including 32/32 ordinary Artifex builds);
`PYTHONPATH=packages/task/lib python3 -m unittest discover -s packages/task/tests -p
'test_canon_literals.py'` — exit 0, 15 tests; `bash packages/task/scripts/validate.sh` — exit 0,
485 tests; `python3 packages/task/scripts/plan-lint.py plans/2026.08.03-ARTIFEX-SUPERVISOR`
— exit 0 (0 errors/0 warnings); `PYTHONPATH=packages/task/lib python3
packages/task/scripts/plan-lint.py --conflicts` — exit 0 (0/0); `python3
packages/task/scripts/verify-plan-citations.py --strict plans/2026.08.03-ARTIFEX-SUPERVISOR` — exit 0 (2 checked/0
findings). Independent 32-item evaluation — 32/32 `{pre_mutation=allow, pre_final=allow}` and
zero foreign-D50 provenance. Protected-transition test matrix includes the exact allow plus
missing, valid-owner-message synthetic `D999`, valid-owner-message duplicate old `D50`, wrong
message reference, wrong gate, branch-superstring, scope-superstring, ambiguous exact/malformed
duplicates and revocation `block:AUTHORITY_BOUNDARY` cases. `codex
doctor --json`, `packages/maind/bin/maind health --cwd --json` and `packages/harness/bin/harness
doctor --provider-audit --json` — each exit 0; memory round-trip and both provider-trust rows are
green. The dirty producer worktree's direct renderer check remains exit 1 only on pre-existing
unrelated managed Codex artifact drift (`publication-lock`, `plan.close/design/exec`); no canonical
command or generated artifact belongs to this repair, and the isolated implementation-commit check
above is green.

The producer may replace only the four fields in this section after the scoped implementation
commit exists. `Status: ready-for-review` is legal only with a full commit hash and exact command
results. It must leave carrier `State: waiting`, must not create or edit the review artifact, and
must hand off the separate launch below.

## Reviewer/terminalizer launch

Run only after `Producer evidence` says `ready-for-review` and names an implementation commit.
This is a distinct cold session, not a continuation or subagent of the producer.

**Next:** manual: frontier/xhigh

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | xhigh |
| Capabilities | repository-read · adversarial-code-review · task-contract-evaluate · plan-evidence-write |
| Context | cold-start — plan-step |
| Суть | Независимо перепроверить implementation commit, записать durable GREEN/RED и единолично terminalize carrier только на полном GREEN |
| Команда | — |

```text
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c model_reasoning_effort="xhigh" -a never -s danger-full-access

TASK-AUTHORITY-CARRIER-01 REVIEW/TERMINALIZE

РЕЖИМ: отдельный cold frontier/xhigh reviewer/terminalizer; не продолжение producer session; Task implementation read-only
ВХОД: plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/design/task-authority-carrier-01.md и его Producer evidence/implementation commit; plans/2026.08.03-ARTIFEX-SUPERVISOR/plan.md D64–D66 и последний Audit design (заход 3); plans/2026.08.03-ARTIFEX-SUPERVISOR/roadmap.md; packages/task/AGENTS.md; packages/task/configs/command-routing.json
СКОУП: проверить scoped diff названного commit; независимо повторить removal, все positive/negative cases, command-boundary parity, ordinary 32-build evaluation, package checks и plan lint/conflicts/citations; на любом неполном conjunct записать durable RED в task-authority-carrier-01-review.md, оставить State=waiting и дать producer relaunch; только при полном GREEN записать durable GREEN с exact commands/results, reviewed commit и plan snapshot hash, обновить Independent verification, сменить State=terminal и commit только carrier/review evidence; P0.1 не запускать
НЕ ТРОГАТЬ: packages/task implementation и generated artifacts; Producer evidence; P0.1–P6.4 statuses/deliverables; Artifex product implementation; unrelated dirty worktree; provider/pilot/hook/package-home/docs/fleet/Brain/release state
```

## Durable reviewer record

The reviewer always writes `artifacts/design/task-authority-carrier-01-review.md`, on both GREEN
and RED. Its required fields are literal `**Verdict:** GREEN|RED`, `**Reviewer route:**
gpt-5.6-sol/xhigh`, `**Reviewed implementation commit:** <full sha>`, `**Plan snapshot:**
<sha256>`, an acceptance-matrix table with every case, and exact commands/exit codes/counts.
The review artifact plus this carrier update are committed together. RED must name every failed or
missing conjunct and keep `State: waiting`; GREEN may set `State: terminal` only after every
terminal predicate row is reproduced. An absent, uncommitted, producer-authored or non-literal
record is not evidence.

## Independent verification

**Verdict:** GREEN
**Reviewed implementation commit:** 635cbdb5717ce2438a17fa674338f7b8502cf0f7
**Review artifact:** `artifacts/design/task-authority-carrier-01-review.md` — Attempt 4
**Review evidence commit:** d96e7425994747d3895e990d668f117768d8df25
