# Lean multi-provider skills design — 2026-08-10

## Design verdict

The existing eight-phase/30-item plan remains the single skills/control-plane plan. Its provider,
locale, fleet and release sequence is still useful, but the skill contract and validation method
must be modernized before corpus migration. No phase or item is added: P0/P1/P2 freeze evidence and
contracts, P3 implements provider/audit seams, P4 migrates only admitted corpus, P6 measures live
health, and P7 proves outcomes on real providers before deterministic regression hardening.

Part I of the audit is a verified reference input to `2026.08.03-ARTIFEX-SUPERVISOR`. This plan
shares only stable boundaries with it: provider-neutral task/handoff payloads, workspace identity,
evidence references and package capability requirements. It does not copy Temporal, worktree or
supervisor runtime into Skiller.

## 1. Minimum sufficient Skill Core

The canonical skill owns observable meaning, not provider mechanics:

| Field | Shared meaning |
|:--|:--|
| identity/job | one stable capability ID and one concrete job |
| trigger boundary | positive intent, near-miss/negative boundary, and explicit-only intent when risk requires it |
| inputs/outputs | data/artifacts required and produced; no provider path |
| invariants/risk | only non-obvious safety, product and domain constraints; `read|draft|write|external` remains semantic |
| capabilities | required tools/features expressed by stable IDs, with no assumption that every provider supports them |
| workflow | shortest imperative sequence that materially changes outcomes |
| resources | one-level links to references/scripts/assets loaded or executed only when needed |
| provenance | local/upstream source identity and refresh policy |

Generic model behavior, broad style advice, repeated verification reminders, exhaustive examples
and provider-specific frontmatter do not belong in the shared body. An instruction stays only when
official provider requirements, a repository invariant, an observed failure or an ablation result
justifies it. High-stakes constraints are concise and explicit.

`Failure modes` is optional and evidence-backed. Empty boilerplate or a mandatory `Gotchas`
heading would recreate the context tax this redesign is meant to remove.

## 2. Additive provider adapters

Each provider adapter consumes an immutable Skill Core and owns only these projections:

| Seam | Claude Code | Codex | Third provider contract |
|:--|:--|:--|:--|
| discovery | Claude-native metadata/listing behavior | Codex metadata/path listing | renderer declares discovery unit, budget and degradation semantics |
| invocation | Claude explicit/model invocation controls | `agents/openai.yaml` policy and Codex invocation controls | maps shared invocation intent or reports unsupported |
| layout | Claude plugin/skill paths | `.agents/skills`/plugin bootstrap paths | declares owned target roots; cannot write another adapter's roots |
| capability | native supported/degraded/unsupported state | native supported/degraded/unsupported state | versioned capability descriptor with explicit fallback/refusal |
| measurement | Claude token counter/live context probe when available | Codex listing/trace/usage observation when available | typed meter with unit, lower/upper bounds, source and observation version |
| replay | Claude CLI/model-tier scenarios | Codex CLI/model/effort scenarios | provider fixture names executable and unavailable/skip semantics |

Adding provider C means adding one descriptor, renderer, invocation mapping, measurement adapter,
replay fixture set and conformance rows. Existing provider adapters and canonical bodies are not
edited unless the shared semantic contract itself changes through a new decision.

## 3. Evidence-led development loop

The acceptance hierarchy is deliberately asymmetric:

1. official documentation/specification defines the expected contract and current provider limits;
2. a real representative task establishes the no-skill baseline;
3. the minimum Skill Core is replayed on Claude Code and Codex;
4. provider-tuned adapters are replayed against the same task and negative trigger prompts;
5. ablation removes each suspect instruction/example/section; retain it only when outcome,
   trigger precision, safety or scope control worsens;
6. deterministic unit/schema/golden/generator tests lock the accepted compiler and artifact shape.

Required scenario families include positive trigger, near-miss negative trigger, explicit
invocation, no-skill baseline, minimal-core, provider-tuned, high-stakes boundary, unsupported
capability and realistic end-to-end repository outcome. Metrics stay provider-qualified:
task success, trigger precision/recall, unnecessary actions, scope drift, user corrections,
tokens/characters/latency with measurement class, and reproducibility. One aggregate score may
not hide a failed provider or mix incompatible units.

Synthetic fixtures are valuable for parsers, graph algorithms, typed failures, generators and
known regressions. They cannot prove that a live provider discovers, invokes or follows a skill.

## 4. Audit architecture

The redesigned audit has three layers:

```text
observations -> independent signals -> evidence-backed recommendation
```

Observations are typed facts: source/publication class, discovery metadata, body/reference weight,
overlap edge, connected component, direct trigger trace, residency window, dependency state,
provider listing state, exact/estimated measurement class and provenance freshness.

Signals are multi-label: `overlap-edge`, `overlap-cluster`, `large-body`, `listing-pressure`,
`resident-unobserved`, `directly-used`, `source-only`, `generated-projection`, `dependency-broken`,
`provider-degraded`, `measurement-uncertain`. No precedence discards another signal.

Recommendations are separate and may be `keep`, `thin`, `merge`, `split`, `reclassify`, `repair`,
`retire`, or `insufficient-evidence`. They carry supporting/contradicting evidence and required
next replay. Lexical Jaccard is one cheap edge producer, never a semantic verdict. Connected
components expose clusters. Private source-only canons are audited against their class policy;
generated projections are checked only against their generator.

`resolve_active_set` returns typed domain failures to library callers; only CLI boundaries convert
them to process exits. Batch reports preserve one broken project as a row and continue. Repeated
dependency warnings are deduplicated while retaining affected profiles.

Measurements carry `provider`, `model/version`, `unit`, `value|lower|upper|unknown`, `method`,
`observed_at`, `expires_at`, and `confidence`. Anthropic's token counter is still an estimate; near
thresholds require headroom and real replay. Claude token units and Codex character/listing units
never enter one arithmetic total.

## 5. Corpus decisions

- Vue/Pinia/Vitest clusters are candidates, not pre-approved merges. Compare triggers, source class,
  project-specific delta and outcome replays before a topology decision.
- Broad `*-super-skill` navigators with granular alternatives face a removal/retrieval-only
  presumption; sole domain entry points may remain if a cross-cutting real task benefits.
- Descriptions front-load job, trigger and negative boundary. Glossaries and implementation detail
  move to the body/reference.
- A singleton bucket may remain when it is a real distribution, ownership or project-scope unit.
  Otherwise consolidate only after provider listing/profile replay proves a benefit.
- One canonical template generates the distributed generator copy. Shared template fields contain
  no Claude/Codex controls; adapters render them.
- Upstream content remains faithful. Local provider guidance wraps or projects it rather than
  rewriting vendor material without provenance.

## 6. Mapping onto the existing 30 items

| Existing item | Added responsibility |
|:--|:--|
| P0.1 | seal current corpus/topology/audit/profile measurements, typed uncertainty and real provider availability |
| P1.2 | freeze Skill Core, provider capability/adapter seams, invocation intent and third-provider onboarding |
| P2.3 | freeze minimum-instruction, progressive-disclosure, failure-mode and eval/ablation authoring rules |
| P3.2 | implement additive Claude/Codex projection/invocation adapters and generic provider registration |
| P3.3 | implement multi-label audit graph, typed resolver errors, longitudinal/provider evidence and deduplicated diagnostics |
| P4.2 | make one canonical template/generator and enforce shared cross-field semantics without provider leakage |
| P4.3 | perform evidence-admitted corpus consolidation/thinning/reclassification in bounded review batches |
| P6.2 | expose per-provider discovery/context health, uncertainty, drift probes and accepted degradation |
| P7.1 | execute real no-skill/minimal/provider-tuned scenario matrix and instruction ablations |
| P7.2 | harden accepted behavior with deterministic unit/golden/generator regressions; never substitute them for P7.1 |
| P7.4 | cold-audit every audit claim, provider row, ablation decision and dynamic D-record exact set |

## 7. Completion conditions

The programme is release-green only when:

- every original audit claim has a current verdict and evidence path;
- the shared Skill Core contains no provider-specific control and both adapters preserve its meaning;
- a documented third-provider fixture can be added without modifying Claude/Codex adapters;
- all shipped profiles have explicit Claude/Codex listing outcomes and no repeated hidden dependency
  failures; over-budget profiles are narrowed or carry an owner-approved degradation with replay;
- every corpus merge/removal/thinning decision cites official constraints where applicable, real
  provider scenarios, baseline/ablation outcome and deterministic regression coverage;
- generated templates/projections are byte-stable and drift checks are green;
- unavailable live providers, skipped replays and uncertain measurements remain non-green or
  explicitly degraded—never silently converted to success.
