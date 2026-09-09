# P6 research — measured Codex context economy

**Date:** 2026-09-09
**Fact classes:** instruction discovery/precedence, skill discovery/disclosure, explicit versus
implicit invocation, non-interactive JSONL/usage, evaluation design.
**Source policy:** official OpenAI documentation only; Context7 `/openai/codex` first, then
Perplexity official-domain synthesis and direct URL cross-check.

## Verified external facts

RAG:✅ 2026-09-09.

- Codex discovers project instructions from the repository root toward the current working
  directory, with deeper files taking precedence; combined project instruction discovery has a
  default 32 KiB cap. Source: <https://developers.openai.com/codex/agent-configuration/agents-md>.
- Skills use progressive disclosure: startup context carries metadata and the full body is loaded
  when used. The initial listing budget is proportional to context and falls back to 8,000
  characters when the context window is unknown; descriptions may be shortened and skills omitted
  when over budget. Explicit `$skill` invocation remains a distinct test surface from implicit
  selection. Source: <https://developers.openai.com/codex/build-skills>.
- `codex exec --json` emits JSONL events and final usage suitable for machine capture. `--ephemeral`
  suppresses persisted rollout files; `--ignore-user-config` skips user configuration/auth loading
  behavior described by the CLI, but neither flag alone establishes a clean-room source set.
  Source: <https://developers.openai.com/codex/non-interactive-mode>.
- Official skill-evaluation guidance favors small representative suites with positive and negative
  controls and comparing behavior/cost rather than optimizing prose size alone. Sources:
  <https://developers.openai.com/blog/eval-skills> and
  <https://developers.openai.com/codex/learn/best-practices>.

No official source found in this pass establishes that blanket deletion of skills or instruction
text improves task quality. That remains a repository hypothesis requiring native measurement.

## Experiment synthesis

The smallest discriminating corpus is twelve cases: four instruction-retention positives, three
implicit-skill positives, their three explicit `$skill` mirrors, and two near-miss controls. Five
arms cover current baseline, no relevant skill, explicit skill, implicit skill and one frozen
AGENTS/provider-delivery candidate. Three repetitions establish the initial matched sample; five
are allowed only for a valid borderline result. Invalid observations never become zero-cost data.

Primary acceptance is behavioral: every mandatory invariant must pass on every admitted run.
Cost is secondary and robust to observed run variation. D11 therefore subtracts the larger MAD
from the median token difference before applying the existing D3 threshold. Optional quality is a
vector so an aggregate cannot hide a case regression; restart and wall-time gates remain separate.

## Pre-mortem

| Failure mode | Early signal | Mitigation / stop rule |
|:--|:--|:--|
| Hidden sources make arms incomparable | source/plugin digest differs between paired runs | invalidate the pair; re-inventory, do not normalize it away |
| Provider nondeterminism fabricates a saving | token result sits inside dispersion | expand matched sides to five only under the frozen borderline rule; otherwise retain |
| Smaller context loses a rare invariant | any mandatory assertion fails | immediate no-change for that candidate; no averaging |
| Explicit invocation biases implicit comparison | explicit and implicit cases are not paired | schema rejects the corpus before calls |
| Resume mixes configurations | case/source/argv digest mismatch | fail before provider invocation and require a new output directory |
| Generated files drift from canonical owners | output diff has no canonical-input provenance | fail P6.4; regenerate through the owner or revert |
| Tuning becomes an unbounded search | request for a second candidate | stop P6.3 and record a later measured hypothesis in `roadmap/` |

## Verification record

Context7 queries covered all named fact classes for `/openai/codex`. Perplexity retrieval was
restricted to official OpenAI sources, and the URLs above were directly opened on 2026-09-09.
Repository observations and exact CLI help are recorded separately in
`findings/07-p6-design-baseline.md`; external documentation is not evidence that the local runtime
actually loaded a source.

Finish reconciliation repeated instruction discovery, catalog budgeting, explicit/implicit skill
invocation and non-interactive JSONL/ephemeral semantics through Context7 and official-source
Perplexity on 2026-09-09. The re-pass confirmed the design premises and left runtime source loading
as P6.1 measurement rather than upgrading documentation into local evidence; see
`findings/08-finish-external-verification.md`.
