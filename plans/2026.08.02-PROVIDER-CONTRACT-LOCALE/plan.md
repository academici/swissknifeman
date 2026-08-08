# 2026.08.02-PROVIDER-CONTRACT-LOCALE — Provider control plane, localization, and fleet recovery

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | 2026.08.02-PROVIDER-CONTRACT-LOCALE |
| Title | Provider control plane, localization, and fleet recovery |
| Version | 1.0.5 |
| Status | 🟡 In progress |
| Document Type | Executable Master Plan |
| Authoring Model | gpt-5.6-sol/high |
| Last Updated | 2026-08-03 |
| Repository | swissknifeman |
| Related Packages | skiller · harness · maind · task · core |
| Execution Mode | phase-first, contract-first |
| Target Operator Models | implementation (execution) · economy (recon) · frontier (design/audit) |
| Approval Owner | repository owner |
| Home | repo:swissknifeman |
| visibility | private |
| Paused By | 2026.08.03-ARTIFEX-SUPERVISOR, 2026-08-03 |
| Design Passes | 3/3 — cross-phase `finish` plus targeted audit remediation F1–F25 reconciled all P0–P7 contracts, brief coverage, routing and the final execution roadmap; repeated independent design audit is next |

## 1. Context

SKM must be a reliable hub rather than a collection of provider-specific copies. The user
selects capabilities once per project; Claude Code and Codex independently realize that
semantic selection and keep state isolated. Canonical skills, plugins, comments and
development documentation move to compact English. Localized rendering remains available,
with English default and independent inheritable language choices for responses, plans and
diagnostics.

The plan starts with security and evidence because current fleet state includes red provider
trust, legacy projections and unclassified local changes. No fleet cleanup or credential
rotation is implicit authority. A project is not reported healthy until both adapters are
observed, reconciled and behaviorally probed.

## 2. Execution Rules

- Canonical intent is the only cross-provider source of truth; adapters own only projections and status.
- Claude Code and Codex may not write each other's target files or share mutable adapter state.
- Existing local skills are preserved until classified; destructive migration needs ownership proof and backup.
- English is source language; localized text is a rendered overlay, never a second implementation.
- Locale resolution and fallback are deterministic, logged and tested at each precedence boundary.
- Every fleet claim names inspected projects and evidence; skipped projects remain non-green.
- Secret rotation/revocation requires an owner-authorized security step; secrets never appear in reports.
- Generated artifacts are regenerated through their owner and checked, never hand-edited.

## 3. Routing

| Items | Model class/effort | Exec | Why |
|:--|:--|:--|:--|
| P0.1 | implementation/high | manual | prescribed read-only fleet capture and final evidence verification; high effort is mandatory, frontier tier is not |
| P0.2–P0.3 | frontier/high | manual | ambiguous ownership classification and a recovery contract that freezes fleet/security boundaries |
| P0.4 | implementation/high | manual | execute only the exact owner-approved external containment transaction and verify rollback |
| P1.1 | frontier/high | manual | freezes the desired/status schema and diagnostics with open contract decisions |
| P1.2 | frontier/high | manual | freezes ecosystem-wide capability negotiation and provider ownership boundaries |
| P1.3 | frontier/high | manual | freezes migration/rollback authority and compatibility after Owner approval |
| P2.1–P2.3 | frontier/high | manual | locale contract and compact-English authoring decisions are still open |
| P3.1 | implementation/high | manual | public shared-core resolver against frozen P1/P2 contracts; high effort is mandatory while implementation tier remains sufficient |
| P3.2 | implementation/high | manual | multi-package adapter boundary and ownership-preserving reconciliation against frozen contracts |
| P3.3 | implementation/high | manual | redacted status/diagnostic semantics feed later migration and fleet gates; full review is mandatory |
| P4.1 | implementation/high | manual | public locale runtime and provider render boundary against frozen contracts; full review required |
| P4.2 | implementation/high | manual | migration admission/rollback validator becomes the write gate for repository canon |
| P4.3 | implementation/high | manual | skill source-ownership migration changes canon consumed by every project; full review required |
| P4.4 | implementation/high | manual | command/plugin/diagnostic migration must preserve parser literals and provider parity |
| P4.5 | implementation/high | manual | broad code-prose migration requires behavior/literal preservation and full review |
| P4.6 | implementation/high | manual | terminal docs/corpus migration and protected generated-artifact regeneration/readback |
| P5.1 | frontier/high | manual | freezes the exact fleet action manifest and Owner authority while classifications/actions remain decision-bearing |
| P5.2 | implementation/high | manual | live project-owned override registration is external-state work against a frozen action set; full review required |
| P5.3 | implementation/high | manual | cross-project provider repair applies frozen adapters with per-project rollback; full review required |
| P5.4 | implementation/high | manual | destructive-boundary quarantine and final fleet convergence require high-effort verification and full review |
| P6.1 | implementation/high | manual | protected external Brain security/profile transaction with Owner gate and rollback; full review required |
| P6.2 | frontier/high | manual | freezes ecosystem-wide provider-health contract and composes multi-package public diagnostics; full review required |
| P6.3 | implementation/high | manual | final exact-set external fleet evidence and non-masking release gate; high effort and full review required |
| P7.1 | implementation/high | manual | exact-set provider acceptance composes frozen multi-package/fleet evidence; full review required |
| P7.2 | implementation/high | manual | cross-package release regressions at frozen provider/locale seams; full review required |
| P7.3 | implementation/high | manual | generated docs, full validation and release-candidate assembly; no tag/push/publish |
| P7.4 | frontier/xhigh | manual | cold adversarial parity/release audit with an Owner-facing verdict |

## 4. Phase Index & Status Board

| Phase | Title | Items 🟢/всего | Status |
|:--|:--|:--|:--|
| P0 | Evidence, safety, and full fleet inventory | 0/4 | ⬜ Not started |
| P1 | Freeze provider-neutral control-plane contract | 0/3 | ⬜ Not started |
| P2 | Freeze locale and compact-English authoring contract | 0/3 | ⬜ Not started |
| P3 | Implement control-plane resolver and adapter boundaries | 0/3 | ⬜ Not started |
| P4 | Implement locale rendering and English canonical migration tooling | 0/6 | ⬜ Not started |
| P5 | Classify and migrate all consumer projects safely | 0/4 | ⬜ Not started |
| P6 | Configure Brain and fleet health/parity gates | 0/3 | ⬜ Not started |
| P7 | Validate provider strengths, release, and operationalize | 0/4 | ⬜ Not started |

## 5. Decision Log

| D# | Date | Decision | Why |
|:--|:--|:--|:--|
| D1 | 2026-08-02 | Use a versioned provider-neutral desired-state contract plus adapter-owned observed status; no adapter writes canonical intent. RAG:✅ 2026-08-02 control-plane query. | Separates user selection from provider quirks; see `research/01-target-architecture.md`. |
| D2 | 2026-08-02 | Locale precedence is command/session → environment → project → user → built-in `en`; `response`, `plan`, and `diagnostics` resolve independently. RAG:— (internal product rule grounded in `brief/00-brief.md` and synthesized in `research/02-p2-locale-authoring-design.md`). | Makes a one-off Russian plan possible without changing default response language; no external standard is claimed to prescribe this precedence. |
| D3 | 2026-08-02 | Canonical authoring becomes compact English; Russian is a rendering overlay, not a parallel source tree. RAG:— (internal product rule grounded in `brief/00-brief.md`, current source-direction evidence in `findings/06-p2-locale-authoring-verification-2026-08-02.md`, and `research/02-p2-locale-authoring-design.md`). | Eliminates two-source language drift while preserving Russian output. |
| D4 | 2026-08-02 | Legacy collisions are classified before mutation: equivalent, local override, stale managed copy, broken link, or ambiguous. RAG:— (repo-grounded: `findings/03-current-defects-2026-08-02.md` and `research/01-target-architecture.md`). | Fail-closed migration protects project-owned work; the five classes are SKM policy, not an externally mandated taxonomy. |
| D5 | 2026-08-02 | Provider parity is a behavior contract: equal shared semantics and explicit supported/degraded/exclusive capability status, not byte-identical files. RAG:— (repo-grounded: root provider-parity instruction). | Providers use native strengths without silently reducing shared capability. |
| D6 | 2026-08-02 | The known Brain credential is a security finding; revocation requires an owner gate. RAG:— (repo-grounded: findings/03-current-defects-2026-08-02.md). | Revocation can interrupt active integrations. |
| D7 | 2026-08-02 | The frozen contracts of archived plan `2026.07.19-DUAL-PROVIDER` remain the predecessor canon; this plan may consume or add a versioned successor but never rewrite the archive. RAG:— (repo-grounded: archived contracts and literal GREEN release audit). | Replacing proven provider semantics would create a second source of truth; additive recovery and locale contracts preserve compatibility. |
| D8 | 2026-08-02 | P0 evidence is an exhaustive, machine-checkable per-project/per-provider file manifest derived from all current `~/.swissknifeman/projects.json` records, with secret-bearing values and absolute roots excluded. RAG:— (repo-grounded: 57 existing registry records observed on 2026-08-02; brief requires per-file evidence). | Prose counts are not enough to support fleet health; committing credentials or machine-specific roots is forbidden. |
| D9 | 2026-08-02 | Every provider-relevant inventory row receives exactly one classification: `canonical-equivalent`, `local-override`, `stale-managed-copy`, `broken-link`, or `ambiguous`; only ownership-proven actions can become automatic. RAG:— (repo-grounded: D4 and predecessor migration gates G01–G11). | Alternatives were bulk cleanup, basename matching, or preserve-all; the chosen exhaustive classification permits safe repair without losing user work. |
| D10 | 2026-08-02 | Recovery-gate approval and live security containment are separate items P0.3/P0.4; P0.4 is a no-op when fresh evidence finds no active exposure, and otherwise requires an exact owner D# before any external write/revocation. RAG:— (repo-grounded: root security/worktree rules and predecessor gate pattern). | A design item cannot self-authorize an irreversible provider action; separation keeps approval, rollback and evidence auditable. |
| D11 | 2026-08-02 | P0 pre-mortem: likely failure modes are partial fleet coverage, dirty-tree state reported as shipped, secret leakage into evidence, ownership inferred from names, provider success masking the other provider, and mutation outside the approved target. RAG:— (repo-grounded: brief, current dirty tree, predecessor P0/P7 findings). | Mitigations are assigned respectively to P0.1 coverage/hash gates, HEAD/worktree separation, redaction self-tests, P0.2 evidence classes, per-provider rows, and P0.3/P0.4 protected-delta/rollback gates. |
| D12 | 2026-08-02 | Coupling surface across phases is explicit: `.swissknife.json` provider selection, provider artifact locks/status, canonical skill/command sources, instruction projections, locale resources, and fleet evidence matrices are touched or consumed by at least two of P1–P7. RAG:— (repo-grounded: phase contracts P1–P7 and `research/01-target-architecture.md`). | Later detailing must reconcile these shared carriers against earlier frozen outputs instead of creating parallel schemas. |
| D13 | 2026-08-02 | A mid-session change of global Codex defaults is evidence, not permission to rewrite user configuration: P0.1 must capture configured defaults separately from the active runtime envelope and flag any mismatch. RAG:— (repo-grounded: `findings/04-authoring-environment-drift-2026-08-02.md`). | Default model/sandbox changed after authoring started; conflating them with the running session would corrupt route provenance and trust claims. |
| D14 | 2026-08-02 | P1 authoring consumes the archived contracts and current repo facts, but P1 execution remains closed until P0.1–P0.4 are terminal and `provider-recovery-gates-v1.md` is frozen; no planned P0 deliverable is claimed as produced. RAG:— (repo-grounded: `phases/P0.md` Status and `phases/P1.md` contract reconcile). | Alternatives were to execute P1 against nonexistent P0 outputs or to hide the dependency; the explicit gate preserves phase-first truth. |
| D15 | 2026-08-02 | `provider-control-plane-v1` composes existing SSOTs additively: provider config owns desired selection, capability manifest owns support, artifact locks own managed provenance, and adapters own only their provider projection/observation/status. It must not introduce a monolithic rival schema or read provider output as canonical intent. RAG:— (repo-grounded: archived provider contracts, `core/provider/{config,manifest,registry,artifact,lock}.py`, `findings/05-p1-contract-verification-2026-08-02.md`). | This is the only option that preserves predecessor identities and independent adapters; replacement/output-derived alternatives create a second source of truth. |
| D16 | 2026-08-02 | P1 does not declare orchestration: P1.2 consumes P1.1 deliverables and P1.3 consumes P1.1/P1.2 plus terminal P0, so the three items are not independent; no long autonomous external-state chain exists. RAG:— (repo-grounded: `phases/P1.md` Inputs/Deliverables and plan-protocol §7 criterion). | The N≥3 count alone is insufficient; a workflow would add a carrier without legal fan-out. |
| D17 | 2026-08-02 | Locale v1 separates three stages: RFC 5646 well-formed syntax (including `x-*` private-use), RFC/IANA canonicalization, and SKM catalog resolution. `ru-RU` remains canonical `ru-RU` but the v1 `en`/`ru` catalog resolves it to `ru`; other valid unsupported registered tags fall back to `en`. Any tag containing a private-use sequence is syntax-valid and canonicalized without interpreting or reordering its opaque private portion, but v1 has no private agreement/catalog mapping and therefore refuses catalog resolution with `unsupported-private-use`, never `malformed`. RFC facts: RAG:✅ 2026-08-03 RFC 5646 §2.1/§2.2.7/§4.5/§4.6 verification in `findings/06-p2-locale-authoring-verification-2026-08-02.md`; precedence, catalog and refusal policy: RAG:— (internal product rule in `research/02-p2-locale-authoring-design.md`). | Preserves BCP 47 syntax truth while making the bounded v1 catalog deterministic; requested/canonical/resolved/fallback provenance remains separate and contains no environment values. |
| D18 | 2026-08-02 | v1 keeps compact English as the sole semantic source for canonical skills, commands, plugins, code comments and development documentation; localized human prose is a key-addressed sparse overlay with English fallback. Stable IDs, schema keys, literals, paths, commands and diagnostic codes are never translated. RAG:✅ 2026-08-02 locale fallback verification in `findings/06-p2-locale-authoring-verification-2026-08-02.md`; RAG:— (repo-grounded: `packages/skiller/scripts/check-translations.sh` and generated-artifact instruction). | A complete second source would recreate semantic drift; immutable machine tokens keep parsers and provider adapters interoperable. |
| D19 | 2026-08-02 | P2 remains sequential and manual: P2.2 consumes the P2.1 locale contract, P2.3 consumes both earlier outputs, and all freeze/translation-review gates require an Owner decision after P1/P0 gates are terminal. RAG:— (repo-grounded: `phases/P2.md` Inputs/Deliverables and plan-protocol §7 criterion). | There are three items but no independent fan-out; a workflow would be an extra unowned carrier. |
| D20 | 2026-08-02 | P3 composes the existing `core/provider` configuration, manifest, registry and artifact-lock primitives into a control-plane resolver and adapter boundary; it does not duplicate their identities, precedence, capability levels, lock semantics or provider projections. RAG:— (repo-grounded: `core/provider/{config,manifest,registry,artifact,lock}.py`, `research/03-p3-control-plane-implementation-design.md`). | A new monolithic store or package-local resolver would become a rival source of truth and break the predecessor's independent-adapter contract. |
| D21 | 2026-08-02 | P3.1, P3.2 and P3.3 are sequential `implementation/high` manual items. They may begin only after P0–P2 are terminal and the P1/P2 contract paths listed in their Inputs exist at their frozen versions; absent draft files are a stop condition, not an invitation to infer the schema. RAG:— (repo-grounded: `phases/P0.md`, `phases/P1.md`, `phases/P2.md`, P3 recon finding). | P3 consumes decisions and recovery evidence that are intentionally not yet produced. Manual high-effort execution preserves the contract gate and prevents an under-routed broad provider change. |
| D22 | 2026-08-02 | Locale runtime lives in a shared stdlib-only `core/locale` domain and consumes already-read P3 descriptors; packages own their catalogs/targets and both providers receive the same immutable per-surface context. RAG:— (repo-grounded: shared-core/provider-parity rules, P2/P3 phase boundaries and `research/04-p4-locale-migration-implementation-design.md`). | Alternatives were provider-local locale state or duplicated package resolvers; both would make fallback/provenance diverge and let an adapter become canonical intent. |
| D23 | 2026-08-02 | English-source migration is controlled by one cumulative P2-derived admission ledger with owner, preimage, immutable tokens, independent EN/RU review, status and rollback; grep/bulk rewrite/hash reversal alone never admits a unit. RAG:— (repo-grounded: current RU→EN validator, D18, evidence-integrity and generated-artifact rules). | Alternatives were one bulk translation or per-package informal checklists; neither proves corpus completeness, generated ownership or recoverability. |
| D24 | 2026-08-02 | Supersedes the pre-D-log three-item blanket draft (there is no accepted predecessor D#): P4 is six sequential `implementation/high`, `manual`, `Review=full` items: runtime → admission tooling → skills → commands/plugins/diagnostics → code prose → docs/terminal regeneration. No parallel Workflow script is declared because every item consumes the previous ledger revision; execution instead follows D39–D40 per-cwd and bounded-checkpoint carriers. **Consequences:** the plan pays for more item sessions, multiple committed ledger checkpoints, independent reviewer passes and terminal regeneration, in exchange for resumable migration and auditable rollback. RAG:— (repo-grounded: P4 Inputs/Deliverables, `findings/08-p4-locale-migration-recon-2026-08-02.md`, and plan-protocol §7). | The superseded draft under-routed public canon/migration work and left a bulk rewrite too large to close honestly. |
| D25 | 2026-08-02 | P4 pre-mortem: likely failures are cosmetic source-direction reversal, translated literals/placeholders, one-provider-only Russian render, half-migrated generated output, incomplete corpus inventory/self-review, and foreign dirty-tree capture. RAG:— (repo-grounded: P4 recon/research, current dirty tree and predecessor generated/ownership gates). | Mitigations are assigned respectively to P4.2/P4.3 writer gates, P4.1/P4.2 token fixtures, P4.1/P4.4 provider-pair tests, P4.6 terminal regeneration, ledger+independent review, and explicit preimage/Files staging. |
| D26 | 2026-08-02 | P5 may reread `~/.swissknifeman/projects.json` only as an ephemeral live-root locator; every stable project ID, repository identity and preimage must rebind to sealed P0 evidence before observation or write, and no selection/classification/ownership/action may come from host state. RAG:— (repo-grounded: P0.1 privacy boundary, `packages/skiller/lib/skiller/state.py`, P5 recon/research). | Absolute consumer roots remain out of committed evidence without making P5 unexecutable; locator drift fails before mutation. |
| D27 | 2026-08-02 | P5 expands to four sequential full-review manual items: freeze exact no-write manifest/Owner D# → preserve/register overrides → non-destructive managed repair → owner-gated quarantine plus two-run convergence. A plan-local runner sequences only terminal P3/P4 public APIs and may not encode provider semantics. RAG:— (repo-grounded: P3.2/P3.3 boundaries and `research/05-p5-consumer-migration-design.md`). | Direct `skiller update --all`, generic `maind sync --all` or ad-hoc per-project commands lack the sealed exact-set action/rollback carrier; the four-way split keeps authority and rollback auditable. |
| D28 | 2026-08-02 | Classification never implies mutation: `ambiguous` → unresolved no-op; `local-override` → preserve or exact owner-approved registration; `canonical-equivalent`/`broken-link` → approved relink with identity/ownership proof; `stale-managed-copy` → approved refresh or quarantine only with SKM provenance, preimage and rollback. RAG:— (repo-grounded: P0.2 five-class contract and predecessor artifact/migration gates). | Age, basename, content equality or managed-looking paths alone cannot authorize adoption, overwrite or cleanup. |
| D29 | 2026-08-02 | P5 pre-mortem: likely failures are registry rebinding to another repo, override/managed misclassification, one-provider-only success, hidden partial fleet progress, irreversible cleanup, source change mid-rollout and evidence leakage. RAG:— (repo-grounded: P5 recon/research, worktree/evidence/provider-parity rules). | Mitigations are assigned respectively to locator rebinding, class/action exact-set gates, independent readback+rollback, the D47 durable append-only per-project transaction journal, quarantine, pinned contracts/action sets and redaction self-tests. |
| D30 | 2026-08-02 | P6 freezes `provider-health-v1` as a composition contract over package-owned evidence: Skiller owns selection/dependencies/budget, Harness owns profiles/trust/settings, P3/P4 own provider and locale readback, and mAInd owns exact-set fleet orchestration. RAG:— (repo-grounded: `findings/10-p6-health-control-recon-2026-08-02.md`, `research/06-p6-health-parity-design.md`). | Existing commands cover different axes; a monolithic parser would duplicate their semantics, while composition preserves ownership and stable diagnostics. |
| D31 | 2026-08-02 | Brain repair is one protected rollback domain: P6.1 must plan without writes and obtain an exact Owner D# before any credential, profile, trust, dependency or budget action. P0.4 remains the exclusive credential-containment authority; implicit full access and author-selected dependency repair are forbidden. RAG:— (repo-grounded: D6/D10, Harness profile catalog and P6 research). | The current finding is unsealed and cannot choose between security/profile alternatives or authorize an external write. |
| D32 | 2026-08-02 | Fleet health requires exact equality with the sealed P0 project set plus complete required provider/capability/shared-plane rows; missing, unreadable, required-unsupported, P5-unresolved or stale evidence is non-green. A complete non-green P6.3 report can close the evidence item but remains a P7 release blocker. RAG:— (repo-grounded: D5/D8/D26-D29 and P6 research). | Item completion and capability readiness are different facts; relabeling a complete report GREEN would hide real fleet debt. |
| D33 | 2026-08-02 | P6 does not declare orchestration: P6.2 consumes P6.1, P6.3 consumes P6.2, and the fleet loop is a deterministic package command/evidence exporter rather than independent agent work. RAG:— (repo-grounded: `phases/P6.md` Inputs/Deliverables and plan-protocol orchestration criterion). | A workflow would add an extra carrier without legal parallel items or improve the exact-set transaction boundary. |
| D34 | 2026-08-02 | P6 pre-mortem: likely failures are provider masking, fleet-set drift, Brain overwrite/credential leakage, excluded required skills, package-conformance-as-project-health, evidence leakage and stale single-run GREEN. RAG:— (repo-grounded: P6 finding/research and root evidence/provider-parity rules). | Mitigations are exact provider rows, sealed-set rebinding, Owner/preimage/rollback gates, machine dependency diagnostics, separated evidence classes, minimized bundles and two pinned fresh scans. |
| D35 | 2026-08-02 | P7 release acceptance is an exact join of frozen desired capability/provider expectations, P6.3 exact-set observations and independent locale/provider rows; provider parity is semantic and non-masking, while native/unsupported strengths keep provider-qualified expectations. RAG:— (repo-grounded: D5/D30/D32, `findings/11-p7-release-acceptance-recon-2026-08-02.md`, `research/07-p7-release-operational-design.md`). | One-provider success, package conformance, row counts or byte equality cannot authorize release; the joined blocker set is the release boundary. |
| D36 | 2026-08-02 | P7 is four sequential manual/full-review items: exact acceptance → permanent regressions → operations/release candidate → cold frontier/xhigh audit. It declares no workflow and performs no tag, push, publish, fleet/Brain repair or destructive cleanup. RAG:— (repo-grounded: P7 Inputs/Deliverables and plan-protocol orchestration criterion). | Every item consumes the prior committed evidence, so parallel fan-out would either race a moving acceptance set or let the audit inherit implementer assumptions. |
| D37 | 2026-08-02 | P7 pre-mortem: likely failures are one-provider masking, byte-parity pressure, locale surface bleed, repo-local Codex discovery masking, generated-doc drift, dirty/stale release evidence and an auditor clearing its own findings. RAG:— (repo-grounded: P7 recon/research and archived dual-provider P7 incidents). | Mitigations are assigned to P7.1 exact sets, P7.2 isolated/negative regressions, P7.3 owned generation and committed manifest, and read-only cold P7.4 plus Owner D#. |
| D38 | 2026-08-02 | Design pass 3/3 accepts the P0→P7 producer/consumer graph as gap-free after adding the missing P2 phase contract/DoR carrier, registering all six exported contracts, restoring brief traceability and pinning unique future research paths. P0–P7 remain strictly sequential; no phase meets the orchestration criterion. RAG:— (repo-grounded: `research/00-user-intent.md`, `research/08-finish-reconcile.md`, phases/P0.md–P7.md and final roadmap). | The executor now has one recoverable chain from owner intent through frozen contracts to fleet evidence and release audit; unresolved owner choices remain explicit item gates rather than author assumptions. |
| D39 | 2026-08-03 | Every multi-package item uses the package-cwd protocol in `roadmap.md`: one root coordinator owns integration, the shared manifest and item closure; every package mutation runs from a fresh `codex -C packages/<name>` session under that package's rules and emits a package-scoped evidence record before integration. RAG:— (repo-grounded: root `AGENTS.md` package-scope-routing and affected item `Files`). | Keeps the existing 30 item identities while making package rules, ownership, commits and validation evidence explicit across cold sessions. |
| D40 | 2026-08-03 | P4.3–P4.6 execute in deterministic, package-scoped ledger batches with hard row/file limits, one committed checkpoint per batch, resume from the first non-accepted row, a distinct read-only reviewer identity, and at most two review/fix rounds before plan-design escalation; P4.6 terminal regeneration starts only after every source batch is accepted. RAG:— (repo-grounded: `findings/08-p4-locale-migration-recon-2026-08-02.md`, P2.3 review contract, and plan-protocol commit/derived-artifact rules). | Bounds context and rollback radius for the measured 173-skill/279-code-file/135-doc-file discovery corpus without changing item statuses or letting author/renderer self-certify. |
| D41 | 2026-08-03 | Locale canonicalization is pinned to one faithfully vendored carrier, `core/locale/data/language-subtag-registry.txt`, with adjacent `upstream.json`: official IANA URL, `File-Date: 2026-06-14`, SHA-256 `be1fad86a99e3a932d07b80c9b3c271ec2381a5909ce22420144e5077ab0a43a`. P2.1 freezes bytes/provenance, P4.1 implements the stdlib reader and sole explicit update producer, and P7.3 verifies the same identity in docs/release evidence. RAG:✅ 2026-08-03 official IANA registry and RFC 5646 verification in `findings/12-design-audit-remediation-2026-08-03.md`. | A host-time registry lookup or duplicated hardcoded subset would let contract checker, runtime and release use different registration/`Preferred-Value` truth; one pinned data carrier preserves reproducibility and shared-core ownership. |
| D42 | 2026-08-03 | The observed `harness hooks --target . --provider codex --observer --trusted --dry-run` failure is a public CLI target-normalization defect: P0.1 records it as non-green baseline evidence, P3.2 owns the forward implementation/regression fix at the Harness boundary, and P7.2 permanently smokes relative and absolute targets with equal planned operations and zero writes. The shared lock invariant remains explicit absolute roots. RAG:— (repo-grounded: exact reproduction in `findings/12-design-audit-remediation-2026-08-03.md`, `packages/harness/lib/harness/hooks.py`, `core/provider/lock.py`). | Green direct unit imports did not exercise the source→target public control path; assigning one implementation owner and one release regression prevents the false-green from recurring without weakening core safety. |
| D43 | 2026-08-03 | Supersedes only D38's pre-audit «gap-free readiness» verdict, while preserving its P0→P7 order, accepted F1–F7 remediation and 30-item topology: readiness now additionally requires the root-relative P0 validations, D41 registry carrier, D42 public hook path and P7.3 provenance gate. The append-only audit denominator is **8 phases (P0–P7)**, correcting the first audit's historical «seven phases» sentence without rewriting that report. **Consequences:** plan v1.0.2 adds one vendored data/provenance carrier and tighter evidence/validation obligations, then pays for another independent design-audit round; statuses remain 0/30 and execution stays closed. RAG:— (repo-grounded: `## Audit design — 2026-08-03 (заход 2)` F8–F12 and remediated phase specs). | The second audit proved that structural lint green did not establish copy/paste executability, registry reproducibility or public hook-path coverage; append-only correction keeps the prior report as provenance while removing its conclusions from readiness. |
| D44 | 2026-08-03 | D39's per-cwd rule explicitly includes P4.2 and P4.3: the root coordinator alone owns `configs/locale-corpus-v1.json`, plan evidence, integration and closure, while a fresh `codex -C packages/skiller` session owns only the exact Skiller paths and package validation commands enumerated in P4/roadmap. RAG:— (repo-grounded: root/package `AGENTS.md`, P4.2/P4.3 Files/Validation and `roadmap.md` exact slice rows). | Removes the remaining root-session write path into `packages/skiller/**` without adding item IDs or splitting shared-ledger authority. |
| D45 | 2026-08-03 | Every P4.3–P4.6 checkpoint uses the dedicated frontier/high zero-mutation reviewer carrier in `roadmap.md`: committed checkpoint + manifest-limited diff + frozen contracts are exact inputs; reviewer stdout is one `APPROVE|FIX_REQUIRED` JSON record owned by the root coordinator; round-1 fixes require a separate commit and fresh round-2 identity, while a second `FIX_REQUIRED` escalates to plan-design and forbids resume. RAG:— (repo-grounded: P2.3, D40 and `roadmap.md` reviewer carrier). | Makes independent review executable and attributable while preserving the author/renderer boundary, the two-round cap and root-owned ledger/closure. |
| D46 | 2026-08-03 | P0.4 evidenced no-op is a deterministic Validation result, never an owner gate: it requires the frozen checker to pass over committed P0.1 classification plus fresh independent detector/provider-trust evidence with `action_set=[]`, zero plaintext-secret findings and zero protected-target delta. Only a non-empty mutation branch requires the exact containment D#. RAG:— (repo-grounded: P0.3/P0.4 Validation and `roadmap.md` deterministic note). | Avoids asking the owner to authorize no mutation or letting an executor treat no-op as a waivable approval branch; security writes remain fail-closed. |
| D47 | 2026-08-03 | P5.1–P5.4 share one durable append-only `artifacts/P5/fleet-transaction-log.jsonl`: canonical hash-chained events are flushed and `fsync`'d before/after each project transaction boundary, carry stable project/action/transaction IDs, frozen manifest/action-set/source identities, pre/post hashes and the closed `before → applied → readback-passed|readback-failed → accepted|rollback-started → rolled-back` state machine. Aggregate result JSON is derived only from terminal journal states. On restart the runner validates the entire chain, rebinds frozen identities, observes the first non-terminal transaction and deterministically accepts an exact postimage after fresh readback, rolls back an exact partial/failed postimage, recognizes an exact preimage as rolled back, or refuses on any third state/drift; it never skips to the next project. RAG:— (repo-grounded: audit F17, D27–D29, `research/05-p5-consumer-migration-design.md` and P5 rollback boundaries). | Makes a crash after live apply but before aggregate write recoverable and attributable; the cost is a shared write-ahead carrier, explicit resume/reconcile commands and negative crash-boundary fixtures across all four P5 items. |
| D48 | 2026-08-03 | Every F18-listed Validation uses exact worktree-local root or package-cwd invocations. `roadmap.md` carries the closed P4.4/P4.6 cwd→command matrix; P5.1–P5.4, P6.1/P6.3 and P7.1/P7.4 name helper path, subcommand, frozen manifest/action/evidence/contract inputs, output carrier and exact plan-lint invocation. Prose aliases such as “targeted tests”, “owning check”, “verify-results”, “Helper --write/--check” or “rerun green” are not acceptance commands. RAG:— (repo-grounded: audit F18 and affected phase `Files`/Validation). | Cold-start executors and the final auditor can reproduce the same gate byte-for-byte; broader full-suite commands are accepted where a package has no narrower stable public runner. |
| D49 | 2026-08-03 | P7.4's decision denominator is computed at audit time from every `D#` row in `plan.md` Decision Log, not from a static upper bound. The current exact set is D1–D49, including this remediation. `artifacts/P7-decision-crosswalk.json` must contain exactly one row per parsed D# and no other row; each row carries disposition, evidence paths, recomputed commands/results and tree anchor. The P7.1 committed helper's `verify-decision-crosswalk` subcommand fails on missing, extra, duplicate or post-crosswalk D# before P7.4 can emit GREEN. RAG:— (repo-grounded: audit F16, P7.1/P7.4 and append-only Decision Log). | Future decisions enter the release audit automatically and stale exact-set reports fail closed; the audit pays for a full decision-to-evidence crosswalk rather than a range checklist. |
| D50 | 2026-08-03 | P4.3–P4.6 source checkpoints use one machine state, `deferred-derived-only`, only when the checkpoint verifier recomputes an exact ordered set of stable `DERIVED_TARGET_STALE` rows (`cwd`, command ID, target path and owning generator), proves zero non-freshness failures and binds the set to the cumulative ledger/resume cursor. P4.6 terminal regeneration consumes that exact union; its frozen helper plan records its canonical payload hash and the Harness writable targets in alphabetic `target_path` order, and Harness `apply` receives them byte-for-byte through `--authorize`. After regeneration every package/docs command must return 0, the deferred set must be empty and a second owner run must be byte-stable. RAG:— (repo-grounded: audit F19/F20, `packages/harness/lib/harness/instructions.py:512-535`, `roadmap.md` checkpoint carrier and plan-protocol derived-artifact coherence). | Gives expected generated drift one reproducible checkpoint/resume representation without greenwashing unrelated validation failures; exact positional authorization preserves the Harness write boundary and the terminal all-green gate. |
| D51 | 2026-08-03 | Three authority classes are distinct: P0.3 `contract_freeze_decision` approves only recovery-contract semantics; conditional P0.4 `containment_mutation_decision` alone authorizes exact security/trust targets; P4.6 ordinary repository generation needs neither and is gated by the terminal ledger, frozen helper-plan hash and exact Harness `--authorize` set. P0.3 produces a versioned plan-local stdlib checker plus schema/tests/evidence; P0.4 verifies the checker byte hash and runs its exact `no-op` or `mutation` branch command, with a containment D# accepted only by the mutation branch. RAG:— (repo-grounded: audit F21/F22, D10/D46, P0.3/P0.4 and the Harness apply contract). | Prevents a contract approval from becoming ambient write authority, keeps the no-op branch deterministic and makes the P0.3 producer consumed by P0.4 executable from a cold session. |
| D52 | 2026-08-03 | P6.1 uses its own durable append-only `artifacts/P6/brain-transaction-log.jsonl`: stable Brain/action/boundary IDs, frozen plan/approval/source identities, exact pre/post identities and a canonical hash chain are appended, flushed, `fsync`'d, reopened and verified before and after every public Skiller/Harness/mAInd/P3 write or readback boundary. `resume` first runs deterministic `reconcile`: exact approved postimage gets fresh readback then acceptance, exact preimage is recorded rolled back, a recognized partial/failed postimage triggers whole-Brain rollback, and any third state, torn chain, missing backup or source drift refuses. Result JSON is derived only from a terminal journal; crash injection covers every append and public CLI boundary. RAG:— (repo-grounded: audit F23, D47's measured failure class and P6.1 whole-project rollback promise). | Extends durable intent across the live Brain crash window; the cost is a second transaction-specific WAL and explicit resume/reconcile/rollback evidence rather than relying on a post-operation result file. |
| D53 | 2026-08-03 | P5.1 `plan` is no-write only with respect to consumer/provider targets and may atomically create exactly the named manifest and initial journal; `check` changes no byte anywhere. Validation records separate byte-delta assertions for the two subcommands and rejects any other initialization output. RAG:— (repo-grounded: audit F24 and P5.1 Files/Validation). | Removes the literal contradiction while retaining a fail-closed target boundary and deterministic initialization carrier. |
| D54 | 2026-08-03 | Targeted fifth-audit remediation closes F19–F25 without changing brief intent, the accepted F1–F18 semantics, the 30-item topology or any item status. D49's dynamic verifier now resolves the append-only Decision Log exact set as D1–D54; execution remains closed until a repeated independent design audit is GREEN. RAG:— (repo-grounded: `## Audit design — 2026-08-03 (заход 5)`, D50–D53 and remediated P0/P4/P5/P6/roadmap carriers). | Keeps audit history append-only and makes the new checker/authority/deferred-state/WAL decisions visible to the release crosswalk before execution opens. |

## 6. Update Log

| Date | Who (role/model) | What |
|:--|:--|:--|
| 2026-08-02 | plan-design/frontier-high | Design pass 1/3: brief, RAG, synthesis, phase skeletons and current defects captured. |
| 2026-08-02 | plan-design/gpt-5.6-sol-high | P0 detailed to DoR: four sequential evidence/safety items, predecessor-contract reuse, routing and owner-gated containment fixed; P1 remains the next design phase. |
| 2026-08-02 | plan-design/gpt-5.6-sol-high | P1 detailed to DoR: three sequential contract items, honest unclosed-P0 gate, legal per-item routing and predecessor composition fixed; P2 is next. |
| 2026-08-02 | plan-design/gpt-5.6-sol-high | Design pass 2/3: P2 detailed to DoR; BCP 47/fallback evidence, English-source overlay boundary and translation-review gates are explicit; P3 is next. |
| 2026-08-02 | plan-design/frontier-high (runtime mapping unverified; see findings/07) | P3 detailed to DoR: resolver, adapter boundary and status diagnostics compose existing primitives; P0–P2 terminal/frozen artifacts remain hard execution inputs; P4 is next. |
| 2026-08-02 | plan-design/gpt-5.6-sol-high (effort self-attested; see findings/08) | P4 detailed to DoR as six sequential full-review items: shared locale runtime, admission ledger, four carrier migrations and terminal regeneration; P5 is next. |
| 2026-08-02 | plan-design/gpt-5.6-sol-high (effort self-attested; see findings/09) | P5 detailed to DoR as four sequential full-review items: exact action freeze, override preservation, managed repair and recoverable cleanup/convergence; P6 is next. |
| 2026-08-02 | plan-design/gpt-5.6-sol-high (effort self-attested; see findings/10) | P6 detailed to DoR as three sequential manual/full-review items: owner-gated Brain repair, frozen composed health contract and exact-set two-run fleet evidence; P7 is next. |
| 2026-08-02 | plan-design/gpt-5.6-sol-high (effort self-attested; see findings/11) | P7 detailed to DoR as four sequential full-review items: exact acceptance, permanent regressions, operations/release candidate and cold audit; `finish` is next. |
| 2026-08-02 | plan-design/frontier-high (Codex config gpt-5.6-sol; active effort self-attested) | Design pass 3/3: P0–P7 producer/consumer contracts, brief trace, Routing and 30-item roadmap reconciled; 5 DoR/provenance/path gaps closed; independent design audit is next. |
| 2026-08-03 | plan-design/gpt-5.6-sol-high | Design-audit remediation F1–F7: locale layers/private-use, RAG provenance, concrete P4.5 runners, per-cwd carriers, bounded P4 checkpoints/review, deterministic release gates and D24 trace reconciled; statuses and Design Passes remain unchanged. |
| 2026-08-03 | plan-design/gpt-5.6-sol-high (effort not exported by runtime) | Design-audit remediation F8–F12: root-relative P0 validation, pinned IANA carrier/provenance/update path, public hook CLI owner/regressions, `docs/reference.md` ownership and append-only 8-phase correction reconciled; statuses remain 0/30. |
| 2026-08-03 | plan-design/gpt-5.6-sol-high (effort not exported by runtime) | Design-audit remediation F13–F15: P4.2/P4.3 exact per-cwd slices, executable P4.3–P4.6 reviewer carrier and deterministic P0.4 no-op note reconciled; statuses and Design Passes remain unchanged. |
| 2026-08-03 | plan-design/gpt-5.6-sol-high (effort not exported by runtime) | Design-audit remediation F16–F18: dynamic exact D# crosswalk, durable P5 write-ahead/resume carrier and exact root/per-cwd validation invocations reconciled; statuses and Design Passes remain unchanged. |
| 2026-08-03 | plan-design/gpt-5.6-sol-high (effort not exported by runtime) | Design-audit remediation F19–F25: exact Harness authorization/deferred-derived state, executable P0 checker and typed authority, P6 WAL/resume, P5 no-write wording and finding scope history reconciled; statuses remain 0/30. |
| 2026-08-03 | plan-design/gpt-5.6-terra (effort not exported by runtime) | ACTIVE transferred to `2026.08.03-ARTIFEX-SUPERVISOR`; this plan is paused with F1–F25, D1–D54 and all 30 item statuses unchanged. |

## 7. Contracts

### Exported

| Контракт | Версия | Статус | Потребители | Уведомлены |
|:--|:--|:--|:--|:--|
| root/contracts/provider-control-plane-v1.md | v1.0.0-draft | draft | P2–P7 | — |
| root/contracts/locale-resolution-v1.md | v1.0.0-draft | draft | P3–P7 | — |
| root/contracts/english-authoring-overlay-v1.md | v1.0.0-draft | draft | P3–P7 | — |
| root/contracts/locale-authoring-review-v1.md | v1.0.0-draft | draft | P3–P7 | — |
| root/contracts/provider-recovery-gates-v1.md | v1.0.0-draft | draft | P0.4–P7 | — |
| root/contracts/provider-health-v1.md | v1.0.0-draft | draft | P6–P7 | — |

### Consumed

| Контракт | Донор-план | Pinned | Замечено | Реакция |
|:--|:--|:--|:--|
| root/contracts/task-contract-v1.md | 2026.07.24-AGENT-RELIABILITY | v1 | portability defect previously observed | P3 preserves provider-neutral task runtime discovery |
| root/contracts/provider-capability-contract.md | 2026.07.19-DUAL-PROVIDER | v1.0.0 | frozen predecessor available in archive | P0 inventories conformance; P1 extends rather than replaces |
| root/contracts/provider-artifact-contract.md | 2026.07.19-DUAL-PROVIDER | v1.3.0 | frozen predecessor available in archive | P0/P1 preserve ownership, lock and drift semantics |
| root/contracts/provider-config-contract.md | 2026.07.19-DUAL-PROVIDER | v1.0.0 | frozen predecessor available in archive | P1 composes locale/control-plane fields additively |
| root/contracts/provider-migration-gates.md | 2026.07.19-DUAL-PROVIDER | v1.0.0 | frozen predecessor available in archive | P0.3 produces successor recovery gates without weakening G01–G11 |
| root/contracts/provider-skill-publication-contract.md | 2026.07.19-DUAL-PROVIDER | v1.0.0 | frozen predecessor available in archive | P1.2 maps publication ownership without output-to-output conversion |
| root/contracts/provider-command-routing-contract.md | 2026.07.19-DUAL-PROVIDER | v1.0.0 | frozen predecessor available in archive | P1.2 preserves semantic command ownership and provider-qualified projection |
| root/contracts/provider-harness-contract.md | 2026.07.19-DUAL-PROVIDER | v1.0.0 | frozen predecessor available in archive | P1.2 maps harness surfaces and independent security axes |
| root/contracts/provider-instruction-contract.md | 2026.07.19-DUAL-PROVIDER | v1.0.0 | frozen predecessor available in archive | P1.2 preserves common canon plus additive provider extensions |
| root/contracts/provider-analytics-contract.md | 2026.07.19-DUAL-PROVIDER | v1.0.0 | frozen predecessor available in archive | P1.2 maps provider-qualified observed evidence without raw payload leakage |

## Audit design — 2026-08-03

**Вердикт: RED** · заход **1-й** (блоков `## Audit design` до этого — 0) · режим
`design` (pre-exec ревью всего плана) · аудитор `plan-audit` / `frontier/xhigh`.

**Линтер:** `python3 packages/task/scripts/plan-lint.py
plans/2026.08.02-PROVIDER-CONTRACT-LOCALE` — **0 ERROR / 0 WARN** на рабочем дереве
`main` @ `d9d44245`; каталог плана untracked. Baseline-проверка относительно `HEAD` отдельно
дала **0 ERROR / 1 WARN**: `git archive` не видит untracked-каталог, поэтому число новых
ошибок не вычислено и не выдано за нулевое. `plan-lint.py --conflicts` — **0 расхождений /
0 предупреждений**. До append отчёта `verify-citations.py --strict` видел **0 цитат / 26
известных исключений / 0 находок**; после добавления доказательной ссылки отчёта — **3 цитаты /
26 исключений / 0 находок**. Нулевой счёт до отчёта не доказывал покрытие внешних фактов,
поэтому BCP 47 перепроверен отдельно по официальному RFC.

**Почему RED, а не ATTENTION.** Четыре дефекта делают план неисполняемым или его приёмку
неоднозначной до первого item: P2 задаёт взаимоисключающие классы для валидного BCP 47 private-use
tag; P4.5 требует отсутствующий runner; несколько items пересекают package roots без носителя
обязательного `codex -C packages/<name>`; миграция сотен единиц с независимой проверкой упакована
в solo-сессии без bounded batch/review/resume carrier. Это дефекты продукта плана, а не только
бухгалтерии. Исполнение P0.1 не открывать до повторного design-аудита `GREEN`.

### Находки

**F1 · Major · high · issue · `phases/P2.md:47–56` ↔ `plan.md:114` ↔
`phases/P4.md:61` — locale contract смешивает синтаксическую валидность BCP 47,
canonicalization и выбор поддерживаемого каталога.** D17 обещает принимать нормализованные BCP 47
requests, а P2.1 одновременно относит private-use tag к ветке `malformed/private-use → refusal`,
хотя RFC 5646 включает private-use в допустимый синтаксис language tag. `ru-RU → ru` также
описано как normalization, хотя для v1 это продуктовая catalog-resolution/fallback policy, а не
общая RFC canonicalization. Официальный источник: [RFC 5646](https://www.rfc-editor.org/rfc/rfc5646.html).
*failure_scenario:* исполнитель либо отвергает синтаксически валидный `x-*`, нарушая D17, либо
считает его обычным unsupported tag и падает на negative fixture; requested/resolved/fallback
provenance получает разные смыслы в P2, P4 и P7. **Конституция:** plan-protocol §7 «внешний
load-bearing факт — `RAG:✅` и согласованный слой findings→research→ТЗ»; plan-audit design §3–4
«слои знаний и phase contracts согласованы». Исправление: отдельно заморозить (a) syntax
validation, (b) RFC canonical form, (c) v1 support/catalog resolution; явно решить private-use
policy и синхронизировать D17, P2.1, P4.1, fixtures и `research/02`.

**F2 · Minor · high · issue · `plan.md:99–101` ↔
`findings/06-p2-locale-authoring-verification-2026-08-02.md:17–20` — D2/D3 (и тот же
класс у D4) несут неверный тип RAG-провенанса.** Finding прямо говорит, что precedence,
independent surfaces и sparse overlay — внутренние продуктовые решения, не результат стандарта;
при этом D2/D3 помечены `RAG:✅ ... locale query`. D4 аналогично превращает найденный внешний
паттерн в внутреннюю fleet-классификацию без repo-grounded marker/прямой ссылки на свой слой 1.
*failure_scenario:* холодный читатель принимает продуктовую политику за внешне предписанную и не
видит, какие части можно менять решением владельца, а какие ограничены стандартом. **Конституция:**
plan-protocol §7: `RAG:✅` — только внешний проверенный факт; `RAG:—` — repo-grounded факт или
internal rule; ровно один корректный marker на load-bearing verdict. Исправление: разделить
внешние факты и внутренние решения, дать D2–D4 правильные markers и прямые findings/research refs.

**F3 · Major · high · issue · `phases/P4.md:137` — Validation P4.5 вызывает несуществующий
`packages/task/scripts/test.sh`.** `Files` P4.5 включает `packages/task/**`, а фактический Task
runner — только `packages/task/scripts/validate.sh`; `test.sh` существует у Analyst, Harness,
mAInd и Skiller, но не у Task. *failure_scenario:* честный исполнитель расширяет «each affected
package's `scripts/test.sh`» на Task и получает `No such file or directory`; пропуск Task оставляет
изменённый пакет без заявленной приёмки. **Конституция:** plan-protocol §14 «каждый item исполним
назначенной моделью» и plan-audit §2 «невоспроизводимая Validation — RED». Исправление: перечислить
конкретные существующие команды всех затронутых пакетов, не использовать собирательный runner.
**PROMOTE-CANDIDATE:** это повтор уже найденного в архивном design-аудите класса — validation
authoring должен резолвить package runner по файловой системе, а не предполагать единое имя.

**F4 · Major · high · issue · `roadmap.md:5–7,23–31,37–41` ↔ `AGENTS.md:90–91` ↔
`phases/P3.md:73,92` — roadmap не несёт исполнимого package-cwd carrier для multi-package
items.** P3.2/P3.3, P4.1/P4.4–P4.6, P6.2, P7.2/P7.3 меняют root/core и два–пять package roots
в одном `task:plan-run` solo item. Репозиторный канон требует перед работой внутри каждого
`packages/<name>/**` перезапуск с `codex -C packages/<name>`, но roadmap даёт только одну root
сессию, не декларирует workflow и не задаёт merge/evidence owner между cwd-сессиями.
*failure_scenario:* исполнитель либо правит package без его локальных правил, либо разрывает один
item на несвязанные сессии, ни одна из которых не может честно закрыть общий Validation/commit.
**Конституция:** root.codex.package-scope-routing; plan-protocol §14 «item исполним без контекста
вне плана»; plan-audit design §6 «roadmap исполним, launch carriers готовы». Исправление:
разделить multi-package items на package-scoped items + root integration item либо объявить
явный workflow с per-cwd launches, общим evidence carrier и одним владельцем закрытия.

**F5 · Major · high · issue · `phases/P4.md:78,87–99,125–137,144–156` ↔
`findings/08-p4-locale-migration-recon-2026-08-02.md:7–24` ↔ `roadmap.md:28–31` — P4
не имеет bounded batch/review/resume carrier для измеренного корпуса.** Один solo item P4.3
охватывает 173 local skills, P4.5 — discovery surface в 279 Python files, P4.6 — 135 Markdown
files и terminal regeneration. Каждая единица требует preimage, rollback и независимую проверку,
причём reviewer не может быть author/renderer; roadmap всё равно обещает по одной сессии на item,
без максимального batch size, checkpoint/resume semantics и запуска независимого reviewer.
*failure_scenario:* сессия обрывается на частично изменённом ledger/corpus, следующий cold start
не знает последний принятый batch; либо один агент сам подписывает review evidence и Validation
становится формально зелёной при нарушенном contract. **Конституция:** plan-protocol §14 «item
исполняем назначенной моделью»; plan-audit design §6 «roadmap исполним, batch/workflow launch
blocks готовы»; собственное правило P4.2 о reviewer independence. Исправление: разложить P4.3–P4.6
на ledger-bounded package/corpus batches или workflow groups, задать checkpoint/resume и отдельный
review carrier; terminal regeneration оставить последним интеграционным item.

**F6 · Minor · high · issue · `roadmap.md:39,41` — детерминированные acceptance predicates
ошибочно записаны как owner gates.** «release blocker set must be empty» у P7.1 и «candidate
blocker set empty» у P7.3 — вычисляемые stop conditions, а не решения владельца.
*failure_scenario:* владелец получает бессмысленный запрос подтвердить пустой набор либо non-empty
blocker set воспринимается как waivable approval. **Конституция:** plan-audit design §6 «гейты
владельца — только там, где решение реально его». Исправление: перенести их в deterministic gates
и поставить `—` в owner column; оставить owner gate только для реального выбора D#.

**F7 · Minor · med · nitpick · `plan.md:121` (D24) — заменяющее решение не несёт inline
`**Consequences:**` и не называет заменённый D#.** D24 прямо говорит, что «original three-item
blanket implementation/medium route» заменён шестью high/full-review items, но trace к прежнему
accepted decision отсутствует. *failure_scenario:* читатель не может определить, какая запись
перестала действовать и какие цены приняты: больше items, последовательный ledger, ручные review
gates и отсутствие workflow. **Конституция:** plan-audit design §7 / plan-protocol §6:
supersede/cancel/replacement entry несёт inline `**Consequences:**`. Исправление: назвать
predecessor или явно зафиксировать, что это пред-D-log draft, и дописать последствия в D24.

### Покрытие брифа

| Мысль владельца | Носитель | Вердикт |
|:--|:--|:--|
| Hub автоматически конфигурирует Claude Code и Codex по project config | P1 contract · P3 resolver/adapters · P6 health | покрыто |
| Канон остаётся в swissknifeman; consumer не получает runtime/plugin copies | P0 inventory · P1 ownership · P3 adapters · P5 migration | покрыто |
| Убрать legacy projections, broken links, overrides и provider drift без потери локальной работы | P0.1–P0.4 · P5.1–P5.4 · P6.3 | покрыто |
| Provider strengths независимы, shared semantics parity не означает byte identity | D5 · P1.2 · P3.2–P3.3 · P7 | покрыто |
| Compact English — semantic source; Russian — render overlay | P2.2–P2.3 · P4.2–P4.6 | покрыто |
| Response/plan/diagnostics наследуются независимо; Russian plan не меняет response | D2/D17 · P2.1 · P4.1 · P7.2 | покрыто, но F1/F2 требуют уточнения основания |
| Полный fleet и per-file evidence, skipped/unresolved остаётся non-green | P0.1–P0.2 · P5 · P6.3 · P7.1 | покрыто |
| Все перечисленные дефекты и live security/trust действия имеют точный gate/rollback | P0.2–P0.4 · P5.1/P5.4 · P6.1 · P7.4 | покрыто |

Непокрытых мыслей брифа не найдено; RED возникает не из пропуска намерения, а из
противоречивого и неисполняемого carrier design.

### Проверено без находок

- **Фазовый producer/consumer graph:** P0→P7 последователен; все шесть exported и девять
  consumed contracts зарегистрированы, consumer не предшествует producer. За пределами F1
  coupling-разрыва не найдено.
- **Routing:** 25 строк §3 покрывают все 30 item IDs (диапазоны P0.2–P0.3 и P2.1–P2.3
  развёрнуты); множество фазовых item'ов и 30 solo-строк roadmap совпадает, route/model drift
  не найден.
- **DoR и бюджет:** семь фаз детализированы, 30/30 specs несут обязательные поля; живых
  `[NEEDS CLARIFICATION]` нет. Meta `Design Passes: 3/3`, Update Log содержит три provenance
  rows, Authoring Model присутствует.
- **Knowledge layers:** `brief/`, 11 findings и 9 research carriers непусты и связаны через
  Inputs/Required Reads/D-log. Исключение качества markers — F2; внешние locale факты вручную
  перепроверены по RFC 5646, две targeted RAG retrieval-сессии не дали основания считать
  SKM precedence/overlay стандартом.
- **Roadmap accounting:** все items имеют solo rationale; workflow/batch groups не объявлены,
  поэтому отсутствующих групповых launch blocks нет. Дефекты самого выбора solo carrier — F4/F5.
- **Owner authority:** security, quarantine, Brain и release verdict gates адресованы точными
  D#/rollback carriers; помимо F6 ложных owner decisions не найдено.
- **Last Updated/provenance:** дата Meta не старше Update Log; три обязательных carrier'а
  авторской модели присутствуют в Meta, Update Log и journal.

### Серые зоны и границы доверия

- Каталог плана untracked, поэтому baseline delta относительно `HEAD` не вычисляется; абсолютный
  lint зелёный, но это не доказательство отсутствия регрессии к committed версии плана.
- До append audit-блока `verify-citations --strict` распознавал 0 citations; после доказательной
  ссылки отчёта — 3. Нулевые findings использованы только как проверка структуры ссылок, не как
  подтверждение полноты внешних фактов. Официальный RFC проверен отдельно; P1/P2 обязаны rebind
  внешние API/standard details непосредственно перед freeze.
- `codex doctor --json` подтвердил configured model `gpt-5.6-sol`, approval `never` и unrestricted
  filesystem, но не экспортировал активный effort; `xhigh` в actor — маршрут команды, а не
  независимо измеренная runtime telemetry.
- `task@swissknifeman` не развёрнут в активном Codex plugin catalog; аудит выполнялся через
  worktree-local canonical command/CLI. `maind health --cwd`, hook integrity и conflict scan
  зелёные; это ограничение deployment, не подмена результата аудита.

### Что запускать

**Next:** design-phase: task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE finish

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | high |
| Capabilities | repository-plan-edit · external-fact-verification |
| Context | cold-start — plan-step |
| Суть | Точечно закрыть F1–F7, пересобрать затронутые contracts/routes/roadmap и вернуть план на повторный design-аудит; code/fleet execution запрещён |
| Команда | — |

| Model | Thinking | Context | Суть | Команда |
|:--|:--|:--|:--|:--|
| gpt-5.6-sol | high | `NEW SESSION — шаг-не-item` | Codex launch: `-C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c model_reasoning_effort="high" -a never -s danger-full-access`; точечная design-remediation F1–F7 | — |

```text
$ task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE finish

РЕЖИМ: точечная remediation находок design-аудита, НЕ исполнение items и НЕ переразработка незатронутых фаз
ВХОД: plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/plan.md → блок `## Audit design — 2026-08-03`; прочитать ПЕРВЫМ
СКОУП: 1) F1 — развести BCP 47 syntax/canonicalization/catalog resolution, явно решить private-use и синхронизировать D17/P2.1/P4.1/fixtures/research 2) F2 — исправить RAG markers и прямые layer refs D2–D4 3) F3 — заменить собирательный `scripts/test.sh` конкретными существующими runners P4.5 4) F4 — дать multi-package items package-scoped decomposition либо явный per-cwd workflow/evidence carrier 5) F5 — разбить P4.3–P4.6 на bounded ledger batches с checkpoint/resume и независимым reviewer carrier 6) F6 — вынести deterministic blocker predicates из owner gates 7) F7 — добавить trace и inline `**Consequences:**` D24 8) пересобрать Routing/roadmap/Update Log только если это следует из F1–F7, затем plan-lint + conflicts + повторный audit-design handoff
НЕ ТРОГАТЬ: brief intent; statuses items и Status Board 0/30; frozen archived contracts; незатронутые phase contracts/owner D#; код, package/fleet/Brain/provider state; `Design Passes: 3/3` без отдельного решения владельца; D-log append-only кроме явно требуемых marker/Consequences corrections; unrelated dirty worktree и plans/archive/**
```

## Audit design — 2026-08-03 (заход 2)

**Вердикт:** RED  
**Режим:** design  
**Попытка:** 2  
**Аудитор:** frontier/xhigh  
**Tree anchor:** `main` @ `d9d44245`; каталог плана остаётся untracked в dirty worktree.

**Линтер:** абсолютный запуск `python3 packages/task/scripts/plan-lint.py
plans/2026.08.02-PROVIDER-CONTRACT-LOCALE` — **0 ERROR / 0 WARN**;
`plan-lint.py --conflicts` — **0 расхождений / 0 предупреждений**. Baseline относительно
`HEAD` — **0 ERROR / 1 WARN**: `git archive` не видит untracked-каталог, поэтому delta новых
ошибок не вычислена. Структурная зелень не снимает находки ниже.

**Почему RED.** Ремедиация F1–F7 содержательно принята, но первый executable phase всё ещё
содержит команды, которые нельзя выполнить из объявленного root launch; locale contract не
называет ни одного файлового носителя закреплённого registry snapshot; а реальный hook planning
control path уже падает при зелёном unit-suite и не включён в acceptance plan. Это разрывы
исполняемости и доказательства, а не косметическая бухгалтерия. P0.1 не открывать до следующего
design-аудита `GREEN`.

### Находки

**F8 · Major · high · issue · `phases/P0.md:48,52,67,71` — обе стартовые P0 Validation
содержат неисполняемые пути/placeholder.** P0.1 создаёт verifier под полным plan-relative путём,
но запускает `python3 artifacts/P0.1/evidence/verify.py` из repository-root launch. P0.2 оставляет
literal `.../p0-provider-fleet-classify.py` и ищет human output как
`research/09-fleet-migration-classification.md`, хотя Files размещает его внутри каталога плана.
*failure_scenario:* первый агент либо получает `No such file or directory`, либо подменяет
предписанный путь догадкой; зелёный completion нельзя воспроизвести по тексту item. **Контракт:**
plan-protocol §14 и plan-audit design §2 требуют исполнимую точную Validation. Исправление:
заменить все три ссылки полными repository-root-relative путями и оставить команды copy/paste
исполняемыми из объявленного root launch.

**F9 · Major · high · issue · `phases/P2.md:49,52,54,56` ↔ `phases/P4.md:63–67` —
закреплённый IANA registry заявлен как semantic input, но не имеет data/provenance carrier.**
P2 обещает registry-backed canonicalization, registered/unsupported distinction и
`Preferred-Value`, однако Files/Deliverables называют только prose contract, fixtures и checker;
P4 pure stdlib runtime также не получает snapshot или сгенерированный canonical subset.
Текущий официальный registry — изменяемый dataset с `File-Date: 2026-06-14`:
[IANA Language Subtag Registry](https://www.iana.org/assignments/language-subtag-registry/language-subtag-registry).
*failure_scenario:* P2 checker и P4 runtime используют разные host-time представления registry,
hardcode несколько fixtures либо не могут отличить зарегистрированный unsupported tag; pinning
остаётся декларацией. **Контракт:** root reference-provenance/generated-artifact и plan-audit
§3–4 требуют явный producer→consumer carrier. Исправление: назвать vendored snapshot либо
детерминированно сгенерированный минимальный dataset, его version/hash/update producer,
`upstream.json` при vendoring, а также протянуть carrier через P2→P4 Files, validation и release
manifest.

**F10 · Major · high · issue · `phases/P0.md:45,52` ↔ `phases/P3.md:82` ↔
`phases/P7.md:68,75` — hook integrity проверяет присутствие и unit surfaces, но не реальный
worktree-local planning CLI.** Наблюдаемый запуск
`packages/harness/bin/harness hooks --target . --provider codex --observer --trusted --dry-run`
падает с `ValueError: root must be explicit and absolute` из `core/provider/lock.py`, тогда как
`PYTHONPATH=packages/harness/lib:. python3 -m unittest packages.harness.tests.test_provider_hooks`
проходит **12/12**. Effective installed hooks и `maind health --cwd` зелёные, то есть это именно
непокрытый source→target control path, а не общий отказ hook runtime. *failure_scenario:* P0
фиксирует hook как callable, P3 меняет provider setup, P7 прогоняет существующие suites — и
release candidate остаётся зелёным при сломанном dry-run/apply planner. **Контракт:**
root.codex.launch-and-hook-integrity и evidence-integrity запрещают считать skipped/false-green
check доказательством. Исправление в плане: занести наблюдаемый дефект в P0.1 evidence, дать ему
owning implementation/regression item, а в P3.2/P7.2 добавить точный absolute/relative-target
CLI smoke с проверкой planned operations и zero-write dry-run. Сам код в design-remediation не
чинить. **PROMOTE-CANDIDATE:** provider hook acceptance должна всегда включать public CLI path,
а не только прямые unit imports.

**F11 · Minor · high · issue · `AGENTS.md:48–49` ↔ `phases/P7.md:87–94` — load-bearing
external sources не имеют обязательной project provenance записи.** План опирается на RFC 5646,
IANA registry и HashiCorp drift/state-upgrade guidance, но `docs/reference.md` не содержит этих
источников, и ни один owning item явно не обновляет его. *failure_scenario:* contracts и tests
остаются, а холодный maintainer не может восстановить внешний design provenance или понять,
какая версия была проверена. **Контракт:** root.reference-provenance. Исправление: назначить P7.3
владельцем точных записей `docs/reference.md` (либо более ранний contract-freeze item, если запись
нужна до implementation) и проверить ссылки/версии.

**F12 · Minor · high · nitpick · `plan.md:314` — предыдущий audit содержит ложный phase
count.** Записано «семь фаз детализированы», хотя Status Board и файлы охватывают P0–P7, то есть
восемь фаз. *failure_scenario:* следующий audit или автоматизация повторяет неверный denominator
и создаёт ложное впечатление неполной/лишней фазы. Исправление: корректирующей append-only
ремаркой зафиксировать **8 фаз**, не переписывая историю захода 1.

### Покрытие брифа

| Мысль владельца | Носитель после remediation F1–F7 | Вердикт |
|:--|:--|:--|
| Hub надёжно конфигурирует Claude Code и Codex по project config | P1 · P3 · P6 | покрыто; F10 блокирует доказательство public hook path |
| Канон остаётся в SKM, без runtime/plugin copies в consumers | P0 · P1 · P3 · P5 | покрыто |
| Legacy/drift/trust дефекты исправляются preserve-first и с rollback | P0 · P5 · P6 · P7 | покрыто |
| Provider adapters независимы поверх shared semantics | D5 · P1 · P3 · P7 | покрыто |
| Compact English canonical, Russian sparse render | P2 · P4 | покрыто |
| Response/plan/diagnostics locale наследуются независимо | D2/D17 · P2.1 · P4.1 · P7.2 | покрыто; F9 блокирует registry reproducibility |
| Полный fleet и per-file evidence, skipped/unresolved non-green | P0 · P5 · P6 · P7 | покрыто; F8 ломает стартовую Validation |
| Security/trust и release действия имеют gates/rollback | P0.3–P0.4 · P5.4 · P6.1 · P7.4 | покрыто |

Непокрытых намерений брифа не найдено. RED вызван качеством трёх технических carriers, а не
утратой product intent.

### Проверено без находок

- **Ремедиация прошлого захода:** F1 — syntax/canonicalization/catalog и private-use разделены;
  F2 — D2–D4 markers разделяют external и internal evidence; F3 — P4.5 перечисляет реальные
  runners; F4 — roadmap несёт per-cwd protocol; F5 — P4 batches имеют bound/reviewer/resume;
  F6 — deterministic blocker predicates убраны из owner gates; F7 — D24 содержит predecessor
  status и inline `**Consequences:**`.
- **Brief→layers→spec:** восемь мыслей брифа имеют carriers; 11 findings и 9 research documents
  связаны Required Reads/Inputs/D-log; живых `[NEEDS CLARIFICATION]` нет.
- **Routing/roadmap:** фазовые specs, Routing и roadmap дают одно множество из **30/30** item IDs;
  для каждой строки есть непустой solo/per-cwd rationale, missing/extra route не найден.
- **Фазовые контракты:** P0→P7 producer/consumer порядок согласован; помимо F9 отсутствующих или
  преждевременных consumers не найдено.
- **DoR/provenance:** **8 фаз**, 30 specs с обязательными полями, `Design Passes: 3/3` и три
  matching Update Log rows; Authoring Model, Update Log actor/model и journal actor присутствуют.
- **Owner authority:** owner gates адресуют решения D#/rollback; вычисляемые predicates больше не
  требуют owner approval.

### Проверка внешних утверждений

- **RAG: OK, high confidence.** RFC 5646 повторно подтверждает полный private-use tag, opaque
  private-use semantics, case regularization и `Preferred-Value` mappings:
  [RFC 5646](https://www.rfc-editor.org/rfc/rfc5646.html).
- **RAG: OK, high confidence.** Актуальный IANA registry проверен у владельца dataset; его
  изменяемая `File-Date` усиливает F9, а не подменяет решение о carrier:
  [IANA registry](https://www.iana.org/assignments/language-subtag-registry/language-subtag-registry).
- **RAG: OK, high confidence.** Load-bearing drift/state facts повторно сверены с официальными
  HashiCorp docs: [detecting drift](https://developer.hashicorp.com/terraform/plugin/sdkv2/best-practices/detecting-drift)
  и [resource state upgrades](https://developer.hashicorp.com/terraform/plugin/framework/resources/state-upgrade).
- Непроверенных внешних классов фактов, от которых зависит этот verdict, не осталось; web
  retrieval использован только для standards/API facts, repository findings получены чтением
  кода, CLI и plan evidence.

### Серые зоны и дефекты среды

- План untracked: абсолютный lint зелёный, baseline delta недоступна и честно остаётся WARN.
- Hook dry-run defect из F10 наблюдён в dirty worktree. Он влияет на доверие к hook integrity и
  поэтому записан как finding; unrelated implementation не изменялся. Installed observer и
  memory hook smoke, `.codex/hooks.json`, `maind health --cwd` и provider hook unit-suite зелёные,
  но не компенсируют упавший public CLI path.
- `task@swissknifeman` отсутствует в активном `codex plugin list --json`; аудит выполнен по
  worktree-local canonical command/CLI, как требует repository rule.
- Canonical `plan-audit` journal command не передаёт `--attempt`, а journal CLI по умолчанию
  пишет `attempt: 1`: поэтому у append-записи захода 2 machine field остался `1`, тогда как
  heading и обязательная `note` честно несут «заход 2». Append-only журнал вручную не переписан;
  это дефект контракта команды/CLI, а не доказательство первого захода.
- `codex doctor --json` подтверждает `gpt-5.6-sol`, approval `never` и unrestricted filesystem,
  но effort не экспортирует; actor `frontier/xhigh` — routed command provenance.
- Исправление счёта прошлого отчёта: детализированы **8 фаз (P0–P7)**, не семь.

### Что запускать

**Next:** design-phase: task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE finish

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | high |
| Capabilities | repository-plan-edit · external-fact-verification |
| Context | cold-start — plan-step |
| Суть | Точечно закрыть F8–F12, сохранить принятую remediation F1–F7 и вернуть план на повторный design-аудит; execution запрещён |
| Команда | — |

| Model | Thinking | Context | Суть | Команда |
|:--|:--|:--|:--|:--|
| gpt-5.6-sol | high | `NEW SESSION — шаг-не-item` | Codex launch: `-C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c model_reasoning_effort="high" -a never -s danger-full-access`; точечная design-remediation F8–F12 | — |

```text
$ task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE finish

РЕЖИМ: точечная remediation повторного design-аудита, НЕ execution items
ВХОД: plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/plan.md → блок `## Audit design — 2026-08-03 (заход 2)`; прочитать ПЕРВЫМ
СКОУП: 1) F8 — сделать P0.1/P0.2 Validation полностью root-relative и copy/paste executable 2) F9 — назначить pinned IANA registry data/subset, provenance/update producer и протянуть carrier P2→P4→P7 3) F10 — занести observed hook dry-run defect в P0 evidence, назначить owning implementation/regression item и добавить exact public CLI smoke в P3.2/P7.2; код в design-сессии не чинить 4) F11 — назначить owning item для `docs/reference.md` и точных external-source записей 5) F12 — append-only исправить denominator на 8 фаз 6) повторить plan-lint, conflicts, citations и design-audit handoff
НЕ ТРОГАТЬ: brief intent; item statuses и Status Board 0/30; принятую семантику remediation F1–F7; frozen archived contracts; код, provider/fleet/Brain/release state; unrelated dirty worktree и plans/archive/**
```

## Audit design — 2026-08-03 (заход 3)

**Вердикт:** RED  
**Режим:** design  
**Попытка:** 3  
**Аудитор:** frontier/xhigh  
**Tree anchor:** `main` @ `d9d44245`; каталог плана остаётся untracked в dirty worktree.

**Линтер:** `python3 packages/task/scripts/plan-lint.py --conflicts` — **0 расхождений /
0 предупреждений**; абсолютный запуск `python3 packages/task/scripts/plan-lint.py
plans/2026.08.02-PROVIDER-CONTRACT-LOCALE` — **0 ERROR / 0 WARN**; baseline относительно
`HEAD` — **0 ERROR / 1 WARN**, потому что `git archive` не видит untracked-каталог плана и
не может вычислить delta новых ошибок. Post-write `verify-citations --strict` — **11 проверенных ссылок /
26 известных исключений / 0 findings**. Структурные проверки не снимают находки ниже.

**Почему RED.** Ремедиация F8–F12 принята: стартовые пути P0 исполнимы, pinned IANA carrier
и provenance/update chain назначены, public hook-path defect имеет implementation/regression
owners, `docs/reference.md` имеет владельца, denominator исправлен на 8 фаз. Однако два
обязательных P4 execution carrier всё ещё не доведены до cold-start формы: P4.2/P4.3 могут
писать в `packages/skiller/**` из root-сессии без package rules, а независимый reviewer для
P4.3–P4.6 не имеет готового read-only запуска. Это позволяет начать необратимо неоднозначную
миграцию corpus до того, как план определил допустимого исполнителя и проверяющего. P0.1 не
открывать до следующего design-аудита `GREEN`.

### Находки

**F13 · Major · high · issue · `phases/P4.md:16–20,82,101` ↔
`roadmap.md:33–43,76–77` — P4.2/P4.3 выпали из обязательного per-cwd carrier.** P4.2
изменяет root/core, `packages/skiller/**` и неопределённые «affected package
`scripts/validate.sh` files»; P4.3 также включает root ledger/plan evidence и Skiller sources.
При этом D39/per-cwd таблица и вводка P4 называют P4.1 и P4.4–P4.6, но не P4.2/P4.3, а roadmap
маршрутизирует оба как root `solo`. *failure_scenario:* исполнитель из root-cwd либо меняет
Skiller, не загрузив `packages/skiller/AGENTS.md`, либо сам придумывает разбиение; root ledger,
package commit и validation evidence перестают иметь доказуемый порядок и владельца.
**Исправление:** добавить P4.2/P4.3 в D39/per-cwd таблицу и roadmap, назвать точные root и
Skiller slices, заменить vague validation paths точным списком, оставить root coordinator
единственным владельцем shared ledger, integration и item closure.

**F14 · Major · high · issue · `roadmap.md:45–56,77–80` ↔
`phases/P4.md:18–20,103–105,122–124,141–143,160–162` — независимый P4 reviewer заявлен,
но executable reviewer launch отсутствует.** Единственный reusable launch в roadmap —
author/package-slice prompt, который разрешает mutation и commit. Для обязательного distinct
read-only reviewer нет модели/effort, точных входов committed checkpoint/diff, запрета edits,
формы `APPROVE|FIX_REQUIRED`, владельца reviewer record и двухраундовой escalation.
*failure_scenario:* cold coordinator повторно использует author session, допускает self-review,
получает неструктурированный verdict либо продолжает batch без проверяемой записи; checkpoint
verifier проверяет данные, которые план не научил никого корректно производить.
**Исправление:** добавить готовый reusable reviewer launch-block и привязать его к каждому
P4.3–P4.6 checkpoint: read-only/zero-mutation, committed manifest+diff+contract inputs,
distinct identity, точный output/evidence owner, `FIX_REQUIRED` fix-commit/fresh-review и
эскалация после второго раунда. **PROMOTE-CANDIDATE:** обязательный independent reviewer
carrier должен иметь отдельную исполняемую форму, а не только schema/verifier predicate.

**F15 · Minor · high · issue · `roadmap.md:65,97` — deterministic no-op всё ещё помещён
в owner gate.** P0.4 route и сводная строка требуют «exact containment D# или evidenced no-op».
No-op — вычисляемый результат evidence predicate, а не решение владельца. *failure_scenario:*
owner получает запрос подтвердить уже вычисленный no-op либо исполнитель считает no-op
waivable approval branch и пропускает строгую Validation. **Исправление:** оставить owner gate
только для exact mutation/containment D#, а evidenced no-op перенести в deterministic
Validation/Note и сводке отделить от owner authority.

### Покрытие брифа

| Мысль владельца | Носитель после remediation F8–F12 | Вердикт |
|:--|:--|:--|
| Hub надёжно конфигурирует Claude Code и Codex по project config | P1 · P3 · P6 | покрыто; F10 carrier теперь назначен |
| Канон остаётся в SKM, без runtime/plugin copies в consumers | P0 · P1 · P3 · P5 | покрыто |
| Legacy/drift/trust дефекты исправляются preserve-first и с rollback | P0 · P5 · P6 · P7 | покрыто |
| Provider adapters независимы поверх shared semantics | D5 · P1 · P3 · P7 | покрыто |
| Compact English canonical, Russian sparse render | P2 · P4 | product scope покрыт; F13/F14 блокируют безопасное исполнение миграции |
| Response/plan/diagnostics locale наследуются независимо | D2/D17 · P2.1 · P4.1 · P7.2 | покрыто; D41 carrier замкнут |
| Полный fleet и per-file evidence, skipped/unresolved non-green | P0 · P5 · P6 · P7 | покрыто; F8 пути исправлены |
| Security/trust и release действия имеют gates/rollback | P0.3–P0.4 · P5.4 · P6.1 · P7.4 | покрыто; F15 сужает только форму no-op gate |

Непокрытых product-intent мыслей брифа не найдено. RED вызван исполнимостью P4 orchestration,
а не утратой scope.

### Проверено без находок

- **Ремедиация F8–F12:** P0.1/P0.2 Validation полностью repository-root-relative; D41 и
  P2.1→P4.1→P7.2/P7.3 несут exact registry snapshot/provenance/update producer; D42 назначает
  observed relative hook defect P3.2 и regression P7.2; P7.3 владеет точными external-source
  entries в `docs/reference.md`; D43 append-only исправляет исторический denominator на **8 фаз**
  и несёт inline `**Consequences:**`.
- **Ранее принятая remediation F1–F7:** locale stages/private-use, RAG markers, реальные runners,
  базовый per-cwd protocol, bounded ledger/resume, deterministic blocker predicates и D24
  predecessor/consequences сохранены без регрессии; F13/F14 уточняют оставшиеся carrier gaps,
  а не отменяют принятую семантику.
- **Brief→layers→spec:** 8/8 мыслей брифа имеют carriers; brief, 12 findings и 9 research
  documents индексированы и связаны через Required Reads/Inputs/D-log; живых
  `[NEEDS CLARIFICATION]` нет.
- **Routing/roadmap/statuses:** Routing, phase specs и roadmap содержат одно множество **30/30**
  item IDs; `Design Passes: 3/3` подтверждены тремя Update Log rows; статусы items и Status Board
  остаются **0/30**. За исключением F13–F15, owner decisions, solo rationales и producer→consumer
  phase contracts согласованы.
- **D-log/provenance carriers:** отменяющие D24/D43 имеют inline `**Consequences:**`; Authoring
  Model, Update Log actor/model и journal actor присутствуют; frozen contract predecessors
  называются явно.

### Проверка внешних утверждений

- **RAG: OK, high confidence.** Официальный IANA registry повторно получен как exact bytes:
  `File-Date: 2026-06-14`, SHA-256
  `be1fad86a99e3a932d07b80c9b3c271ec2381a5909ce22420144e5077ab0a43a`:
  [IANA Language Subtag Registry](https://www.iana.org/assignments/language-subtag-registry/language-subtag-registry).
- **RAG: OK, high confidence.** Private-use opacity, case-insensitive matching и
  `Preferred-Value` canonicalization повторно сверены с
  [RFC 5646](https://www.rfc-editor.org/rfc/rfc5646.html).
- **RAG: OK, high confidence.** Drift/state-migration основания плана повторно сверены с
  официальными HashiCorp материалами: [detecting drift](https://developer.hashicorp.com/terraform/plugin/sdkv2/best-practices/detecting-drift)
  и [resource state upgrades](https://developer.hashicorp.com/terraform/plugin/framework/resources/state-upgrade).
- Непроверенных внешних fact classes, от которых зависит verdict, не осталось; F13–F15 получены
  из repository canon/spec/roadmap, а не из внешнего поиска.

### Серые зоны и дефекты среды

- План остаётся untracked: абсолютный lint воспроизводим и зелёный, но baseline delta недоступна
  и честно остаётся WARN.
- Worktree-local public hook planning всё ещё имеет известный F10 defect: relative `--target .`
  падает с `ValueError: root must be explicit and absolute`; absolute-target dry-run возвращает 0,
  но сообщает два `stale-source` lifecycle target. Это назначенный P3.2/P7.2 долг, а не зелёная
  проверка среды; код и hook state аудитом не менялись.
- `task@swissknifeman` отсутствует в активном `codex plugin list --json`; команда аудита прочитана
  и исполнена из worktree-local canonical files. `codex doctor --json` подтверждает configured
  `gpt-5.6-sol`, approval `never` и unrestricted filesystem, но не экспортирует active effort;
  command frontmatter pin `opus/xhigh` в этой Codex-сессии недоступен, поэтому journal actor
  остаётся честным route-class `frontier/xhigh`, а не ложным `opus/xhigh`.
- Memory hook, корректно вызванный SessionStart observer, `maind health --cwd --strict` и
  `harness doctor --provider-audit --json` зелёные. Предыдущие две audit-записи journal имеют
  default machine `attempt: 1`; текущая запись использует поддерживаемый CLI флаг `--attempt 3`,
  не переписывая append-only историю.

### Что запускать

**Next:** design-phase: task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE finish

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | high |
| Capabilities | repository-plan-edit · orchestration-contract-review |
| Context | cold-start — plan-step |
| Суть | Точечно закрыть F13–F15, сохранить принятую remediation F1–F12 и вернуть план на повторный design-аудит; execution запрещён |
| Команда | — |

| Model | Thinking | Context | Суть | Команда |
|:--|:--|:--|:--|:--|
| gpt-5.6-sol | high | `NEW SESSION — шаг-не-item` | Codex launch: `-C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c model_reasoning_effort="high" -a never -s danger-full-access`; точечная design-remediation F13–F15 | — |

```text
$ task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE finish

РЕЖИМ: точечная remediation третьего design-аудита, НЕ execution items
ВХОД: plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/plan.md → блок `## Audit design — 2026-08-03 (заход 3)`; прочитать ПЕРВЫМ
СКОУП: 1) F13 — протянуть P4.2/P4.3 через D39/per-cwd roadmap с точными root/package slices, validation paths и root-owned ledger/closure 2) F14 — добавить отдельный executable read-only reviewer launch/carrier для каждого P4.3–P4.6 checkpoint с exact inputs/output, distinct identity, two-round fix/review и escalation 3) F15 — вынести evidenced no-op P0.4 из owner gate в deterministic Validation/Note 4) повторить conflicts, absolute/baseline plan-lint, citations и design-audit handoff
НЕ ТРОГАТЬ: brief intent; item statuses и Status Board 0/30; принятую семантику remediation F1–F12; frozen archived contracts; код, provider/fleet/Brain/release state; unrelated dirty worktree и plans/archive/**
```

## Audit design — 2026-08-03 (заход 4)

**Вердикт:** RED  
**Режим:** design  
**Попытка:** 4  
**Аудитор:** frontier/xhigh  
**Tree anchor:** `main` @ `d9d44245`; каталог плана остаётся untracked в dirty worktree.

**Линтер:** `python3 packages/task/scripts/plan-lint.py --conflicts` — **0 расхождений /
0 предупреждений**; абсолютный запуск `python3 packages/task/scripts/plan-lint.py
plans/2026.08.02-PROVIDER-CONTRACT-LOCALE` — **0 ERROR / 0 WARN**; baseline относительно
`HEAD` — **0 ERROR / 1 WARN**, потому что `git archive` не видит untracked-каталог плана и
не может вычислить delta новых ошибок. `verify-citations --strict` — **6 проверенных ссылок /
26 известных исключений / 0 findings**. Task plan-lint/contract suite — **258 tests, OK** на
том же worktree после корректного запуска с `PYTHONPATH=packages/task/lib:packages/task/tests:.`.
Структурная зелень не снимает находки ниже.

**Почему RED.** Ремедиация F13–F15 принята: P4.2/P4.3 включены в per-cwd protocol,
P4.3–P4.6 получили отдельный read-only reviewer carrier, а P0.4 no-op отделён от Owner
authority. Но final audit всё ещё явно отсекает новые решения D41–D46, P5 обещает
append-only per-project progress без какого-либо durable carrier/restart protocol, а несколько
критических Validation оставляют cold-start исполнителю выбор неназванной команды. Это дефекты
release evidence и recoverable live execution, а не бухгалтерия. P0.1 не открывать до следующего
design-аудита `GREEN`.

### Находки

**F16 · Major · high · issue · `phases/P7.md:112` — финальный audit crosswalk зафиксирован
на устаревшем диапазоне D1–D40.** После него D-log уже содержит D41–D46: pinned IANA carrier,
public hook regression owner, readiness correction, P4.2/P4.3 per-cwd ownership, reviewer
carrier и deterministic P0.4 no-op. *failure_scenario:* P7.4 исполняет literal checklist,
не проверяет один или несколько этих release-bearing решений и всё равно выпускает GREEN,
потому что его собственная Validation не требует exact equality с текущим множеством D#.
**Исправление:** заменить статический предел на exact-set crosswalk всех существующих к моменту
аудита release-bearing D# (сейчас D1–D46), добавить отказ на missing/extra decision rows и
протянуть тот же denominator в P7.4 Validation/deliverable.

**F17 · Major · high · issue · `plan.md:126` ↔
`research/05-p5-consumer-migration-design.md:53` ↔ `phases/P5.md:51–55,70–74,89–93,108–112`
— заявленная append-only per-project защита от скрытого partial rollout не имеет носителя.**
D29 назначает mitigation «append-only per-project results», research требует transaction states,
но P5 Files называют только один итоговый `P5.x-results.json` на item, а Implementation/Validation
не определяют write-ahead запись, состояния проекта, atomic acceptance, restart cursor или
reconciliation уже применённого проекта после падения процесса. Per-project rollback при
наблюдаемой ошибке не закрывает crash boundary. *failure_scenario:* процесс падает после live
apply/readback проекта A, но до записи aggregate results; новая сессия встречает изменённый
preimage и не может доказуемо отличить ранее одобренный успех от чужого drift, безопасно
продолжить с B или восстановить A. **Исправление:** назначить один durable append-only P5
transaction/checkpoint carrier с stable project/action IDs, before/apply/readback/accepted-or-
rolled-back states, pre/post hashes, committed action-set/source identities и deterministic
resume/reconcile algorithm; включить его во Files P5.1–P5.4, runner subcommands, negative crash
fixtures, `verify-results`, convergence и P6 handoff. **PROMOTE-CANDIDATE:** live fleet loops,
которые обещают resumability, должны иметь write-ahead per-target carrier, а не только финальный
aggregate JSON.

**F18 · Major · high · issue · `phases/P4.md:124,162`; `phases/P5.md:55,74,93,112`;
`phases/P6.md:74,112`; `phases/P7.md:56,113` — roadmap ведёт в items, чьи Validation всё ещё
содержат prose placeholders вместо cold-start команд.** Примеры: «that package's exact targeted
tests», «the full cross-package unittest command from the frozen spec», «the owning
standalone/link check», «Runner tests», голый `verify-results`, «Helper --write/--check» и
«P7.1 verifier … rerun green». Files иногда позволяют догадаться о helper, но не задают cwd,
полный invocation, arguments/input artifacts и exit/result gate. *failure_scenario:* разные
исполнители выбирают разные discovery suites или вызывают `verify-results` без frozen action-set
и evidence paths; один закрывает item зелёным, другой получает иную матрицу, а P7.4 не может
повторить опубликованную Validation byte-for-byte. **Исправление:** для каждого перечисленного
item заменить placeholders точными worktree-local root/per-cwd командами, включая helper path,
subcommand, обязательные action/evidence/contract arguments и план-lint invocation; для
package-dependent P4 checkpoints дать замкнутую cwd→command таблицу, как уже сделано в P4.5.

### Покрытие брифа

| Мысль владельца | Носитель после remediation F13–F15 | Вердикт |
|:--|:--|:--|
| Hub надёжно конфигурирует Claude Code и Codex по project config | P1 · P3 · P6 | покрыто; D42 implementation/regression chain сохранён |
| Канон остаётся в SKM, без runtime/plugin copies в consumers | P0 · P1 · P3 · P5 | покрыто |
| Legacy/drift/trust дефекты исправляются preserve-first и с rollback | P0 · P5 · P6 · P7 | product scope покрыт; F17 блокирует crash-resumability live rollout |
| Provider adapters независимы поверх shared semantics | D5 · P1 · P3 · P7 | покрыто |
| Compact English canonical, Russian sparse render | P2 · P4 | покрыто; F18 требует точные acceptance invocations |
| Response/plan/diagnostics locale наследуются независимо | D2/D17 · P2.1 · P4.1 · P7.2 | покрыто; D41 registry carrier сохранён |
| Полный fleet и per-file evidence, skipped/unresolved non-green | P0 · P5 · P6 · P7 | покрыто по intent; F17 скрывает interrupted per-project progress |
| Security/trust и release действия имеют gates/rollback | P0.3–P0.4 · P5.4 · P6.1 · P7.4 | покрыто; F16/F18 блокируют воспроизводимый final gate |

Непокрытых product-intent мыслей брифа не найдено. RED вызван тремя execution/evidence
carriers, а не утратой scope.

### Проверено без находок

- **Ремедиация F13–F15:** P4.2/P4.3 имеют точные root/Skiller slices и root-owned
  ledger/integration/closure; P4.3–P4.6 имеют frontier/high distinct-identity read-only reviewer,
  exact committed inputs, JSON `APPROVE|FIX_REQUIRED`, root-owned record и two-round escalation;
  P0.4 no-op определён Validation predicate, а Owner D# остаётся только для mutation branch.
- **Brief→layers→spec:** 8/8 мыслей брифа имеют carriers; brief, 12 findings и 9 research
  документов связаны через Inputs/Required Reads/D-log; живых `[NEEDS CLARIFICATION]` нет.
- **Структура/roadmap:** 30 item specs P0.1–P7.4 присутствуют, phase/status/roadmap IDs и routes
  согласованы по lint; статусы остаются 0/30; solo/per-cwd rationales и owner gates, кроме
  находок, не противоречат последовательным producer→consumer contracts.
- **Design provenance:** `Design Passes: 3/3` подтверждён тремя Update Log rows; Authoring Model,
  Update Log role/model и journal actor carriers присутствуют.
- **D-log:** D24 и D43, которые отменяют прежнюю форму/вердикт, несут inline
  `**Consequences:**`; новых superseding-записей без consequences не найдено.
- **External provenance:** D41 по-прежнему связывает exact IANA bytes/hash/upstream/update
  producer с P2→P4→P7; P7.3 владеет `docs/reference.md` и citation gate.

### Проверка внешних утверждений

- **RAG: OK, high confidence.** Официальный IANA dataset повторно получен как exact bytes:
  `File-Date: 2026-06-14`, SHA-256
  `be1fad86a99e3a932d07b80c9b3c271ec2381a5909ce22420144e5077ab0a43a`:
  [IANA Language Subtag Registry](https://www.iana.org/assignments/language-subtag-registry/language-subtag-registry).
- **RAG: OK, high confidence.** Private-use/canonicalization основания сверены с
  [RFC 5646](https://www.rfc-editor.org/rfc/rfc5646.html); drift/state-upgrade основания — с
  официальными HashiCorp материалами [detecting drift](https://developer.hashicorp.com/terraform/plugin/sdkv2/best-practices/detecting-drift)
  и [resource state upgrades](https://developer.hashicorp.com/terraform/plugin/framework/resources/state-upgrade).
- Непроверенных external fact classes, от которых зависит verdict, не осталось. F16–F18 —
  repository/plan-grounded findings; внешние материалы не подменяют их доказательство.

### Серые зоны и дефекты среды

- План остаётся untracked: absolute/conflict lint воспроизводимы, baseline delta недоступна и
  честно остаётся WARN.
- Worktree-local hook integrity не зелёная: relative `harness hooks --target . ... --dry-run`
  падает с `ValueError: root must be explicit and absolute`; absolute-target dry-run возвращает
  0, но планирует два `stale-source` обновления. Это известный D42/F10 defect с владельцами
  P3.2/P7.2, а не новая находка; hook state аудитом не менялся.
- `codex doctor --json` подтверждает configured `gpt-5.6-sol`, approval `never` и unrestricted
  filesystem, но не экспортирует active effort; actor `frontier/xhigh` — routed provenance.
- Первый локальный запуск Task tests не включил `packages/task/tests` в `PYTHONPATH` и не принят
  как evidence; исправленный полный запуск дал 258/258 OK. Попытка временного citation-download
  с cleanup была отклонена до изменения данных; exact IANA bytes затем проверены stream-only.
- `task@swissknifeman` не развёрнут в активном plugin catalog; аудит выполнен через
  worktree-local canonical command/CLI. `maind health --cwd`, `harness doctor` и memory
  round-trip зелёные, но не компенсируют hook defect.

### Что запускать

**Next:** design-phase: task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE finish

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | high |
| Capabilities | repository-plan-edit · execution-contract-review |
| Context | cold-start — plan-step |
| Суть | Точечно закрыть F16–F18, сохранить принятую remediation F1–F15 и вернуть план на повторный design-аудит; execution запрещён |
| Команда | — |

| Model | Thinking | Context | Суть | Команда |
|:--|:--|:--|:--|:--|
| gpt-5.6-sol | high | `NEW SESSION — шаг-не-item` | Codex launch: `-C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c model_reasoning_effort="high" -a never -s danger-full-access`; точечная design-remediation F16–F18 | — |

```text
$ task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE finish

РЕЖИМ: точечная remediation четвёртого design-аудита, НЕ execution items
ВХОД: plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/plan.md → блок `## Audit design — 2026-08-03 (заход 4)`; прочитать ПЕРВЫМ
СКОУП: 1) F16 — сделать P7.4 crosswalk exact-set по всем актуальным release-bearing D# (сейчас D1–D46) и запретить GREEN при missing/extra rows 2) F17 — добавить durable append-only per-project P5 transaction/checkpoint carrier, crash-boundary states, deterministic resume/reconcile и протянуть его через P5.1–P5.4→P6 3) F18 — заменить prose placeholders в P4.4/P4.6/P5/P6.1/P6.3/P7.1/P7.4 точными root/per-cwd helper/test/verify/lint командами и обязательными аргументами 4) повторить conflicts, absolute/baseline plan-lint, citations и design-audit handoff
НЕ ТРОГАТЬ: brief intent; item statuses и Status Board 0/30; принятую семантику remediation F1–F15; frozen archived contracts; код, provider/fleet/Brain/release state; unrelated dirty worktree и plans/archive/**
```

## Audit design — 2026-08-03 (заход 5)

**Вердикт:** RED  
**Режим:** design  
**Попытка:** 5  
**Аудитор:** frontier/xhigh (Codex `gpt-5.6-sol`; active effort runtime не экспортирует)  
**Tree anchor:** `main` @ `d9d44245`; каталог плана остаётся untracked в dirty worktree.

**Линтер:** `python3 packages/task/scripts/plan-lint.py --conflicts` — **0 расхождений /
0 предупреждений**; `python3 packages/task/scripts/plan-lint.py
plans/2026.08.02-PROVIDER-CONTRACT-LOCALE` — **0 ошибок / 0 предупреждений**; baseline
относительно `HEAD` — **0 ошибок / 1 предупреждение**, потому что `git archive` не видит
untracked-каталог плана и delta новых ошибок не вычисляется. `python3 plans/verify-citations.py
plans/2026.08.02-PROVIDER-CONTRACT-LOCALE --strict` — **11 проверенных ссылок / 26 известных
исключений / 0 находок**. `bash packages/task/scripts/validate.sh` — **479 tests, OK**,
`plan-lint --conflicts` внутри suite — **0/0**. Структурная зелень не снимает дефекты
исполняемости ниже.

**Почему RED.** Ремедиация F16–F18 добавила dynamic D# exact-set, durable P5 journal и
большинство exact invocations, но холодный проход выявил четыре новых Major-класса: один из
«точных» 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.6 apply-вызовов гарантированно отказывается на
ненулевом diff; промежуточный P4 протокол одновременно требует zero exit и допускает deferred
generated drift; 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.4 потребляет неназванный checker, а
2026.08.02-PROVIDER-CONTRACT-LOCALE P6.1 защищает наблюдаемую ошибку rollback-ом, но не
процессный crash между live write и result carrier. Дополнительно
2026.08.02-PROVIDER-CONTRACT-LOCALE P4.6 требует неоднозначный
2026.08.02-PROVIDER-CONTRACT-LOCALE P0.3 D#, который
может отсутствовать на no-op ветке. Открывать 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.1 до
следующего независимого GREEN design-аудита нельзя.

### Находки

**F19 · Major · high · issue · `phases/P4.md:161–162` ↔
`packages/harness/lib/harness/instructions.py:520–528` — exact
2026.08.02-PROVIDER-CONTRACT-LOCALE P4.6 Harness apply invocation
не передаёт обязательный target authorization set.** План перечисляет только
`harness instructions plan|apply|check --target ... --provider claude-code,codex --json`, тогда
как публичный `apply` сравнивает writable targets с `authorized_target_paths` и при отсутствии
точного ordered `--authorize` возвращает `INSTRUCTION_WRITE_FORBIDDEN`. *failure_scenario:*
terminal plan находит хотя бы одну stale/missing projection; apply получает пустой authorization
set, завершается 1, generated drift остаётся, а 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.6 не может
достичь своего же acceptance. **Исправление:** frozen helper plan должен зафиксировать exact
ordered writable target set и plan hash, а apply-вызов — передать этот набор через
`--authorize <ordered-paths>`; negative fixtures должны доказать отказ на missing/extra/reordered
authorization и byte-stable clean check после применения.

**F20 · Major · high · issue · `roadmap.md:24–31,60–99` ↔
`phases/P4.md:105,124,143,154,160–162` — deferred generated drift не имеет одного непротиворечивого
checkpoint state.** Общий carrier принимает slice только когда все named commands вернули 0,
закрытая 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.4 / 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.6
cwd-матрица тоже требует exit 0, но 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.3–
2026.08.02-PROVIDER-CONTRACT-LOCALE P4.5 намеренно
допускают только enumerated 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.6
derived drift, а docs-checkpoints 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.6 исполняются до
terminal regeneration. *failure_scenario:* первый canonical source batch делает ожидаемо stale
generated projection; full package validation возвращает ненулевой freshness gate. Phase spec
разрешает этот результат, generic/closed roadmap carrier запрещает acceptance, поэтому resume
никогда не доходит до единственного owning regeneration stage. **Исправление:** определить один
machine-checkable `deferred-derived-only` state с exact diagnostic/path set и нулём прочих ошибок
либо использовать до terminal stage runner без freshness gate; после terminal regeneration все
package/docs validations обязаны вернуть 0. Тот же state надо протянуть в evidence schema,
checkpoint verifier, resume и 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.6 close gate.
**PROMOTE-CANDIDATE:** terminal regeneration
требует канонического межфазного состояния для ожидаемого derived drift, а не противоречащих
друг другу prose exceptions.

**F21 · Major · high · issue · `phases/P0.md:83–90,104–109` — frozen
2026.08.02-PROVIDER-CONTRACT-LOCALE P0.3 checker, обязательный для no-op
2026.08.02-PROVIDER-CONTRACT-LOCALE P0.4, не имеет producer/path/invocation.** Files и Deliverables
2026.08.02-PROVIDER-CONTRACT-LOCALE P0.3 называют contract, matrix, premortem и finding;
Validation оставляет «checker/structured review» без executable carrier. Затем
2026.08.02-PROVIDER-CONTRACT-LOCALE P0.4 уже требует «the frozen
2026.08.02-PROVIDER-CONTRACT-LOCALE P0.3 checker» и его
deterministic pass. *failure_scenario:* no-op predicate семантически верен, но новая сессия не
может создать повторяемое доказательство, какой checker, schema и exit contract закрывают
2026.08.02-PROVIDER-CONTRACT-LOCALE P0.4;
ручной review либо plan-lint ошибочно принимается за эквивалент. **Исправление:** добавить в
2026.08.02-PROVIDER-CONTRACT-LOCALE P0.3 plan-local stdlib checker, schema/fixtures, Files,
Deliverables и exact root invocation; 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.4 должен потреблять
его версию/hash и точную команду для action/no-op branches.

**F22 · Major · high · issue · `phases/P0.md:88–90,100–109` ↔
`phases/P4.md:161–162` ↔ `roadmap.md:148–149,164,177–193` —
2026.08.02-PROVIDER-CONTRACT-LOCALE P4.6 привязывает ordinary generated write к неразличимому
«2026.08.02-PROVIDER-CONTRACT-LOCALE P0.3 Owner D#».** P0 отделяет mutation-only containment authority от
deterministic `action_set=[]` без authority request; roadmap даёт
2026.08.02-PROVIDER-CONTRACT-LOCALE P4.6 gate `terminal ledger`. Однако terminal-regeneration
approval требует «the 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.3 Owner D#»,
не определяя, это freeze решения recovery contract, security action D# или новое разрешение на
generated target set. *failure_scenario:* P0 закрывается no-op без containment D#, terminal ledger
зелёный, но 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.6 helper не может собрать требуемый approval;
либо исполнитель повторно использует
security D# для неавторизованного им repository write. **Исправление:** типизировать и развести
contract-freeze, containment-mutation и terminal-regeneration decisions. Если
2026.08.02-PROVIDER-CONTRACT-LOCALE P4.6 действительно
требует Owner authority, создать отдельный D# над exact plan hash/authorized target set/rollback;
иначе убрать чужой D# и оставить terminal ledger + helper authorization как единственный gate.

**F23 · Major · high · issue · `phases/P6.md:62–76` — live Brain transaction не имеет durable
write-ahead/restart carrier на crash boundary.** 2026.08.02-PROVIDER-CONTRACT-LOCALE P6.1
обещает whole-project rollback при обнаруженном failed readback, но runner имеет только
`plan|check|apply|rollback|verify-results`; `P6.1-results.json` — итоговый carrier после операции.
Нет pre-write append+fsync, закрытой state machine, `resume/reconcile` или crash injection после
каждого public CLI boundary, хотя тот же класс уже закрыт D47 для P5. *failure_scenario:* процесс
падает после первого разрешённого Skiller/Harness/mAInd write, но до results/readback; новая
сессия не может доказуемо отличить exact approved postimage от чужого drift и безопасно принять
или откатить всю Brain transaction. **Исправление:** расширить D47-class durable carrier на
2026.08.02-PROVIDER-CONTRACT-LOCALE P6.1 либо ввести отдельный hash-chained WAL с stable action
IDs, pre/post identities, append+fsync до/после каждого write/readback, deterministic
resume/reconcile/rollback и crash-boundary fixtures. **PROMOTE-CANDIDATE:** любой multi-boundary
live transaction, заявляющий recoverability, обязан иметь write-ahead carrier независимо от
числа target projects.

**F24 · Minor · high · issue · `phases/P5.md:58–60` —
2026.08.02-PROVIDER-CONTRACT-LOCALE P5.1 одновременно объявляет `plan`/`check`
strictly no-write и требует от `plan` создать manifest/journal outputs.** Validation уже допускает
delta в named initialization outputs, поэтому буквальный запрет невыполним. **Исправление:** назвать
гарантию точно: zero writes to consumer/provider targets; `plan` атомарно создаёт только named
manifest/journal, `check` не меняет ни одного байта. Добавить separate byte-delta assertions для
обоих subcommands.

**F25 · Minor · high · issue · `findings/12-design-audit-remediation-2026-08-03.md:3–7,78–94`
— knowledge-layer scope противоречит собственному содержимому.** Scope утверждает, что файл
фиксирует только provenance/reproductions для F8–F12, но тот же finding теперь несёт remediation
F16–F18. **Исправление:** append-only уточнить scope/историю расширения либо вынести F16–F18 в
новый indexed finding; не переписывать наблюдавшуюся историю как будто первоначальный scope был
шире.

### Покрытие брифа

| Мысль владельца | Носитель после remediation F16–F18 | Вердикт |
|:--|:--|:--|
| Hub надёжно конфигурирует Claude Code и Codex по project config | 2026.08.02-PROVIDER-CONTRACT-LOCALE P1 · P3 · P6 | product scope покрыт; F23 блокирует crash-safe Brain apply |
| Канон остаётся в SKM, без runtime/plugin copies в consumers | 2026.08.02-PROVIDER-CONTRACT-LOCALE P0 · P1 · P3 · P5 | покрыто |
| Legacy/drift/trust дефекты исправляются preserve-first и с rollback | 2026.08.02-PROVIDER-CONTRACT-LOCALE P0 · P5 · P6 · P7 | покрыто; F21/F23 оставляют no-op/live recovery недоказуемыми |
| Provider adapters независимы поверх shared semantics | D5 · 2026.08.02-PROVIDER-CONTRACT-LOCALE P1 · P3 · P7 | покрыто |
| Compact English canonical, Russian sparse render | 2026.08.02-PROVIDER-CONTRACT-LOCALE P2 · P4 | покрыто; F19/F20 блокируют terminal regeneration |
| Response/plan/diagnostics locale наследуются независимо | D2/D17 · 2026.08.02-PROVIDER-CONTRACT-LOCALE P2.1 · 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.1 · 2026.08.02-PROVIDER-CONTRACT-LOCALE P7.2 | покрыто; pinned registry carrier воспроизводим |
| Полный fleet и per-file evidence, skipped/unresolved non-green | 2026.08.02-PROVIDER-CONTRACT-LOCALE P0 · P5 · P6 · P7 | покрыто по intent; F21/F23 ломают два evidence transitions |
| Security/trust и release действия имеют gates/rollback | 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.3–2026.08.02-PROVIDER-CONTRACT-LOCALE P0.4 · 2026.08.02-PROVIDER-CONTRACT-LOCALE P5.4 · 2026.08.02-PROVIDER-CONTRACT-LOCALE P6.1 · 2026.08.02-PROVIDER-CONTRACT-LOCALE P7.4 | покрыто; F22 смешивает разные authority classes |

Непокрытых product-intent мыслей брифа не найдено. RED вызван producer/consumer,
authority, generated-drift и crash-recovery carriers, а не потерей scope.

### Проверено без находок

- **Ремедиация F16–F18:** D49/P7 dynamic verifier требует exact equality с текущими D1–D49;
  D47/P5 durable journal имеет hash chain, fsync, closed states и resume/reconcile; новые
  root/per-cwd команды в большинстве перечисленных items раскрыты и действительные
  `harness instructions plan|check|apply` subcommands существуют. F19 — точечный missing argument,
  а не отсутствие CLI.
- **Brief→layers→spec:** 8/8 мыслей брифа имеют carriers; brief, 12 findings и 9 research
  документов связаны через Inputs/Required Reads/D-log. Живых skeleton/clarification markers нет;
  F25 — узкое противоречие scope одного knowledge carrier.
- **Структура/roadmap:** 30 item specs 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.1–
  2026.08.02-PROVIDER-CONTRACT-LOCALE P7.4
  присутствуют; phase/status/roadmap IDs и routes согласованы по lint, статусы остаются 0/30.
  Package docs commands из 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.6 cwd-матрицы существуют;
  Task корректно остаётся без npm docs.
- **Design provenance:** `Design Passes: 3/3`, `Authoring Model`, три Update Log carrier и journal
  actor присутствуют; active Codex effort не наблюдаем и не выдан за доказанный.
- **D-log:** current exact set D1–D49; D24/D43 superseding rows несут inline
  `**Consequences:**`; новых superseding записей без consequences не найдено.
- **External provenance:** pinned IANA bytes/hash/update owner проходят repeat verification;
  2026.08.02-PROVIDER-CONTRACT-LOCALE P7.3 владеет `docs/reference.md` и strict citation gate.

### Проверка внешних утверждений

- **RAG: OK, high confidence.** Official IANA registry повторно получен stream-only:
  `File-Date: 2026-06-14`, `731605` bytes, SHA-256
  `be1fad86a99e3a932d07b80c9b3c271ec2381a5909ce22420144e5077ab0a43a`:
  [IANA Language Subtag Registry](https://www.iana.org/assignments/language-subtag-registry/language-subtag-registry).
- **RAG: OK, high confidence.** `Preferred-Value` canonical mapping и private-use opacity
  повторно сверены с [RFC 5646](https://www.rfc-editor.org/rfc/rfc5646.html). Официальные
  HashiCorp страницы [detecting drift](https://developer.hashicorp.com/terraform/plugin/sdkv2/best-practices/detecting-drift)
  и [resource state upgrades](https://developer.hashicorp.com/terraform/plugin/framework/resources/state-upgrade)
  доступны и остаются design provenance, не dependency.
- Perplexity Web использован первым как retrieval draft, но вопреки official-only query добавил
  стороннюю нерелевантную ссылку; она отброшена. Все четыре external fact classes независимо
  проверены прямым открытием official primary sources; непроверенных external facts, от которых
  зависит verdict, нет. F19–F25 — repository/plan-grounded.

### Серые зоны и дефекты среды

- План untracked: absolute/conflict lint воспроизводимы, baseline delta недоступна и остаётся WARN.
- `codex doctor --json` подтверждает configured `gpt-5.6-sol`, approval `never`, unrestricted
  filesystem и network, но не экспортирует active effort; `frontier/xhigh` — routed provenance.
- Worktree содержит широкие чужие изменения. Аудит не менял code/provider/fleet/Brain/generated
  state и не интерпретирует dirty tree как evidence результата.
- Первый citation invocation был ошибочно направлен в несуществующий plan-local path и завершился
  2; он не принят. Точная команда `python3 plans/verify-citations.py ... --strict` затем зелёная.
  Первая попытка локального IANA hash с cleanup была отклонена до изменения данных; stream-only
  повтор дал exact header/size/hash выше.
- Worktree-local `harness doctor`, provider audit, `maind health --cwd --strict` и memory round-trip
  зелёные. Финальный hook preflight воспроизвёл известную границу: relative
  `harness hooks --target . ... --dry-run` завершился 1 с `root must be explicit and absolute`,
  absolute-target форма завершилась 0 и показала два `stale-source → update` действия. Дефект
  остаётся назначен 2026.08.02-PROVIDER-CONTRACT-LOCALE P3.2 /
  2026.08.02-PROVIDER-CONTRACT-LOCALE P7.2 и не исправлялся этим аудитом.
- Активный runtime не предоставляет provider-native Opus; audit выполнен доступным Codex
  frontier route. Если независимый Opus является обязательным организационным gate, этот запуск
  дополнительно считается degraded, а не заменяет его.

### Что запускать

**Next:** design-phase: task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE finish

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | high |
| Capabilities | repository-plan-edit · execution-contract-review |
| Context | cold-start — plan-step |
| Суть | Точечно закрыть F19–F25, сохранить принятую remediation F1–F18 и вернуть план на повторный design-аудит; execution запрещён |
| Команда | — |

| Model | Thinking | Context | Суть | Команда |
|:--|:--|:--|:--|:--|
| gpt-5.6-sol | high | `NEW SESSION — шаг-не-item` | Codex launch: `-C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c model_reasoning_effort="high" -a never -s danger-full-access`; точечная design-remediation F19–F25 | — |

```text
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c model_reasoning_effort="high" -a never -s danger-full-access

$ task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE finish

РЕЖИМ: точечная remediation пятого design-аудита, НЕ execution items
ВХОД: plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/plan.md → блок `## Audit design — 2026-08-03 (заход 5)`; прочитать ПЕРВЫМ
СКОУП: 1) F19 — добавить exact ordered `--authorize` в 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.6 Harness apply carrier 2) F20 — согласовать machine-checkable deferred-derived state и terminal all-green gate 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.3–2026.08.02-PROVIDER-CONTRACT-LOCALE P4.6 3) F21/F22 — создать executable 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.3 checker и развести contract/containment/terminal-regeneration authority 4) F23 — добавить durable WAL/resume/reconcile/crash fixtures 2026.08.02-PROVIDER-CONTRACT-LOCALE P6.1 5) F24/F25 — уточнить 2026.08.02-PROVIDER-CONTRACT-LOCALE P5.1 no-write semantics и knowledge-layer scope 6) повторить conflicts, absolute/baseline plan-lint, citations и design-аудит
НЕ ТРОГАТЬ: brief intent; item statuses и Status Board 0/30; принятую семантику remediation F1–F18; frozen archived contracts; code/provider/fleet/Brain/generated/release state; append-only D-log/history; unrelated dirty worktree и plans/archive/**
```

## Audit design — 2026-08-03 (заход 6)

**Вердикт:** ATTENTION  
**Content verdict:** GREEN — F19–F25 закрыты, новых design findings не найдено.  
**Режим:** design, same-session adversarial replay after targeted remediation  
**Попытка:** 6  
**Аудитор:** Codex `gpt-5.6-sol/high`; runtime не экспортирует active effort  
**Tree anchor:** `main` @ `d9d44245`; plan tree status hash
`2d89097f7ac0dc5df74aed10ef9b8cc2b53f798c27cdcc87b27a59c2ba68cec4`, каталог плана untracked.

**Почему ATTENTION, а не GREEN.** Содержательная повторная проверка зелёная, но она выполнена
тем же design-сеансом после собственных правок. Обязательные для независимого protocol-аудита
cold-start/frontier-xhigh separation и наблюдаемый route/effort не доказаны; выдавать такой запуск
за независимый GREEN нарушило бы audit separation. Это процессный gate, не новая design-находка:
execution 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.1 остаётся закрыт до следующего cold
`task:plan-audit ... design` с literal GREEN.

### Результат ремедиации F19–F25

| Находка | Закрывающий carrier | Повторная проверка |
|:--|:--|:--|
| F19 | D50; 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.6 frozen plan hash, Harness-only alphabetic `authorized_target_paths`, exact `--authorize` и missing/extra/reordered negatives | closed |
| F20 | D50; единый roadmap `clean|deferred-derived-only` schema, verifier-owned exact diagnostic/path set, cumulative resume union и terminal all-green/empty/byte-stable gate | closed |
| F21 | D51; plan-local P0.3 stdlib checker, schema/tests/evidence, exact `write|check|verify-branch` invocations и recorded checker/input/decision-row hashes | closed |
| F22 | D51; distinct `contract_freeze_decision`, `containment_mutation_decision` и technical P4.6 item authorization; checker parses the exact D# row and refuses wrong type | closed |
| F23 | D52; P6.1 hash-chained append+flush+fsync/reopen Brain WAL, closed restart/reconcile/rollback semantics and crash fixtures at every append/public boundary | closed |
| F24 | D53; P5.1 `plan` may create exactly manifest/journal with zero target writes, while `check` changes no byte; separate delta assertions | closed |
| F25 | append-only scope-extension history plus F19–F25 remediation section in `findings/12-design-audit-remediation-2026-08-03.md` | closed |

### Проверено без находок

- Brief intent and F1–F18 remediation semantics remain unchanged; 30/30 item specs and all 30
  item Status fields remain `⬜ Not started`, while the Status Board remains 0/30.
- Decision Log is the exact unique ordered set D1–D54. P7.4 still computes its denominator
  dynamically; both current explanatory occurrences now say D1–D54 without weakening D49.
- P4 distinguishes the cumulative generated target union from the Harness-only writable
  authorization subset. No source checkpoint can defer a semantic/test/link/launch failure, and
  terminal P4.6 requires every named command 0, empty deferred state and byte-stable second runs.
- P0 checker authority is executable from a cold session: it hashes its own bytes and frozen
  inputs, parses the exact append-only Decision Log row, records that row's canonical hash and
  requires the expected decision type. P4.6 consumes no P0 contract/security authority.
- P6.1's exact-preimage restart branch is consistently terminal `rolled-back`; exact postimage
  proceeds only to fresh readback, partial planned state rolls back, and third state/source/WAL
  drift refuses before write.
- No brief, archive, package/code/provider/fleet/Brain/generated/release or unrelated dirty-tree
  file was changed by this remediation. The plan-local research summaries were aligned with the
  normative D50/D52 phase carriers; no execution artifact was produced.

### Executable evidence

- `bash packages/task/scripts/validate.sh` — **479 tests, OK**, final `validate: OK`.
- `python3 packages/task/scripts/plan-lint.py --conflicts` — **0/0**.
- absolute plan lint — **0 errors / 0 warnings**; `--baseline HEAD` — **0 errors / 1 warning**
  because the plan directory is untracked and `git archive HEAD` cannot supply a baseline.
- `python3 plans/verify-citations.py plans/2026.08.02-PROVIDER-CONTRACT-LOCALE --strict` —
  **12 citations / 26 known exceptions / 0 findings**.
- Independent invariant script — **30 unique item IDs, 30 Not started statuses, exact unique
  D1–D54**. Textual mentions of `[NEEDS CLARIFICATION]` are negative assertions/history, not live
  clarification markers.

### External verification and environment limits

No new external fact class was introduced by F19–F25. The existing official-source classes were
reopened directly on 2026-08-03: IANA still reports `File-Date: 2026-06-14`, and a stream-only
read remains `731605` bytes with SHA-256
`be1fad86a99e3a932d07b80c9b3c271ec2381a5909ce22420144e5077ab0a43a`; RFC 5646 and the two
official HashiCorp drift/state-upgrade pages remain available. The verdict on F19–F25 is
repository-grounded; these sources are provenance continuity, not a dependency.

Environment disclosures remain material: the broad dirty worktree is foreign and preserved;
the plan is untracked, so HEAD baseline attribution is unavailable; `codex doctor` does not expose
active effort; absolute hook dry-run is executable but reports the already assigned two
`stale-source → update` operations. None is counted green or repaired here.

### Что запускать

**Next:** audit-design: task:plan-audit 2026.08.02-PROVIDER-CONTRACT-LOCALE design

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | xhigh |
| Capabilities | repository-plan-read · adversarial-design-audit |
| Context | cold-start — plan-step; reviewer identity distinct from заход 6 author/auditor |
| Суть | Independently confirm the finding-free content verdict after F19–F25; execution stays closed unless literal GREEN is recorded. |
| Команда | `$ task:plan-audit 2026.08.02-PROVIDER-CONTRACT-LOCALE design` |

| Model | Thinking | Context | Суть | Команда |
|:--|:--|:--|:--|:--|
| gpt-5.6-sol | xhigh | `NEW SESSION — шаг-не-item` | Codex launch: `-C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c model_reasoning_effort="xhigh" -a never -s danger-full-access`; independent design audit only | `$ task:plan-audit 2026.08.02-PROVIDER-CONTRACT-LOCALE design` |

```text
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c model_reasoning_effort="xhigh" -a never -s danger-full-access

$ task:plan-audit 2026.08.02-PROVIDER-CONTRACT-LOCALE design

РЕЖИМ: независимый повторный design-аудит после remediation F19–F25, НЕ execution items
ВХОД: plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/plan.md → `## Audit design — 2026-08-03 (заход 6)`; brief/plan/roadmap/phases/findings/research перечитать cold
СКОУП: проверить closure F19–F25, brief→layers→spec, exact D1–D54 dynamic crosswalk contract, authorize/deferred split, typed P0 authority/checker, P6 Brain WAL/resume, 0/30 statuses; повторить conflicts/absolute+baseline lint/citations; записать GREEN|ATTENTION|RED без remediation в audit-сеансе
НЕ ТРОГАТЬ: brief intent; item statuses 0/30; remediation F1–F25; frozen archives; code/provider/fleet/Brain/generated/release state; unrelated dirty worktree
```

## Audit design — 2026-08-03 (заход 7)

**Вердикт: GREEN**
**Режим:** design; independent cold repeat after remediation F19–F25
**Попытка:** 7
**Аудитор:** frontier/xhigh route; cold Codex session configured as `gpt-5.6-sol`;
active effort is not exported by the runtime and is not presented as observed evidence
**Tree anchor:** `main` @ `d9d44245`; pre-audit input snapshot
`sha256:f3e993ac7de2cb7b8ea9ec729ceb8d506a3adc8d08dc357e70867d4627041bb3`, computed by
`LC_ALL=C find plans/2026.08.02-PROVIDER-CONTRACT-LOCALE -type f -print0 | LC_ALL=C sort -z |
xargs -0 sha256sum | sha256sum`; the plan directory is untracked in a foreign dirty worktree.

### Findings

Находок нет. Повторный cold-read не воспроизвёл F19–F25 и не выявил новых
producer/consumer, authority, recovery, roadmap или brief-coverage разрывов.

### Closure F19–F25

| Находка | Проверенный carrier | Вердикт |
|:--|:--|:--|
| F19 | D50 + 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.6 freeze exact alphabetic Harness-only `authorized_target_paths`; apply consumes the identical ordered set through `--authorize`, with missing/extra/reordered refusal fixtures. | closed |
| F20 | `roadmap.md` defines the closed `clean\|deferred-derived-only` state, verifier-owned exact ordered stale rows, cumulative union/resume binding and P4.6 terminal zero/empty/byte-stable gate. | closed |
| F21 | 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.3 names the plan-local stdlib checker, schema, tests, evidence and exact `write\|check\|verify-branch` commands; P0.4 consumes recorded checker/input/decision-row hashes. | closed |
| F22 | D51 and P0 separate `contract_freeze_decision`, conditional `containment_mutation_decision` and technical P4.6 helper authorization; no authority class is reused as ambient write permission. | closed |
| F23 | D52 + 2026.08.02-PROVIDER-CONTRACT-LOCALE P6.1 define a hash-chained WAL with append/flush/fsync/reopen verification around every public write/readback boundary, deterministic reconcile/resume/rollback and crash injection at every append/public boundary. | closed |
| F24 | 2026.08.02-PROVIDER-CONTRACT-LOCALE P5.1 `plan` may create only the named manifest/initial journal and writes no consumer/provider target; `check` changes no byte; separate delta assertions gate both. | closed |
| F25 | `findings/12-design-audit-remediation-2026-08-03.md` carries append-only scope-extension history and a distinct F19–F25 remediation section. | closed |

### Покрытие брифа

| Мысль владельца | Носитель | Вердикт |
|:--|:--|:--|
| Hub задаёт provider-neutral intent и надёжно конфигурирует Claude Code/Codex | P1 · P3 · P6 | covered |
| Канон остаётся в SKM, consumer copies не становятся runtime truth | P0 · P1 · P3 · P5 | covered |
| Legacy/drift/trust исправляются preserve-first, с preimage/rollback | P0 · P5 · P6 · P7 | covered |
| Provider adapters независимы поверх shared semantics | D5 · P1 · P3 · P7 | covered |
| Compact English — canonical source, Russian — sparse rendered overlay | P2 · P4 | covered |
| Response/plan/diagnostics locale наследуются независимо | D2/D17 · P2.1 · P4.1 · P7.2 | covered |
| Fleet claims имеют exact-set/per-file evidence; skipped/unresolved не зелёные | P0 · P5 · P6 · P7 | covered |
| Security/trust/release mutations имеют typed gates, backup и rollback | P0.3–P0.4 · P5.4 · P6.1 · P7.4 | covered |

Непокрытых product-intent мыслей и серых зон, необходимых для цели плана, не найдено.

### Проверено без находок

- **D-log:** 54 unique ordered rows, exact D1–D54. P7.4 computes the denominator dynamically
  from current Decision Log rows and rejects missing/extra/duplicate/post-crosswalk decisions;
  current explanatory carriers name D1–D54. Superseding D24/D43 retain inline
  `**Consequences:**`; no other decision supersedes an accepted D#.
- **Topology/status:** phase specs and execution-map roadmap each contain the same 30 unique
  item IDs; every one of 30 item Status fields and 30 Phase Status rows is `⬜ Not started`;
  the eight Status Board rows remain 0/30 in aggregate. Routing covers the same set; every item
  remains manual/solo with its dependency or review reason stated.
- **P4 authorization/deferred split:** cumulative generated-target union is distinct from the
  alphabetic Harness writable subset. Only P4.3–P4.6 freshness rows may enter
  `deferred-derived-only`; semantic, test, link, launch and other errors cannot defer. Terminal
  P4.6 requires every named command 0, an empty deferred set and byte-stable second owner runs.
- **P0 authority/checker:** the named P0.3 checker hashes itself and all frozen inputs, parses and
  hashes the exact Decision Log row, verifies the expected typed decision and supports both
  action/no-op branches from explicit commands. P4.6 consumes neither P0 authority type.
- **P6 WAL/resume:** results derive only from terminal WAL state. Exact postimage receives a
  fresh readback before acceptance; exact preimage records `rolled-back`; recognized partial or
  failed state triggers whole-Brain rollback; third state, torn chain, missing backup or source
  drift refuses before write.
- **Layers/roadmap/DoR:** non-empty brief, 12 indexed findings and 9 indexed research documents
  link through Inputs/Required Reads/D-log; there are no live clarification or skeleton markers.
  `Design Passes: 3/3`, three distinct Design pass Update Log carriers and journal actor
  provenance remain present. Exported/consumed contracts and sequential P0→P7 dependencies agree.
- **Scope safety:** this audit changed no remediation text, item/status field, archive, package
  code, provider/fleet/Brain state, generated/release carrier or unrelated dirty-worktree path.

### Executable evidence

- `bash packages/task/scripts/validate.sh` — **479 tests, OK**, final `validate: OK`; its aggregate
  archive scan reports only pre-existing out-of-scope warnings and ends with conflict scan 0/0.
- `python3 packages/task/scripts/plan-lint.py --conflicts` — **0 mismatches / 0 warnings**.
- `python3 packages/task/scripts/plan-lint.py
  plans/2026.08.02-PROVIDER-CONTRACT-LOCALE` — **0 errors / 0 warnings** on `d9d44245`.
- The same lint with `--baseline HEAD` — **0 errors / 1 warning** on `d9d44245`: the plan directory
  is untracked and unavailable to `git archive HEAD`, so baseline delta attribution is not
  computed and is not reported as green.
- `python3 plans/verify-citations.py
  plans/2026.08.02-PROVIDER-CONTRACT-LOCALE --strict` — **12 citations / 26 known exceptions /
  0 findings**.
- Independent invariant check — **30/30 unique phase/roadmap item IDs with empty set difference;
  30/30 Not started item fields; 30/30 Not started Phase Status rows; 8 zero Status Board rows;
  54/54 unique ordered D1–D54; 0 live clarification markers; 0 skeleton markers**.

### Verification footer and environment disclosures

- **RAG:** not invoked. No new external fact class is decision-bearing for this repeat; closure
  F19–F25 and the GREEN verdict are repository/plan-grounded. Existing external provenance remains
  cited and strict-citation-checked, but was not re-presented as freshly verified.
- **Unverified verdict dependencies:** none. The active-effort value is unobservable and disclosed,
  not used as a product/design fact.
- **Preflight:** `codex doctor --json` reports configured `gpt-5.6-sol`, overall `ok`, approval
  `Never`, unrestricted filesystem and network enabled; it does not export active effort.
  `packages/maind/bin/maind health --cwd --strict --json` passed with memory roundtrip/provider
  trust green; `packages/harness/bin/harness doctor --provider-audit --json` returned `[]`.
- **Known environment defects:** the relative Harness hook dry-run still exits 1 with
  `ValueError: root must be explicit and absolute`; the absolute-path control exits 0 and reports
  the two already assigned `stale-source → update` operations. The plan remains untracked in a broad
  foreign dirty worktree, so baseline attribution is unavailable. None was repaired or counted green.
- **Audit-command workaround:** the first aggregate invariant command used `rg -h`, which this
  environment interprets as help, and a corrected intermediate run exited before output on an
  over-narrow Phase Status regex. Neither failed run is evidence; the final explicit
  `--no-filename`/section-bounded check produced the counts above.

### Что запускать

**Next:** manual: implementation/high

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | repository-plan-edit · fleet-evidence-capture · provider-health-read |
| Context | same-session — item |
| Суть | Execute only 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.1: capture and seal the read-only provider/fleet baseline before classification or repair. |
| Команда | — |

| Model | Thinking | Context | Суть | Команда |
|:--|:--|:--|:--|:--|
| gpt-5.6-terra | high | `same-session — item` | Codex launch: `-C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c model_reasoning_effort="high" -a never -s danger-full-access`; P0.1 only | — |

```text
Execute 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.1 under task:plan-run semantics. Start from the committed handoff inputs in plan.md, roadmap.md and phases/P0.md, read every P0.1 Required Read, and produce only the plan-local privacy-minimized read-only fleet/provider baseline carriers named by P0.1. Preserve the foreign dirty worktree; do not classify or repair anything, mutate consumer/provider/Brain state, expose secrets or absolute consumer roots, or start P0.2. Treat the relative hook dry-run failure and any other command failure as non-green evidence, then close P0.1 only through its exact Validation and plan-protocol bookkeeping.
```
