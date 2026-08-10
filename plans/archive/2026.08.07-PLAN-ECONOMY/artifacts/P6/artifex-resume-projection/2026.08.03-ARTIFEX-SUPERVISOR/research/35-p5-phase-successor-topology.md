# P5 phase-wide additive successor topology

## Inputs

- `brief/23-p5.2-frozen-contract-reconciliation.md` and
  `brief/24-p5-phase-successor-authorization.md` — owner boundary and whole-phase requirement.
- `findings/P5.2-terminal-g2-native-capability-conflict-2026-08-05.md` and
  `findings/P5-successor-provider-surface-2026-08-05.md` — frozen/runtime/provider facts.
- `research/34-p5.2-frozen-successor-decision.md` — D107 additive-only decision.
- Terminal P5.1 D105 catalog/request/grant/admission carriers and terminal P4.8 G2 evidence.

## Coupling hotspot and rejected layouts

The hotspot is one package generation consumed by four downstream boundaries: live repository
pilot, recovery/provider-failure pilot, economic adjudication and P6 productization. The previous
spec left that generation as a nameless “future input” inside P5.2, so it had no owner, no Files,
no acceptance command and no terminal artifact for P5.3/P5.4/P6 to pin.

1. Renumber P5.2–P5.4 and insert the producer numerically — rejected: all 14 terminal D105
   admissions hash-bind the existing parent item IDs.
2. Build the successor and execute the live pilot in one P5.2 commit — rejected: contract/runtime
   failure could be hidden by pilot logic, provider readiness would consume business evidence, and
   downstream items would still lack a stable generation boundary.
3. Add compatibility slot P5.5 and execute it before P5.2 — selected. Item numbering remains an
   immutable evidence identifier; roadmap order remains the execution carrier.

RAG:— (repo-grounded: D105–D107, terminal P5.1 carriers and plan-protocol phase/coupling rules).

## Reconciled producer chain

`P5.1 terminal frozen carriers → P5.5 G2B successor → P5.2 exact three-slice pilot → P5.3
recovery/provider-failure pilot → P5.4 G3 GO/NO-GO → P6.1 productization freeze`.

P5.5 is the only new producer. It creates:

- additive `root/contracts/business-dispatch-admission-v1.md` without editing
  `dispatch-admission-v1@1.0.0`;
- package-owned business loader/security/activity/CLI/provider mappings while preserving the old
  smoke entry point and its negative behavior;
- `provider-business-projection-v1.json` pinned to Codex `0.146.0` and Claude Code `2.1.222`;
- `business-successor-generation-v1.json` naming G2 as immutable predecessor and G2B as the new
  exact package digest;
- `business-successor-assurance-v1.json` plus an independent validator covering contract,
  runtime, provider and predecessor invariants.

Two bounded disposable capability probes (one per provider) are successor assurance, not P5
business pilots: they use no D105 admission, create no business intent/usage and cannot satisfy
P5.2/P5.3/P5.4 acceptance. Any provider version drift, unenforceable permission mapping, original
smoke regression, P4 evidence mutation or nonzero D105 usage keeps P5.5 non-terminal.

## Downstream contract

- P5.2–P5.4 consume the same terminal P5.5 generation/assurance/contract/provider manifest and
  rerun its independent validator before their first provider call.
- D105 task/grant/admission bytes and parent item IDs remain unchanged; G2 stays a required
  negative predecessor, never a business runtime. Their frozen `g2_package_digest` is accepted
  only when it equals the G2 predecessor named by D108 and the executing package independently
  equals the one G2B successor digest; this is a two-link projection, not an admission rewrite.
- P5.4 G3 pins unchanged G2B bytes, not G2.
- P6.1 consumes G1→G2→G2B→G3 and protects G2B runtime rows during G4 integration. Historical
  G1/G2 records and any later terminal G3 record are never regenerated against successor bytes.
- D108 does not extend the D105 `2026-08-12T23:59:59Z` expiry or its 14-dispatch ceiling. Every
  pilot item checks expiry before intent; expiry closes execution until a new explicit owner
  carrier and additive forward item exist, never until a local refresh of P5.1 bytes.

This medium-batch reconcile has one stop criterion: zero downstream reference treating G2 as
business-capable, and every named P5.5 output has exactly one producer before all consumers.

## Ecosystem-core pre-mortem

| Failure after 6–12 months | Early signal | Mitigation | Owner |
|:--|:--|:--|:--|
| G2 is silently widened and old assurance becomes false | original smoke negatives become positive or P4 paths change | byte-preserve P4, keep smoke module/entry point, explicit G2→G2B predecessor tests | P5.5 |
| Provider upgrade bypasses the frozen mapping | local version differs from provider manifest | exact version gate; mismatch refuses before intent and returns to plan-design | P5.5/P5.2 |
| “Capability smoke” spends a D105 trial | admission usage or business intent changes | separate two-root probe grant; assert all 14 usage rows remain zero | P5.5 |
| Later pilot reads G2 directly | Required Reads/validator lacks G2B artifacts | all P5.2–P5.4 and P6 producer/consumer checks name the same G2B files | P5 phase/P6.1 |
| Non-numeric execution order is normalized away | roadmap launches P5.2 before P5.5 | D109 freezes P5.5 compatibility slot and handoff launches only P5.5 | plan-close/audit |
| D105 expires midway through the phase | wall clock reaches 2026-08-12 or any admission says expired | pre-intent expiry gate; pause for a new owner carrier/additive item, never regenerate P5.1 locally | P5.2–P5.4/owner |

## Проверка (verification status)

- RAG: existing first-party Codex/Claude documentation evidence ×2 findings; current local
  version/help ×2 providers; repository code/carrier/preflight reads — OK.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: actual safe business-write behavior is intentionally not
  claimed by design; P5.5 must prove it with its bounded provider assurance before terminality.
- Обходки/[POSSIBLE-DEFECT]: no workaround accepted; item-order compatibility slot P5.5 is an
  explicit preservation mechanism for frozen D105 IDs, not a bypass.
