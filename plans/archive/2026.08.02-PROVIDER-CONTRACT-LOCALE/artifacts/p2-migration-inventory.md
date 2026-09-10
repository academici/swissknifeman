# Migration inventory archive

## 1

2026.08.02-PROVIDER-CONTRACT-LOCALE

## 2

Provider control plane, localization, and fleet recovery

## 3

1.0.5

## 4

🟡 In progress

## 5

Executable Master Plan

## 6

gpt-5.6-sol/high

## 7

2026-08-03

## 8

swissknifeman

## 9

skiller · harness · maind · task · core

## 10

phase-first, contract-first

## 11

implementation (execution) · economy (recon) · frontier (design/audit)

## 12

repository owner

## 13

repo:swissknifeman

## 14

private

## 15

2026.08.03-ARTIFEX-SUPERVISOR, 2026-08-03

## 16

3/3 — cross-phase `finish` plus targeted audit remediation F1–F25 reconciled all P0–P7 contracts, brief coverage, routing and the final execution roadmap; repeated independent design audit is next

## 17

⬜ Not started

## 18

Создать запечатанный, пофайловый и per-provider baseline для всех текущих записей project registry и самого SKM, отделяя committed от worktree state. RAG:— (repo-grounded: `brief/00-brief.md`, `~/.swissknifeman/projects.json`, predecessor P0 sealed inventory pattern)

## 19

`findings/03-current-defects-2026-08-02.md` называет counts и семь проблемных consumer paths, но не несёт команд, пофайловых строк и tree anchors; без них health флота недоказуем. RAG:— (repo-grounded: `findings/03-current-defects-2026-08-02.md`, plan D8)

## 20

Все existing records из `~/.swissknifeman/projects.json`; для каждого — stable redacted project ID, repo HEAD/status-path set, provider selection, каждый provider-relevant relative path, node/symlink/managed/tracked state, secret-safe structural/content digest, Claude/Codex health/trust/capability status, channel overlap, first-turn budget; SKM `codex doctor`, installed plugin inventory including `task@swissknifeman` presence/provenance, hook presence/callability, exact relative/absolute-target public hook dry-run results, `maind health --cwd --strict`, graph view, provider audit and plan-lint baseline.

## 21

Любая запись в consumer roots или provider control plane; raw setting values; environment values; secret/token hashes; абсолютные roots; transcript/prompt content; classification и repair decisions (P0.2/P0.3).

## 22

`brief/00-brief.md` · `research/00-user-intent.md` · `findings/03-current-defects-2026-08-02.md` · `findings/04-authoring-environment-drift-2026-08-02.md` · `findings/12-design-audit-remediation-2026-08-03.md` · `research/01-target-architecture.md` · current git HEAD/worktree · archived predecessor evidence anchors and frozen provider contracts. The live project registry is a capture source, not semantic authority: P0.1 immediately minimizes it into the committed evidence bundle listed below. P5 may reread it only as an ephemeral root locator, then must rebind every stable project ID, repository identity and preimage to this sealed bundle before observation or write; no later item derives selection, classification, ownership or action from host state. RAG:— (repo-grounded: plan D26 and `research/05-p5-consumer-migration-design.md`)

## 23

`plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p0-provider-fleet-inventory.py` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P0.1/evidence/{manifest.json,verify.py,project-registry-redacted.json,provider-source-snapshot.json,provider-fleet-inventory.json,command-results-redacted.json}` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/findings/P0-provider-fleet-baseline.md` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/index.md`

## 24

1) `brief/00-brief.md` 2) `research/00-user-intent.md` 3) `research/01-target-architecture.md` 4) `findings/03-current-defects-2026-08-02.md` 5) `findings/04-authoring-environment-drift-2026-08-02.md` 6) `findings/12-design-audit-remediation-2026-08-03.md` 7) `plans/archive/2026.07.19-DUAL-PROVIDER/research/03-p0-design-and-premortem.md` 8) `plans/archive/2026.07.19-DUAL-PROVIDER/artifacts/p0-provider-inventory.py` 9) `plans/archive/2026.07.19-DUAL-PROVIDER/artifacts/p0-evidence-anchors.json` 10) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-capability-contract.md` 11) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-artifact-contract.md` 12) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-config-contract.md` 13) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-harness-contract.md` 14) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-instruction-contract.md` 15) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-migration-gates.md` 16) `packages/skiller/AGENTS.md` 17) `packages/harness/AGENTS.md` 18) `packages/maind/AGENTS.md` 19) `packages/skiller/lib/skiller/state.py` 20) `packages/skiller/lib/skiller/status.py` 21) `packages/skiller/lib/skiller/budget.py` 22) `packages/skiller/lib/skiller/doctor.py` 23) `packages/harness/lib/harness/doctor.py` 24) `packages/harness/lib/harness/provider_audit.py` 25) `packages/harness/lib/harness/settings_audit.py` 26) `packages/maind/lib/maind/health.py` 27) `packages/maind/lib/maind/graph.py` 28) `packages/maind/lib/maind/projects.py` 29) `packages/skiller/skills/general/plan-protocol/snippets/source-evidence-template.md` 30) `AGENTS.md` 31) `.swissknife.json`.

## 25

Helper is plan-local, stdlib-only, read-only and scans allowlisted provider carriers; registry membership is derived, never hardcoded. It must distinguish committed bytes, dirty tracked paths, untracked paths, configured defaults and the active runtime envelope; a default/runtime mismatch is a named diagnostic, not silently reconciled. One provider's GREEN cannot mask the other's missing/unsupported/red row. RAG:— (repo-grounded: root provider-parity/worktree/evidence instructions, D13, predecessor migration gates) Secret-bearing configs are parsed only through an explicit redaction allowlist: store key paths/types/counts and diagnostic IDs, never values or hashes of excluded values; finding publishes the exact commands and evidence classes. RAG:— (repo-grounded: predecessor provider analytics/artifact privacy boundaries)

## 26

Reuse the predecessor helper as a pattern, not a runtime dependency. Implement `--write`, `--check`, `--self-test`; canonical JSON is sorted and timestamp-independent except an explicit observation field supplied to `--write`. The bundle follows `source-evidence-template.md`: exact member list, `privacy.minimized=true`, excluded raw transcripts/chain-of-thought/tool payloads/secrets, deterministic producer and `verify.py`. Project IDs come from registry identity plus a collision-safe short digest; absolute roots never leave process memory. Inventory only the documented carrier families (`CLAUDE.md`, `AGENTS.md`, provider rules/skills/agents/config/hooks/MCP/locks and SKM manifests); do not recursively hash application source. Symlinks are `lstat`-classified before resolution; broken/out-of-root targets are recorded without target bytes. Subprocesses have timeouts, captured exit/stdout schema and no `--fix`/apply/repair flags. A command failure is evidence `red|unavailable`, never a skipped green.

## 27

`PYTHONPATH=. python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p0-provider-fleet-inventory.py --write`; then `--check` and `--self-test` return 0. `PYTHONPATH=packages/task/lib:. python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P0.1/evidence/verify.py` returns `allow` from `task.task_contract.bundle_lint` with exact declared privacy. Coverage set-difference against the captured redacted registry member set and provider-relevant path set is empty; every project has separate Claude/Codex rows or an explicit `not-selected` row. Negative fixtures for a missing project, extra path, duplicate artifact ID, raw absolute root, secret-like value, secret digest, bundle member mismatch, broken-symlink misclassification, unsupported provider and malformed command result each return nonzero. The helper records exact no-write results for `packages/harness/bin/harness hooks --target . --provider codex --observer --trusted --dry-run` and `packages/harness/bin/harness hooks --target "$(git rev-parse --show-toplevel)" --provider codex --observer --trusted --dry-run`: until P3.2 repairs the relative form, its nonzero `ValueError: root must be explicit and absolute` is required baseline evidence rather than GREEN, while the resolved-absolute form must emit a plan identity/operation set and neither command may change hook target bytes. `packages/harness/bin/harness doctor --provider-audit --json` parses and has empty diagnostics; `packages/maind/bin/maind health --cwd --strict` passes; `codex doctor --json` is `overallStatus=ok`; `codex plugin list --json` records an explicit `task@swissknifeman` installed/enabled row or a stable non-green missing-runtime diagnostic; `python3 packages/task/scripts/plan-lint.py plans/2026.08.02-PROVIDER-CONTRACT-LOCALE --baseline HEAD` adds 0 errors.

## 28

Committed helper and privacy-minimized evidence bundle, canonical redacted manifest and human finding; exact registry count and per-provider/per-file coverage anchored to the item commit; observed relative-target hook public-CLI defect plus absolute-target/no-write control named without repair; SKM/fleet observed failures named without repair; index provenance updated; item commit and separate plan bookkeeping commit.

## 29

—

## 30

—

## 31

—

## 32

no

## 33

⬜ Not started

## 34

Классифицировать каждый provider-relevant ряд P0.1 и выдать точную no-write disposition, чтобы ни один local override не был принят за stale copy или canonical asset. RAG:— (repo-grounded: P0.1 manifest, plan D4/D9)

## 35

Same-name trees, broken links, backups and managed copies need different authority and rollback; basename/content similarity alone does not prove ownership. RAG:— (repo-grounded: `findings/03-current-defects-2026-08-02.md`, predecessor migration gates G08–G11)

## 36

Exact-one classification for every manifest artifact row: `canonical-equivalent`, `local-override`, `stale-managed-copy`, `broken-link`, `ambiguous`; evidence class and source; owner (`skm-managed`, `project-owned`, `unknown`); allowed next action; rollback/preimage requirement; destination item P5.1/P5.2/P5.3 or no-op. Explicit rows for every reported FlexCRM, Vintera, Insiders, Azguard and Dterema case plus any newly discovered case.

## 37

Filesystem mutation; automatic adoption; semantic merging of local overrides; deletion; credential handling; implementation of migration tools; treating a missing provider selection as an error when project intent says `not-selected`.

## 38

Terminal P0.1 manifest/finding and item commit · plan D4/D7–D9 · predecessor provider artifact/config/migration contracts.

## 39

`plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p0-provider-fleet-classify.py` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P0-provider-fleet-classification.json` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/research/09-fleet-migration-classification.md` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/index.md`

## 40

1) P0.1 Completion Notes 2) `artifacts/P0.1/evidence/manifest.json` 3) `artifacts/P0.1/evidence/verify.py` 4) `artifacts/P0.1/evidence/provider-fleet-inventory.json` 5) `artifacts/P0.1/evidence/provider-source-snapshot.json` 6) `findings/P0-provider-fleet-baseline.md` 7) `research/01-target-architecture.md` 8) `findings/03-current-defects-2026-08-02.md` 9) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-artifact-contract.md` 10) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-capability-contract.md` 11) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-config-contract.md` 12) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-migration-gates.md` 13) `AGENTS.md` worktree-safety/provider-parity rules.

## 41

Classification is exhaustive and mutually exclusive; uncertainty maps to `ambiguous`, never to the cheapest action. RAG:— (repo-grounded: D9 and predecessor fail-closed migration contract) `canonical-equivalent` requires content/semantic identity against a named canonical source; `stale-managed-copy` requires valid ownership/provenance plus older source identity; `broken-link` records link and intended source evidence; `local-override` requires a semantic delta; absence of proof is `ambiguous`. Auto-relink/repair may be proposed only with ownership proof, exact preimage and rollback; no proposal executes here. RAG:— (repo-grounded: root worktree safety and provider artifact contract)

## 42

Validator reads the sealed P0.1 fleet and provider-source snapshots plus a manually reviewed classification document; it must not infer final classes heuristically or read live/dirty provider source. Require exact artifact-ID set equality, enum/type validation, non-empty evidence references, provider identity, project ID, proposed action, owner, rollback rule and destination item. Reject `delete`/`overwrite` actions for `local-override` or `ambiguous`; reject any automatic action lacking `skm-managed` proof. Markdown synthesis groups counts and known cases but never becomes the machine source.

## 43

`PYTHONPATH=. python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p0-provider-fleet-classify.py --check` returns 0 and reports empty missing/extra/duplicate sets against the committed P0.1 manifest. Negative fixtures for every enum/action contradiction, absent evidence, missing known-case trace, automatic ambiguous/local action, invalid ownership, missing rollback and secret/absolute-path leakage return nonzero. `rg -n "FlexCRM|Vintera|Insiders|Azguard|Dterema" plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/research/09-fleet-migration-classification.md` covers all brief-known cases. `python3 packages/task/scripts/plan-lint.py plans/2026.08.02-PROVIDER-CONTRACT-LOCALE --baseline HEAD` adds 0 errors.

## 44

Committed classification validator, complete canonical classification matrix, human synthesis with per-project migration disposition, exact unresolved set and explicit P5 destinations; no external filesystem delta.

## 45

—

## 46

—

## 47

—

## 48

no

## 49

⬜ Not started

## 50

Freeze a recovery/admission contract that maps every P0 red/ambiguous condition to an owning item, evidence carrier, pass/fail rule, rollback and exact authority gate; prepare but do not execute any live credential/trust action. RAG:— (repo-grounded: P0.1/P0.2, predecessor `provider-migration-gates.md`)

## 51

Later phases otherwise can silently treat a partial provider success, stale inventory or unapproved security action as permission to migrate the fleet. RAG:— (repo-grounded: D6/D10, predecessor G01–G11 and current phase contracts)

## 52

Versioned successor `provider-recovery-gates-v1`; entry gates for P1–P7; required producer/verifier/evidence/owner/pass/failure action for every gate; independent provider and security axes; dirty-tree vs release evidence; protected fleet/Brain paths; exact P0.4 action inventory for any verified plaintext credential or trust prerequisite; typed `contract_freeze_decision` and conditional `containment_mutation_decision`; executable checker/schema/fixtures and frozen evidence; P0 pre-mortem with assigned mitigations.

## 53

Editing archived predecessor contracts; package implementation; credential value access/reporting beyond a local redacted detector; revocation, rotation, trust activation, cleanup or fleet writes; approving its own security action.

## 54

Terminal P0.1/P0.2 committed outputs · plan D6–D12 · all frozen predecessor provider contracts · P1–P7 phase contracts.

## 55

`plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-recovery-gates-v1.md` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P0-security-trust-action-matrix.md` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p0-recovery-gates-check.py` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/test-p0-recovery-gates-check.py` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P0.3/recovery-gates-check.json` · deterministic fixtures under `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P0.3/fixtures/**` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/research/10-p0-premortem.md` · conditional `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/findings/P0-provider-security-procedure.md` when P0.4 needs an external provider action · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/index.md`

## 56

1) P0.1/P0.2 Completion Notes and their committed outputs 2) `plan.md` D6–D12 and `## 7. Contracts` 3) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-migration-gates.md` 4) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-capability-contract.md` 5) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-artifact-contract.md` 6) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-config-contract.md` 7) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-harness-contract.md` 8) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-instruction-contract.md` 9) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-command-routing-contract.md` 10) `phases/P1.md` 11) `phases/P2.md` 12) `phases/P3.md` 13) `phases/P4.md` 14) `phases/P5.md` 15) `phases/P6.md` 16) `phases/P7.md` 17) `research/01-target-architecture.md` 18) `AGENTS.md` security/evidence/generated-artifact rules.

## 57

The new contract is additive: it references exact predecessor versions and may tighten a gate, never weaken or rewrite a frozen obligation. RAG:— (repo-grounded: D7, provider migration gates) Every gate is binary and names producer, independent verifier, evidence path, owner, pass rule and failure action; absent/stale/uncommitted/partial evidence fails. Claude/Codex, trust/approval/sandbox and credential containment remain independent rows. RAG:— (repo-grounded: predecessor capability/migration contracts) Authority is typed per D51: the P0.3 `contract_freeze_decision` approves only contract v1.0.0; a non-empty P0.4 branch requires a separate `containment_mutation_decision` naming target/action/preimage/backup/rollback/stop rule; an empty branch accepts neither decision as a waiver. The checker evidence uses schema `p0-recovery-gates-check/v1` and records the checker, contract, manifest, classification and action-matrix SHA-256 values, exact branch/action set, typed decision references and binary result. If P0.1 plus the fresh P0.4 detector satisfy the frozen no-op predicate, `action_set=[]` is a deterministic Validation result requiring no owner authority; it is not a waivable approval branch or speculative mutation.

## 58

Use stable gate IDs `R01…`; include a predecessor-version/hash table and a phase transition matrix. Implement the plan-local stdlib-only `p0-recovery-gates-check.py` with exact `write`, `check` and `verify-branch` subcommands; canonical JSON is sorted, schema-versioned and hashes its own checker bytes plus every frozen input. The authority input is the append-only Decision Log plus an exact D# identifier: the checker parses that row itself, requires the expected decision type and records the canonical row hash, without hashing the whole later-appendable plan. `write` creates only the named evidence carrier atomically, `check` is byte-for-byte no-write, and `verify-branch` refuses on checker/input/decision-row hash drift, an unknown branch, nonempty no-op action set, missing mutation authority or any unlisted mutation row. The action matrix stores only semantic secret reference/issuer, affected config key path and boolean exposure/rotation state; never secret bytes, token hashes or provider account identifiers. Define protected inventory and paired before/after checks. Run the pre-mortem scenario «plan failed after 6–12 months», cluster causes, and assign each mitigation to a gate/item owner. Contract status stays `draft` until the typed contract-freeze D# is recorded; freezing requires version `v1.0.0` and an approval line.

## 59

`PYTHONPATH=. python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/test-p0-recovery-gates-check.py` returns 0 and fixtures reject missing gate fields, weakened G01–G11 coverage, missing/extra action rows, checker/input hash drift, missing/duplicate/untyped/self authority rows, nonempty no-op, mutation without containment D#, secret/root leakage and undeclared future evidence. `python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p0-recovery-gates-check.py write --manifest plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P0.1/evidence/manifest.json --classification plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P0-provider-fleet-classification.json --contract plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-recovery-gates-v1.md --action-matrix plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P0-security-trust-action-matrix.md --decision-log plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/plan.md --contract-freeze-decision <P0.3-contract-freeze-D#> --output plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P0.3/recovery-gates-check.json` and the identical frozen-input invocation with subcommand `check` plus `--evidence plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P0.3/recovery-gates-check.json` return 0; `check` changes no byte. The evidence proves every P1–P7 transition and P0.1/P0.2 red/ambiguous class, no orphaned G01–G11 obligation, exact future evidence paths, zero secret/account/root material, a uniquely parsed typed contract-freeze decision row and its canonical hash, and an exact P0.4 branch predicate. `python3 packages/task/scripts/plan-lint.py plans/2026.08.02-PROVIDER-CONTRACT-LOCALE --baseline HEAD` adds 0 errors.

## 60

Owner-approved frozen recovery contract v1.0.0, exact security/trust action matrix, versioned executable checker/tests/frozen hash evidence, pre-mortem, updated Contracts rows/notifications, and a P0.4 launch payload or evidenced no-op; no live external delta.

## 61

—

## 62

—

## 63

—

## 64

no

## 65

⬜ Not started

## 66

Execute only the urgent credential/trust containment transaction named by a distinct P0.4 `containment_mutation_decision`, or close as an evidenced no-op when P0.1/P0.3 prove no active exposure; publish redacted read-after-write and rollback evidence. RAG:— (repo-grounded: D10/D51 and frozen P0.3 recovery gate)

## 67

A verified live credential exposure or trust prerequisite is unsafe to carry silently into later fleet work, but revocation/rotation and external project writes require authority and recoverability. RAG:— (repo-grounded: D6, root security/destructive-action instructions)

## 68

Only targets/actions named by the P0.4 `containment_mutation_decision`; recoverable local backup before mutation; provider-side revoke/rotate only when explicitly authorized; redacted read-after-write; per-provider trust check; rollback on any failed postcondition; protected-delta proof for every non-target fleet root; no-op evidence branch.

## 69

General Brain profile/skill cleanup (P6.1); provider/control-plane implementation; any target/action not named by the D#; broad fleet repair; deletion of legacy skills/bundles; disclosure of credential/preimage bytes; interpreting `approval_policy=never` as trust or full access.

## 70

Frozen P0.3 contract, action matrix, checker byte hash and checker evidence · committed P0.1 baseline/manifest · P0.2 classifications · exact P0.4 `containment_mutation_decision` only for the mutation branch. If mutation is required and that typed D# is absent, this item remains waiting and performs no write; the evidenced no-op branch never requests a D#.

## 71

`plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P0.4/fresh-security-trust-evidence.json` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P0.4/branch-verdict.json` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/findings/P0-security-containment-evidence.md` · semantic external targets named verbatim by the conditional P0.4 `containment_mutation_decision` only.

## 72

1) P0.3 Completion Notes, typed contract-freeze decision, checker byte hash and frozen checker evidence 2) `root/contracts/provider-recovery-gates-v1.md` 3) `artifacts/P0-security-trust-action-matrix.md` 4) `artifacts/P0.3/recovery-gates-check.json` 5) `artifacts/p0-recovery-gates-check.py` 6) `artifacts/P0.1/evidence/manifest.json` 7) `artifacts/P0.1/evidence/verify.py` 8) `findings/P0-provider-fleet-baseline.md` 9) `artifacts/P0-provider-fleet-classification.json` 10) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-migration-gates.md` security/no-write/rollback sections 11) conditional `findings/P0-provider-security-procedure.md` and P0.4 `containment_mutation_decision` when an external action exists.

## 73

On the mutation branch, the pre-mutation gate verifies exact target identity/preimage, P0.4 `containment_mutation_decision`, backup and rollback; neither the P0.3 contract-freeze D# nor any P4 decision is accepted as mutation authority, and mismatch refuses before any write. On both branches the frozen checker byte hash and every P0.3 evidence/input hash must match before evaluation. On the no-op branch, the checker evaluates pass over the committed P0.1 manifest/classification and a fresh independent redacted detector/provider-trust result, with `action_set=[]`, plaintext-secret findings 0 and protected-target delta 0; no D# substitutes for or waives that predicate. RAG:— (repo-grounded: frozen P0.3 contract, D46/D51 and predecessor artifact/migration gates) Apply is one transaction; partial provider success is failure, triggers rollback where reversible, and keeps the dependent gate closed. Evidence records commands, exit classes, boolean exposure/trust state, backup identity and protected delta, never secret material. RAG:— (repo-grounded: root evidence/security instructions) External provider facts/procedures are reverified against official current documentation immediately before action; unavailable verification leaves the mutation branch waiting.

## 74

Use worktree-local CLIs and provider-native secure interfaces only. Never pass secrets on the command line, write them into shell history, echo them, or capture raw config/environment output. Backup only declared local target bytes with mode `0600`; record a non-secret backup ID and restore/delete policy. The no-op path still runs the redacted detector and trust checks and commits the evidence carrier. Do not use global `--fix`, recursive cleanup, `git add -A`, or a best-effort continuation after partial failure.

## 75

Pre-mutation contract gate returns `allow`, the P0.3 checker byte hash equals `recovery-gates-check.json.checker_sha256`, and exactly one branch command returns 0. No-op command: `python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p0-recovery-gates-check.py verify-branch --branch no-op --manifest plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P0.1/evidence/manifest.json --classification plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P0-provider-fleet-classification.json --contract plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-recovery-gates-v1.md --action-matrix plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P0-security-trust-action-matrix.md --p0-check-evidence plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P0.3/recovery-gates-check.json --fresh-evidence plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P0.4/fresh-security-trust-evidence.json --decision-log plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/plan.md --expected-checker-sha256 <P0.3-recorded-sha256> --output plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P0.4/branch-verdict.json`. Mutation command is byte-identical except `--branch mutation --owner-decision <P0.4-containment-mutation-D#>`; the checker parses exactly one matching Decision Log row, requires `containment_mutation_decision`, binds its canonical row hash and refuses a contract-freeze or terminal-regeneration decision. For mutation, provider confirms old credential revoked and replacement reference usable without exposing bytes; target redacted scan reports 0 plaintext credentials; required Claude/Codex trust rows satisfy the frozen gate; read-after-write and second reconcile are clean/no-op; rollback rehearsal or verified rollback procedure is recorded; all non-target fleet roots have delta 0. For no-op, `branch-verdict.json` records `action_set=[]`, plaintext-secret findings 0, protected-target delta 0 and no authority reference. In both branches, evidence secret scan is 0 and `python3 packages/task/scripts/plan-lint.py plans/2026.08.02-PROVIDER-CONTRACT-LOCALE --baseline HEAD` adds 0 errors.

## 76

Committed redacted containment/no-op evidence, exact provider/trust verdicts, backup/rollback disposition and protected-delta proof; P1 gate opened only when the frozen contract says pass.

## 77

—

## 78

—

## 79

—

## 80

no

## 81

⬜ Not started

## 82

Author the normative v1 control-plane envelope and deterministic checker for canonical desired state, adapter-scoped last-applied/observed evidence, derived drift and provider-qualified aggregate status. RAG:✅ 2026-08-02 desired-state vs observed-drift verification in `findings/05-p1-contract-verification-2026-08-02.md`

## 83

Current `core/provider/config.py`, `manifest.py`, `registry.py` and artifact lock model own separate valid facts but do not expose one versioned status contract; inventing a second desired-state carrier or treating rendered output as intent would violate predecessor ownership. RAG:— (repo-grounded: `core/provider/config.py`, `core/provider/manifest.py`, `core/provider/registry.py`, archived `provider-artifact-contract.md`)

## 84

`provider-control-plane-v1` purpose/vocabulary/versioning; exact JSON-safe schemas for `desired`, per-provider `last_applied`, fresh `observed`, derived `drift`, diagnostics and aggregate result; stable project/provider/artifact/capability identities; source/evidence/version/digest requirements; timestamp placement that cannot affect semantic hashes; no-partial-result and no-write read/check semantics; positive/negative normative fixtures and a stdlib checker.

## 85

Choosing locale fields or message language; implementation in `core/` or packages; defining new Support Levels or artifact observations; provider-native target syntax; writes/apply/repair; fleet state; credentials, raw config values, absolute roots or provider payloads.

## 86

Active plan D1/D5/D7/D12/D14–D15 · `brief/00-brief.md` · `research/01-target-architecture.md` · `findings/05-p1-contract-verification-2026-08-02.md` · frozen predecessor capability/config/artifact contracts · current core provider domain and root capability manifest. P0 outputs are not inputs until their producing items are terminal.

## 87

`plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-control-plane-v1.md` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p1-provider-control-plane-check.py` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P1-control-plane-fixtures/schema-positive.json` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P1-control-plane-fixtures/schema-negative.json` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/research/11-p1-control-plane-design.md` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/index.md`

## 88

1) `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/research/01-target-architecture.md` 2) `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/findings/05-p1-contract-verification-2026-08-02.md` 3) `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/plan.md` D1, D5, D7, D12, D14–D15 and Contracts 4) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-config-contract.md` 5) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-capability-contract.md` 6) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-artifact-contract.md` 7) `core/provider/values.py` 8) `core/provider/config.py` 9) `core/provider/manifest.py` 10) `core/provider/registry.py` 11) `core/provider/artifact.py` 12) `core/provider/lock.py` public enums, lock/projection and classification functions 13) `configs/provider-capabilities.json` 14) `.swissknife.json` 15) `packages/skiller/schema/swissknife.schema.json`.

## 89

Compose, do not replace, the frozen domains: `desired` is a materialized projection of the frozen provider-config resolver with leaf provenance; support is referenced from the capability catalog; `last_applied` is adapter/artifact provenance from a successful committed apply; `observed` is fresh provider-qualified evidence; `drift` and aggregate health are derived and never user-authored. RAG:— (repo-grounded: archived provider config/capability/artifact contracts and current core modules) One selected provider cannot mask another selected provider's missing/stale/error row; disabled/not-selected, unsupported, untrusted and unknown remain distinct. RAG:— (repo-grounded: plan D5, predecessor capability/migration contracts) The schema must preserve stable codes/identities in English and allow only human `message` rendering to localize later in P2. RAG:— (repo-grounded: plan D3 and predecessor structured diagnostics)

## 90

Анти-подгонка: checker fixtures are authored from the contract, never regenerated from current serializer output; no special branch for a fixture digest or provider. Анти-самообман: a syntactically valid example is not a frozen contract—schema completeness, exact negative refusals, predecessor compatibility and Owner gate must all pass. If any required field would duplicate or weaken a frozen predecessor SSOT, stop and escalate under plan-protocol §10 because that changes D7/D15; do not rename the conflict or silently fork semantics. Keep checker stdlib-only, deterministic, path-contained and independent from package runtime objects whose conformance it checks.

## 91

`PYTHONPATH=. python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p1-provider-control-plane-check.py --stage schema --contract plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-control-plane-v1.md --fixtures plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P1-control-plane-fixtures` returns 0 with literal `schema: pass`; the same checker `--self-test schema` returns 0 after proving every declared negative fixture is rejected by its exact code. `python3 -m unittest core.tests.provider.test_config core.tests.provider.test_manifest core.tests.provider.test_registry core.tests.provider.test_artifact` is green. `python3 packages/task/scripts/plan-lint.py plans/2026.08.02-PROVIDER-CONTRACT-LOCALE` has 0 errors.

## 92

Complete draft contract sections for identity/envelope/status/diagnostics/versioning; normative positive and negative schema fixtures; independent checker and design synthesis; explicit trace table from every new field to its frozen or current owner; no code/provider/fleet write.

## 93

—

## 94

—

## 95

—

## 96

no

## 97

⬜ Not started

## 98

Extend the P1.1 schema with deterministic capability negotiation and an exhaustive ownership matrix that assigns every canonical input, adapter projection, managed target, lock and status field to exactly one owner. RAG:— (repo-grounded: P1.1 deliverables, archived provider capability/artifact/instruction/harness contracts)

## 99

Provider parity is semantic, not byte identity, while current surfaces span root/core, skiller, task, harness, maind and analyst; without exact ownership and negotiation rules an adapter can accidentally read the other provider's output, claim unsupported parity or mutate canonical intent. RAG:— (repo-grounded: root provider-parity instruction, archived provider capability/instruction/harness contracts)

## 100

Negotiation input/output and failure ordering; required vs optional capabilities; `native`/`adapted`/`unsupported` reuse; native-extension separation; selected-provider independence; explicit-decision precedence; complete owner/read/write/derived/forbidden-use matrix for provider config, capability manifest, adapter registry, canonical sources, rendered targets, locks, status/evidence and human diagnostics; provider-qualified aggregate/degraded/exclusive presentation derived without a rival support enum; golden provider matrices.

## 101

New provider or capability IDs; changing catalog support claims/evidence; locale selection; package code; carrier/application writes; global install; credentials; cross-provider conversion; declaring parity from path/file equality.

## 102

Terminal P1.1 contract/checker/fixtures and item commit · current `configs/provider-capabilities.json` · archived frozen downstream provider contracts · current adapter descriptors and provider-owned status/audit implementations.

## 103

`plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-control-plane-v1.md` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P1-provider-ownership-capability-matrix.json` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P1-provider-ownership-capability-matrix.md` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P1-control-plane-fixtures/negotiation-positive.json` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P1-control-plane-fixtures/negotiation-negative.json` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p1-provider-control-plane-check.py` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/index.md`

## 104

1) P1.1 Completion Notes and item commit 2) `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-control-plane-v1.md` 3) `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P1-control-plane-fixtures/schema-positive.json` 4) `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p1-provider-control-plane-check.py` 5) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-capability-contract.md` 6) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-artifact-contract.md` 7) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-skill-publication-contract.md` 8) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-command-routing-contract.md` 9) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-harness-contract.md` 10) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-instruction-contract.md` 11) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-analytics-contract.md` 12) `core/provider/registry.py` 13) `core/provider/artifact.py` 14) `core/provider/lock.py` 15) `configs/provider-capabilities.json` 16) `packages/harness/lib/harness/provider_audit.py` 17) `packages/maind/lib/maind/provider_deploy.py` 18) `packages/skiller/lib/skiller/publication.py` provider selection/plan functions 19) `packages/task/lib/task/command_render.py`.

## 105

Capability negotiation consumes only the frozen manifest, effective provider selection with provenance and one explicit adapter descriptor; required missing/denied/unsupported/level-rejected blocks before render, optional unsupported stays an explicit provider-qualified limitation, and one provider result never supplies or masks another. RAG:— (repo-grounded: `core/provider/registry.py`, predecessor capability contract) The ownership matrix is exact and exhaustive over the declared carrier families: canonical intent/source may be read but not written by adapters; each adapter may observe only its provider and write only matching managed boundaries plus its provider-scoped status; cross-provider output and stale lock are never semantic input. RAG:— (repo-grounded: predecessor artifact/instruction/harness contracts) Public `supported/degraded/exclusive` wording must be a documented projection over frozen Support Levels, limitations and Native Extensions, not a fourth Support Level or hidden parity claim. RAG:— (repo-grounded: plan D5 and predecessor capability contract)

## 106

Анти-подгонка: build expected owner/capability sets from frozen contract inventories and explicit current catalogs, never from rendered targets or the observed matrix being validated; every negative fixture changes one invariant only. Анти-самообман: a green Claude row plus a missing/red Codex row is aggregate non-green whenever both are selected; do not collapse `unsupported`, disabled, not-selected, unknown or untrusted. If a surface has no unique semantic owner or needs output-to-output translation, stop and escalate because it changes D5/D15; do not resolve ambiguity by path order, basename or current bytes. The JSON matrix is the machine source and Markdown is its deterministic human projection, not a second editable matrix.

## 107

`PYTHONPATH=. python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p1-provider-control-plane-check.py --stage ownership --contract plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-control-plane-v1.md --matrix plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P1-provider-ownership-capability-matrix.json --fixtures plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P1-control-plane-fixtures` returns 0 with literal `ownership: pass`, empty missing/extra/duplicate owner sets and byte-identical regenerated Markdown. `--self-test ownership` returns 0 after exact refusals for duplicate owner, unowned carrier, cross-provider read/write, output-as-source, unsupported-required capability, missing provider row and partial-provider masking. `python3 -m unittest core.tests.provider.test_registry core.tests.provider.test_artifact core.tests.provider.test_lock` is green. `python3 packages/task/scripts/plan-lint.py plans/2026.08.02-PROVIDER-CONTRACT-LOCALE` has 0 errors.

## 108

Contract negotiation/ownership/parity sections; exhaustive canonical JSON matrix plus generated review projection; positive/negative negotiation fixtures; checker extensions; explicit provider-by-provider status behavior and no-write proof.

## 109

—

## 110

—

## 111

—

## 112

no

## 113

⬜ Not started

## 114

Complete and freeze control-plane v1 with recognized legacy upgrade classes, exact plan/check/apply/rollback transactions, refusal rules and Owner-approved compatibility boundaries. RAG:✅ 2026-08-02 versioned state-upgrade fail-closed verification in `findings/05-p1-contract-verification-2026-08-02.md`

## 115

The fleet contains legacy absence, provider-aware v1 config, managed/stale/unowned assets and ambiguous overrides; a silent partial upgrade could destroy project-owned state or report health against an uncommitted/incomplete snapshot. RAG:— (repo-grounded: P0 specification, plan D4/D8–D10, archived provider migration/artifact contracts)

## 116

Recognized source-version/class table; additive upgrade to one complete v1 snapshot; absent-config Claude-only compatibility; exact preimage/ownership/backup/rollback/stop rules; plan/check/dry-run no-write; explicit apply authorization; read-after-write, second-noop and protected-delta proof; unknown/ambiguous/newer-major refusals; stable diagnostic/action codes; normative migration goldens; predecessor obligation crosswalk; atomic Owner approval set C1–C6 and freeze bookkeeping.

## 117

Executing any migration; changing consumer files or global provider state; deletion/adoption without P0 classification and authority; locale migration; auto-enabling Codex; weakening G01–G11; editing archived contracts; credential/trust containment beyond consuming its P0 gate result.

## 118

Terminal P1.1/P1.2 outputs and item commits · terminal P0.1–P0.4 outputs · frozen `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-recovery-gates-v1.md` · P0 classifications/action matrix · archived migration/config/artifact contracts · active plan Contracts and D-log.

## 119

`plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-control-plane-v1.md` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P1-control-plane-fixtures/migration-positive.json` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P1-control-plane-fixtures/migration-negative.json` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p1-provider-control-plane-check.py` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P1-provider-control-plane-conformance.md` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/index.md`

## 120

1) P1.1 and P1.2 Completion Notes/item commits 2) `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-control-plane-v1.md` 3) `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P1-provider-ownership-capability-matrix.json` 4) `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p1-provider-control-plane-check.py` 5) P0.1–P0.4 Completion Notes/item commits 6) `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-recovery-gates-v1.md` 7) `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P0.1/evidence/manifest.json` 8) `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P0-provider-fleet-classification.json` 9) `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P0-security-trust-action-matrix.md` 10) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-migration-gates.md` 11) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-config-contract.md` 12) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-artifact-contract.md` 13) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-capability-contract.md` 14) `core/provider/config.py` 15) `core/provider/lock.py` 16) `packages/skiller/lib/skiller/state.py` 17) `packages/skiller/lib/skiller/update.py` provider-config migration helpers 18) `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/plan.md` D4, D7–D10, D14–D16 and Contracts.

## 121

Only an exact recognized source class/version with complete P0 classification and ownership evidence may produce a migration plan; unknown, ambiguous, local-override, corrupt/newer-major or changed-preimage input refuses before backup/write. RAG:— (repo-grounded: archived provider migration/artifact contracts, P0.2 rules) The target snapshot is complete and validated before apply; source bytes remain recoverable, lock/status writes are transactionally ordered, partial provider success is failure, rollback touches only declared managed targets, and a second reconcile must be empty before health can be green. RAG:— (repo-grounded: archived provider artifact/migration contracts) Missing provider config preserves frozen Claude-only compatibility and never silently enables Codex. Freeze requires terminal P0, final checker/conformance green and one atomic Owner reply `APPROVE P1.3 PROVIDER-CONTROL-PLANE C1-C6 AS WRITTEN`, recorded as a D#; C1–C6 are identity/schema, SSOT composition/ownership, negotiation/parity, status/diagnostics, migration/rollback, and compatibility/authority. RAG:— (repo-grounded: archived config compatibility, plan D14–D15 and contract-item Owner gate)

## 122

Анти-подгонка: migration goldens are contract-authored and include changed-preimage/unknown/ambiguous/partial-provider cases; never regenerate expected results from the migrator or special-case a known fleet path/hash. Анти-самообман: draft text, a successful plan/check, one provider's success or an uncommitted artifact cannot satisfy freeze/apply/health gates; any missing evidence leaves the transition failed. If compatibility requires weakening a frozen predecessor obligation or expanding mutation beyond an exact P0 classification/Owner D#, stop and escalate for a superseding D# with `**Consequences:**`; do not call it a patch or silently adopt. Keep apply authority out of the contract checker: it proves shape/outcome only and performs no external write.

## 123

`PYTHONPATH=. python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p1-provider-control-plane-check.py --stage final --contract plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-control-plane-v1.md --matrix plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P1-provider-ownership-capability-matrix.json --fixtures plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P1-control-plane-fixtures` returns 0 with literals `schema: pass`, `ownership: pass`, `migration: pass`, `predecessor-crosswalk: pass`; `--self-test all` returns 0 and proves every negative code. Contract says `Version: v1.0.0`, `Status: frozen`, contains the exact Owner D# and a complete G01–G11/no-weaken crosswalk; `plan.md ## 7. Contracts` records v1.0.0 and notification. `PYTHONPATH=packages/skiller/lib:packages/maind/lib:. python3 -m unittest core.tests.provider.test_config core.tests.provider.test_manifest core.tests.provider.test_registry core.tests.provider.test_artifact core.tests.provider.test_lock packages.skiller.tests.test_provider_config packages.maind.tests.test_config` is green. `python3 packages/task/scripts/plan-lint.py plans/2026.08.02-PROVIDER-CONTRACT-LOCALE` has 0 errors.

## 124

Owner-approved frozen `provider-control-plane-v1.md` v1.0.0; complete migration/refusal/rollback goldens and independent conformance report; predecessor crosswalk; updated Contracts/index notifications; no package, provider, Brain or fleet mutation.

## 125

—

## 126

—

## 127

—

## 128

no

## 129

⬜ Not started

## 130

Specify and freeze `locale-resolution-v1`: independent locale surfaces, trusted preference carriers, distinct RFC 5646 syntax and registry-backed canonicalization, SKM catalog resolution/fallback, diagnostic codes and redacted provenance. RAG:✅ 2026-08-03 RFC 5646 syntax/private-use/canonicalization verification in `findings/06-p2-locale-authoring-verification-2026-08-02.md`; RAG:— (internal catalog policy: D2/D17 and `research/02-p2-locale-authoring-design.md`).

## 131

The brief requires English by default plus independently inheritable Russian responses, plans and diagnostics; a shared mutable provider option would let one adapter change another surface or make fallback irreproducible. RAG:— (repo-grounded: `brief/00-brief.md`, plan D1–D3, D5 and D17).

## 132

Versioned locale-policy schema with exactly `response`, `plan`, `diagnostics`; command/session, environment, project, user and built-in carriers; RFC 5646 well-formed syntax; canonicalization against an explicitly pinned IANA Language Subtag Registry snapshot; v1 rendered set `en`/`ru`; catalog exact/parent/`en` fallback for registered tags; explicit private-use catalog refusal; per-surface requested/canonical/resolved/fallback provenance and diagnostics; positive/negative vectors; independent checker and P1-config crosswalk.

## 133

Provider configuration writes; adapter projection as preference; OS locale inference; new rendered locales; translation content; rendering implementation; modifying `.swissknife.json`, user state, environment, provider files or fleet files; treating a locale tag as a provider/model/region selection.

## 134

Terminal P0.1–P0.4 and P1.3 outputs/commits · `findings/01-rag-locale-2026-08-02.md` · `findings/06-p2-locale-authoring-verification-2026-08-02.md` · `findings/12-design-audit-remediation-2026-08-03.md` · `research/01-target-architecture.md` · `research/02-p2-locale-authoring-design.md` · plan D1–D3, D5, D12, D17, D41.

## 135

`plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/locale-resolution-v1.md` · `core/locale/data/language-subtag-registry.txt` · `core/locale/data/upstream.json` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P2-locale-resolution-fixtures/{positive,negative}.json` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p2-locale-authoring-check.py` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/research/02-p2-locale-authoring-design.md` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/index.md`.

## 136

1) P0.3/P0.4 and P1.3 Completion Notes/item commits 2) `root/contracts/provider-recovery-gates-v1.md` 3) `root/contracts/provider-control-plane-v1.md` 4) `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-config-contract.md` 5) `findings/01-rag-locale-2026-08-02.md` 6) `findings/06-p2-locale-authoring-verification-2026-08-02.md` 7) `findings/12-design-audit-remediation-2026-08-03.md` 8) `research/01-target-architecture.md` 9) `research/02-p2-locale-authoring-design.md` 10) `.swissknife.json` 11) `core/provider/config.py` 12) `packages/skiller/lib/skiller/config.py` 13) `packages/maind/lib/maind/config.py` provider-config paths 14) `AGENTS.md` reference-provenance/provider-parity/generated-artifact/evidence rules.

## 137

The resolver is pure and consumes already-read, non-secret descriptors; exactly one carrier owns each rank and no adapter can persist, outrank or reinterpret a resolved value. RAG:— (repo-grounded: `core/provider/config.py`, plan D1/D17) Run three explicit stages: (1) validate RFC 5646 well-formed syntax, where `x-acme` and `en-x-acme` are valid; (2) canonicalize with locale-neutral case handling and the exact vendored `core/locale/data/language-subtag-registry.txt`, preserving the opaque private-use sequence without interpretation/reordering; (3) resolve against the internal `en`/`ru` catalog. The snapshot identity is official URL `https://www.iana.org/assignments/language-subtag-registry/language-subtag-registry`, `File-Date: 2026-06-14`, SHA-256 `be1fad86a99e3a932d07b80c9b3c271ec2381a5909ce22420144e5077ab0a43a`; adjacent `upstream.json` records URL, retrieval date, File-Date, hash, bytes and vendoring policy. RAG:✅ 2026-08-03 official IANA bytes/RFC 5646 verification in `findings/12-design-audit-remediation-2026-08-03.md`. `ru-RU` canonicalizes to `ru-RU` and catalog-resolves to `ru`; valid registered unsupported input catalog-falls back to `en`; any tag containing private-use reaches stage 3 and refuses `unsupported-private-use` with no fallback, never `malformed`. RAG:— (internal product policy: D17 and P2 research) Each surface selects independently; provenance has rank/kind/requested/canonical/resolved/fallback/diagnostic only. Future project policy is additive at `.swissknife.json#/locale`, user policy at `~/.swissknifeman/locale.json`; neither file is created in this item.

## 138

Анти-подгонка: author vectors from normative tables and the pinned registry bytes, not resolver output or host environment; each negative changes one invariant and expected code. Vendor the registry faithfully, never hand-edit its bytes, and refuse a source whose `File-Date`/SHA-256 differs from the approved identity; P4.1 owns the explicit future update producer and runtime parser, not P2.1. Анти-самообман: a normalized tag, one Russian message or one green provider does not prove registry membership, `Preferred-Value`, independent surfaces, redaction, compatibility or freeze authority. Keep checker stdlib-only and deterministic; filesystem reads are limited to the declared contract, fixtures, registry and `upstream.json`, with no environment/network access. If a carrier conflicts with frozen P1 ownership or needs provider output as input, stop and escalate under plan-protocol §10.

## 139

`sha256sum core/locale/data/language-subtag-registry.txt` returns exactly `be1fad86a99e3a932d07b80c9b3c271ec2381a5909ce22420144e5077ab0a43a` and `sed -n '1p' core/locale/data/language-subtag-registry.txt` returns `File-Date: 2026-06-14`; the checker rejects any mismatch among bytes, `upstream.json`, contract identity or approved URL. `PYTHONPATH=. python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p2-locale-authoring-check.py --stage resolution --contract plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/locale-resolution-v1.md --registry core/locale/data/language-subtag-registry.txt --registry-upstream core/locale/data/upstream.json --fixtures plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P2-locale-resolution-fixtures` returns 0 with `resolution: pass`; `--self-test resolution` separates syntax/canonicalization/catalog/provenance failures. Positive syntax vectors include `x-acme` and `en-x-acme`; canonicalization vectors prove `ru-ru → ru-RU`, `ru-RU` remains `ru-RU`, registry `Preferred-Value` mapping uses the pinned snapshot, and private-use opaque order is preserved. Catalog vectors prove canonical `ru-RU` → resolved `ru`, valid registered unsupported → fallback `en`, and syntax-valid private-use → `unsupported-private-use` with `resolved=null`/`fallback=false`; malformed ABNF alone yields `malformed`. Other negatives cover unsupported surface, duplicate rank, adapter-status input, environment persistence and cross-surface leakage. `PYTHONPATH=. python3 -m unittest core.tests.provider.test_config` and plan lint are green.

## 140

Owner-approved frozen `locale-resolution-v1.md` v1.0.0 with separate syntax/canonicalization/catalog tables; faithfully vendored pinned IANA registry plus adjacent provenance; private-use policy, ownership/precedence/fallback, diagnostics/provenance and P1 crosswalk; independent checker/vectors; Contracts/index update; no runtime code, state, provider or fleet mutation.

## 141

—

## 142

—

## 143

—

## 144

no

## 145

⬜ Not started

## 146

Specify the English canonical-source and sparse localized-overlay contract for skills, commands, plugins, comments, development docs and provider-rendered human text, including source identity, translation keys, generated ownership and migration admission. RAG:— (repo-grounded: brief, `packages/skiller/scripts/check-translations.sh`, package-architecture generated-artifact map and plan D3/D18).

## 147

Existing local skills use RU source plus derived EN, while the requested target reverses ownership; renaming files or letting providers translate one another would create two sources and drift. RAG:— (repo-grounded: `packages/skiller/scripts/check-translations.sh`, writing-style RU source and plan D3/D18).

## 148

Canonical English inventory/classification; stable translation-unit key grammar and immutable tokens; sparse overlay envelope/English fallback; renderer boundary; provider projection provenance; migration manifest with preimage/owner/status/rollback; coexistence rules for `SKILL.ru.md`; generation/check path; source/overlay fixtures.

## 149

Translating/re-writing content; changing skill/command/plugin semantics; hand-editing generated adapters, registries or marketplace manifests; translating IDs, paths, commands, schemas, keys, diagnostic/action codes or parser literals; provider conversion; publishing locale; deleting legacy RU or local overrides.

## 150

Terminal P2.1 contract/checker/vectors and P1.3 contract · `findings/06-p2-locale-authoring-verification-2026-08-02.md` · `research/02-p2-locale-authoring-design.md` · `packages/skiller/scripts/check-translations.sh` · `packages/skiller/lib/skiller/publication.py` · `packages/task/lib/task/command_render.py` · `packages/skiller/skills/general/writing-style/{SKILL.md,SKILL.ru.md}` · package-architecture map.

## 151

`plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/english-authoring-overlay-v1.md` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P2-authoring-carrier-matrix.{json,md}` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P2-locale-resolution-fixtures/{overlay-positive,overlay-negative}.json` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p2-locale-authoring-check.py` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/index.md`.

## 152

1) P2.1 Completion Notes/item commit 2) `root/contracts/locale-resolution-v1.md` 3) checker and positive vectors 4) brief 5) P2 finding/research 6) translation script 7) `packages/skiller/lib/skiller/publication.py` 8) `packages/task/lib/task/command_render.py` 9) writing-style EN/RU 10) package-architecture generated artifacts/sync matrix 11) `AGENTS.md` generated-artifact/provider-parity rules.

## 153

A canonical artifact has one English semantic source and stable identity; localized prose is a resource/key overlay and a missing `ru` key follows P2.1 fallback, never copying/re-writing English. RAG:✅ 2026-08-02 fallback verification in P2 finding Existing `SKILL.ru.md` is a migration input, not authority after matrix admission; P4 changes only rows with owner, preimage, equivalence evidence, generated owner and rollback. RAG:— (repo-grounded: generated-artifacts/worktree-safety and D18) Providers receive the same resolved semantic message request and render only owned targets; overlay cannot alter canonical source, capability, lock/provenance or other-adapter files. RAG:— (repo-grounded: D1/D5/D15) Comments and development docs are English canonical prose; only provider/user-facing messages and plan rendering enter the catalog.

## 154

Анти-подгонка: build matrix from declared carrier inventory/owner rules, never current filenames, output or grep; JSON is source and Markdown deterministic projection. Анти-самообман: byte-equal EN/RU, one stamp or one regenerated adapter does not prove semantics, ownership, literal preservation or rollback. Require immutable-token/key parity. If an asset has no owner, is locally overridden or requires generated-file editing, classify it for P4/P5 review and stop—never adopt/delete silently.

## 155

`PYTHONPATH=. python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p2-locale-authoring-check.py --stage overlay --locale-contract plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/locale-resolution-v1.md --contract plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/english-authoring-overlay-v1.md --matrix plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P2-authoring-carrier-matrix.json --fixtures plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P2-locale-resolution-fixtures` returns `overlay: pass` and `matrix: pass`; self-test refuses duplicate source, untranslated immutable token, localized semantic source, generated edit, missing fallback, cross-provider target and override adoption. Generated Markdown is byte-identical; `bash packages/skiller/scripts/check-translations.sh --strict` reports pre-existing baseline separately and P2 introduces no hard literal violation; plan lint is green.

## 156

Owner-approved frozen overlay contract v1.0.0; exhaustive JSON matrix/generated review projection; checker/vectors; immutable-token/generated-artifact rules; P4 admission/rollback handoff; no content/provider/fleet mutation.

## 157

—

## 158

—

## 159

—

## 160

no

## 161

⬜ Not started

## 162

Specify and freeze compact-English, translation-review and comment/diagnostic policy that makes P2.1/P2.2 enforceable without author or provider renderer self-certifying semantic correctness. RAG:— (repo-grounded: brief, plan D3/D18, translation script and writing-style EN/RU).

## 163

Current internal writing policy defaults to Russian and current translation validation checks stamp/literal shape, not requested English ownership, compactness, Russian provider rendering or independent semantic review. RAG:— (repo-grounded: writing-style and translation script).

## 164

English policy for canonical artifacts; compactness budget/exception record; comment/docstring/test-description distinction from literals; locale-aware diagnostics; automated source/key/literal/link/format checks; independent English semantic and Russian-render review; reviewer evidence schema; migration batch/rollback/stop; Owner approval; P4/P7 acceptance criteria.

## 165

Editing all prose; subjective fluency as sole evidence; changing API/test/diagnostic-code/command/commit/provider behavior; machine-translation self-approval; replacing existing validators; release/publish/fleet actions.

## 166

Terminal P2.1/P2.2 contracts/matrices/checker/commits · P2 finding/research · current writing-style/compact-response skills · translation/registry/package validation commands · P4/P7 phase contracts · plan D3, D5, D17–D19.

## 167

`plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/locale-authoring-review-v1.md` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P2-locale-authoring-review-fixtures/{positive,negative}.json` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p2-locale-authoring-check.py` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/research/02-p2-locale-authoring-design.md` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/index.md`.

## 168

1) P2.1/P2.2 Completion Notes/item commits 2) all P2 contracts/matrix/checker 3) P2 finding/research 4) compact-responses skill 5) writing-style EN/RU 6) translation script 7) `packages/skiller/scripts/validate.sh` 8) `packages/task/scripts/validate.sh` 9) `phases/P4.md` 10) `phases/P7.md`.

## 169

English prose is compact by budgets and exception record, not arbitrary token deletion; required invariant, safety condition, validation command, code, URL, ID/path/literal is never removed to meet size. RAG:— (repo-grounded: brief, plan-protocol and compact-response skill) Diagnostics are stable English code/action/context plus locale-rendered message; rendering preserves interpolated identifiers and locale/fallback trace. RAG:— (repo-grounded: D17/D18 and P1 structured diagnostics) Each migrated unit needs structural checks plus independent English semantic and Russian-render review; author/renderer cannot approve itself, unavailable review leaves it unadmitted. RAG:— (repo-grounded: evidence-integrity instruction) Freeze requires terminal P0/P1/P2 prerequisites and Owner reply `APPROVE P2.3 LOCALE-AUTHORING C1-C6 AS WRITTEN` for resolution, ownership, overlay/tokens, review, migration/rollback and parity.

## 170

Анти-подгонка: contract-authored fixtures include concise valid unit plus one violation per check; never derive expected output from formatter, translator or corpus. Анти-самообман: spellcheck, EN stamp, literal grep or fluent Russian is not semantic review, safe migration, fallback or parity proof. Compose existing validators where they own a predicate; P2 checker must not duplicate/weaken schemas. If compactness conflicts with invariant, retain invariant and record exception; if independent review is unavailable, stop batch and escalate.

## 171

`PYTHONPATH=. python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p2-locale-authoring-check.py --stage review --locale-contract plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/locale-resolution-v1.md --overlay-contract plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/english-authoring-overlay-v1.md --contract plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/locale-authoring-review-v1.md --fixtures plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P2-locale-authoring-review-fixtures` returns `review: pass`; self-test refuses source-language violation, missing/self review, changed interpolation/literal, missing Russian render, unsupported fallback, invariant deletion and stale generated projection. Translation/Skiller/Task validation reports pre-existing baseline separately; Owner approval and frozen v1.0.0 are present before P2 terminal; plan lint is green.

## 172

Owner-approved frozen review contract v1.0.0; reviewer evidence/fixtures/checker; enforceable compactness/comment/diagnostic policy; P4 migration batches/P7 release matrix; Contracts/index update; no production content/provider/fleet mutation.

## 173

—

## 174

—

## 175

—

## 176

no

## 177

⬜ Not started

## 178

Implement the frozen `provider-control-plane-v1` and P2 locale-policy integration as an immutable, pure desired-state snapshot and schema resolver that composes existing provider selections, capability support and artifact provenance rather than reading provider projections as intent. RAG:✅ 2026-08-02 desired/observed and state-upgrade verification in `findings/05-p1-contract-verification-2026-08-02.md`.

## 179

`core/provider/config.py` already resolves provider selection with provenance, `manifest.py` owns support levels, and `artifact.py`/`lock.py` own managed provenance; P3 needs one typed read model for adapters without introducing a second configuration carrier. RAG:— (repo-grounded: `core/provider/{config,manifest,artifact,lock}.py`, D15/D20).

## 180

New `core/provider/control_plane.py` typed immutable envelope/parser/resolver; narrow additions to `core/provider/{values,config,__init__}.py` only where the frozen contracts require a shared type; deterministic canonical serialization and schema/compatibility diagnostics; conversion from already-read project/user/fleet/operation descriptors; desired, last-applied and observed identity/provenance boundaries; locale policy passed as canonical input but no message rendering; positive/negative tests and source-contract compatibility fixtures.

## 181

Reading filesystem, environment or provider outputs inside the resolver; writing `.swissknife.json`, user state, lock/status files or provider targets; changing capability-manifest/lock schemas; implementing adapter apply, locale rendering, migration or CLI options; accepting an absent/unknown-major contract through fallback.

## 182

Terminal P0.1–P0.4 evidence/recovery gates and P1.1–P1.3/P2.1 terminal item commits · frozen `root/contracts/provider-control-plane-v1.md` and `root/contracts/locale-resolution-v1.md` · plan D1–D5, D12, D15, D17–D21 · `research/01-target-architecture.md` · `research/03-p3-control-plane-implementation-design.md` · `findings/05-p1-contract-verification-2026-08-02.md` · `findings/07-p3-control-plane-recon-2026-08-02.md`.

## 183

`core/provider/control_plane.py` · `core/provider/{__init__,values,config}.py` (only contract-required changes) · `core/tests/provider/test_control_plane.py` · `core/tests/provider/test_config.py` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/index.md`.

## 184

1) terminal P0.3/P0.4 and P1.1/P1.3/P2.1 Completion Notes/item commits 2) `root/contracts/provider-recovery-gates-v1.md` 3) `root/contracts/provider-control-plane-v1.md` 4) `root/contracts/locale-resolution-v1.md` 5) `findings/05-p1-contract-verification-2026-08-02.md` 6) `research/01-target-architecture.md` 7) `research/03-p3-control-plane-implementation-design.md` 8) `core/provider/values.py` 9) `core/provider/config.py` 10) `core/provider/manifest.py` 11) `core/provider/artifact.py` 12) `core/provider/lock.py` 13) `core/tests/provider/test_config.py` 14) `AGENTS.md` shared-core/provider-parity/generated-artifact rules.

## 185

P1's desired selection, P2's independently resolved locale policy, manifest support and adapter evidence retain separate owners and are only composed into a snapshot; no output, status file, timestamp, host path, secret or raw environment value can affect its semantic hash. RAG:— (repo-grounded: P1 D15, P2 D17–D18, `core/provider/config.py`) Parse exact supported majors and emit stable diagnostics for malformed, duplicate, missing, incompatible or cross-owner fields; never coerce a legacy shape beyond the P1-recognized upgrade table. Desired resolution and observation remain no-write and deterministic for identical descriptors. RAG:✅ 2026-08-02 versioned-upgrade verification in `findings/05-p1-contract-verification-2026-08-02.md`.

## 186

Анти-подгонка: author fixture snapshots directly from frozen contract tables; do not serialize then use the implementation's own output as an oracle. Анти-самообман: one resolved provider or one valid locale does not prove provenance, snapshot immutability, semantic-hash stability, unsupported capability refusal or output/input separation. Keep the module stdlib-only and pure; reuse existing `ProviderId`, `ResolvedProviderConfig`, manifest and artifact types rather than shadow enums/digests. If a frozen contract requires a new identity or a change to existing lock/config semantics, stop under plan-protocol §10 and request P1/P2 re-design instead of broadening P3.

## 187

`PYTHONPATH=. python3 -m unittest core.tests.provider.test_control_plane core.tests.provider.test_config core.tests.provider.test_manifest core.tests.provider.test_artifact core.tests.provider.test_lock` returns 0; fixtures prove deterministic bytes/hash across reordered inputs, no environment/filesystem access, separate desired/last-applied/observed carriers, P2 surface independence, unknown-major refusal and no provider output accepted as intent. `PYTHONPATH=packages/skiller/lib:packages/maind/lib:. python3 -m unittest packages.skiller.tests.test_provider_config packages.maind.tests.test_config` returns 0 without changing their legacy carriers. `python3 packages/task/scripts/plan-lint.py plans/2026.08.02-PROVIDER-CONTRACT-LOCALE` has 0 errors.

## 188

Contract-conformant pure core resolver with immutable desired snapshot, stable diagnostics and deterministic fixtures; no-write integration proof for Skiller/Maind config adapters; updated plan index; no provider/fleet/user-state mutation.

## 189

—

## 190

—

## 191

—

## 192

—

## 193

⬜ Not started

## 194

Implement a provider-neutral reconciliation protocol and provider-scoped package adapters that perform `observe → diff → preflighted apply → readback` against the P3.1 desired snapshot, with every write controlled by existing artifact-lock/adoption rules. RAG:— (repo-grounded: `core/provider/{registry,artifact,lock}.py`, package provider projection modules, D20).

## 195

Current render/deploy paths already protect individual artifacts, but they do not share a typed control-plane readback contract; adapters must expose equal semantics without gaining authority over canonical intent or another provider's target. RAG:— (repo-grounded: `packages/{harness,maind,skiller,task}/lib/**`, `research/03-p3-control-plane-implementation-design.md`).

## 196

New shared no-write reconciliation protocol/types in `core/provider/reconcile.py`; adapter registration/selection integration only as required; package adapter façades around Harness provider render/hooks, Maind deploy, Skiller publication/connect/update, and Task command rendering; Harness public hook CLI target normalization before the absolute-root artifact-lock boundary; exact provider ownership/target declarations; no-write observe/diff/report, explicit apply from a previously validated plan, mandatory post-apply readback, and deterministic fixture tests for both providers.

## 197

Cross-provider target access; silent adoption/repair; rewriting generated artifacts by hand; project/fleet bulk rollout; changing canonical source text, command semantics, skill selection, trust policy, locale resources or provider capability levels; external provider API calls or credentials.

## 198

Terminal P3.1 resolver/item commit · terminal P0–P2 outputs and all frozen P1/P2 contracts · plan D4–D5, D12, D15, D20–D21 · `research/03-p3-control-plane-implementation-design.md` · `findings/07-p3-control-plane-recon-2026-08-02.md` · current adapter and lock tests.

## 199

`core/provider/{reconcile,registry,artifact,lock}.py` (only shared-boundary changes) · `core/tests/provider/{test_reconcile,test_registry,test_artifact_e2e,test_lock}.py` · `packages/harness/lib/harness/{hooks,provider_render,provider_audit,provider_trace}.py` · `packages/harness/tests/{test_provider_conformance,test_provider_hooks,test_provider_trace}.py` · `packages/maind/lib/maind/provider_deploy.py` · `packages/maind/tests/test_provider_deploy.py` · `packages/skiller/lib/skiller/{publication,connect,update}.py` · `packages/skiller/tests/{test_provider_distribution,test_update,test_codex_publication}.py` · `packages/task/lib/task/command_render.py` · `packages/task/tests/{test_provider_command_parity,test_codex_command_adapter}.py` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/execution/P3.2/**` · plan index.

## 200

1) P3.1 Completion Notes/item commit and core resolver tests 2) all frozen P1/P2 contracts 3) archived `provider-artifact-contract.md` and `provider-capability-contract.md` 4) `roadmap.md` «Per-cwd execution and evidence carrier» 5) `findings/12-design-audit-remediation-2026-08-03.md` 6) `core/provider/{registry,artifact,lock}.py` 7) `core/tests/provider/test_artifact_e2e.py` 8) `packages/harness/lib/harness/{hooks,provider_render,provider_audit,provider_trace}.py` 9) `packages/maind/lib/maind/provider_deploy.py` 10) `packages/skiller/lib/skiller/{publication,connect,update}.py` 11) `packages/task/lib/task/command_render.py` 12) root and each affected package `AGENTS.md` before its slice.

## 201

An adapter receives the immutable desired snapshot and may observe only declared provider-owned targets; it emits a value-free observation/diff and cannot write until all capability, ownership, provenance, boundary and recovery gates are green. RAG:— (repo-grounded: archived artifact/capability contracts, `core/provider/lock.py`) Apply consumes one immutable no-write plan and then repeats observe/readback; a failed or partial readback remains non-green and never updates canonical intent. Existing `plan_artifact_lock` and package renderers remain the only owners of their artifact semantics; the new boundary orchestrates, never reimplements them. RAG:— (repo-grounded: `core/provider/artifact.py`, `core/provider/lock.py`, package projection modules).

## 202

Анти-подгонка: use declared desired/expected fixtures and temp roots for both providers; do not let the adapter under test construct expected output from its own observation. Repair F10 at the Harness public CLI boundary by resolving `--target` to an explicit absolute root before `plan_artifact_lock`; keep the shared core invariant that lock roots are explicit/absolute and do not special-case `.` inside `core/provider/lock.py`. Анти-самообман: a green unit import, Claude projection, byte-equal generated output, or a successful apply without a fresh readback does not prove the worktree-local public CLI, Codex parity, ownership isolation or drift safety. Retain existing `check`/`dry-run` as strictly no-write; `apply` accepts only the explicit, already-classified artifact plan and must preserve user-owned bytes/overrides. If an adapter needs an undeclared target, missing support level, raw credential, generated-file hand edit, or another package's write function, stop and escalate to P1/P3 design.

## 203

`PYTHONPATH=packages/harness/lib:packages/maind/lib:packages/skiller/lib:packages/task/lib:. python3 -m unittest core.tests.provider.test_reconcile core.tests.provider.test_registry core.tests.provider.test_artifact_e2e core.tests.provider.test_lock packages.harness.tests.test_provider_conformance packages.harness.tests.test_provider_hooks packages.harness.tests.test_provider_trace packages.maind.tests.test_provider_deploy packages.skiller.tests.test_provider_distribution packages.skiller.tests.test_update packages.skiller.tests.test_codex_publication packages.task.tests.test_provider_command_parity packages.task.tests.test_codex_command_adapter` returns 0. `packages/harness/bin/harness hooks --target . --provider codex --observer --trusted --dry-run` and `packages/harness/bin/harness hooks --target "$(git rev-parse --show-toplevel)" --provider codex --observer --trusted --dry-run` both return 0, emit the same plan identity and operation identities/statuses after target normalization, and leave `.codex/hooks.json` plus `.codex/hooks/lifecycle.py` byte-identical; a temporary-root regression asserts the same relative/resolved-absolute equivalence and zero-write property and fails on the pre-fix `ValueError`. Fixtures additionally prove one provider cannot observe/write the other's target, check/diff are no-write, stale source and managed drift remain distinct, local override/ambiguous ownership refuse, apply failure forces non-green readback, and both providers expose the same shared semantic results. `bash packages/harness/scripts/validate.sh`, `bash packages/maind/scripts/validate.sh`, `bash packages/skiller/scripts/validate.sh`, and `bash packages/task/scripts/validate.sh` are green on the committed scope; plan lint has 0 errors.

## 204

Shared reconciliation protocol plus four package-owned provider adapters, deterministic two-provider observe/diff/apply/readback conformance tests, and no-write/ownership/readback evidence; updated plan index; no fleet migration or generated-manifest hand edit.

## 205

—

## 206

—

## 207

—

## 208

—

## 209

⬜ Not started

## 210

Implement the P1-defined adapter-scoped status store and deterministic diagnostics that turn P3.2 observations/readbacks into redacted ownership, drift, migration-readiness and aggregate provider state for P5–P7. RAG:— (repo-grounded: frozen P1 contract required by D21, existing `ProviderDiagnostic`, `ArtifactLock` and provider audit/report code).

## 211

A raw provider file or one green adapter cannot state fleet health; operators need a stable, value-free diagnostic surface that distinguishes `not-selected`, unsupported, ownership conflict, stale source, managed drift, broken link, local override and ambiguous state without silently repairing it. RAG:— (repo-grounded: plan D4–D5/D8–D10, `core/provider/lock.py`, `findings/07-p3-control-plane-recon-2026-08-02.md`).

## 212

New core status/diagnostic model and deterministic serialization/redaction validator; adapter-scoped durable status updates only after P3.2 readback; aggregate rules that preserve each provider's result; mapping of P0/P1 classification/migration gates to stable diagnostic codes and operator actions; package-facing no-write doctor/status projections; positive/negative fixtures and compatibility tests.

## 213

Claiming live fleet health; reading or storing secrets, raw environment values, absolute consumer roots, provider payloads or prompt/transcript bodies; changing P0 classifications; applying migration/repair/delete; altering locale text/code localization; creating a second fleet registry or provider status written by another adapter.

## 214

Terminal P3.1/P3.2 commits and fresh readbacks · terminal P0 classification/recovery artifacts · frozen P1 control-plane/recovery and P2 locale contracts · plan D4–D5, D8–D10, D12, D20–D21 · `findings/03-current-defects-2026-08-02.md` · `findings/07-p3-control-plane-recon-2026-08-02.md` · `research/03-p3-control-plane-implementation-design.md`.

## 215

`core/provider/{status,diagnostics,values,__init__}.py` · `core/tests/provider/{test_status,test_diagnostics,test_lock}.py` · `packages/harness/lib/harness/{provider_audit,settings_audit}.py` · `packages/harness/tests/{test_provider_conformance,test_settings_audit}.py` · `packages/maind/lib/maind/{health,provider_deploy}.py` · `packages/maind/tests/{test_provider_deploy,test_config}.py` · `packages/skiller/lib/skiller/{status,doctor,update}.py` · `packages/skiller/tests/{test_provider_distribution,test_update}.py` · `packages/task/lib/task/{command_render,route_evidence}.py` · `packages/task/tests/{test_provider_command_parity,test_plan_command_routing}.py` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/execution/P3.3/**` · plan index.

## 216

1) P3.1/P3.2 Completion Notes/item commits and their conformance fixtures 2) terminal P0.1/P0.2/P0.3 artifacts and recovery gates 3) frozen `provider-control-plane-v1.md` 4) `roadmap.md` «Per-cwd execution and evidence carrier» 5) archived `provider-artifact-contract.md`, `provider-migration-gates.md`, `provider-analytics-contract.md` 6) `core/provider/{values,lock,artifact}.py` 7) affected package modules named in Files 8) P0 finding/classification and P3 finding/research 9) root and each affected package `AGENTS.md` before its slice.

## 217

Status has one adapter-scoped writer and records only contract-declared identity/version/digest/classification/diagnostic/provenance fields; the aggregate is derived from complete provider rows and is non-green for required missing/error/unreadable rows. RAG:— (repo-grounded: D5/D8–D10, `core/provider/values.py`) Migration action remains a recommendation linked to P0 classification/gate evidence, not an apply capability; absent proof is `ambiguous` and an unsupported or not-selected provider is explicit rather than collapsed into healthy. Diagnostics are stable codes plus key/value-safe context and optional localized rendering happens later under P2/P4. RAG:— (repo-grounded: P1/P2 phase scope, archived migration gates).

## 218

Анти-подгонка: build expected status/aggregate fixtures by hand from contract tables, including one independent row per provider and all refusal classes. Анти-самообман: a status JSON schema pass, a redacted field, or one green provider does not prove complete pair coverage, secure value minimization, provenance, migration authority or P6 fleet health. Use atomic writes and exact schema validation for the declared adapter-owned status path only; unknown fields/major, duplicate provider rows, wrong writer, missing readback and secret-like values must refuse. Do not emit paths/values merely because a local doctor can see them. Escalate if P0 supplies no evidence for a migration class or if the frozen P1 status schema lacks the needed diagnostic identity.

## 219

`PYTHONPATH=packages/harness/lib:packages/maind/lib:packages/skiller/lib:packages/task/lib:. python3 -m unittest core.tests.provider.test_status core.tests.provider.test_diagnostics core.tests.provider.test_lock packages.harness.tests.test_provider_conformance packages.harness.tests.test_settings_audit packages.maind.tests.test_provider_deploy packages.maind.tests.test_config packages.skiller.tests.test_provider_distribution packages.skiller.tests.test_update packages.task.tests.test_provider_command_parity packages.task.tests.test_plan_command_routing` returns 0. Negative fixtures reject raw absolute root, secret-like value or digest, duplicate/cross-provider status writer, unknown major, missing readback, unsupported requirement, ambiguous ownership auto-action and aggregate green with a required red/missing row. `packages/harness/bin/harness doctor --provider-audit --json`, `packages/maind/bin/maind health --cwd --strict`, and each package validation command from P3.2 are green on the committed scope; `python3 packages/task/scripts/plan-lint.py plans/2026.08.02-PROVIDER-CONTRACT-LOCALE` has 0 errors.

## 220

Versioned redacted status/diagnostic implementation, adapter-owned status projections, aggregate and migration-readiness conformance evidence, and P5/P6/P7-ready stable operator diagnostics; updated plan index; no fleet-health claim or consumer mutation.

## 221

—

## 222

—

## 223

—

## 224

—

## 225

⬜ Not started

## 226

Implement the frozen locale contract as a pure shared runtime and wire immutable, independently resolved `response`, `plan`, and `diagnostics` contexts into package/provider-owned render boundaries. RAG:✅ 2026-08-02 BCP 47 normalization/casing verification in `findings/06-p2-locale-authoring-verification-2026-08-02.md`; RAG:— (repo-grounded: D17/D22 and P3 ownership design).

## 227

P3 supplies canonical locale intent and redacted diagnostics but deliberately renders no text; placing locale state inside either provider or duplicating resolvers per package would violate independent adapter ownership and deterministic fallback. RAG:— (repo-grounded: P3 Scope Excluded, D1/D5/D17/D20 and `research/04-p4-locale-migration-implementation-design.md`).

## 228

`core/locale` immutable surface/tag/request/result/provenance types; BCP 47 boundary normalization constrained to the frozen v1 rendered set; per-surface precedence/fallback; key-addressed catalog lookup; immutable-token/interpolation checks; stable render diagnostic codes; fixture English catalogs and sparse RU overlays; narrow P3 snapshot/status integration; Task plan-context and Harness response/diagnostic instruction render seams; equal Claude/Codex locale context fixtures.

## 229

Reading environment, project/user files or provider output inside `core/locale`; writing locale policy/state; translating the production corpus; changing command/provider semantics; formatting arbitrary machine tokens; fleet rollout; accepting a missing/unknown contract major; claiming model-authored Russian prose from a single injected string without provider readback.

## 230

Terminal P0–P3 item commits · frozen `root/contracts/{provider-control-plane-v1,locale-resolution-v1,english-authoring-overlay-v1,locale-authoring-review-v1}.md` · terminal P2 checker/fixtures, exact `core/locale/data/{language-subtag-registry.txt,upstream.json}` identity and P3 desired/status types · plan D1–D5, D17–D25, D41 · P4 finding/research.

## 231

`core/locale/{__init__,values,resolution,catalog,render}.py` · `core/locale/data/{language-subtag-registry.txt,upstream.json}` (consume/update only through the pinned contract) · `scripts/update-iana-language-subtag-registry.py` · `scripts/test-update-iana-language-subtag-registry.py` · `core/tests/locale/{__init__,test_values,test_resolution,test_catalog,test_render}.py` · `core/provider/{control_plane,diagnostics}.py` (contract-required wiring only) · `core/tests/provider/{test_control_plane,test_diagnostics}.py` · `packages/harness/lib/harness/{instructions,provider_render}.py` · `packages/harness/tests/{test_provider_instructions,test_provider_conformance}.py` · `packages/task/lib/task/{command_catalog,command_render}.py` · `packages/task/tests/{test_provider_command_parity,test_codex_command_adapter}.py` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P4-locale-runtime-fixtures/{catalog.en,catalog.ru,positive,negative}.json` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/execution/P4.1/**` · plan index.

## 232

1) P3.3 Completion Notes/item commit 2) all four frozen contracts named in Inputs 3) P2.1 Completion Notes plus `core/locale/data/{language-subtag-registry.txt,upstream.json}` 4) terminal P2 checker/fixtures and carrier matrix 5) `findings/12-design-audit-remediation-2026-08-03.md` 6) `roadmap.md` «Per-cwd execution and evidence carrier» 7) P3 desired/status modules and tests 8) P2/P4 findings and research 9) core/provider modules 10) Harness/Task modules named in Files 11) root and each affected package `AGENTS.md` before its slice.

## 233

`core/locale` accepts already-read descriptors and has no environment/provider I/O; its only filesystem semantic input is the exact P2-pinned registry file read through one stdlib loader whose File-Date/SHA-256/upstream identity is checked before use. Each surface runs frozen P2 syntax → canonicalization → catalog stages independently. RFC canonical tag and SKM catalog result are separate values: `ru-RU` stays canonical `ru-RU` and resolves to catalog `ru`; valid registered unsupported tags may fall back to `en`; any tag containing private-use is syntax-valid but catalog-refused as `unsupported-private-use`, with opaque private subtags preserved and never labeled `malformed`. RAG:✅ 2026-08-03 official IANA/RFC 5646 verification in `findings/12-design-audit-remediation-2026-08-03.md`; RAG:— (internal catalog policy: D17 and P2 contract/research) `scripts/update-iana-language-subtag-registry.py` is the sole update producer: it accepts an explicit downloaded source file, verifies registry structure/File-Date, writes snapshot plus adjacent provenance atomically, and requires an explicit reviewed hash change; runtime never fetches host-time data. Provenance contains only declared rank/kind/requested/canonical/resolved/fallback/diagnostic fields. Catalog values may change human prose only: keys, placeholders, commands, paths, codes and literals are byte-preserved or the render refuses. Packages own catalogs and targets; both providers consume the same resolved semantic context, and neither stores locale as adapter intent. RAG:— (repo-grounded: D5/D18/D22/D41 and provider-parity/generated-artifact rules).

## 234

Анти-подгонка: author expected results from frozen contract tables, the P2-pinned registry and hand-written fixture catalogs, never by snapshotting renderer output or querying IANA at test/runtime. Анти-самообман: one `ru-RU → ru` case, a Russian Task prompt or a green Claude render does not prove registry membership/Preferred-Value, surface independence, missing-key fallback, literal preservation or Codex parity. Keep `core/locale` stdlib-only/frozen/pure apart from the single immutable registry-data read; parse the faithful snapshot without a second hardcoded registered-tag/mapping table and reuse P3 diagnostic/provenance identities instead of shadow types. The update producer must prove a second `--check` run byte-stable and never modify data on validation failure. If the frozen P2/P3 contracts expose a different owner, tag grammar, catalog envelope or status interface, stop and escalate under plan-protocol §10 rather than adapting by inference.

## 235

`sha256sum core/locale/data/language-subtag-registry.txt`, the adjacent provenance checker and the frozen P2 contract all resolve the same approved identity before runtime tests. `python3 scripts/test-update-iana-language-subtag-registry.py` covers explicit-source refresh, atomic failure, stale/mismatched File-Date/hash/upstream metadata, malformed records and byte-stable `--check`; no test or runtime path uses network. `PYTHONPATH=. python3 -m unittest core.tests.locale.test_values core.tests.locale.test_resolution core.tests.locale.test_catalog core.tests.locale.test_render core.tests.provider.test_control_plane core.tests.provider.test_diagnostics` returns 0. `PYTHONPATH=packages/harness/lib:packages/task/lib:. python3 -m unittest packages.harness.tests.test_provider_instructions packages.harness.tests.test_provider_conformance packages.task.tests.test_provider_command_parity packages.task.tests.test_codex_command_adapter` returns 0. Fixtures prove all three surfaces can differ; `ru-ru` syntax-valid → canonical `ru-RU` → catalog `ru`; multiple registry `Preferred-Value` classes; valid registered unsupported → fallback `en`; unregistered non-private tag refuses; `x-acme` and `en-x-acme` syntax-valid/canonical but catalog-refused `unsupported-private-use`; malformed ABNF alone → `malformed`; missing RU key → EN; placeholder/literal refusal; no environment values in trace; and equal locale context with provider-owned output. Plan lint has 0 errors.

## 236

Shared locale runtime consuming the exact P2 registry carrier, explicit deterministic update producer, and typed render result/diagnostics; Task/Harness provider-owned integration; deterministic positive/negative two-provider fixtures; no production corpus, state or consumer mutation.

## 237

—

## 238

P4.2 owns production admission/rollback tooling; P4.6 owns terminal regeneration/readback of derived provider artifacts.

## 239

—

## 240

no

## 241

⬜ Not started

## 242

Implement one cumulative, machine-readable corpus ledger plus no-write inventory/check/plan and preimage-gated apply/rollback tooling that enforces English source ownership, sparse overlays, immutable tokens, independent review and generated-owner boundaries. RAG:— (repo-grounded: frozen P2 contracts/matrix, D18/D23 and current `check-translations.sh`).

## 243

The existing green RU→EN hash gate proves pair freshness but cannot prove the requested source direction, semantic review, generated ownership, corpus completeness or rollback; changing stamps alone would preserve the wrong authority. RAG:— (repo-grounded: `findings/08-p4-locale-migration-recon-2026-08-02.md` and P2.2/P2.3 scope).

## 244

Long-lived corpus ledger derived exactly from the approved P2 matrix; row schema for owner/source/overlay/generator/preimage/tokens/reviews/status/rollback; bounded-batch manifest/checkpoint/reviewer schema, verifier and deterministic resume cursor; extension-aware candidate inventory; no-write `check`/`plan`; explicit admitted-row apply and recoverable rollback; source-direction compatibility for local/external skills; generated-artifact refusal; stale/foreign/ambiguous classification; deterministic Markdown review projection; positive/negative fixtures; package/aggregate validator integration without duplicated predicates.

## 245

Translating or admitting production content; author/renderer self-approval; auto-adopting a grep match, local override or generated output; overwriting on preimage mismatch; editing provider locks/manifests directly; deleting legacy RU; introducing gettext/CLDR/pip/npm runtime dependencies; replacing existing package validators instead of composing them.

## 246

Terminal P4.1 commit/runtime fixtures · terminal P2.2/P2.3 commits · frozen overlay/review contracts · approved P2 JSON carrier matrix/checker/review fixtures · P4 finding/research · current translation/registry/task render validators and generated-owner locks.

## 247

Root slice, owned only by the root coordinator: `configs/locale-corpus-v1.json` · `core/locale/corpus.py` · `core/tests/locale/test_corpus.py` · `scripts/check-locale-corpus.py` · `scripts/test-check-locale-corpus.py` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/execution/P4.2/**` · deterministic P4 corpus fixtures/review projection · plan index. Skiller cwd slice, owned only by a fresh `codex -C packages/skiller` session: `packages/skiller/scripts/check-translations.sh` · `packages/skiller/scripts/validate.sh` (integration call only) · `packages/skiller/tests/test_translation_direction.py`. No Harness/Task source or another package validator is mutated by P4.2.

## 248

1) P4.1 Completion Notes/item commit 2) frozen P2 overlay/review contracts 3) approved P2 carrier matrix/checker/fixtures 4) P4 finding/research 5) `roadmap.md` «Per-cwd execution and evidence carrier» row P4.2 6) `packages/skiller/AGENTS.md` in the Skiller session 7) `packages/skiller/scripts/check-translations.sh` 8) `packages/skiller/lib/skiller/{common,publication,registry,vendor,skillset}.py` 9) `packages/task/lib/task/command_render.py` and `packages/harness/lib/harness/instructions.py` as read-only integration inputs 10) `packages/skiller/scripts/{test,validate}.sh` 11) package-architecture generated-artifact map 12) root `AGENTS.md`.

## 249

One JSON ledger is source of admission truth and its Markdown view is deterministic output; inventory candidates missing from the ledger or rows missing owner/preimage/review/rollback remain non-green. The root coordinator alone mutates the root slice, cumulative ledger, manifest/evidence and plan closure; the fresh Skiller session mutates only the declared Skiller slice, commits it separately and returns its commit/validation record without touching the ledger or plan. RAG:— (repo-grounded: D18/D23/D39/D44 and P2 matrix contract) Add `--batch <id>` checking plus a closed D39/D40 checkpoint shape: exact row IDs/paths/cwd/preimages, author, commits, commands/exit codes, rollback, reviewer/verdict/round, result and next row. The verifier rejects overlap/out-of-order rows, cap overflow, cross-cwd batches, author=reviewer, more than two review/fix rounds, missing commit/rollback and a resume cursor that skips the first non-accepted row. Apply accepts only `admitted` rows whose current bytes equal the recorded preimage and whose target is source-owned; generated, external-upstream, local-override, stale or ambiguous rows refuse with stable codes. RAG:— (repo-grounded: D39–D40, P2.3 and evidence-integrity/generated-artifact instructions).

## 250

Анти-подгонка: fixtures enumerate one invariant violation each and expected codes come from the frozen contract, not from live scan output. Анти-самообман: a green grep, hash reversal, fluent translation or registry regeneration does not prove ownership, equivalence, reviewer independence or rollback. Keep generic parsing in `core/locale/corpus.py`; package-specific path/owner knowledge stays in declared ledger rows/thin validators. Apply must create a recoverable preimage before mutation and re-check bytes immediately before write. Any unowned path, changed preimage, unknown contract major or missing review stops the row and the batch.

## 251

In `packages/skiller`, `bash scripts/check-translations.sh --strict`, `bash scripts/test.sh` (the package-owned runner that supplies its own monorepo/core import path) and `bash scripts/validate.sh` return 0 and are recorded in `artifacts/execution/P4.2/cwd/skiller.json`; the future `tests/test_translation_direction.py` is covered by that exact discovery runner. Back at repository root, `PYTHONPATH=. python3 -m unittest core.tests.locale.test_corpus`, `python3 scripts/test-check-locale-corpus.py`, `python3 scripts/check-locale-corpus.py --inventory --check --ledger configs/locale-corpus-v1.json`, `bash packages/skiller/scripts/check-translations.sh --strict`, `bash packages/skiller/scripts/test.sh` and `bash packages/skiller/scripts/validate.sh` return 0 before root-owned closure. Positive checkpoint fixtures prove deterministic next-row selection after an accepted commit and safe revalidation of an interrupted batch. Negative fixtures reject reversed/self review, third review round, cap overflow, cross-cwd/overlapping/out-of-order batches, resume skip, missing English fallback, token/placeholder drift, duplicate key/source, generated edit, external-upstream adoption, preimage mismatch, missing rollback and cross-provider target. `python3 packages/task/scripts/plan-lint.py plans/2026.08.02-PROVIDER-CONTRACT-LOCALE --baseline HEAD` adds 0 errors.

## 252

Versioned corpus ledger; deterministic review projection; no-write inventory/check/plan; explicit preimage-gated apply/rollback; bounded checkpoint/reviewer verifier and resume cursor consumed by P4.3–P4.6; source-direction and generated-owner validators; no production content or provider/fleet mutation.

## 253

—

## 254

P4.3–P4.6 execute reviewed carrier batches and advance one cumulative ledger; P4.6 turns compatibility mode off only after all in-scope rows are terminal.

## 255

—

## 256

no

## 257

⬜ Not started

## 258

Move every admitted local registry skill from RU-owned generation to compact-English semantic ownership with contract-defined Russian overlay/reference handling, while preserving external-upstream authority and provider publication identity. RAG:— (repo-grounded: D3/D18/D23, P2 matrix and current 173-pair translation baseline).

## 259

`SKILL.md` is already the provider-consumed compact English file, but current authoring canon, freshness stamp and root-bootstrap provenance still tell maintainers to edit `SKILL.ru.md`; ownership is not migrated until those writers, validators and every admitted row agree. RAG:— (repo-grounded: `check-translations.sh`, skill-authoring skill and `publication.py`).

## 260

All P2/P4-ledger rows classified as local skills; English canonical frontmatter/body; contract-defined RU overlay or preserved migration reference; immutable literals/snippets/references; skill-authoring/package-architecture/field-feedback-loop canon updates; translation-direction validator/tests; root-bootstrap canonical provenance; external/upstream exception behavior; per-unit independent review evidence and rollback; cumulative ledger transition for the skill carrier class.

## 261

Changing skill semantics, names, buckets, requires/produces_for, upstream strategy or provider support; rewriting external upstream EN; admitting missing/self-reviewed units; deleting a legacy RU file before its row's rollback/equivalence gate; hand-editing `.claude/skills`, `.agents/skills`, `skills.json`, plugin/marketplace manifests or publication locks; fleet/vendor updates.

## 262

Terminal P4.2 tooling/ledger commit · terminal frozen P2 contracts/matrix/review evidence · current green translation baseline · skill-authoring/package-architecture canons · generated publication locks · plan D3/D18/D23–D25.

## 263

Root slice, owned only by the root coordinator: `configs/locale-corpus-v1.json` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/execution/P4.3/{manifest.json,checkpoints/**,reviews/**,cwd/**}` · plan index and item closure. Skiller cwd slice, owned only by fresh `codex -C packages/skiller` sessions: ledger-admitted canonical/overlay paths under `packages/skiller/skills/**` · `packages/skiller/skills/repository-bootstrap/{skill-authoring,package-architecture,field-feedback-loop}/**` · `packages/skiller/scripts/check-translations.sh` · `packages/skiller/lib/skiller/{common,publication,registry,vendor,skillset}.py` only where source-direction semantics require · corresponding `packages/skiller/tests/**`. Generated provider/registry artifacts are excluded until P4.6; package sessions never mutate the root ledger, evidence or plan.

## 264

1) P4.2 Completion Notes/item commit and ledger/tool tests 2) frozen P2 overlay/review contracts and P2 matrix 3) `roadmap.md` sections «Per-cwd execution and evidence carrier» row P4.3 and «P4.3–P4.6 read-only checkpoint reviewer carrier» 4) P4 finding/research 5) `packages/skiller/AGENTS.md` 6) canonical `skill-authoring`, `package-architecture`, `field-feedback-loop` skills 7) translation/publication/lock/upstream rules 8) `packages/skiller/scripts/{test,validate}.sh` and root generated-artifact/worktree rules.

## 265

Activate `skill-authoring`; edit only ledger-admitted canonical sources/overlays and update the authoring canon before marking any corpus row migrated. Existing English bytes may stay only with recorded semantic review; external `upstream.json` keeps upstream EN authoritative and is never relabeled local. The root coordinator owns the cumulative ledger, manifest/checkpoint/review ingestion, cross-slice integration and item closure; each fresh Skiller session owns only the exact batch paths and a separate package commit. RAG:— (repo-grounded: skill-authoring/upstream rules and D23/D39/D44) Process deterministic ledger order in batches of at most 12 skill units, never crossing the `packages/skiller` cwd. Each committed checkpoint at `artifacts/execution/P4.3/checkpoints/<checkpoint-id>.json` records exact row IDs/paths/preimages, author identity, base/candidate commits, rollback, `next` and the closed roadmap validation object. The distinct read-only carrier in `roadmap.md` returns `APPROVE|FIX_REQUIRED`, and the coordinator stores its stdout unchanged as `artifacts/execution/P4.3/reviews/<checkpoint-id>.round-<1|2>.json`. Only a verifier-green `APPROVE` plus `clean|deferred-derived-only` validation advances the resume pointer. Generated projections remain intentionally stale until P4.6 only through the exact ordered `DERIVED_TARGET_STALE` rows; any other nonzero result blocks. RAG:— (repo-grounded: D40/D45/D50, P2.3 review gate and plan-protocol derived-artifact coherence).

## 266

Анти-подгонка: do not make the new validator green by accepting both source directions indefinitely or by stamping current bytes without review. Анти-самообман: `SKILL.md` already being English, provider-loadable or hash-stable does not prove it is the edited SSOT or that RU is a safe overlay. Migrate in deterministic ledger order with explicit paths; no `git add -A`, bulk machine translation, basename inference or provider projection edits. A reviewer cannot equal author/renderer and is read-only. `FIX_REQUIRED` returns to the author for a separate fix commit and fresh review; after two review/fix rounds, stop and escalate with the batch checkpoint instead of continuing. If a unit cannot preserve semantics/literals, leave it non-admitted and do not advance `next`.

## 267

Per batch, the Skiller cwd session runs `bash scripts/check-translations.sh --strict --direction en-source`, `bash scripts/test.sh` (covering `tests/test_translation_direction.py`, `tests/test_registry_state.py`, `tests/test_skillset.py`, `tests/test_codex_publication.py` and `tests/test_provider_distribution.py`) and `bash scripts/validate.sh`; tests/translation return 0, while a nonzero full validation is accepted only as roadmap `deferred-derived-only`. Back at root, `python3 scripts/check-locale-corpus.py --check --class skill --batch <checkpoint-id> --ledger configs/locale-corpus-v1.json` and `python3 scripts/check-locale-corpus.py --verify-checkpoint plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/execution/P4.3/checkpoints/<checkpoint-id>.json --review plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/execution/P4.3/reviews/<checkpoint-id>.round-<1|2>.json --ledger configs/locale-corpus-v1.json` return 0 and prove ≤12 units, exact paths/preimages, resolvable commits, distinct identities, `APPROVE`, zero reviewer mutation, rollback, next-row continuity and exact recomputed deferred rows with zero other errors. At item terminal, the class ledger/translation/tests gates are 0; package validation is either 0 or the same verified deferred set, which P4.6 must consume. Plan lint has 0 errors.

## 268

English-owned local skill corpus with contract-defined RU overlays/references, updated authoring canon/provenance, terminal skill ledger rows, one accepted checkpoint/reviewer record per bounded batch and deterministic resume/rollback evidence; no generated projection or consumer mutation.

## 269

—

## 270

P4.6 regenerates `skills.json`, root bootstrap/provider projections, plugin/marketplace manifests and publication locks once all source carrier batches are complete.

## 271

—

## 272

no

## 273

⬜ Not started

## 274

Migrate admitted Task command prose, package/plugin human text and package diagnostic messages to compact-English canonical sources with contract-defined RU catalogs, while preserving semantic command IDs, codes, literals and independent provider projections. RAG:— (repo-grounded: brief, D5/D18/D23, Task command renderer and provider artifact locks).

## 275

All current Task command sources contain Cyrillic and package diagnostics are mostly inline Russian, but provider renderers and parsers depend on byte-stable command/literal/code identities; a search/replace would mix human localization with protocol semantics. RAG:— (repo-grounded: P4 finding, `packages/task/lib/task/command_render.py`, `core/provider/values.py`).

## 276

Ledger-admitted `packages/task/commands/*.md`; contract-defined RU command overlays; canonical plugin/package descriptions and provider-rendered human prompts; stable-code + localized-message catalogs for P3/P4 diagnostic surfaces; Task/Harness/Skiller/Maind thin catalog integration; immutable command/plan literals and interpolation; Claude/Codex render parity; cumulative ledger transition for command/plugin/diagnostic rows.

## 277

Renaming semantic command IDs, UI invocations, model classes/efforts, capability IDs, JSON/schema keys or diagnostic/action codes; changing command behavior/routing; translating paths/code blocks/parser literals; editing generated Codex command files, plugin manifests or locks directly; local/fleet config writes; converting every code comment (P4.5) or development doc (P4.6).

## 278

Terminal P4.3 ledger revision · P4.1 runtime · P4.2 tooling · frozen P2/P3 contracts/status types · Task command catalog/render locks · package diagnostic inventory · independent EN/RU review evidence.

## 279

Ledger-admitted sources under `packages/task/commands/**` · `packages/{harness,maind,skiller,task}/locales/{en,ru}.json` · canonical package/plugin metadata sources identified by exact ledger paths · `core/locale/**` only for contract-required catalog additions · `core/provider/{values,diagnostics}.py` only for message-key wiring · narrow catalog calls in `packages/{harness,maind,skiller,task}/lib/**` · corresponding tests/fixtures · `configs/locale-corpus-v1.json` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/execution/P4.4/**` · plan index. Generated adapters/manifests/locks remain excluded until P4.6.

## 280

1) P4.3 Completion Notes/item commit and current ledger 2) P4.1/P4.2 runtime/tool tests 3) frozen P2 overlay/review and P3 status/diagnostic contracts 4) `roadmap.md` sections «Per-cwd execution and evidence carrier» and «P4.3–P4.6 read-only checkpoint reviewer carrier» row P4.4 5) P4 finding/research 6) Task command/literal/lock sources 7) core diagnostics/catalog sources 8) root and each affected package `AGENTS.md` before its slice.

## 281

English source owns meaning; RU catalogs may change only human prose, while command IDs, invocations, placeholders, parser literals, schema keys and stable diagnostic/action codes remain byte-identical. RAG:— (repo-grounded: D18 and Task command/linter literals) Process at most 10 ledger rows per checkpoint and never mix package cwd values in one batch; root/core rows are a separate coordinator batch. Provider artifacts are rendered independently from the same semantic source+locale context through existing owners; output-to-output translation and other-provider writes are forbidden. Every committed checkpoint at `artifacts/execution/P4.4/checkpoints/<checkpoint-id>.json` records preimages/base/candidate commits/rollback/next plus the closed roadmap validation object; only `clean|deferred-derived-only` with exact recomputed rows and zero other errors is admissible. The separate read-only carrier in `roadmap.md` returns `APPROVE|FIX_REQUIRED`, and the root coordinator stores stdout unchanged as `artifacts/execution/P4.4/reviews/<checkpoint-id>.round-<1|2>.json` before the next batch. RAG:— (repo-grounded: D5/D17/D23/D39–D40/D45/D50 and P4.1 runtime).

## 282

Анти-подгонка: golden expectations come from frozen semantic commands/codes and reviewed catalog fixtures, not by copying current provider output. Анти-самообман: a green command adapter, Russian prompt or translated exception string alone does not prove preserved routing, literals, fallback, diagnostic code/action or both providers. Use message keys and value-free structured diagnostics. Reviewer identity must differ from author/renderer; `FIX_REQUIRED` gets a separate fix commit and fresh review, with a hard maximum of two review/fix rounds before escalation. Parser-literal difference, missing review, preimage drift or provider-specific semantic branch blocks the batch and leaves the resume pointer unchanged.

## 283

Per checkpoint from repository root, `python3 scripts/check-locale-corpus.py --check --class command --class plugin --class diagnostic --batch <checkpoint-id> --ledger configs/locale-corpus-v1.json` and `python3 scripts/check-locale-corpus.py --verify-checkpoint plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/execution/P4.4/checkpoints/<checkpoint-id>.json --review plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/execution/P4.4/reviews/<checkpoint-id>.round-<1|2>.json --ledger configs/locale-corpus-v1.json` return 0; the fresh package session runs every selected cwd command and records its real exit. The verifier proves ≤10 rows, one cwd, immutable-token parity, distinct identities, `APPROVE`, zero reviewer mutation, accepted commit/rollback, contiguous resume and either `clean` or the exact `deferred-derived-only` set with zero other error. At terminal, the class ledger and expanded cross-package unittest command return 0; package validations are either 0 or the same verified cumulative deferred set. Fixtures prove EN default, RU per-surface render, missing-key EN fallback, placeholder/literal/code preservation and independent Claude/Codex targets. P4.6 must consume that exact set and later prove all commands 0. `python3 packages/task/scripts/plan-lint.py plans/2026.08.02-PROVIDER-CONTRACT-LOCALE --baseline HEAD` adds 0 errors.

## 284

English canonical Task/plugin/diagnostic prose, reviewed RU catalogs, stable code/literal preservation, two-provider render fixtures, terminal ledger rows and accepted per-cwd checkpoint/reviewer/rollback carriers; no generated artifact, config, fleet or trust mutation.

## 285

—

## 286

P4.5 migrates non-user-facing code prose; P4.6 migrates docs and regenerates/checks every derived provider artifact.

## 287

—

## 288

no

## 289

⬜ Not started

## 290

Convert every ledger-admitted code comment, docstring and test description in shared core and package source/tests/scripts to compact English without changing executable behavior, literals, public API, fixture meaning or localized diagnostics. RAG:— (repo-grounded: brief, D18/D23 and P4 corpus reconnaissance).

## 291

Cyrillic code prose is spread across hundreds of files and a raw grep cannot distinguish comments from user-facing strings, fixtures or machine literals; owner-aware classification and behavioral no-diff tests are required. RAG:— (repo-grounded: `findings/08-p4-locale-migration-recon-2026-08-02.md` and evidence-integrity rule).

## 292

Ledger-admitted comments, module/class/function docstrings, inline maintenance notes, test names/descriptions and non-runtime explanatory fixture comments across `core/`, package `lib/tests/scripts/config` source; compact-English policy and exceptions; preservation of executable bytes/AST where prose-only; independent semantic review; cumulative ledger transition for code-prose rows.

## 293

User-facing/runtime messages already owned by P4.4 catalogs; semantic code changes; API identifier renames; translating stable codes, commands, paths, shell snippets, expected diagnostics, fixtures or protocol literals; generated/vendor/upstream files; broad formatting/refactor; docs prose (P4.6); treating Cyrillic absence as semantic proof.

## 294

Terminal P4.4 ledger revision · P4.2 inventory/parser/tooling · frozen P2 compactness/comment policy · P4 finding/research · package source/test ownership and validation commands · independent English review evidence.

## 295

Only `code-prose` rows admitted in `configs/locale-corpus-v1.json` under `core/**` and `packages/{analyst,harness,maind,skiller,task}/**` · `scripts/**` where classified source-owned · related tests only when needed to preserve/verify behavior · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/execution/P4.5/**` · plan index. Generated, external and runtime-message rows are excluded.

## 296

1) P4.4 Completion Notes/item commit and current ledger 2) P4.2 inventory/parser tests 3) frozen P2 compactness/comment/review contract 4) `roadmap.md` sections «Per-cwd execution and evidence carrier» and «P4.3–P4.6 read-only checkpoint reviewer carrier» row P4.5 5) P4 finding/research 6) root and current package `AGENTS.md` 7) every exact ledger path in the current batch and nearest tests 8) concrete runner paths below 9) generated/upstream ownership records and immutable-token list.

## 297

Only admitted prose spans change; executable tokens, public identifiers, stable diagnostics, test inputs/expectations and shell/code literals retain bytes unless the frozen row explicitly classifies them as human prose. RAG:— (repo-grounded: D18/D23 and ledger token policy) A batch is bounded by both at most 12 files and at most 40 prose spans (whichever limit is reached first), stays within one root/package cwd, and records exact pre/postimages, base/candidate commit, rollback, next row and the closed roadmap validation object in `artifacts/execution/P4.5/checkpoints/<checkpoint-id>.json`. The separate read-only carrier in `roadmap.md` returns `APPROVE|FIX_REQUIRED`; the root coordinator stores stdout unchanged as `artifacts/execution/P4.5/reviews/<checkpoint-id>.round-<1|2>.json`, and only verifier-green `APPROVE` plus `clean|deferred-derived-only` validation permits resume. AST/behavioral/owning-runner failures can never be deferred; only exact recomputed generated freshness rows can. RAG:— (repo-grounded: D39–D40/D45/D50, P2.3 and evidence-integrity instruction).

## 298

Анти-подгонка: do not make the scan green by excluding broad directories/extensions or allowlisting unexplained Cyrillic. Анти-самообман: zero Cyrillic hits, unchanged AST or green unit tests alone does not prove that maintenance intent survived; reviewer evidence and ledger coverage are separate gates. Work in deterministic path/span order, preserve encoding/newlines and avoid opportunistic refactors. Reviewer identity differs from author; `FIX_REQUIRED` gets a separate fix commit and fresh review, with two rounds maximum before escalation. Ambiguous prose/runtime/literal classification leaves bytes and resume pointer unchanged.

## 299

Per batch, `python3 scripts/check-locale-corpus.py --check --class code-prose --batch <checkpoint-id> --ledger configs/locale-corpus-v1.json`, contract AST/command-byte comparison, the exact owning runner and `python3 scripts/check-locale-corpus.py --verify-checkpoint plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/execution/P4.5/checkpoints/<checkpoint-id>.json --review plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/execution/P4.5/reviews/<checkpoint-id>.round-<1|2>.json --ledger configs/locale-corpus-v1.json` return 0; verification proves ≤12 files, ≤40 spans, one cwd, distinct identities, `APPROVE`, zero reviewer mutation, accepted commit/rollback, contiguous resume and either `clean` or exact `deferred-derived-only` with zero other error. Concrete runners are: root/core `PYTHONPATH=. python3 -m unittest discover -s core/tests -p 'test_*.py'`; Analyst `bash packages/analyst/scripts/test.sh`; Harness `bash packages/harness/scripts/test.sh`; mAInd `bash packages/maind/scripts/test.sh`; Skiller `bash packages/skiller/scripts/test.sh`; Task `bash packages/task/scripts/validate.sh` (Task has no `scripts/test.sh`). At item terminal, the class ledger and every behavioral runner return 0; affected package freshness failures may be only the same verifier-enumerated cumulative deferred set. P4.6 consumes it; negative fixtures and plan lint are green.

## 300

Reviewed compact-English code prose with behavior/literal preservation evidence, terminal code-prose ledger rows, accepted per-cwd checkpoints, independent reviewer records and deterministic resume/rollback; no runtime semantic, diagnostic catalog, generated artifact or fleet mutation.

## 301

—

## 302

P4.6 owns development docs, full corpus closure and every deferred generated artifact/readback.

## 303

—

## 304

no

## 305

⬜ Not started

## 306

Migrate all ledger-admitted development documentation to compact English, close every in-scope corpus row, then run each owning generator once and prove standalone/aggregate docs plus Claude/Codex projections are coherent and readable. RAG:— (repo-grounded: brief, D12/D18/D23–D25 and docs-build/generated-artifact instructions).

## 307

Source batches P4.3–P4.5 deliberately defer derived outputs to avoid publishing half-migrated snapshots; the phase is not complete until docs, registry, command adapters, instruction projections, plugin manifests and locks are regenerated from the final admitted corpus and read back by both providers. RAG:— (repo-grounded: plan-protocol derived-artifact coherence and P4 research).

## 308

Ledger-admitted root/package development docs and README/contribution/reference prose; relative-link preservation; compactness/review evidence; terminal corpus completeness; exact generator order for Skiller registry/root bootstrap, Task provider commands, Harness instructions and docs sync; generated lock/manifest/projection readback; standalone and umbrella docs builds; package validations; two-provider locale/parity report for P5/P7; cumulative ledger closure.

## 309

User/business docs not classified as development documentation; changing documented behavior to fit code; deleting unresolved/ambiguous/foreign content; editing generated output directly; consumer/fleet publish/update; release tag/version/announcement (P7); credential/trust repair; declaring fleet health from repository-local readback.

## 310

Terminal P4.1–P4.5 commits and latest ledger · all frozen P2/P3 contracts · exact cumulative `deferred-derived-only` set · generator ownership map · package docs build contracts · P4 review evidence · plan D12/D18/D23–D25/D50–D51. P0 contract-freeze/containment authority is explicitly not a repository-generation input.

## 311

Ledger-admitted development docs under root `README.md`/`CONTRIBUTING.md`/`docs/**` and `packages/*/docs/**` · package metadata descriptions classified as docs · `configs/locale-corpus-v1.json` · deterministic outputs of named generators only: Skiller registry/marketplace/root-bootstrap projections/locks, Task Claude/Codex commands/plugins/locks/reference, Harness instruction projections/locks, docs-sync aggregate · affected package validation fixtures · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p4-terminal-regeneration.py` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/test-p4-terminal-regeneration.py` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P4.6/repository-acceptance.json` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/execution/P4.6/**` · plan index. No other generated or consumer path.

## 312

1) P4.5 Completion Notes/item commit and latest ledger 2) P4.1–P4.4 Completion Notes and deferred-derived lists 3) all frozen P2/P3 contracts 4) `roadmap.md` sections «Per-cwd execution and evidence carrier» and «P4.3–P4.6 read-only checkpoint reviewer carrier» row P4.6 5) P4 finding/research 6) package-architecture sync/generator map 7) root/current-package `AGENTS.md` 8) docs source/build/link configuration 9) Skiller/Task/Harness owning generators and checks 10) every exact ledger path in the docs batch.

## 313

Development docs describe committed behavior and keep relative internal links valid standalone and in the umbrella; compactness cannot delete constraints, rollback, validation, provenance or unsupported/degraded boundaries. RAG:— (repo-grounded: docs-build/evidence-integrity/provider-parity rules) Process at most 10 doc files per checkpoint, never crossing cwd; each records exact pre/postimages, base/candidate commit, rollback, next and the closed roadmap validation object in `artifacts/execution/P4.6/checkpoints/<checkpoint-id>.json`. The separate read-only semantic/link carrier in `roadmap.md` returns `APPROVE|FIX_REQUIRED`; the root coordinator stores stdout unchanged as `artifacts/execution/P4.6/reviews/<checkpoint-id>.round-<1|2>.json`, and only verifier-green `APPROVE` plus `clean|deferred-derived-only` validation permits source-checkpoint resume. Only after all doc checkpoints are accepted and the complete source ledger is terminal may the root coordinator open a distinct `terminal-regeneration` stage. Its plan generated-path set must equal the cumulative deferred union exactly; it invokes owning generators in declared package cwd order, requires byte-stable second runs/provider readback, and can close only when the deferred union becomes empty and every package/docs command is 0. RAG:— (repo-grounded: D39–D40/D45/D50, generated-artifact instruction, P2.3 review gate and plan-protocol coherence rule).

## 314

Анти-подгонка: never edit a generated projection or expected snapshot to hide source drift; fix its canonical source/generator or stop. Анти-самообман: one green docs build, registry count or provider plugin install does not prove relative-link integrity, English ownership, RU fallback, both-provider parity or corpus completeness. Reviewer differs from author; `FIX_REQUIRED` gets a separate fix commit/fresh review with two rounds maximum, then escalation. Implement the plan-local stdlib-only `p4-terminal-regeneration.py` with exact `plan`, `check`, `apply`, `verify-results` subcommands. `plan` writes a canonical payload with ordered owner commands, the cumulative-union `generated_target_paths` with exact target/action/preimages, cumulative deferred rows, and a distinct `authorized_target_paths` equal only to the writable target paths returned by the frozen Harness plan, sorted alphabetically by `target_path`; `plan_sha256` is computed over the payload excluding that field. `check` recomputes the cumulative generated set and the Harness-only authorization subset without writes. `apply` requires `--expected-plan-sha256`, refuses any recomputed plan/target/subset/order drift, and invokes only worktree-local owners; for Harness it passes the exact comma-joined Harness-only `authorized_target_paths` through `--authorize`. This is technical item-scope authorization, not a P0.3/P0.4 Owner D#. Terminal regeneration is not a docs batch and cannot start early or resume past a red hash/check gate; generated output is never hand-fixed.

## 315

Per docs checkpoint from repository root, `python3 scripts/check-locale-corpus.py --check --class development-doc --batch <checkpoint-id> --ledger configs/locale-corpus-v1.json` and `python3 scripts/check-locale-corpus.py --verify-checkpoint plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/execution/P4.6/checkpoints/<checkpoint-id>.json --review plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/execution/P4.6/reviews/<checkpoint-id>.round-<1|2>.json --ledger configs/locale-corpus-v1.json` return 0; the fresh cwd session runs every matrix command and records real exits. Verification proves ≤10 files, one cwd, distinct identities, `APPROVE`, zero reviewer mutation, accepted commit/rollback, contiguous resume and either `clean` or exact `deferred-derived-only` with zero other error. `python3 scripts/check-locale-corpus.py --check --require-terminal --ledger configs/locale-corpus-v1.json` returns 0 with no unclassified candidate and all reviews/rollbacks. For the distinct terminal stage, `PYTHONPATH=. python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/test-p4-terminal-regeneration.py` returns 0; `python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p4-terminal-regeneration.py plan --ledger configs/locale-corpus-v1.json --providers claude-code,codex --deferred-set plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/execution/P4.6/deferred-derived.json --output plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/execution/P4.6/terminal-regeneration-plan.json`, `python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p4-terminal-regeneration.py check --ledger configs/locale-corpus-v1.json --deferred-set plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/execution/P4.6/deferred-derived.json --plan plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/execution/P4.6/terminal-regeneration-plan.json --expected-plan-sha256 <plan_sha256>`, `python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p4-terminal-regeneration.py apply --ledger configs/locale-corpus-v1.json --deferred-set plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/execution/P4.6/deferred-derived.json --plan plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/execution/P4.6/terminal-regeneration-plan.json --expected-plan-sha256 <plan_sha256> --results plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/execution/P4.6/terminal-regeneration-results.json`, and `python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p4-terminal-regeneration.py verify-results --ledger configs/locale-corpus-v1.json --deferred-set plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/execution/P4.6/deferred-derived.json --plan plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/execution/P4.6/terminal-regeneration-plan.json --expected-plan-sha256 <plan_sha256> --results plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/execution/P4.6/terminal-regeneration-results.json --repository-acceptance plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P4.6/repository-acceptance.json` return 0. The frozen plan contains only `packages/skiller/bin/skiller registry`, `python3 packages/task/scripts/render-provider-commands.py --root . --write`, and repository-root-target Harness operations: `packages/harness/bin/harness instructions plan --target "$(git rev-parse --show-toplevel)" --provider claude-code,codex --json`; `packages/harness/bin/harness instructions apply --target "$(git rev-parse --show-toplevel)" --provider claude-code,codex --authorize <exact-alphabetic-comma-separated-authorized_target_paths> --json`; `packages/harness/bin/harness instructions check --target "$(git rev-parse --show-toplevel)" --provider claude-code,codex --json`. Fixtures reject missing/extra/reordered authorization, stale plan hash, target-set mismatch and any non-freshness deferred row. After apply, every P4.6 package/docs matrix command returns 0, deferred set is empty, second owner runs are byte-stable/zero-diff, and two-provider fixtures prove EN default plus independent RU surfaces and no cross-write. `python3 packages/task/scripts/plan-lint.py plans/2026.08.02-PROVIDER-CONTRACT-LOCALE --baseline HEAD` adds 0 errors.

## 316

Compact-English development docs; terminal corpus ledger; accepted ≤10-file per-cwd checkpoints with independent reviewer/resume/rollback evidence; a separate terminal-regeneration checkpoint; coherent regenerated registries, provider adapters, instructions, plugins and locks; byte-stable second generation; standalone/aggregate docs build proof; P5/P7 locale/parity acceptance bundle; no consumer/fleet/release/credential action.

## 317

—

## 318

P5 consumes the migration tooling and repository-local acceptance bundle for classified consumer reconciliation; P7 owns final release documentation/tag/audit.

## 319

—

## 320

no

## 321

⬜ Not started

## 322

Скомпилировать из terminal P0 evidence и P3/P4 контрактов полный no-write план миграции, доказать его на temporary roots и получить точный Owner D# над immutable action-set IDs до любого consumer write. RAG:— (repo-grounded: P0.1–P0.3, D26–D28 and `research/05-p5-consumer-migration-design.md`)

## 323

Ни `skiller update --all`, ни generic `maind sync --all` не связывают каждую live mutation с sealed P0 classification, preimage, rollback и one-owner approval; прямой запуск потерял бы exact-set coverage и authority boundary. RAG:— (repo-grounded: `findings/09-p5-consumer-migration-recon-2026-08-02.md`)

## 324

Locator-only resolution of every sealed project ID through the live registry; exact stable-ID/repository/preimage rebind; complete action manifest with one row per P0 artifact; closed action enum `no-op-unresolved|preserve|register-override|relink|refresh-managed|quarantine-remove`; provider/relative target/class/owner/evidence/action/preimage/backup/rollback/expected-readback/destination-item fields; one durable canonical-JSONL transaction schema and hash chain; stable project/action/transaction IDs; `before|applied|readback-passed|readback-failed|accepted|rollback-started|rolled-back` events; atomic project acceptance; deterministic resume/reconcile; temporary-root/crash fixtures; plan/check/apply/resume/rollback/verify-results runner; protected-project set; Owner D# and frozen manifest identity.

## 325

Any consumer/provider/user-global write; deriving classification/action from live state; storing absolute roots, raw settings, override contents, secret values or excluded hashes; implementing provider render/lock/status semantics; approving its own action set; accepting a missing/changed P0/P3/P4 deliverable.

## 326

Terminal P0.1–P0.4 commits and evidence bundle · frozen `provider-recovery-gates-v1.md` · terminal P3.2/P3.3 reconcile/status APIs · terminal P4.2 migration tooling and P4.6 repository acceptance bundle · plan D4/D8–D12/D20/D22–D29 · P5 finding/research.

## 327

`plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p5-consumer-reconcile.py` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/test-p5-consumer-reconcile.py` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-action-manifest.json` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-action-approval.md` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-transaction-log.jsonl` · deterministic transaction/crash fixtures under `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fixtures/**` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/findings/P5-fleet-preflight.md` · plan index.

## 328

1) P0.1–P0.4 Completion Notes/item commits 2) `artifacts/P0.1/evidence/{manifest.json,provider-fleet-inventory.json,provider-source-snapshot.json}` 3) `artifacts/P0-provider-fleet-classification.json` 4) `root/contracts/provider-recovery-gates-v1.md` 5) terminal P3.2/P3.3 Completion Notes, public APIs and tests 6) terminal P4.2/P4.6 Completion Notes, ledger and acceptance bundle 7) `findings/09-p5-consumer-migration-recon-2026-08-02.md` 8) `research/05-p5-consumer-migration-design.md` 9) archived `provider-{artifact,config,migration-gates}.md` contracts 10) `packages/skiller/lib/skiller/{state,update}.py` 11) `packages/maind/lib/maind/provision/sync.py` 12) root worktree/provider-parity/evidence rules.

## 329

Live registry data may resolve a root only; before any observation the runner recomputes the sealed stable project identity and rejects missing, duplicate, moved-to-different-repository or preimage-drift rows. RAG:— (repo-grounded: D26 and P0.1 revised locator boundary) Classification and action are separate exact enums: `ambiguous` only permits `no-op-unresolved`; `local-override` permits `preserve` or owner-approved `register-override`; destructive action requires `skm-managed` proof plus a separately approved exact preimage/rollback. RAG:— (repo-grounded: D28 and P0.2 gates) Each transaction ID is derived from manifest hash, destination item, stable project ID, ordered action IDs and frozen source/contract identities. Before mutation the runner append-writes canonical `before`, flushes, `fsync`s, reopens and verifies the entire ordinal/`prev_event_sha256` chain. It appends each later boundary similarly and derives aggregate results only from terminal `accepted|rolled-back` states. Acceptance is project-atomic after all selected-provider readbacks; a partial state never advances the cursor. Resume validates the chain and frozen inputs, selects the first non-terminal manifest transaction, then: exact planned postimage → fresh readback and `accepted`; failed/partial planned postimage → rollback and exact-preimage `rolled-back`; exact preimage → reconciled `rolled-back`; any third state/missing backup/mixed image/source drift → refuse all remaining actions. RAG:— (repo-grounded: D47 and `research/05-p5-consumer-migration-design.md`) The runner only sequences terminal P3/P4 public plan/apply/readback calls and validates evidence; it must not render, infer ownership, edit provider targets directly or translate output.

## 330

Анти-подгонка: expected actions come from hand-reviewed P0 rows and frozen gate tables, never from live adapter output. Анти-самообман: full row count, successful dry-run, aggregate JSON or matching content does not prove current root identity, durable intent, authority, both-provider readback or rollback. Keep the runner stdlib-only and plan-local; implement exact subcommands `plan`, `check`, `apply`, `resume`, `rollback`, `verify-results`; every mutating subcommand requires `--manifest`, `--approval`, `--recovery-contract`, `--action-set`, `--journal` and the relevant result/transaction carrier. `plan` performs zero consumer/provider-target writes and may atomically create or replace only `fleet-action-manifest.json` and the initial `fleet-transaction-log.jsonl`; `check` is strictly no-write and must leave every byte, including those two carriers, unchanged. Tests use temporary roots and fake P3 adapter responses; crash injection occurs after every append and public apply/readback boundary. Production apply imports only the frozen public entrypoint named by P3 Completion Notes. Any API/version/action/log-chain mismatch or unclassified extra row refuses the whole manifest and escalates to plan-design.

## 331

From repository root, `PYTHONPATH=. python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/test-p5-consumer-reconcile.py` returns 0 and covers missing/extra/duplicate rows, locator/preimage drift, class/action contradiction, cross-provider target, secret/root leakage, self-approval, absent rollback, destructive non-owned rows, apply without frozen approval, torn/truncated/reordered/duplicate journal events, bad previous hash, crash after every boundary, cursor skip, exact-post reconcile, exact-preimage reconcile and third-state refusal. Before `plan`, record byte identities for every rebound consumer/provider target and all plan output paths; `python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p5-consumer-reconcile.py plan --p0-manifest plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P0.1/evidence/manifest.json --classification plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P0-provider-fleet-classification.json --recovery-contract plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-recovery-gates-v1.md --control-plane-contract plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-control-plane-v1.md --repository-acceptance plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P4.6/repository-acceptance.json --manifest plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-action-manifest.json --journal plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-transaction-log.jsonl` returns 0 and its byte delta is exactly those two named atomic initialization outputs, with zero consumer/provider-target delta. The exact `check` invocation below then returns 0 with byte delta empty across all paths. Two `plan` runs produce byte-identical manifest/action-set/transaction IDs and no third output; the Owner approval names that exact manifest hash before P5.2. `python3 packages/task/scripts/plan-lint.py plans/2026.08.02-PROVIDER-CONTRACT-LOCALE --baseline HEAD` adds 0 errors.
Exact `check` expansion (the shorthand above is not a second acceptance form): `python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p5-consumer-reconcile.py check --p0-manifest plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P0.1/evidence/manifest.json --classification plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P0-provider-fleet-classification.json --recovery-contract plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-recovery-gates-v1.md --control-plane-contract plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-control-plane-v1.md --repository-acceptance plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P4.6/repository-acceptance.json --manifest plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-action-manifest.json --journal plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-transaction-log.jsonl`.

## 332

Committed non-semantic transaction runner/tests, frozen redacted exact-set action manifest, owner approval, protected-project set, initialized durable append-only transaction carrier and no-write preflight finding; no consumer or provider state change.

## 333

—

## 334

—

## 335

—

## 336

no

## 337

⬜ Not started

## 338

Выполнить только approved `preserve`/`register-override` actions, закрепив exclusions до managed repair и оставив каждый ambiguous/unsupported case явным unresolved no-op. RAG:— (repo-grounded: P0.2 classification, D4/D28 and frozen P5.1 manifest)

## 339

Same-name local trees are project-owned until доказано обратное; если repair запустить раньше preservation exclusions, provider adapter может принять override за drift или stale managed copy. RAG:— (repo-grounded: `findings/03-current-defects-2026-08-02.md`, P0.2 and predecessor ownership gates)

## 340

Rebind/verify only P5.1 rows assigned to P5.2; byte-preserving no-op for every `preserve`/`ambiguous` row; explicit project-config/lock registration only where the frozen P1 contract defines a local-override carrier and the Owner action names exact target/preimage; private backup before config mutation; P3 provider-scoped readback; redacted per-project result and rollback evidence; explicit unresolved reasons.

## 341

Copying override bytes into SKM; merging/adopting them as canonical; changing their content; inventing an override field when P1 has none; relink/refresh/cleanup; enabling a provider not selected by project intent; raw paths/content/secrets in committed evidence; touching rows outside the approved action set.

## 342

Terminal P5.1 manifest/runner/Owner D# · terminal P0 classifications · frozen P1 override/config contract and P3 APIs · P4 terminal locale/provider artifacts.

## 343

Approved live consumer targets referenced only by stable project/artifact IDs in `artifacts/P5/fleet-action-manifest.json` · private per-project backup area declared by the frozen recovery contract · append-only `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-transaction-log.jsonl` · derived `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/P5.2-results.json` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/findings/P5-local-override-disposition.md` · plan index.

## 344

1) P5.1 Completion Notes/item commit, frozen manifest/approval and complete transaction log 2) P0.2 classification and synthesis 3) frozen `provider-control-plane-v1.md`, `provider-recovery-gates-v1.md` and predecessor config/artifact contracts 4) terminal P3.2/P3.3 APIs/status codes 5) P4.6 repository acceptance bundle 6) P5 finding/research 7) each selected consumer's nearest `AGENTS.md` and exact target preimage after locator rebind.

## 345

`ambiguous` always remains `no-op-unresolved`; `local-override` content is never changed. Registration is legal only through the P1-owned explicit carrier and P3 plan/apply/readback boundary; a missing carrier, changed preimage, dirty overlapping target, unsupported provider or absent Owner action leaves the row unresolved without write. RAG:— (repo-grounded: D28, P0.2 and P3.2 boundaries) Private backups remain under the consumer's contract-defined state directory with restrictive permissions and are not committed; plan evidence stores value-free transaction/backup IDs and status only. One project is one rollback domain and one D47 transaction: `before` is durable before write, `accepted` is durable only after both-provider readback, and any partial provider/config failure reaches verified `rolled-back` before the cursor may continue.

## 346

Use only `p5-consumer-reconcile.py apply|resume` with the frozen P5.2 action-set, approval, recovery contract and shared journal. Never call raw `skiller update --all`, generic `maind sync --all`, `--force`, global repair, `git add -A` or direct JSON mutation. Compare declared preimage immediately before write and read back through P3, not by trusting the writer result. On restart never replay an `accepted` transaction or skip a non-terminal one; run `resume` against the same carriers. If preservation requires semantic merge or a new schema field, stop that row and escalate; do not normalize, translate or relocate override bytes opportunistically.

## 347

From repository root, `python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p5-consumer-reconcile.py apply --manifest plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-action-manifest.json --approval plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-action-approval.md --recovery-contract plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-recovery-gates-v1.md --action-set P5.2 --journal plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-transaction-log.jsonl --results plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/P5.2-results.json` completes or returns the documented interrupted exit; the identical carrier invocation with subcommand `resume` must then return 0 without replaying terminal transactions. `python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p5-consumer-reconcile.py verify-results --manifest plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-action-manifest.json --approval plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-action-approval.md --recovery-contract plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-recovery-gates-v1.md --action-set P5.2 --journal plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-transaction-log.jsonl --results plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/P5.2-results.json` returns 0 and proves exact-set subset, valid chain, no non-terminal transaction, project-atomic accepted/rolled-back results, registered-row backup/Owner/readback evidence, zero byte delta for preserved/unresolved/non-P5.2 rows and non-green P3 aggregate for required unresolved rows. `PYTHONPATH=. python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/test-p5-consumer-reconcile.py` and `python3 packages/task/scripts/plan-lint.py plans/2026.08.02-PROVIDER-CONTRACT-LOCALE --baseline HEAD` return 0/add 0 errors.
Exact `resume` expansion (the shorthand above is not a second acceptance form): `python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p5-consumer-reconcile.py resume --manifest plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-action-manifest.json --approval plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-action-approval.md --recovery-contract plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-recovery-gates-v1.md --action-set P5.2 --journal plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-transaction-log.jsonl --results plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/P5.2-results.json`.

## 348

Durable journal events plus committed derived override disposition/results, recoverable approved registrations and explicit unresolved set; local bytes preserved, no canonical/provider-source adoption and no fleet-health claim.

## 349

—

## 350

—

## 351

—

## 352

no

## 353

⬜ Not started

## 354

Применить approved non-destructive `relink`/`refresh-managed` actions к ownership-proven rows через independent P3 adapters, сохранив P5.2 exclusions и доказав readback/rollback по каждому consumer. RAG:— (repo-grounded: P3.2 boundary, D5/D28 and frozen P5.1 action manifest)

## 355

Equivalent, broken and stale-managed assets требуют разных preconditions; package-local update discovery или один aggregate success не доказывают exact source, provider isolation и current readback. RAG:— (repo-grounded: P0.2 classes and `findings/09-p5-consumer-migration-recon-2026-08-02.md`)

## 356

P5.1 rows assigned `relink` or `refresh-managed`; fresh rebind/preimage check; provider-scoped observe/diff; recoverable per-project backup; apply from the immutable plan; post-apply readback/status; rollback on any project/provider failure; classification/action evidence retained; P5.2 exclusion set enforced; redacted results and remaining unresolved rows.

## 357

`register-override`, `quarantine-remove`, ambiguous/local content writes, provider selection changes, direct generated-file edits, output-to-output conversion, cross-provider target access, broad hub/profile/health repair, package/source modification or release.

## 358

Terminal P5.1/P5.2 commits/results · terminal P3/P4 public APIs and acceptance bundle · frozen P0/P1 recovery/ownership contracts · exact approved action subset.

## 359

Approved live consumer targets referenced by P5.3 action-set IDs · private per-project backups · append-only `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-transaction-log.jsonl` · derived `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/P5.3-results.json` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/findings/P5-managed-reconcile-results.md` · plan index.

## 360

1) P5.1/P5.2 Completion Notes, complete transaction log and derived result hashes 2) frozen action manifest/approval 3) P0 inventory/classification and recovery contract 4) terminal P3.2/P3.3 APIs/tests/status codes 5) P4.6 provider/locale acceptance bundle 6) predecessor artifact/publication/instruction contracts 7) P5 finding/research 8) each selected consumer's nearest `AGENTS.md` and current exact target preimages.

## 361

Apply consumes the immutable P3 plan generated after fresh observation; adapter owns only its provider targets and cannot rewrite canonical intent, the other provider or P5.2 exclusions. RAG:— (repo-grounded: P3.2 and root provider-parity) `canonical-equivalent` requires named canonical identity; `broken-link` requires intended-target and parent ownership proof; `stale-managed-copy` requires a valid current lock/provenance chain and an approved refresh action. Any mismatch becomes unresolved, not a heuristic repair. One provider failure drives the current D47 project transaction through `readback-failed → rollback-started → rolled-back`; the executor may continue only after exact preimage verification and cannot publish aggregate GREEN.

## 362

Use only the P5.3 action-set ID through runner `apply|resume`, the shared durable journal and terminal P3 public APIs. Never use raw `--adopt-codex`, `--cleanup-vendored`, `--force`, generic repair or basename/content similarity as authority. Validate symlinks with `lstat` before resolution and keep targets inside the rebound project root. Compare readback to the frozen expected semantic identity, not merely to writer bytes. A missing adapter/capability/lock/source version, journal defect or dirty overlapping preimage blocks that transaction and all later cursor progress.

## 363

From repository root, `python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p5-consumer-reconcile.py apply --manifest plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-action-manifest.json --approval plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-action-approval.md --recovery-contract plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-recovery-gates-v1.md --action-set P5.3 --journal plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-transaction-log.jsonl --results plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/P5.3-results.json` completes or returns the documented interrupted exit; the identical carrier invocation with subcommand `resume` then returns 0 without replay. `python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p5-consumer-reconcile.py verify-results --manifest plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-action-manifest.json --approval plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-action-approval.md --recovery-contract plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-recovery-gates-v1.md --action-set P5.3 --journal plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-transaction-log.jsonl --results plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/P5.3-results.json` returns 0 and proves the exact subset, chain/terminality, before/apply/readback/accepted-or-rolled-back coverage, both-provider rows, P5.2 protected-byte delta 0 and non-target delta 0. `PYTHONPATH=. python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/test-p5-consumer-reconcile.py` exercises failed-readback crash+rollback to exact preimage; package public status/doctor readback has no secret/root leakage. `python3 packages/task/scripts/plan-lint.py plans/2026.08.02-PROVIDER-CONTRACT-LOCALE --baseline HEAD` adds 0 errors.
Exact `resume` expansion (the shorthand above is not a second acceptance form): `python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p5-consumer-reconcile.py resume --manifest plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-action-manifest.json --approval plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-action-approval.md --recovery-contract plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-recovery-gates-v1.md --action-set P5.3 --journal plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-transaction-log.jsonl --results plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/P5.3-results.json`.

## 364

Durable journal events plus recoverable per-project relink/managed-refresh outcomes with independent provider readback, explicit unresolved set and redacted derived evidence; no cleanup, local override adoption, source/package or release change.

## 365

—

## 366

—

## 367

—

## 368

no

## 369

⬜ Not started

## 370

Увести из active paths только exact approved `quarantine-remove` rows с повторной ownership/preimage проверкой, затем дважды перечитать весь P5 fleet и доказать no-op convergence либо опубликовать явный unresolved остаток. RAG:— (repo-grounded: frozen P0/P5 gates, D28–D29 and worktree-safety rule)

## 371

Stale or backup-looking path is not доказательство obsolete ownership, а первый успешный apply не доказывает идемпотентность; cleanup должен быть recoverable и завершаться complete second-run evidence. RAG:— (repo-grounded: P0.2 action boundary, `research/05-p5-consumer-migration-design.md`)

## 372

Only frozen `quarantine-remove` action-set IDs; fresh project/artifact/preimage/owner checks; move to private restrictive per-project quarantine before active-path removal; P3 readback/status after each project; exact rollback on failure; full P0 project/artifact coverage reconciliation; two consecutive no-write observe/diff/readback runs; redacted final outcomes, unresolved inventory and P6 handoff.

## 373

Permanent deletion of quarantine bytes; cleanup inferred from age/name/Cyrillic/backup suffix; ambiguous/local override targets; registry pruning; provider/global cache deletion; Brain/profile/health repair; claiming required unresolved rows healthy; release/tag/docs publication.

## 374

Terminal P5.1–P5.3 commits, complete transaction log and derived results · approved cleanup subset · frozen P0 recovery contract and ownership evidence · terminal P3/P4 APIs/acceptance bundle.

## 375

Approved live consumer active targets and private quarantine paths referenced by P5.4 action-set IDs · append-only `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-transaction-log.jsonl` · derived `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/P5.4-results.json` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-convergence.json` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/findings/P5-fleet-migration-verdict.md` · plan index.

## 376

1) P5.1–P5.3 Completion Notes/item commits, complete transaction log and derived results 2) frozen action manifest/approval 3) P0.1 evidence verifier, P0.2 classification and P0.3 recovery gates 4) terminal P3 reconcile/status APIs and P4.6 acceptance bundle 5) predecessor artifact/migration contracts 6) P5 finding/research 7) each selected consumer's nearest `AGENTS.md` and current exact preimage.

## 377

`quarantine-remove` is legal only with exact `skm-managed` provenance, current preimage, named active target, private quarantine target, rollback and Owner action; any mismatch is unresolved and bytes stay active. RAG:— (repo-grounded: D28 and destructive-action/worktree-safety rules) Every cleanup project uses the same D47 durable state machine; active-path removal cannot precede durable `before` with quarantine/rollback identity, and accepted means both active-path and provider readback match the frozen expected postimage. The first full pass may change only approved rows; the next two full observations are strictly no-write and semantically identical. Convergence consumes the verified terminal journal: any non-terminal/drifted transaction, required unresolved/missing/red provider row keeps readiness non-green. Evidence reports stable IDs/status/diagnostics/action/rollback only, never roots, raw output, secrets or quarantine contents.

## 378

Move with same-filesystem atomic rename when possible; otherwise copy to a mode-restricted quarantine, verify through the frozen non-secret proof, then unlink only the active managed target. Never recursively delete, glob, prune registry rows or erase quarantine in this item. Use runner `apply|resume|convergence|verify-results` with P5.4 action set and the shared journal; a source/contract/log-chain change refuses remaining actions. Idempotence is proven by two fresh public observations after journal reconciliation, not by replaying cached result JSON.

## 379

From repository root, `python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p5-consumer-reconcile.py apply --manifest plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-action-manifest.json --approval plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-action-approval.md --recovery-contract plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-recovery-gates-v1.md --action-set P5.4 --journal plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-transaction-log.jsonl --results plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/P5.4-results.json` completes or returns the documented interrupted exit; the identical carrier invocation with subcommand `resume` returns 0 without replay. `python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p5-consumer-reconcile.py convergence --manifest plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-action-manifest.json --approval plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-action-approval.md --recovery-contract plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-recovery-gates-v1.md --p0-manifest plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P0.1/evidence/manifest.json --journal plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-transaction-log.jsonl --passes 2 --output plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-convergence.json` returns 0 after two identical no-write semantic observations. `python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p5-consumer-reconcile.py verify-results --manifest plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-action-manifest.json --approval plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-action-approval.md --recovery-contract plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-recovery-gates-v1.md --all-action-sets --journal plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-transaction-log.jsonl --results plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/P5.4-results.json --convergence plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-convergence.json` returns 0 and proves journal chain/terminality, exact P0 coverage, cleanup ownership/preimage/approval/quarantine/rollback/readback evidence, explicit unresolved rows and zero planned action for migrated rows. `PYTHONPATH=. python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/test-p5-consumer-reconcile.py` proves crash rollback and quarantine permission/content boundaries; `python3 packages/task/scripts/plan-lint.py plans/2026.08.02-PROVIDER-CONTRACT-LOCALE --baseline HEAD` adds 0 errors.
Exact `resume` expansion (the shorthand above is not a second acceptance form): `python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p5-consumer-reconcile.py resume --manifest plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-action-manifest.json --approval plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-action-approval.md --recovery-contract plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-recovery-gates-v1.md --action-set P5.4 --journal plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-transaction-log.jsonl --results plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/P5.4-results.json`.

## 380

Durable terminal journal, recoverable cleanup outcomes, private quarantine disposition, complete redacted convergence bundle and honest migrated/unresolved verdict for P6/P7; no irreversible deletion, registry prune, Brain repair or release action.

## 381

—

## 382

—

## 383

—

## 384

no

## 385

⬜ Not started

## 386

Generate, obtain Owner approval for, and apply one exact recoverable Brain transaction that resolves only verified security/profile/trust/dependency/budget actions and proves independent provider readback. RAG:— (repo-grounded: P0.3/P0.4 authority split, P5.4 convergence boundary, `findings/03-current-defects-2026-08-02.md`)

## 387

Brain is currently reported with provider trust, credential, oversized/unclear first-turn and `session-observer`/`shared-memory` dependency defects, but an unsealed observation is neither current preimage nor write authority. RAG:— (repo-grounded: `findings/03-current-defects-2026-08-02.md`, D6/D10 and `research/06-p6-health-parity-design.md`)

## 388

Rebind the stable Brain identity to sealed P0/P5 evidence; fresh provider/config/security/dependency/channel/budget observation; exact no-write action plan; one Owner D# over action-set/preimage/rollback IDs; public worktree-local Skiller/Harness/mAInd/P3 apply only for approved actions; private backup; whole-project rollback on failed provider, dependency, budget or security readback; redacted result and unresolved rows.

## 389

Author-selected credential rotation/revocation; reading or recording credential values/hashes; implicit `trusted-full-access`; choosing by guess between adding a required skill and removing its requester; adopting/rewriting local skill content; generic fleet update; direct JSON/TOML/provider-file mutation; P5 unresolved repair; permanent backup/quarantine deletion.

## 390

Terminal P0.1-P0.4 evidence and exact security disposition · terminal P5.4 complete verified transaction journal, migrated/unresolved bundle and protected-project set · frozen P1 provider/recovery contracts · terminal P3.1-P3.3 resolver/reconcile/status APIs · terminal P4.6 acceptance bundle · D6/D10/D26-D31/D47-D48 · P6 finding/research.

## 391

`plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p6-brain-repair.py` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/test-p6-brain-repair.py` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6/brain-repair-plan.json` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6/brain-repair-approval.md` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6/brain-transaction-log.jsonl` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6/P6.1-results.json` · deterministic crash/reconcile fixtures under `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6/fixtures/**` · approved live Brain targets referenced only by stable artifact/action IDs · private contract-owned Brain backup area · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/findings/P6-brain-repair-verdict.md` · plan index.

## 392

1) P0.3/P0.4 Completion Notes, frozen recovery gates and security action evidence 2) P5.4 Completion Notes, complete `artifacts/P5/fleet-transaction-log.jsonl`, convergence bundle and protected-project set 3) frozen `provider-control-plane-v1.md` and `provider-recovery-gates-v1.md` 4) terminal P3.2/P3.3 public API and status-code documentation 5) P4.6 acceptance bundle 6) `findings/03-current-defects-2026-08-02.md` 7) `findings/10-p6-health-control-recon-2026-08-02.md` 8) `research/06-p6-health-parity-design.md` 9) `packages/skiller/lib/skiller/{config,status,budget,skillset}.py` 10) `packages/harness/lib/harness/{profiles,settings_audit,doctor}.py` 11) `packages/maind/lib/maind/{health,projects,provision/workspace}.py` 12) each rebound Brain root/package `AGENTS.md` 13) root security/worktree/provider-parity rules.

## 393

The no-write plan and Owner D# must name the exact stable action set, current preimages, target owners and rollback; a changed/missing/extra row refuses before mutation. RAG:— (repo-grounded: D10/D26-D29 and P5 exact-set gates) P0.4 exclusively owns credential containment; P6.1 only verifies its terminal result and keeps Brain non-green when the security row remains unresolved. Trust, approval and sandbox stay independent; full access requires an explicit named operation/target and is never inherited. RAG:— (repo-grounded: Harness profile catalog and D31) Before and after every public Skiller/Harness/mAInd/P3 write or readback boundary, the runner appends one canonical hash-chained WAL event with stable Brain/action/boundary IDs, ordinal/previous-event hash, frozen plan/approval/source identities, expected pre/post identities, backup ID and state; it flushes, `fsync`s, reopens and validates the complete chain before crossing the boundary. Results are derived only from a terminal `accepted|rolled-back` journal state. On restart, `resume` invokes `reconcile` before any write: exact approved postimage gets fresh full readback then acceptance; exact preimage is recorded rolled back; a recognized partial/failed planned postimage triggers whole-Brain rollback and exact-preimage verification; any third state, mixed image, missing backup, torn/reordered/duplicate/bad-hash event or source drift refuses every remaining action. RAG:— (repo-grounded: D52 and P6.1 whole-project rollback boundary) Required dependency closure and Skiller-owned first-turn policy must pass after apply; warning-only or unavailable evidence is non-green, not an accepted shortcut.

## 394

Keep the plan-local runner stdlib-only and non-semantic with exact subcommands `plan`, `check`, `apply`, `resume`, `reconcile`, `rollback`, `verify-results`. `plan` requires the stable Brain ID plus sealed P0/P5 evidence and frozen recovery/control-plane contracts and initializes only its named plan/WAL carriers; `check` is no-write. Every mutating/restart subcommand requires the generated plan, separate Owner approval carrier and `--journal`; `verify-results` additionally requires results. It may call only the worktree-local public CLIs and terminal P3 boundary; never import package internals, run `skiller update --all`/`maind sync --all`, use `--force`, edit provider files directly, or infer expected bytes from live output. Crash injection must fire after every durable append and every public apply/readback return, including before aggregate results. Anti-fit: derive expected actions from sealed rows before observation. Anti-self-deception: a successful writer, one provider GREEN or a lower token count is not closure without a terminal valid WAL plus fresh dual-provider, dependency, security and budget readback. On a missing carrier or semantic merge need, stop and escalate to plan-design.

## 395

From repository root, `PYTHONPATH=. python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/test-p6-brain-repair.py` returns 0 and temporary Brain-shaped fixtures reject missing/extra actions, identity/preimage drift, self-approval, secret/root leakage, implicit full access, cross-provider access, unresolved P5 mutation, dependency contradiction, absent rollback, torn/truncated/reordered/duplicate/bad-hash WAL events, missing fsync boundary and third-state reconcile; crash injection after every append and every public apply/readback boundary deterministically resumes to `accepted` or whole-Brain `rolled-back`. `python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p6-brain-repair.py plan --project-id brain --p0-manifest plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P0.1/evidence/manifest.json --p5-convergence plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-convergence.json --p5-journal plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-transaction-log.jsonl --recovery-contract plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-recovery-gates-v1.md --control-plane-contract plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-control-plane-v1.md --output plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6/brain-repair-plan.json --journal plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6/brain-transaction-log.jsonl` and the exact `check` expansion below return 0; `check` changes no byte. After `brain-repair-approval.md` names the exact plan hash and Owner D#, `python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p6-brain-repair.py apply --plan plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6/brain-repair-plan.json --approval plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6/brain-repair-approval.md --journal plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6/brain-transaction-log.jsonl --results plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6/P6.1-results.json` completes or returns the documented interrupted exit. The exact restart is `python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p6-brain-repair.py resume --plan plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6/brain-repair-plan.json --approval plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6/brain-repair-approval.md --journal plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6/brain-transaction-log.jsonl --results plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6/P6.1-results.json`; it runs the same deterministic `reconcile` boundary before any write and returns 0 only on a terminal journal. `python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p6-brain-repair.py verify-results --plan plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6/brain-repair-plan.json --approval plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6/brain-repair-approval.md --journal plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6/brain-transaction-log.jsonl --results plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6/P6.1-results.json` returns 0 and proves a valid complete chain, terminal result derivation, exact approved postimage or exact restored preimage, independent Claude/Codex rows, P0.4 disposition, Skiller dependency closure, channel hygiene and first-turn budget policy. `python3 packages/task/scripts/plan-lint.py plans/2026.08.02-PROVIDER-CONTRACT-LOCALE --baseline HEAD` adds 0 errors.
Exact `check` expansion (the shorthand above is not a second acceptance form): `python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p6-brain-repair.py check --project-id brain --p0-manifest plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P0.1/evidence/manifest.json --p5-convergence plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-convergence.json --p5-journal plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-transaction-log.jsonl --recovery-contract plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-recovery-gates-v1.md --control-plane-contract plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-control-plane-v1.md --plan plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6/brain-repair-plan.json --journal plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6/brain-transaction-log.jsonl`.
Exact read-only reconcile expansion: `python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p6-brain-repair.py reconcile --plan plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6/brain-repair-plan.json --approval plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6/brain-repair-approval.md --journal plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6/brain-transaction-log.jsonl --results plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6/P6.1-results.json`; it reports the deterministic next action but changes neither target nor WAL, while `resume` is the sole command allowed to append/act on that report.

## 396

Committed Brain transaction runner, exact approved action plan, durable hash-chained Brain WAL, deterministic resume/reconcile/rollback evidence, recoverable live outcome, dual-provider/dependency/budget/security readback and redacted human verdict; unresolved rows stay explicit and no credential value, root or private backup enters git.

## 397

—

## 398

—

## 399

—

## 400

no

## 401

⬜ Not started

## 402

Freeze and implement `provider-health-v1`, composing package-owned desired/status, capability, trust, settings, dependency, budget, locale and mAInd evidence into deterministic project and fleet verdicts without treating provider outputs as intent. RAG:— (repo-grounded: P1/P3 contracts, D5/D15/D20 and `research/06-p6-health-parity-design.md`)

## 403

Current `maind health`, `maind projects status`, `maind doctor --provider-trust`, Harness provider audit and Skiller status each cover a different axis; no public exact-set gate proves selected-provider capability health or prevents a green subset from masking missing evidence. RAG:— (repo-grounded: `findings/10-p6-health-control-recon-2026-08-02.md`)

## 404

Frozen composition schema and stable diagnostics; pure aggregate over complete project/provider/axis rows; desired support versus observed activation/readback rules; machine-readable Skiller dependency-closure status; public provider-specific Harness settings audit; mAInd `projects health` orchestration using worktree-local package CLIs and P3/P4 status; exact project-set input; deterministic redaction and compatibility tests.

## 405

New provider capability claims or manifest levels; changing skill-selection/exclude precedence; automatic repair; importing Skiller/Harness Python internals into mAInd; duplicating token math, profile policy, locale fallback, adapter readback or migration classification; secrets, absolute roots or raw tool output in durable status; declaring unsupported/not-selected capability healthy when desired requires it.

## 406

Terminal P6.1 result · terminal P0/P1/P3/P4/P5 artifacts and versions · frozen provider capability/control-plane/recovery/locale contracts · P3.3 status codes · current package audit/status/health surfaces · D5/D12/D15/D17-D18/D20-D24/D26-D34 · P6 finding/research.

## 407

`plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-health-v1.md` · `core/provider/health.py` · `core/provider/__init__.py` · `core/tests/provider/test_health.py` · `packages/skiller/lib/skiller/{common,vendor,skillset,status}.py` · `packages/skiller/tests/{test_status,test_requires}.py` · `packages/harness/lib/harness/{doctor,settings_audit}.py` · `packages/harness/tests/{test_doctor,test_settings_audit_codex}.py` · `packages/maind/lib/maind/{provider_health,projects,probe,doctor}.py` · `packages/maind/tests/{test_provider_health,test_projects,test_probe,test_doctor}.py` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/execution/P6.2/**` · plan index.

## 408

1) P6.1 Completion Notes/result 2) frozen provider/recovery/locale contracts and P3 status schema 3) `roadmap.md` «Per-cwd execution and evidence carrier» 4) archived provider capability/config/harness/analytics contracts 5) P6 finding/research 6) core provider sources 7) Skiller/Harness/mAInd sources named in Files 8) root and each affected package `AGENTS.md` before its slice.

## 409

`provider-health-v1` composes immutable results from their owners; it cannot read provider targets, recalculate token budgets, redefine capability levels or write adapter status. RAG:— (repo-grounded: D15/D20 and P3 ownership map) Exact required project/provider/capability/axis coverage is mandatory; any missing, duplicate, unreadable, unresolved or required-unsupported row makes the aggregate non-green. `not-selected`/`not-required` is legal only from desired intent. RAG:— (repo-grounded: D5/D30/D32) Provider parity compares shared semantic IDs and declared support/readback, never byte-identical files; provider-specific strengths retain independent evidence. Skiller exposes excluded/unknown required dependencies as stable diagnostics without silently changing selection. mAInd coordinates Skiller through the worktree-local subprocess and does not import package internals. RAG:— (repo-grounded: root package-boundary and CLI-routing rules)

## 410

Implement a small pure immutable evaluator in `core/provider/health.py`; hand-author contract fixtures for every state/aggregate, including required unsupported and one-provider missing. Extend the shared requires BFS with an optional diagnostic collector used by existing callers; preserve warning text and selection behavior. Wire `harness doctor --settings --provider claude-code|codex` to provider-specific readers while keeping legacy no-provider output unchanged. Add `maind projects health [--project ID|--namespace NS|--all] --evidence-set <sealed file> --json`; subprocesses have timeouts and JSON-schema checks, failures become rows, never skipped. No automatic `--fix`, repair or provider fallback is allowed.

## 411

Core tests prove deterministic ordering/hash, exact-set coverage, non-masking aggregate, legal optional unsupported/not-selected cases, required-unsupported failure, stale evidence refusal and redaction. Skiller tests prove excluded/unknown transitive requirements appear as stable diagnostics while legacy resolver selection/warnings remain compatible. Harness CLI tests prove both provider readers, malformed/unreadable layers and legacy output. mAInd tests fake public CLI/P3/P4 results and reject missing/extra projects, provider rows, capability levels, timeouts, malformed JSON, secrets/roots and one-provider success. `PYTHONPATH=. python3 -m unittest discover -s core/tests -p 'test_*.py'`, `bash packages/skiller/scripts/validate.sh`, `bash packages/harness/scripts/validate.sh`, `bash packages/maind/scripts/validate.sh` and plan lint are green.

## 412

Frozen `provider-health-v1`, pure evaluator, package-owned dependency/settings diagnostics, public exact-set mAInd health command and deterministic dual-provider/failure conformance evidence; no consumer/fleet mutation.

## 413

—

## 414

—

## 415

—

## 416

no

## 417

⬜ Not started

## 418

Run two complete, fresh `provider-health-v1` scans over the sealed P0 project set and publish a minimized per-project/per-provider evidence bundle whose aggregate stays non-green for every required unresolved or unavailable row. RAG:— (repo-grounded: D8/D26/D29-D32 and P6.2 contract)

## 419

Migration results, package conformance and one successful project do not prove current fleet health; the brief requires evidence for every project and each selected provider. RAG:— (repo-grounded: `brief/00-brief.md`, P5.4 convergence boundary and `findings/10-p6-health-control-recon-2026-08-02.md`)

## 420

Rebind live roots only as P5 permits; exact equality with sealed P0/P5 project and artifact IDs; invoke P6.2 public health over every project; separate Claude/Codex/shared-plane rows; bounded disposable memory store/recall/forget probes with cleanup evidence; two consecutive scans pinned to the same SKM/contracts; semantic comparison; minimized evidence bundle/verifier, human matrix and explicit release-blocking set.

## 421

Any repair/apply/fix during measurement; reclassification; provider selection change; persistent memory facts from probes; raw roots, settings, environment, outputs, secrets or prompt/transcript content; treating `not-run`, timeout, missing project or P5 unresolved as green; release/tag/push or permanent quarantine deletion.

## 422

Terminal P6.1/P6.2 commits, Brain result and frozen health contract · terminal P0.1 manifest/verifier and P0.2/P0.3 gates · terminal P3/P4 public status/acceptance · terminal P5.4 complete verified transaction journal, convergence and unresolved sets · pinned provider manifest and package command identities.

## 423

`plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p6-fleet-health-evidence.py` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6.3/evidence/{manifest.json,verify.py,project-set.json,provider-health-run-1.json,provider-health-run-2.json,fleet-health-verdict.json,command-results-redacted.json}` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/findings/P6-fleet-health-verdict.md` · plan index.

## 424

1) P6.1/P6.2 Completion Notes, commits, results and frozen health contract 2) P0.1 evidence manifest/verifier and P0.2/P0.3 classifications/gates 3) P3.3 status API and P4.6 acceptance bundle 4) P5.4 complete transaction log, convergence/results and `verify-results` evidence 5) P6 finding/research 6) `packages/maind/lib/maind/provider_health.py` and public CLI tests 7) `packages/skiller/skills/general/plan-protocol/snippets/source-evidence-template.md` 8) root evidence-integrity/provider-parity/worktree rules.

## 425

Live registry data resolves roots only; stable project/repository/preimage identity must match sealed P0/P5 evidence before any probe. RAG:— (repo-grounded: D26 and P5 locator boundary) Both scans use the same committed SKM source, contract versions, desired set and provider manifest; any source/config/project-set drift refuses comparison. Every required project has all expected provider and shared-plane rows; unavailable/timeouts/malformed/missing/unresolved stay non-green. RAG:— (repo-grounded: D8/D29-D32) Memory round-trip uses one collision-safe disposable token per project and proves forget; cleanup failure is a named non-green residue. Evidence stores stable IDs, versions, digests, states, diagnostics, commands and evidence classes only.

## 426

Reuse the P0 bundle pattern and P6.2 public JSON contract; do not parse provider target files, import package internals or construct expected results from observed output. Implement exact subcommands `self-test`, `write`, `check`; `write|check` require the P0 manifest, P5 convergence and complete transaction journal, frozen health contract, provider manifest and evidence directory. All subprocesses have timeouts and no `--fix`/apply/repair flags. Run 1 and run 2 independently from fresh observations, then compare canonical semantic projections after excluding only contract-declared observation timestamps/probe IDs. Anti-self-deception: row-count equality alone does not prove project identity, provider completeness, freshness, memory cleanup or redaction. A non-green fleet verdict is a valid evidence deliverable but must be listed as a P7 release blocker.

## 427

From repository root, `PYTHONPATH=. python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p6-fleet-health-evidence.py self-test --health-contract plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-health-v1.md --fixtures plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6.3/fixtures` returns 0 and rejects missing/extra/duplicate project/provider/axis rows, locator rebinding, stale contract/source, non-terminal or invalid P5 journal, one-provider masking, timeout-as-green, unclean memory probe, secret/digest/root leakage and mismatched two-run semantics. `PYTHONPATH=. python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p6-fleet-health-evidence.py write --p0-manifest plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P0.1/evidence/manifest.json --p5-convergence plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-convergence.json --p5-journal plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-transaction-log.jsonl --health-contract plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-health-v1.md --provider-manifest configs/provider-capabilities.json --output-dir plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6.3/evidence` runs two fresh read-only scans and returns 0; the identical frozen-input invocation with subcommand `check` returns 0 and changes no project/provider file. `PYTHONPATH=packages/task/lib:. python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6.3/evidence/verify.py --bundle-root plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6.3/evidence --manifest plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6.3/evidence/manifest.json` returns 0 and passes `task.task_contract.bundle_lint` with exact members and forbidden transcript/chain-of-thought/tool-payload/secret/root classes. Exact set differences versus sealed P0 and P5 migrated/unresolved sets are empty; disposable probes are forgotten and the two command-result semantics match modulo contract-declared observation fields. `python3 packages/task/scripts/plan-lint.py plans/2026.08.02-PROVIDER-CONTRACT-LOCALE --baseline HEAD` adds 0 errors.
Exact `check` expansion (the shorthand above is not a second acceptance form): `PYTHONPATH=. python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p6-fleet-health-evidence.py check --p0-manifest plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P0.1/evidence/manifest.json --p5-convergence plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-convergence.json --p5-journal plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-transaction-log.jsonl --health-contract plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-health-v1.md --provider-manifest configs/provider-capabilities.json --output-dir plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6.3/evidence`.

## 428

Complete privacy-minimized two-run fleet health bundle, per-project Claude/Codex/shared-plane matrix, explicit GREEN/non-green aggregate and exact P7 release-blocking set; no repair, persistent probe residue, raw root/secret or release action.

## 429

—

## 430

—

## 431

—

## 432

no

## 433

⬜ Not started

## 434

Produce a minimized, deterministic acceptance bundle that proves shared provider semantics by semantic capability ID and proves each provider-native strength against its own frozen support/limitation contract, without substituting byte equality or one-provider success. RAG:— (repo-grounded: D5/D15/D30/D32, `configs/provider-capabilities.json`, P6.3 contract)

## 435

Package conformance, migration completion and a green row from one provider do not prove the brief's end state; release needs one exact-set carrier joining desired selection, declared support, adapter readback and current fleet health without masking absent or unsupported required evidence. RAG:— (repo-grounded: `brief/00-brief.md`, `research/06-p6-health-parity-design.md`, `findings/11-p7-release-acceptance-recon-2026-08-02.md`)

## 436

Rebind terminal P0–P6 commit/contract identities; enumerate every shared capability and native/unsupported provider record from the frozen manifest; exact project/provider/axis equality with P6.3; independent Claude Code and Codex acceptance rows; response/plan/diagnostics locale cases; desired-versus-observed and status provenance; deterministic ordering/hash; two-run freshness comparison; minimized evidence manifest/verifier and human capability matrix; explicit release-blocker set; reusable `verify-decision-crosswalk` and `verify-release-tree` subcommands with negative exact-set/drift fixtures for P7.4.

## 437

Provider-file byte equality; support inference from generated output; changing desired selection or capability levels; live repair/fix/apply; rerunning destructive migration; raw roots, secrets, settings or tool payloads; relabeling a complete non-green P6.3 result as release-ready.

## 438

Terminal P0–P6 Completion Notes and item commits · frozen plan Contracts rows · `configs/provider-capabilities.json` · P3 status schema · P4 acceptance bundle · P5 migrated/unresolved sets · P6.3 two-run health evidence · P7 recon/research.

## 439

`plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p7-provider-acceptance.py` · deterministic fixtures under `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P7.1/fixtures/**` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P7.1/evidence/{manifest.json,verify.py,project-set.json,capability-expectations.json,acceptance-results.json,release-blockers.json}` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/findings/P7-provider-acceptance.md` · plan index.

## 440

1) terminal P0–P6 Completion Notes and commits 2) frozen `root/contracts/{provider-control-plane-v1,locale-resolution-v1,provider-recovery-gates-v1,provider-health-v1}.md` 3) `artifacts/P6.3/evidence/manifest.json` and `findings/P6-fleet-health-verdict.md` 4) `configs/provider-capabilities.json` and `docs/provider-support.md` 5) `findings/11-p7-release-acceptance-recon-2026-08-02.md` 6) `research/07-p7-release-operational-design.md` 7) archived provider capability/artifact/command/harness/instruction/analytics contracts 8) plan-protocol evidence-bundle template and root evidence/provider-parity rules.

## 441

Expected project/provider/capability/axis sets come only from sealed desired inputs and frozen contracts, never from observed output; duplicates, missing/extra rows, stale source/contract IDs or required `unsupported`/`unavailable`/`unresolved` states remain release blockers. RAG:— (repo-grounded: D5/D8/D30/D32) Shared parity compares semantic IDs, declared support and readback outcomes; native strengths and legitimate unsupported rows are evaluated independently against their manifest expectations. Locale surfaces remain independent and fallback provenance is checked without capturing environment values. Evidence is privacy-minimized, deterministically ordered and self-verifying; live commands are read-only and contain no `--fix`, `apply`, `repair` or mutation path. RAG:— (repo-grounded: P6.3 rules and root evidence-integrity/provider-parity instructions)

## 442

Implement one plan-local pure checker with exact subcommands `self-test`, `write`, `check`, `verify-decision-crosswalk`, `verify-release-tree`; reuse the P0/P6 evidence-bundle shape and public JSON outputs rather than importing package internals or parsing provider targets. `write|check` require P6 evidence, the complete verified P5 journal, contracts directory, capability manifest and output directory. `verify-decision-crosswalk` parses Decision Log rows itself and requires exact equality with crosswalk IDs; no static upper bound or caller-supplied denominator. `verify-release-tree` resolves release/protected paths and commits from the committed release manifest/evidence rather than accepting shell placeholders. Hand-author negative fixtures for one-provider masking, missing required capability, legal not-selected/unsupported, stale contract, duplicate row, locale bleed, secret/root leakage, missing/extra/duplicate/post-snapshot D#, protected-path drift and dirty release tree. Anti-self-deception: counts and hashes alone are insufficient unless exact identities and required states also match. On any frozen-contract ambiguity or absent terminal producer, stop and return to `task:plan-design`; do not add a fallback.

## 443

From repository root, `PYTHONPATH=. python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p7-provider-acceptance.py self-test --contracts-dir plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts --capabilities configs/provider-capabilities.json --fixtures plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P7.1/fixtures` returns 0 and covers all masking/staleness/leakage/crosswalk/release-tree negatives while preserving legal not-selected/unsupported cases. `PYTHONPATH=. python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p7-provider-acceptance.py write --p6-evidence plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6.3/evidence --p5-journal plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-transaction-log.jsonl --contracts-dir plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts --capabilities configs/provider-capabilities.json --output-dir plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P7.1/evidence` returns 0; `PYTHONPATH=. python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p7-provider-acceptance.py check --p6-evidence plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6.3/evidence --p5-journal plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-transaction-log.jsonl --contracts-dir plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts --capabilities configs/provider-capabilities.json --output-dir plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P7.1/evidence` returns 0 without mutation. `PYTHONPATH=packages/task/lib:. python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P7.1/evidence/verify.py --bundle-root plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P7.1/evidence --manifest plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P7.1/evidence/manifest.json` returns 0 and passes bundle lint with exact members and forbidden secret/root/transcript/tool-payload classes. Exact differences for projects/providers/shared capabilities/native strengths/axes are empty and two observations agree modulo declared volatile fields. `PYTHONPATH=. python3 -m unittest discover -s core/tests -p 'test_*.py'`, `bash packages/skiller/scripts/validate.sh`, `bash packages/task/scripts/validate.sh`, `bash packages/harness/scripts/validate.sh`, `bash packages/maind/scripts/validate.sh`, `bash packages/analyst/scripts/validate.sh`, `python3 scripts/provider-docs.py --check`, and `python3 packages/task/scripts/plan-lint.py plans/2026.08.02-PROVIDER-CONTRACT-LOCALE --baseline HEAD` return 0/add 0 errors. Any non-empty `release-blockers.json` is valid evidence but blocks P7.2/P7.3 release-green progression.

## 444

Committed self-verifying provider acceptance bundle, per-project/per-provider shared/native matrix, exact release-blocker set, human verdict and committed reusable exact-set decision/release-tree verifier subcommands for P7.4; no source/provider/fleet mutation.

## 445

—

## 446

—

## 447

—

## 448

no

## 449

⬜ Not started

## 450

Convert the frozen P1–P6 contracts and P7.1 negative matrix into permanent deterministic regression tests for provider parity, adapter ownership, locale isolation, generated drift and clean-consumer discovery. RAG:— (repo-grounded: P7.1 deliverables and existing provider-focused test surfaces)

## 451

A one-time acceptance bundle can go stale; release safety requires repository-owned tests that fail on the same masking, cross-provider write, locale bleed and false-green publication defects that the programme was created to eliminate. RAG:— (repo-grounded: `findings/11-p7-release-acceptance-recon-2026-08-02.md`, archived dual-provider P7 incidents)

## 452

Exact-set capability/status tests; provider-qualified adapter readback; cross-provider protected-path deltas; independent response/plan/diagnostics locale precedence and fallback against the pinned registry; generated source/lock/check drift; relative/absolute-target worktree-local public hook CLI planning with zero-write dry-run; clean Codex consumer discovery outside the repo; Claude compatibility goldens; timeouts/malformed JSON/unreadable state; stable diagnostic codes; deterministic evidence fixtures; validation wiring only through existing package suites.

## 453

Changing frozen semantics to make a test pass; broad product refactor; live fleet/Brain writes; real credentials/network-dependent assertions; provider-output snapshots as canonical expectations; weakening or deleting legacy compatibility coverage; tag/push/publish.

## 454

Terminal GREEN P7.1 with empty release-blocker set · frozen contracts and exact negative matrix · P4/P6 public APIs and tests · archived dual-provider conformance/release evidence.

## 455

`core/tests/provider/{test_health,test_status,test_manifest}.py` · `core/tests/locale/test_resolution.py` · `packages/skiller/tests/{test_provider_distribution,test_provider_publication_parity,test_codex_consumer_acceptance}.py` · `packages/task/tests/test_provider_command_parity.py` · `packages/harness/tests/{test_provider_conformance,test_provider_security,test_provider_trace}.py` · `packages/maind/tests/{test_provider_health,test_provider_deploy}.py` · `packages/analyst/tests/test_provider_readers.py` · `scripts/test-provider-docs.py` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P7-regression-matrix.md` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/execution/P7.2/**`.

## 456

1) P7.1 evidence/verdict 2) frozen P1/P2/P6 contracts 3) P3/P4/P6 Completion Notes and public tests 4) `findings/12-design-audit-remediation-2026-08-03.md` 5) `roadmap.md` «Per-cwd execution and evidence carrier» 6) `configs/provider-capabilities.json` 7) existing provider-focused tests named in Files 8) archived dual-provider P7 findings/conformance 9) root and each affected package `AGENTS.md` before its slice.

## 457

Add tests against frozen public behavior and stable diagnostics; do not duplicate production algorithms inside fixtures or derive expected rows from the actual result under test. RAG:— (repo-grounded: evidence-integrity and provider-parity rules) Every mutation test snapshots both provider target sets and proves only the selected adapter-owned paths changed; locale tests vary one surface at a time and assert the other two byte-identical. The hook regression invokes the worktree-local public CLI twice (`--target .` and the explicit repository absolute path), requires equal planned operation identities/statuses and plan hash, and proves hook target bytes unchanged under `--dry-run`; direct unit imports alone are insufficient. RAG:— (repo-grounded: D42 and `findings/12-design-audit-remediation-2026-08-03.md`) Clean-consumer Codex discovery uses an isolated `CODEX_HOME` outside the repository; absence of a provider binary is an explicit SKIP distinct from GREEN. Any discovered product defect is repaired only by a separate forward fix within the owning earlier item/contract; P7.2 does not silently change semantics or broaden Files.

## 458

Prefer table-driven stdlib tests and existing synthetic tmpdir helpers. Add the smallest fixture that distinguishes the old false-green behavior from the required contract; each regression must fail before the owning fix and pass after it. No sleeps, real user homes, network, credentials, global mutable registries or repo-local discovery shortcuts. Keep provider-specific expected differences explicit instead of forcing symmetric bytes. If a red test requires a frozen contract change, block and emit a scope-payload for plan-design rather than relaxing the assertion.

## 459

Run provider/locale core discovery and every affected package validation: `PYTHONPATH=. python3 -m unittest discover -s core/tests -p 'test_*.py'`; `bash packages/skiller/scripts/validate.sh`; `bash packages/task/scripts/validate.sh`; `bash packages/harness/scripts/validate.sh`; `bash packages/maind/scripts/validate.sh`; `bash packages/analyst/scripts/validate.sh`. Run `packages/harness/bin/harness hooks --target . --provider codex --observer --trusted --dry-run` and `packages/harness/bin/harness hooks --target "$(git rev-parse --show-toplevel)" --provider codex --observer --trusted --dry-run`; both return 0 with the same plan/operation identity, and pre/post SHA-256 of `.codex/hooks.json` plus `.codex/hooks/lifecycle.py` is unchanged. Run `python3 scripts/provider-docs.py --check` before and after; output stays clean. Targeted negative matrix covers one-provider masking, unsupported-required, cross-write, locale bleed, stale/mismatched registry identity, stale lock/generated output, relative-target public CLI regression, repo-local discovery masking, malformed evidence and secret/root leakage. Plan lint returns 0 and P7.1 evidence remains byte-valid.

## 460

Permanent regression coverage mapped one-to-one to P7.1 acceptance rows, including pinned-registry semantics and public hook CLI relative/absolute-target zero-write planning; deterministic test matrix and green affected package validations; no semantic-contract or external-state mutation.

## 461

—

## 462

—

## 463

—

## 464

no

## 465

⬜ Not started

## 466

Publish compact-English operator, migration, locale and rollback guidance from the frozen contracts and verified commands, then assemble a reproducible release-candidate manifest without performing a release. RAG:— (repo-grounded: brief, docs-maintenance map and release-discipline)

## 467

Green code and tests are not operable unless a cold-start maintainer can select providers/locales, inspect health, classify failure, run safe check/apply/repair boundaries and roll back from the documented public surfaces; release evidence must also distinguish committed proof from the current dirty worktree. RAG:— (repo-grounded: `brief/00-brief.md`, `docs/provider-support.md`, root worktree/generated-artifact rules)

## 468

Operator decision tree; desired config and three locale surfaces; provider-native examples; health/status diagnostics; classification and preserve-first migration; explicit plan/check/apply/repair/rollback authority; unsupported/degraded behavior; evidence/privacy boundaries; known non-green cases; exact `docs/reference.md` provenance entries for RFC 5646, the pinned IANA registry and HashiCorp drift/state-upgrade guidance; generated provider docs/check; relative-link and standalone/aggregate docs builds; CHANGELOG `[Unreleased]`; release-candidate manifest with commits, versions, registry File-Date/SHA-256/upstream/update-producer identity, contract/catalog/render hashes, validations, rollback pointers and residual blockers.

## 469

Hand-editing generated docs; duplicating support matrices; raw roots/secrets/settings; claiming every provider feature is equivalent; unverified commands; deleting quarantine or compatibility carriers; version/tag/push/publish/release announcement; editing consumer projects or Brain.

## 470

Terminal P7.1/P7.2 commits and green evidence · frozen P1/P2/P6 contracts · terminal P4 English/locale corpus and generators · P5 migration/rollback artifacts · P6 operations/health evidence · root CHANGELOG/release policy and current docs.

## 471

`scripts/provider-docs.py` · `scripts/test-provider-docs.py` · `README.md` · `docs/provider-support.md` (generated only) · `docs/develop.md` · `docs/status.md` · `docs/reference.md` · `packages/skiller/docs/multi-provider-distribution.md` · `packages/harness/docs/reference/instruction-canon.md` · `CHANGELOG.md` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/{P7-operations-readback.md,P7-release-candidate-manifest.md}` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/execution/P7.3/**` · plan index.

## 472

1) P7.1/P7.2 Completion Notes and commits 2) frozen P1/P2/P6 contracts 3) P4.6 corpus ledger/acceptance and registry update producer 4) P5.4 convergence/rollback evidence 5) P6.3 fleet-health bundle 6) `findings/01-rag-locale-2026-08-02.md` 7) `findings/02-rag-control-plane-2026-08-02.md` 8) `findings/06-p2-locale-authoring-verification-2026-08-02.md` 9) `findings/12-design-audit-remediation-2026-08-03.md` 10) `roadmap.md` «Per-cwd execution and evidence carrier» 11) root/package docs named in Files 12) docs-maintenance/release-discipline skills 13) owning generator/docs build configuration 14) root and each affected package `AGENTS.md` before its slice.

## 473

Documentation describes only committed public commands and maturity; unsupported, skipped and non-green states stay explicit. RAG:— (repo-grounded: D5/D32 and docs status maturity vocabulary) `docs/reference.md` records the exact official URLs and 2026-08-03 verification date for RFC 5646, IANA Language Subtag Registry and both HashiCorp pages; the IANA entry additionally records `File-Date: 2026-06-14`, SHA-256 `be1fad86a99e3a932d07b80c9b3c271ec2381a5909ce22420144e5077ab0a43a`, vendored path and `scripts/update-iana-language-subtag-registry.py` update producer. RAG:✅ 2026-08-03 official sources captured in `findings/12-design-audit-remediation-2026-08-03.md`. Provider support tables remain generated from the validated manifest; edit their source/generator, run `--write`, then require `--check` and byte-stable second generation. Internal package links remain relative and both standalone and umbrella builds must pass. The release-candidate manifest cites actual commits/hashes and separates repository HEAD from dirty-worktree observations; any P6/P7 release blocker keeps the candidate non-releasable. CHANGELOG records release-visible behavior once under root `[Unreleased]`; no package ledger is created.

## 474

Extend existing pages rather than creating duplicate topics. Keep the operator path check-first and fail-closed: select intent → dry/check → inspect provider-qualified diagnostics → exact authorized apply/repair → readback → rollback on mismatch. Generate the provider matrix through `scripts/provider-docs.py`; never patch its output. Validate every documented command via help/dry-run or a synthetic fixture and record its exit class. Do not include absolute machine paths, credentials, raw settings or speculative future commands. A release candidate is an evidence artifact, not authorization to tag or publish.

## 475

Run `python3 scripts/provider-docs.py --write` twice and prove the second run byte-stable, then `python3 scripts/provider-docs.py --check` and `python3 scripts/test-provider-docs.py`; all return 0. `rg -n "rfc5646|language-subtag-registry|detecting-drift|state-upgrade|2026-06-14|be1fad86a99e3a932d07b80c9b3c271ec2381a5909ce22420144e5077ab0a43a|update-iana-language-subtag-registry" docs/reference.md` resolves every required provenance field and `python3 packages/task/scripts/verify-plan-citations.py plans/2026.08.02-PROVIDER-CONTRACT-LOCALE --strict` returns 0. Run `npm --prefix packages/skiller run docs:standalone:build`, `npm --prefix packages/analyst run docs:build`, `npm --prefix packages/harness run docs:build`, `npm --prefix packages/maind run docs:build`, and `npm --prefix packages/skiller run docs:build`; every build and relative-link check returns 0 (`docs:build` owns the aggregate `scripts/docs-sync.sh` step). Every command in the operator readback is exercised with `--help`, `--dry-run`, `--check` or a synthetic target without external mutation. All affected package validations, P7.1 bundle verification and P7.2 regressions remain green. `CHANGELOG.md` has one complete `[Unreleased]` entry. Release manifest resolves every cited commit/path/hash, including the registry/upstream/update-producer identity, and carries an empty blocker set; plan lint returns 0.

## 476

Updated compact-English operator/migration/rollback docs; exact external design provenance in `docs/reference.md`; coherent generated provider reference; green docs/readback evidence, root CHANGELOG entry and reproducible non-published release-candidate manifest with pinned registry identity.

## 477

—

## 478

—

## 479

—

## 480

no

## 481

⬜ Not started

## 482

Independently audit the committed release candidate against the brief, frozen contracts, exact-set fleet evidence and provider/locale regression gates, then issue one Owner-facing GREEN/ATTENTION/RED verdict without repairing findings in the audit session. RAG:— (repo-grounded: plan-protocol audit separation and D5/D32)

## 483

The implementer-created matrix and release manifest can share the same blind spots as the implementation; a cold adversarial pass is the final control against provider masking, evidence substitution, locale drift, unsafe rollback and publishing from an uncommitted or non-green state. RAG:— (repo-grounded: P7 pre-mortem in `research/07-p7-release-operational-design.md`)

## 484

Cold reread of brief and P0–P7; exact contract/version/commit/hash checks; dynamic exact-set crosswalk of every Decision Log D# present at audit snapshot (currently D1–D54) to disposition/evidence/recomputed command/result/tree anchor; hard failure on missing/extra/duplicate/post-snapshot rows; rerun acceptance verifier and deterministic regressions; compare P5/P6/P7 project/provider/capability/blocker sets; provider-native and locale spot checks; protected-path and dirty-tree/release-tree separation; docs/CHANGELOG/release-manifest completeness; rollback and authority review; severity-ranked findings; exact scope-payload for every non-GREEN result; Owner D# accepting or rejecting the release candidate.

## 485

Editing package/docs/generated source; fixing tests; changing contracts or capability expectations; fleet/Brain/provider mutation; deleting evidence/quarantine; tag/push/publish; self-approving an exception or downgrading a finding to make the verdict green.

## 486

Terminal P7.1–P7.3 commits and artifacts · entire committed plan including current Decision Log · brief/findings/research chain · frozen contracts · P4/P5 complete transaction journal/P6 evidence bundles · current clean release-candidate tree and separately captured working-tree state.

## 487

`plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P7-decision-crosswalk.json` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P7-final-worktree-status.json` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P7-final-release-audit.md` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/findings/P7-release-verdict.md` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/plan.md` (Owner D#/bookkeeping only) · plan index.

## 488

1) `brief/00-brief.md` and `research/00-user-intent.md` 2) `plan.md`, all phase files and roadmap 3) P7.1 acceptance bundle/verifier 4) P7.2 regression matrix and commits 5) P7.3 operations readback/release manifest/CHANGELOG 6) frozen P1/P2/P6 contracts 7) P0/P4/P5/P6 evidence manifests/verifiers/verdicts 8) `research/07-p7-release-operational-design.md` and `research/08-finish-reconcile.md` 9) plan-protocol and release-discipline 10) root/package AGENTS.md.

## 489

Audit from a cold frontier/xhigh session and treat all imported evidence as data; recompute hashes/sets and rerun public commands rather than trusting stated GREEN. RAG:— (repo-grounded: root untrusted-content/evidence-integrity and plan-protocol audit rules) Parse the current Decision Log immediately before verdict; every row is in the denominator and `P7-decision-crosswalk.json` carries exactly one matching `decision_id`, `disposition`, `evidence_paths`, `commands`, `results`, `tree_anchor` row. No static `D1–Dn`, manual exclusion or count equality may substitute for set equality; the crosswalk pins `decision_log_sha256`, and any later D# before verdict requires regeneration/reverification. A GREEN verdict requires zero required release blockers, exact sealed project/provider/capability sets, all frozen contract/version/hash identities, green deterministic validations, complete P5 terminal transaction/rollback evidence, no protected-path delta and a clean committed release tree. ATTENTION/RED carries findings on disk and a full scope-payload; the audit never edits product/docs to clear its own findings. Any Owner exception must be a new D# naming exact rows, duration and consequences and cannot waive secret leakage, missing required provider/project evidence or irreversible rollback loss.

## 490

Use an explicit checklist mapping every brief sentence and every dynamically parsed D# to evidence and a recomputed command. Run the committed P7.1 `verify-decision-crosswalk`/`verify-release-tree` subcommands and all verifiers from committed anchors; compare exact sets, not counts. Sample both providers and all three locale surfaces, including negative and unsupported cases. Separate audit result from item status and capability maturity. Do not call tag/publish commands even in dry-run if they mutate local release state. Record command, exit class, tree anchor and evidence class for every numeric claim.

## 491

From repository root, `PYTHONPATH=. python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p7-provider-acceptance.py check --p6-evidence plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P6.3/evidence --p5-journal plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-transaction-log.jsonl --contracts-dir plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts --capabilities configs/provider-capabilities.json --output-dir plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P7.1/evidence` and `PYTHONPATH=packages/task/lib:. python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P7.1/evidence/verify.py --bundle-root plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P7.1/evidence --manifest plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P7.1/evidence/manifest.json` return 0. `PYTHONPATH=. python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p7-provider-acceptance.py verify-decision-crosswalk --plan plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/plan.md --crosswalk plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P7-decision-crosswalk.json --require-exact-set` returns 0 and reports equal missing/extra/duplicate sets; currently the required set is D1–D54. `PYTHONPATH=. python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p7-provider-acceptance.py verify-release-tree --release-manifest plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P7-release-candidate-manifest.md --acceptance-manifest plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P7.1/evidence/manifest.json --worktree-status plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P7-final-worktree-status.json` returns 0 and resolves protected paths/commits/contracts, clean committed release tree and forbidden secret/root/transcript/tool-payload scans without shell placeholders. Rerun `PYTHONPATH=. python3 -m unittest discover -s core/tests -p 'test_*.py'`, `bash packages/skiller/scripts/validate.sh`, `bash packages/task/scripts/validate.sh`, `bash packages/harness/scripts/validate.sh`, `bash packages/maind/scripts/validate.sh`, `bash packages/analyst/scripts/validate.sh`, `python3 scripts/provider-docs.py --check`, `python3 scripts/test-provider-docs.py`, `python3 packages/task/scripts/verify-plan-citations.py plans/2026.08.02-PROVIDER-CONTRACT-LOCALE --strict`, and `python3 packages/task/scripts/plan-lint.py plans/2026.08.02-PROVIDER-CONTRACT-LOCALE --baseline HEAD`; every executable returns 0 and lint adds 0 errors. The P5 journal is terminal/hash-valid, P6.3/P7.1 exact sets match and `release-blockers.json` is empty. The audit report contains literal `**Вердикт: GREEN|ATTENTION|RED**`, severity/findings, evidence anchors, Owner decision request and a full next launch-block; no source mutation occurs.

## 492

Committed adversarial audit report and verdict, exact dynamic D#-to-evidence crosswalk with machine-proven missing/extra/duplicate sets empty, release-tree evidence, Owner D# and next-step launch block; GREEN authorizes only the separately invoked release operation, never executes it.

## 493

—

## 494

—

## 495

—

## 496

no

## 497

Use a versioned provider-neutral desired-state contract plus adapter-owned observed status; no adapter writes canonical intent. RAG:✅ 2026-08-02 control-plane query.

## 498

Separates user selection from provider quirks; see `research/01-target-architecture.md`.

## 499

Locale precedence is command/session → environment → project → user → built-in `en`; `response`, `plan`, and `diagnostics` resolve independently. RAG:— (internal product rule grounded in `brief/00-brief.md` and synthesized in `research/02-p2-locale-authoring-design.md`).

## 500

Makes a one-off Russian plan possible without changing default response language; no external standard is claimed to prescribe this precedence.

## 501

Canonical authoring becomes compact English; Russian is a rendering overlay, not a parallel source tree. RAG:— (internal product rule grounded in `brief/00-brief.md`, current source-direction evidence in `findings/06-p2-locale-authoring-verification-2026-08-02.md`, and `research/02-p2-locale-authoring-design.md`).

## 502

Eliminates two-source language drift while preserving Russian output.

## 503

Legacy collisions are classified before mutation: equivalent, local override, stale managed copy, broken link, or ambiguous. RAG:— (repo-grounded: `findings/03-current-defects-2026-08-02.md` and `research/01-target-architecture.md`).

## 504

Fail-closed migration protects project-owned work; the five classes are SKM policy, not an externally mandated taxonomy.

## 505

Provider parity is a behavior contract: equal shared semantics and explicit supported/degraded/exclusive capability status, not byte-identical files. RAG:— (repo-grounded: root provider-parity instruction).

## 506

Providers use native strengths without silently reducing shared capability.

## 507

The known Brain credential is a security finding; revocation requires an owner gate. RAG:— (repo-grounded: findings/03-current-defects-2026-08-02.md).

## 508

Revocation can interrupt active integrations.

## 509

The frozen contracts of archived plan `2026.07.19-DUAL-PROVIDER` remain the predecessor canon; this plan may consume or add a versioned successor but never rewrite the archive. RAG:— (repo-grounded: archived contracts and literal GREEN release audit).

## 510

Replacing proven provider semantics would create a second source of truth; additive recovery and locale contracts preserve compatibility.

## 511

P0 evidence is an exhaustive, machine-checkable per-project/per-provider file manifest derived from all current `~/.swissknifeman/projects.json` records, with secret-bearing values and absolute roots excluded. RAG:— (repo-grounded: 57 existing registry records observed on 2026-08-02; brief requires per-file evidence).

## 512

Prose counts are not enough to support fleet health; committing credentials or machine-specific roots is forbidden.

## 513

Every provider-relevant inventory row receives exactly one classification: `canonical-equivalent`, `local-override`, `stale-managed-copy`, `broken-link`, or `ambiguous`; only ownership-proven actions can become automatic. RAG:— (repo-grounded: D4 and predecessor migration gates G01–G11).

## 514

Alternatives were bulk cleanup, basename matching, or preserve-all; the chosen exhaustive classification permits safe repair without losing user work.

## 515

Recovery-gate approval and live security containment are separate items P0.3/P0.4; P0.4 is a no-op when fresh evidence finds no active exposure, and otherwise requires an exact owner D# before any external write/revocation. RAG:— (repo-grounded: root security/worktree rules and predecessor gate pattern).

## 516

A design item cannot self-authorize an irreversible provider action; separation keeps approval, rollback and evidence auditable.

## 517

P0 pre-mortem: likely failure modes are partial fleet coverage, dirty-tree state reported as shipped, secret leakage into evidence, ownership inferred from names, provider success masking the other provider, and mutation outside the approved target. RAG:— (repo-grounded: brief, current dirty tree, predecessor P0/P7 findings).

## 518

Mitigations are assigned respectively to P0.1 coverage/hash gates, HEAD/worktree separation, redaction self-tests, P0.2 evidence classes, per-provider rows, and P0.3/P0.4 protected-delta/rollback gates.

## 519

Coupling surface across phases is explicit: `.swissknife.json` provider selection, provider artifact locks/status, canonical skill/command sources, instruction projections, locale resources, and fleet evidence matrices are touched or consumed by at least two of P1–P7. RAG:— (repo-grounded: phase contracts P1–P7 and `research/01-target-architecture.md`).

## 520

Later detailing must reconcile these shared carriers against earlier frozen outputs instead of creating parallel schemas.

## 521

A mid-session change of global Codex defaults is evidence, not permission to rewrite user configuration: P0.1 must capture configured defaults separately from the active runtime envelope and flag any mismatch. RAG:— (repo-grounded: `findings/04-authoring-environment-drift-2026-08-02.md`).

## 522

Default model/sandbox changed after authoring started; conflating them with the running session would corrupt route provenance and trust claims.

## 523

P1 authoring consumes the archived contracts and current repo facts, but P1 execution remains closed until P0.1–P0.4 are terminal and `provider-recovery-gates-v1.md` is frozen; no planned P0 deliverable is claimed as produced. RAG:— (repo-grounded: `phases/P0.md` Status and `phases/P1.md` contract reconcile).

## 524

Alternatives were to execute P1 against nonexistent P0 outputs or to hide the dependency; the explicit gate preserves phase-first truth.

## 525

`provider-control-plane-v1` composes existing SSOTs additively: provider config owns desired selection, capability manifest owns support, artifact locks own managed provenance, and adapters own only their provider projection/observation/status. It must not introduce a monolithic rival schema or read provider output as canonical intent. RAG:— (repo-grounded: archived provider contracts, `core/provider/{config,manifest,registry,artifact,lock}.py`, `findings/05-p1-contract-verification-2026-08-02.md`).

## 526

This is the only option that preserves predecessor identities and independent adapters; replacement/output-derived alternatives create a second source of truth.

## 527

P1 does not declare orchestration: P1.2 consumes P1.1 deliverables and P1.3 consumes P1.1/P1.2 plus terminal P0, so the three items are not independent; no long autonomous external-state chain exists. RAG:— (repo-grounded: `phases/P1.md` Inputs/Deliverables and plan-protocol §7 criterion).

## 528

The N≥3 count alone is insufficient; a workflow would add a carrier without legal fan-out.

## 529

Locale v1 separates three stages: RFC 5646 well-formed syntax (including `x-*` private-use), RFC/IANA canonicalization, and SKM catalog resolution. `ru-RU` remains canonical `ru-RU` but the v1 `en`/`ru` catalog resolves it to `ru`; other valid unsupported registered tags fall back to `en`. Any tag containing a private-use sequence is syntax-valid and canonicalized without interpreting or reordering its opaque private portion, but v1 has no private agreement/catalog mapping and therefore refuses catalog resolution with `unsupported-private-use`, never `malformed`. RFC facts: RAG:✅ 2026-08-03 RFC 5646 §2.1/§2.2.7/§4.5/§4.6 verification in `findings/06-p2-locale-authoring-verification-2026-08-02.md`; precedence, catalog and refusal policy: RAG:— (internal product rule in `research/02-p2-locale-authoring-design.md`).

## 530

Preserves BCP 47 syntax truth while making the bounded v1 catalog deterministic; requested/canonical/resolved/fallback provenance remains separate and contains no environment values.

## 531

v1 keeps compact English as the sole semantic source for canonical skills, commands, plugins, code comments and development documentation; localized human prose is a key-addressed sparse overlay with English fallback. Stable IDs, schema keys, literals, paths, commands and diagnostic codes are never translated. RAG:✅ 2026-08-02 locale fallback verification in `findings/06-p2-locale-authoring-verification-2026-08-02.md`; RAG:— (repo-grounded: `packages/skiller/scripts/check-translations.sh` and generated-artifact instruction).

## 532

A complete second source would recreate semantic drift; immutable machine tokens keep parsers and provider adapters interoperable.

## 533

P2 remains sequential and manual: P2.2 consumes the P2.1 locale contract, P2.3 consumes both earlier outputs, and all freeze/translation-review gates require an Owner decision after P1/P0 gates are terminal. RAG:— (repo-grounded: `phases/P2.md` Inputs/Deliverables and plan-protocol §7 criterion).

## 534

There are three items but no independent fan-out; a workflow would be an extra unowned carrier.

## 535

P3 composes the existing `core/provider` configuration, manifest, registry and artifact-lock primitives into a control-plane resolver and adapter boundary; it does not duplicate their identities, precedence, capability levels, lock semantics or provider projections. RAG:— (repo-grounded: `core/provider/{config,manifest,registry,artifact,lock}.py`, `research/03-p3-control-plane-implementation-design.md`).

## 536

A new monolithic store or package-local resolver would become a rival source of truth and break the predecessor's independent-adapter contract.

## 537

P3.1, P3.2 and P3.3 are sequential `implementation/high` manual items. They may begin only after P0–P2 are terminal and the P1/P2 contract paths listed in their Inputs exist at their frozen versions; absent draft files are a stop condition, not an invitation to infer the schema. RAG:— (repo-grounded: `phases/P0.md`, `phases/P1.md`, `phases/P2.md`, P3 recon finding).

## 538

P3 consumes decisions and recovery evidence that are intentionally not yet produced. Manual high-effort execution preserves the contract gate and prevents an under-routed broad provider change.

## 539

Locale runtime lives in a shared stdlib-only `core/locale` domain and consumes already-read P3 descriptors; packages own their catalogs/targets and both providers receive the same immutable per-surface context. RAG:— (repo-grounded: shared-core/provider-parity rules, P2/P3 phase boundaries and `research/04-p4-locale-migration-implementation-design.md`).

## 540

Alternatives were provider-local locale state or duplicated package resolvers; both would make fallback/provenance diverge and let an adapter become canonical intent.

## 541

English-source migration is controlled by one cumulative P2-derived admission ledger with owner, preimage, immutable tokens, independent EN/RU review, status and rollback; grep/bulk rewrite/hash reversal alone never admits a unit. RAG:— (repo-grounded: current RU→EN validator, D18, evidence-integrity and generated-artifact rules).

## 542

Alternatives were one bulk translation or per-package informal checklists; neither proves corpus completeness, generated ownership or recoverability.

## 543

Supersedes the pre-D-log three-item blanket draft (there is no accepted predecessor D#): P4 is six sequential `implementation/high`, `manual`, `Review=full` items: runtime → admission tooling → skills → commands/plugins/diagnostics → code prose → docs/terminal regeneration. No parallel Workflow script is declared because every item consumes the previous ledger revision; execution instead follows D39–D40 per-cwd and bounded-checkpoint carriers. **Consequences:** the plan pays for more item sessions, multiple committed ledger checkpoints, independent reviewer passes and terminal regeneration, in exchange for resumable migration and auditable rollback. RAG:— (repo-grounded: P4 Inputs/Deliverables, `findings/08-p4-locale-migration-recon-2026-08-02.md`, and plan-protocol §7).

## 544

The superseded draft under-routed public canon/migration work and left a bulk rewrite too large to close honestly.

## 545

P4 pre-mortem: likely failures are cosmetic source-direction reversal, translated literals/placeholders, one-provider-only Russian render, half-migrated generated output, incomplete corpus inventory/self-review, and foreign dirty-tree capture. RAG:— (repo-grounded: P4 recon/research, current dirty tree and predecessor generated/ownership gates).

## 546

Mitigations are assigned respectively to P4.2/P4.3 writer gates, P4.1/P4.2 token fixtures, P4.1/P4.4 provider-pair tests, P4.6 terminal regeneration, ledger+independent review, and explicit preimage/Files staging.

## 547

P5 may reread `~/.swissknifeman/projects.json` only as an ephemeral live-root locator; every stable project ID, repository identity and preimage must rebind to sealed P0 evidence before observation or write, and no selection/classification/ownership/action may come from host state. RAG:— (repo-grounded: P0.1 privacy boundary, `packages/skiller/lib/skiller/state.py`, P5 recon/research).

## 548

Absolute consumer roots remain out of committed evidence without making P5 unexecutable; locator drift fails before mutation.

## 549

P5 expands to four sequential full-review manual items: freeze exact no-write manifest/Owner D# → preserve/register overrides → non-destructive managed repair → owner-gated quarantine plus two-run convergence. A plan-local runner sequences only terminal P3/P4 public APIs and may not encode provider semantics. RAG:— (repo-grounded: P3.2/P3.3 boundaries and `research/05-p5-consumer-migration-design.md`).

## 550

Direct `skiller update --all`, generic `maind sync --all` or ad-hoc per-project commands lack the sealed exact-set action/rollback carrier; the four-way split keeps authority and rollback auditable.

## 551

Classification never implies mutation: `ambiguous` → unresolved no-op; `local-override` → preserve or exact owner-approved registration; `canonical-equivalent`/`broken-link` → approved relink with identity/ownership proof; `stale-managed-copy` → approved refresh or quarantine only with SKM provenance, preimage and rollback. RAG:— (repo-grounded: P0.2 five-class contract and predecessor artifact/migration gates).

## 552

Age, basename, content equality or managed-looking paths alone cannot authorize adoption, overwrite or cleanup.

## 553

P5 pre-mortem: likely failures are registry rebinding to another repo, override/managed misclassification, one-provider-only success, hidden partial fleet progress, irreversible cleanup, source change mid-rollout and evidence leakage. RAG:— (repo-grounded: P5 recon/research, worktree/evidence/provider-parity rules).

## 554

Mitigations are assigned respectively to locator rebinding, class/action exact-set gates, independent readback+rollback, the D47 durable append-only per-project transaction journal, quarantine, pinned contracts/action sets and redaction self-tests.

## 555

P6 freezes `provider-health-v1` as a composition contract over package-owned evidence: Skiller owns selection/dependencies/budget, Harness owns profiles/trust/settings, P3/P4 own provider and locale readback, and mAInd owns exact-set fleet orchestration. RAG:— (repo-grounded: `findings/10-p6-health-control-recon-2026-08-02.md`, `research/06-p6-health-parity-design.md`).

## 556

Existing commands cover different axes; a monolithic parser would duplicate their semantics, while composition preserves ownership and stable diagnostics.

## 557

Brain repair is one protected rollback domain: P6.1 must plan without writes and obtain an exact Owner D# before any credential, profile, trust, dependency or budget action. P0.4 remains the exclusive credential-containment authority; implicit full access and author-selected dependency repair are forbidden. RAG:— (repo-grounded: D6/D10, Harness profile catalog and P6 research).

## 558

The current finding is unsealed and cannot choose between security/profile alternatives or authorize an external write.

## 559

Fleet health requires exact equality with the sealed P0 project set plus complete required provider/capability/shared-plane rows; missing, unreadable, required-unsupported, P5-unresolved or stale evidence is non-green. A complete non-green P6.3 report can close the evidence item but remains a P7 release blocker. RAG:— (repo-grounded: D5/D8/D26-D29 and P6 research).

## 560

Item completion and capability readiness are different facts; relabeling a complete report GREEN would hide real fleet debt.

## 561

P6 does not declare orchestration: P6.2 consumes P6.1, P6.3 consumes P6.2, and the fleet loop is a deterministic package command/evidence exporter rather than independent agent work. RAG:— (repo-grounded: `phases/P6.md` Inputs/Deliverables and plan-protocol orchestration criterion).

## 562

A workflow would add an extra carrier without legal parallel items or improve the exact-set transaction boundary.

## 563

P6 pre-mortem: likely failures are provider masking, fleet-set drift, Brain overwrite/credential leakage, excluded required skills, package-conformance-as-project-health, evidence leakage and stale single-run GREEN. RAG:— (repo-grounded: P6 finding/research and root evidence/provider-parity rules).

## 564

Mitigations are exact provider rows, sealed-set rebinding, Owner/preimage/rollback gates, machine dependency diagnostics, separated evidence classes, minimized bundles and two pinned fresh scans.

## 565

P7 release acceptance is an exact join of frozen desired capability/provider expectations, P6.3 exact-set observations and independent locale/provider rows; provider parity is semantic and non-masking, while native/unsupported strengths keep provider-qualified expectations. RAG:— (repo-grounded: D5/D30/D32, `findings/11-p7-release-acceptance-recon-2026-08-02.md`, `research/07-p7-release-operational-design.md`).

## 566

One-provider success, package conformance, row counts or byte equality cannot authorize release; the joined blocker set is the release boundary.

## 567

P7 is four sequential manual/full-review items: exact acceptance → permanent regressions → operations/release candidate → cold frontier/xhigh audit. It declares no workflow and performs no tag, push, publish, fleet/Brain repair or destructive cleanup. RAG:— (repo-grounded: P7 Inputs/Deliverables and plan-protocol orchestration criterion).

## 568

Every item consumes the prior committed evidence, so parallel fan-out would either race a moving acceptance set or let the audit inherit implementer assumptions.

## 569

P7 pre-mortem: likely failures are one-provider masking, byte-parity pressure, locale surface bleed, repo-local Codex discovery masking, generated-doc drift, dirty/stale release evidence and an auditor clearing its own findings. RAG:— (repo-grounded: P7 recon/research and archived dual-provider P7 incidents).

## 570

Mitigations are assigned to P7.1 exact sets, P7.2 isolated/negative regressions, P7.3 owned generation and committed manifest, and read-only cold P7.4 plus Owner D#.

## 571

Design pass 3/3 accepts the P0→P7 producer/consumer graph as gap-free after adding the missing P2 phase contract/DoR carrier, registering all six exported contracts, restoring brief traceability and pinning unique future research paths. P0–P7 remain strictly sequential; no phase meets the orchestration criterion. RAG:— (repo-grounded: `research/00-user-intent.md`, `research/08-finish-reconcile.md`, phases/P0.md–P7.md and final roadmap).

## 572

The executor now has one recoverable chain from owner intent through frozen contracts to fleet evidence and release audit; unresolved owner choices remain explicit item gates rather than author assumptions.

## 573

Every multi-package item uses the package-cwd protocol in `roadmap.md`: one root coordinator owns integration, the shared manifest and item closure; every package mutation runs from a fresh `codex -C packages/<name>` session under that package's rules and emits a package-scoped evidence record before integration. RAG:— (repo-grounded: root `AGENTS.md` package-scope-routing and affected item `Files`).

## 574

Keeps the existing 30 item identities while making package rules, ownership, commits and validation evidence explicit across cold sessions.

## 575

P4.3–P4.6 execute in deterministic, package-scoped ledger batches with hard row/file limits, one committed checkpoint per batch, resume from the first non-accepted row, a distinct read-only reviewer identity, and at most two review/fix rounds before plan-design escalation; P4.6 terminal regeneration starts only after every source batch is accepted. RAG:— (repo-grounded: `findings/08-p4-locale-migration-recon-2026-08-02.md`, P2.3 review contract, and plan-protocol commit/derived-artifact rules).

## 576

Bounds context and rollback radius for the measured 173-skill/279-code-file/135-doc-file discovery corpus without changing item statuses or letting author/renderer self-certify.

## 577

Locale canonicalization is pinned to one faithfully vendored carrier, `core/locale/data/language-subtag-registry.txt`, with adjacent `upstream.json`: official IANA URL, `File-Date: 2026-06-14`, SHA-256 `be1fad86a99e3a932d07b80c9b3c271ec2381a5909ce22420144e5077ab0a43a`. P2.1 freezes bytes/provenance, P4.1 implements the stdlib reader and sole explicit update producer, and P7.3 verifies the same identity in docs/release evidence. RAG:✅ 2026-08-03 official IANA registry and RFC 5646 verification in `findings/12-design-audit-remediation-2026-08-03.md`.

## 578

A host-time registry lookup or duplicated hardcoded subset would let contract checker, runtime and release use different registration/`Preferred-Value` truth; one pinned data carrier preserves reproducibility and shared-core ownership.

## 579

The observed `harness hooks --target . --provider codex --observer --trusted --dry-run` failure is a public CLI target-normalization defect: P0.1 records it as non-green baseline evidence, P3.2 owns the forward implementation/regression fix at the Harness boundary, and P7.2 permanently smokes relative and absolute targets with equal planned operations and zero writes. The shared lock invariant remains explicit absolute roots. RAG:— (repo-grounded: exact reproduction in `findings/12-design-audit-remediation-2026-08-03.md`, `packages/harness/lib/harness/hooks.py`, `core/provider/lock.py`).

## 580

Green direct unit imports did not exercise the source→target public control path; assigning one implementation owner and one release regression prevents the false-green from recurring without weakening core safety.

## 581

Supersedes only D38's pre-audit «gap-free readiness» verdict, while preserving its P0→P7 order, accepted F1–F7 remediation and 30-item topology: readiness now additionally requires the root-relative P0 validations, D41 registry carrier, D42 public hook path and P7.3 provenance gate. The append-only audit denominator is **8 phases (P0–P7)**, correcting the first audit's historical «seven phases» sentence without rewriting that report. **Consequences:** plan v1.0.2 adds one vendored data/provenance carrier and tighter evidence/validation obligations, then pays for another independent design-audit round; statuses remain 0/30 and execution stays closed. RAG:— (repo-grounded: `## Audit design — 2026-08-03 (заход 2)` F8–F12 and remediated phase specs).

## 582

The second audit proved that structural lint green did not establish copy/paste executability, registry reproducibility or public hook-path coverage; append-only correction keeps the prior report as provenance while removing its conclusions from readiness.

## 583

D39's per-cwd rule explicitly includes P4.2 and P4.3: the root coordinator alone owns `configs/locale-corpus-v1.json`, plan evidence, integration and closure, while a fresh `codex -C packages/skiller` session owns only the exact Skiller paths and package validation commands enumerated in P4/roadmap. RAG:— (repo-grounded: root/package `AGENTS.md`, P4.2/P4.3 Files/Validation and `roadmap.md` exact slice rows).

## 584

Removes the remaining root-session write path into `packages/skiller/**` without adding item IDs or splitting shared-ledger authority.

## 585

Every P4.3–P4.6 checkpoint uses the dedicated frontier/high zero-mutation reviewer carrier in `roadmap.md`: committed checkpoint + manifest-limited diff + frozen contracts are exact inputs; reviewer stdout is one `APPROVE

## 586

FIX_REQUIRED` JSON record owned by the root coordinator; round-1 fixes require a separate commit and fresh round-2 identity, while a second `FIX_REQUIRED` escalates to plan-design and forbids resume. RAG:— (repo-grounded: P2.3, D40 and `roadmap.md` reviewer carrier).

## 587

P0.4 evidenced no-op is a deterministic Validation result, never an owner gate: it requires the frozen checker to pass over committed P0.1 classification plus fresh independent detector/provider-trust evidence with `action_set=[]`, zero plaintext-secret findings and zero protected-target delta. Only a non-empty mutation branch requires the exact containment D#. RAG:— (repo-grounded: P0.3/P0.4 Validation and `roadmap.md` deterministic note).

## 588

Avoids asking the owner to authorize no mutation or letting an executor treat no-op as a waivable approval branch; security writes remain fail-closed.

## 589

P5.1–P5.4 share one durable append-only `artifacts/P5/fleet-transaction-log.jsonl`: canonical hash-chained events are flushed and `fsync`'d before/after each project transaction boundary, carry stable project/action/transaction IDs, frozen manifest/action-set/source identities, pre/post hashes and the closed `before → applied → readback-passed

## 590

readback-failed → accepted

## 591

Every F18-listed Validation uses exact worktree-local root or package-cwd invocations. `roadmap.md` carries the closed P4.4/P4.6 cwd→command matrix; P5.1–P5.4, P6.1/P6.3 and P7.1/P7.4 name helper path, subcommand, frozen manifest/action/evidence/contract inputs, output carrier and exact plan-lint invocation. Prose aliases such as “targeted tests”, “owning check”, “verify-results”, “Helper --write/--check” or “rerun green” are not acceptance commands. RAG:— (repo-grounded: audit F18 and affected phase `Files`/Validation).

## 592

Cold-start executors and the final auditor can reproduce the same gate byte-for-byte; broader full-suite commands are accepted where a package has no narrower stable public runner.

## 593

P7.4's decision denominator is computed at audit time from every `D#` row in `plan.md` Decision Log, not from a static upper bound. The current exact set is D1–D49, including this remediation. `artifacts/P7-decision-crosswalk.json` must contain exactly one row per parsed D# and no other row; each row carries disposition, evidence paths, recomputed commands/results and tree anchor. The P7.1 committed helper's `verify-decision-crosswalk` subcommand fails on missing, extra, duplicate or post-crosswalk D# before P7.4 can emit GREEN. RAG:— (repo-grounded: audit F16, P7.1/P7.4 and append-only Decision Log).

## 594

Future decisions enter the release audit automatically and stale exact-set reports fail closed; the audit pays for a full decision-to-evidence crosswalk rather than a range checklist.

## 595

P4.3–P4.6 source checkpoints use one machine state, `deferred-derived-only`, only when the checkpoint verifier recomputes an exact ordered set of stable `DERIVED_TARGET_STALE` rows (`cwd`, command ID, target path and owning generator), proves zero non-freshness failures and binds the set to the cumulative ledger/resume cursor. P4.6 terminal regeneration consumes that exact union; its frozen helper plan records its canonical payload hash and the Harness writable targets in alphabetic `target_path` order, and Harness `apply` receives them byte-for-byte through `--authorize`. After regeneration every package/docs command must return 0, the deferred set must be empty and a second owner run must be byte-stable. RAG:— (repo-grounded: audit F19/F20, `packages/harness/lib/harness/instructions.py:512-535`, `roadmap.md` checkpoint carrier and plan-protocol derived-artifact coherence).

## 596

Gives expected generated drift one reproducible checkpoint/resume representation without greenwashing unrelated validation failures; exact positional authorization preserves the Harness write boundary and the terminal all-green gate.

## 597

Three authority classes are distinct: P0.3 `contract_freeze_decision` approves only recovery-contract semantics; conditional P0.4 `containment_mutation_decision` alone authorizes exact security/trust targets; P4.6 ordinary repository generation needs neither and is gated by the terminal ledger, frozen helper-plan hash and exact Harness `--authorize` set. P0.3 produces a versioned plan-local stdlib checker plus schema/tests/evidence; P0.4 verifies the checker byte hash and runs its exact `no-op` or `mutation` branch command, with a containment D# accepted only by the mutation branch. RAG:— (repo-grounded: audit F21/F22, D10/D46, P0.3/P0.4 and the Harness apply contract).

## 598

Prevents a contract approval from becoming ambient write authority, keeps the no-op branch deterministic and makes the P0.3 producer consumed by P0.4 executable from a cold session.

## 599

P6.1 uses its own durable append-only `artifacts/P6/brain-transaction-log.jsonl`: stable Brain/action/boundary IDs, frozen plan/approval/source identities, exact pre/post identities and a canonical hash chain are appended, flushed, `fsync`'d, reopened and verified before and after every public Skiller/Harness/mAInd/P3 write or readback boundary. `resume` first runs deterministic `reconcile`: exact approved postimage gets fresh readback then acceptance, exact preimage is recorded rolled back, a recognized partial/failed postimage triggers whole-Brain rollback, and any third state, torn chain, missing backup or source drift refuses. Result JSON is derived only from a terminal journal; crash injection covers every append and public CLI boundary. RAG:— (repo-grounded: audit F23, D47's measured failure class and P6.1 whole-project rollback promise).

## 600

Extends durable intent across the live Brain crash window; the cost is a second transaction-specific WAL and explicit resume/reconcile/rollback evidence rather than relying on a post-operation result file.

## 601

P5.1 `plan` is no-write only with respect to consumer/provider targets and may atomically create exactly the named manifest and initial journal; `check` changes no byte anywhere. Validation records separate byte-delta assertions for the two subcommands and rejects any other initialization output. RAG:— (repo-grounded: audit F24 and P5.1 Files/Validation).

## 602

Removes the literal contradiction while retaining a fail-closed target boundary and deterministic initialization carrier.

## 603

Targeted fifth-audit remediation closes F19–F25 without changing brief intent, the accepted F1–F18 semantics, the 30-item topology or any item status. D49's dynamic verifier now resolves the append-only Decision Log exact set as D1–D54; execution remains closed until a repeated independent design audit is GREEN. RAG:— (repo-grounded: `## Audit design — 2026-08-03 (заход 5)`, D50–D53 and remediated P0/P4/P5/P6/roadmap carriers).

## 604

Keeps audit history append-only and makes the new checker/authority/deferred-state/WAL decisions visible to the release crosswalk before execution opens.

## 605

2026-08-02 | plan-design/frontier-high | Design pass 1/3: brief, RAG, synthesis, phase skeletons and current defects captured.

## 606

2026-08-02 | plan-design/gpt-5.6-sol-high | P0 detailed to DoR: four sequential evidence/safety items, predecessor-contract reuse, routing and owner-gated containment fixed; P1 remains the next design phase.

## 607

2026-08-02 | plan-design/gpt-5.6-sol-high | P1 detailed to DoR: three sequential contract items, honest unclosed-P0 gate, legal per-item routing and predecessor composition fixed; P2 is next.

## 608

2026-08-02 | plan-design/gpt-5.6-sol-high | Design pass 2/3: P2 detailed to DoR; BCP 47/fallback evidence, English-source overlay boundary and translation-review gates are explicit; P3 is next.

## 609

2026-08-02 | plan-design/frontier-high (runtime mapping unverified; see findings/07) | P3 detailed to DoR: resolver, adapter boundary and status diagnostics compose existing primitives; P0–P2 terminal/frozen artifacts remain hard execution inputs; P4 is next.

## 610

2026-08-02 | plan-design/gpt-5.6-sol-high (effort self-attested; see findings/08) | P4 detailed to DoR as six sequential full-review items: shared locale runtime, admission ledger, four carrier migrations and terminal regeneration; P5 is next.

## 611

2026-08-02 | plan-design/gpt-5.6-sol-high (effort self-attested; see findings/09) | P5 detailed to DoR as four sequential full-review items: exact action freeze, override preservation, managed repair and recoverable cleanup/convergence; P6 is next.

## 612

2026-08-02 | plan-design/gpt-5.6-sol-high (effort self-attested; see findings/10) | P6 detailed to DoR as three sequential manual/full-review items: owner-gated Brain repair, frozen composed health contract and exact-set two-run fleet evidence; P7 is next.

## 613

2026-08-02 | plan-design/gpt-5.6-sol-high (effort self-attested; see findings/11) | P7 detailed to DoR as four sequential full-review items: exact acceptance, permanent regressions, operations/release candidate and cold audit; `finish` is next.

## 614

2026-08-02 | plan-design/frontier-high (Codex config gpt-5.6-sol; active effort self-attested) | Design pass 3/3: P0–P7 producer/consumer contracts, brief trace, Routing and 30-item roadmap reconciled; 5 DoR/provenance/path gaps closed; independent design audit is next.

## 615

2026-08-03 | plan-design/gpt-5.6-sol-high | Design-audit remediation F1–F7: locale layers/private-use, RAG provenance, concrete P4.5 runners, per-cwd carriers, bounded P4 checkpoints/review, deterministic release gates and D24 trace reconciled; statuses and Design Passes remain unchanged.

## 616

2026-08-03 | plan-design/gpt-5.6-sol-high (effort not exported by runtime) | Design-audit remediation F8–F12: root-relative P0 validation, pinned IANA carrier/provenance/update path, public hook CLI owner/regressions, `docs/reference.md` ownership and append-only 8-phase correction reconciled; statuses remain 0/30.

## 617

2026-08-03 | plan-design/gpt-5.6-sol-high (effort not exported by runtime) | Design-audit remediation F13–F15: P4.2/P4.3 exact per-cwd slices, executable P4.3–P4.6 reviewer carrier and deterministic P0.4 no-op note reconciled; statuses and Design Passes remain unchanged.

## 618

2026-08-03 | plan-design/gpt-5.6-sol-high (effort not exported by runtime) | Design-audit remediation F16–F18: dynamic exact D# crosswalk, durable P5 write-ahead/resume carrier and exact root/per-cwd validation invocations reconciled; statuses and Design Passes remain unchanged.

## 619

2026-08-03 | plan-design/gpt-5.6-sol-high (effort not exported by runtime) | Design-audit remediation F19–F25: exact Harness authorization/deferred-derived state, executable P0 checker and typed authority, P6 WAL/resume, P5 no-write wording and finding scope history reconciled; statuses remain 0/30.

## 620

2026-08-03 | plan-design/gpt-5.6-terra (effort not exported by runtime) | ACTIVE transferred to `2026.08.03-ARTIFEX-SUPERVISOR`; this plan is paused with F1–F25, D1–D54 and all 30 item statuses unchanged.

## 621


