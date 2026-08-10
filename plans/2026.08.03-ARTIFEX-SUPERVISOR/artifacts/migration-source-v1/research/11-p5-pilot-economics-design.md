# P5 design: measured pilots and independent economics

## Sources and execution gate

This synthesis uses `findings/09-p5-pilot-economy-recon-2026-08-03.md`,
`findings/08-p4-recovery-security-recon-2026-08-03.md`, `research/00-user-intent.md`,
`research/04-token-economy-and-acceptance.md`, `research/10-p4-assurance-design.md`, the archived
FOREMAN and AGENT-RELIABILITY carriers named below, and the detailed P0–P4 phase specifications.
P5 execution is forbidden until P4 is terminal, `validate-assurance.py` returns exact green on the
terminal candidate hashes, and all P0/P1 contracts and baselines still validate. Planned producers
are preconditions, not facts already obtained. RAG:— (repo-grounded plan state).

## Sequential evidence ladder

| Item | Evidence class | Produces | What it cannot prove |
|:--|:--|:--|:--|
| P5.1 | archived/recomputed shadow | frozen trial catalog, mapping and shadow results | live provider, write isolation or economics |
| P5.2 | real reversible repository pilot | exactly three accepted/refused slices and rollback evidence | crash recovery breadth or N=5 economics |
| P5.3 | controlled recovery pilot | crash/resume/duplicate/provider-failure results | economic GO |
| P5.4 | five non-synthetic paired waves | independent matched metrics and one GO/NO-GO verdict | universal product performance |

The ladder cannot be skipped. A later item reruns every upstream validator and pins its manifest
hash. Failure does not cause a post-hoc case, baseline, provider or threshold replacement; it emits
the exact failed floor and stops or returns NO-GO.

## P5.1 trial freeze and archive shadow

Before any candidate pilot, P5.1 writes `trial-catalog-v1.json`. Each row pins a stable trial ID,
source plan/item/case, Git base, plan/source/contract/acceptance hashes, provider/model/effort,
required capabilities, exact Files/validation, baseline lane/evidence class and order. It contains:

1. FOREMAN run-folder/policy/terminal cases mapped explicitly to the current P1 contracts; the
   obsolete historical parser contract is reference provenance only.
2. AGENT-RELIABILITY state-transition and reliability-bank cases, including positive controls and
   the `owner_question = unmappable` precedent.
3. one exact three-slice repository pilot for P5.2;
4. one exact recovery/provider-failure pilot for P5.3;
5. exactly five real paired battle waves for P5.4, selected from repository tasks before candidate
   execution and each bound to an eligible measured incumbent lane.

The shadow validator recomputes archive hashes and expected actions through the frozen current
contracts. It does not import archived Python, mutate an archive or call a provider. A mapping gap
is a named refusal; expected results are not derived from candidate output.

## P5.2 reversible three-slice repository pilot

P5.2 uses a thin measurement harness that repeatedly invokes the candidate's public one-slice CLI.
The harness owns no run state and makes no transition/authority decision: after each invocation it
reads only the closed result code and either invokes the next ready slice or stops on terminal/OWNER.
This preserves P3's `--max-slices 1` safety boundary and avoids changing the P4-assured candidate
before live evidence.

Exactly three predeclared real repository slices run sequentially in an identity-locked disposable
worktree/controlled repository at the frozen base. Each worker is a fresh process. The complete
delta is checked against Files, frozen validation is run, integration is serialized inside the
controlled target, and final rollback reproduces the exact base. The owner's dirty worktree is
never a pilot target. Result evidence contains identities, hashes, counts, provider usage with
unknown reasons and acceptance refs, never raw prompts/transcripts/tool payloads/environment values.

## P5.3 recovery pilot on the live path

P5.3 reuses the exact P5.2 task/base and P4 cut identities. It covers crash after durable intent,
after provider observation and before acceptance; duplicate dispatch/result; verified and
unverified process death; timeout/overflow/schema/provider refusal; exact postimage acceptance;
no-effect bounded retry; recognized-partial whole-slice rollback; and third-state OWNER. Provider
failure is induced with the P3 fake-binary seam or a naturally observed closed failure—never by
breaking credentials, forcing quota or widening permissions. No fault/recovery result counts toward
the five economic waves.

The independent validator checks the strict journal, external call canary, exact filesystem/process
postimage, attempt budget and P4 matrix row. It refuses a rerun of unknown intent and refuses any
candidate repair that changes a frozen P0/P1/P4 expected result without a D#/re-audit.

## P5.4 five paired battle waves and verdict

Each of exactly five catalogued non-synthetic waves runs candidate and incumbent on separate clean
controlled roots at the same base, task bundle, acceptance hash, provider/model/effort and capability
set. The order is frozen before execution and adjacent in time. An incumbent row must be either a
live paired manual/Workflow/`harness run` lane or a P0 measured row with exact matching hashes;
`synthetic`, `baseline_pending`, unmatched or unknown-critical rows are ineligible.

Metrics are recomputed over all attempts and coordinator overhead:

- tokens per accepted slice, with each observed input/cache/output/reasoning component retained;
- provider-reported or P0-pinned cost, never a remembered/current price constant;
- owner decision requests divided by dispatched non-synthetic slices;
- retry amplification, rollback/orphan/validation counts, wall time and return-envelope size;
- per-provider completeness and explicit `unknown_reason` for every absent field.

GO is legal only when every P0–P4 reliability/recovery/security floor is still green and a D14
economic branch validates byte-for-byte. Both providers must have an eligible live wave unless a
separate Owner D# approved a single-provider product scope before adjudication; otherwise parity is
NO-GO. A reliable but uneconomic, economical but unsafe, unmatched, N<5 or unknown-critical result
is NO-GO. The validator emits exactly one verdict and the failing floor/branch; the candidate's own
summary is evidence input, never authority.

## Orchestration boundary

P5 items are sequential and manually routed: P5.1 freezes the complete trial set, P5.2 consumes it,
P5.3 consumes the exact pilot, and P5.4 consumes all prior evidence. The phase therefore has no
three-item independent fan-out. The autonomous activity inside P5.2/P5.4 is the Artifex candidate
being measured, invoked through its durable one-slice public boundary; wrapping it in a Workflow
would add a second coordinator and contaminate the comparator. No plan-protocol workflow is declared.
RAG:— (repo-grounded dependency graph and owner brief).

## Ecosystem-core pre-mortem

| Failure after 6–12 months | Early signal | Mitigation | Owner |
|:--|:--|:--|:--|
| Easy tasks are selected after seeing candidate output | catalog or order timestamp/hash follows first candidate event | freeze exact trials/bases/lanes before any candidate call | P5.1 |
| Archive replay passes by copying stale parser semantics | archived code imported or current contract hash absent | explicit mapping, data-only archive reads and current-contract validator | P5.1 |
| Measurement harness becomes a second scheduler | harness stores transitions or interprets prose | stateless loop over closed one-slice result codes; candidate journal remains authority | P5.2 |
| Pilot mutates owner/foreign work | main-tree delta or worktree identity mismatch | controlled disposable roots, exact inventory and rollback-to-base proof | P5.2 |
| Recovery pilot reruns an unknown external call | call canary increments twice or no pre/postimage | P4 cut IDs, strict replay and OWNER on third state | P5.3 |
| Provider failure test damages auth/quota | credential/config change or forced billing side effect | fake-binary seam/natural failure only; no credential or quota manipulation | P5.3 |
| Candidate looks cheap because retries/coordinator were omitted | independent totals differ from journal attempts | recompute every component from strict replay and provider evidence | P5.4 |
| Missing owner channel is read as zero interventions | no proven event mapping but ratio is numeric | unknown blocks GO, preserving the AGENT-RELIABILITY precedent | P5.4 |
| One provider masks the other | absent eligible provider wave or pooled completeness | per-provider rows; parity or prior Owner single-provider D# | P5.4 |
| N=5 is marketed as universal proof | P6 removes opt-in/telemetry/circuit breaker | classify GO as productization evidence only; keep experimental rollout guards | P5.4/P6 |

## Stop condition and verification status

P5 is ready when all four items have finite files/reads, immutable producer order, exact independent
validators, explicit unknown/parity/hook handling and legal manual routes. Execution remains closed
until terminal P4 exact green. Actual P5 GO additionally requires five eligible paired waves and no
failed or unknown critical floor.

- RAG: current official Codex accounting JSONL via official manual helper; current Claude structured
  usage/cost surfaces via Context7 first-party docs; repository/archive donors read directly.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: installed terminal provider envelopes, matched tasks/baselines,
  real pilots, recovery outcomes, owner-channel observability and economic verdict remain P0–P5
  execution evidence.
- Обходки/[POSSIBLE-DEFECT]: none accepted; the current hook `stale-source` warning remains a hard
  readiness failure and no price/token field is synthesized.
