# P6 design: measured home, bounded integration and reversible operation

## Sources and execution gate

This synthesis uses `findings/10-p6-productization-recon-2026-08-03.md`,
`findings/09-p5-pilot-economy-recon-2026-08-03.md`, `research/00-user-intent.md`,
`research/05-package-boundary-and-rollout.md`, `research/11-p5-pilot-economics-design.md`, root
and package canons, and the detailed P0–P5 specifications. P6 execution is forbidden until P5 is
terminal and its independent validator reproduces one exact GO/NO-GO over terminal P0–P4 hashes.
Planned manifests and approvals are preconditions, not facts already obtained. RAG:—
(repo-grounded plan state).

## Sequential productization ladder

| Item | Consumes | Produces | Stop condition |
|:--|:--|:--|:--|
| P6.1 | terminal P5 verdict plus candidate ownership | one home, router axis and exact scope | missing/ambiguous Owner authority or evidence |
| P6.2 | terminal P6.1 scope | roadmap return or one live runtime owner | out-of-scope/duplicate runtime/generated drift |
| P6.3 | terminal integration | default-off operations and rollback evidence, or a terminal zero-surface operations manifest on NO-GO | implicit enable, destructive/unsupported rollback, or missing NO-GO evidence carrier |
| P6.4 | all terminal P6 evidence | independent GREEN/RED audit | any skipped/degraded required check |

The ladder is strict and branch-preserving. A failure does not select another package or weaken a
gate. P6.4 runs in a different cold session and cannot repair what it audits.

## Product-home state machine

P6.1 validates terminal P5 first. `NO-GO` has one outcome: `roadmap-only`; the live tree gains no
runtime or generated distribution artifact. `GO` activates ownership classification:

1. `task-extension` is legal only when the candidate has collapsed to plan compilation/lifecycle
   mechanics and owns no durable run state, provider process, worktree or authority transition.
   Task remains plugin-only and gets no standalone/root group.
2. `harness-extension` is legal only when live Harness already owns every transition, state and
   acceptance decision, leaving the candidate as provider/environment launch mechanics. Reusing
   `harness run` must not create another scheduler or journal authority.
3. Retained supervisor store, scheduler, authority evaluator and worker lifecycle mean an
   independent capability. The outcome is `artifex-package`, but no integration scope becomes
   terminal until an exact Owner D# approves the sixth package. An umbrella command is a separate
   boolean and remains unchanged unless the D# explicitly approves it.

The decision is responsibility-based, not LOC-based. Ambiguous or mixed ownership stops at OWNER.
`core/` receives nothing until two live runtime consumers are demonstrated.

## Integration and provenance

P6.1 emits `integration-scope-v1.json`: exact source/destination paths, permitted generated outputs,
owning generators, validators, public surfaces, compatibility promises and D# references. P6.2
compares the intended and actual diff against this allowlist before writing.

On GO, plan-local candidate bytes remain immutable evidence but are never importable by the live
package. Runtime code is rewritten/moved into one owner with contract/golden parity and a manifest
mapping candidate hashes to product hashes. Generated manifests and docs snapshots are regenerated
only through owners. On NO-GO, P6.2 only updates the roadmap with failed floors, evidence links and
a measurable reactivation criterion. P6.3 then executes a bounded evidence-only branch: it produces
compatibility, rollback and operations carriers marked `roadmap-only`, pins the P6.1/P6.2 hashes and
proves zero package/root/generated surface; it is not skipped and creates no live product surface.

## Opt-in, compatibility and rollback

The product is `experimental` after GO, not generally available. No project/fleet/Brain target is
enabled automatically. Explicit local config or a command enables new starts; absence leaves manual
`task:plan-*` and current `harness run` behavior unchanged. A kill switch rejects new starts but
keeps inspect/resume/reconcile/rollback reachable.

State upgrades are fail-closed: validate source schema/hash, create a separate backup/copy, run the
new reader and prove downgrade/rollback postimages before switching. Never delete run history on
uninstall and never perform a silent in-place downgrade. Documentation names supported providers,
known hook/readiness limits, recovery semantics, opt-out and unsupported v1 surfaces; package docs
build standalone and in the umbrella aggregate. These live-surface requirements are GO-only; the
NO-GO branch instead closes on the validated zero-surface evidence set above.

## Cold audit contract

P6.4 records a different actor/session from P6.2/P6.3 and recomputes the branch from raw minimized
evidence. NO-GO is GREEN only if no live productization diff exists. GO is GREEN only with exact
authority, one runtime owner, default-off behavior, preserved old paths, reproducible rollback,
privacy-clean evidence, green package/root/docs/generated validation and no foreign capture. RED
names the owning item and yields a scoped remediation; it is not fixed by the auditor. GREEN permits
phase close, never tag/push/publish.

## Orchestration boundary

P6 is not a fan-out. The home must be frozen before integration; operations consume that exact
integration; audit consumes both and must be cold/independent. P6.1 may also wait on an Owner D#.
Therefore neither N≥3 independent items nor a long unattended external chain exists. No workflow is
declared. RAG:— (repo-grounded dependency graph and plan-protocol orchestration criterion).

## Ecosystem-core pre-mortem

| Failure after 6–12 months | Early signal | Mitigation | Owner |
|:--|:--|:--|:--|
| GO is treated as package/router approval | no exact D# but live root/package diff | separate package/router authority fields and fail-closed validator | P6.1 |
| Independent scheduler is hidden in Harness/Task | second journal/transition owner appears | responsibility predicates; ambiguity → OWNER | P6.1 |
| Prototype and package both keep running | imports from `plans/**` or divergent hash map | one live owner; plan bytes evidence-only | P6.2 |
| Generated/public surface drifts | hand-edited manifest or registry `--check` red | name and run each owning generator | P6.2/P6.3 |
| Experimental feature becomes fleet default | enablement without explicit local action | default-off config, no fleet/Brain writes | P6.3 |
| Upgrade strands old runs | in-place mutation, no verified backup/postimage | copy-upgrade plus downgrade/rollback drill | P6.3 |
| Kill switch prevents recovery too | inspect/resume/rollback unavailable when disabled | deny new starts only; preserve recovery surface | P6.3 |
| Auditor certifies its own assumptions | same actor/session or imports prior verdict functions | cold independent raw-evidence recomputation | P6.4 |
| NO-GO still ships leftovers | package/router/generated diff exists | zero-live-diff audit and roadmap-only manifest | P6.4 |
| Docs market N=5 as universal proof | maturity says available or unsupported scope omitted | `experimental`, bounded evidence and exclusions | P6.3/P6.4 |

## Stop condition and verification status

P6 design is ready when all branches, authority stops, finite scopes, migration/rollback proofs,
validation commands and audit independence are explicit. Execution remains closed until terminal P5.
GO without the selected-home authority remains a valid designed stop, not permission to improvise.

- RAG: no new external query; current repository/package/router/generator sources read directly.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: terminal P5 verdict, candidate ownership, exact Owner D#,
  integrated paths, migration/rollback evidence and cold audit remain P6 execution evidence.
- Обходки/[POSSIBLE-DEFECT]: none accepted; the current hook `stale-source` warning remains a hard
  assurance failure until repaired outside this design pass.
