# P0 evidence-freeze design

## Purpose

P0 is a sequential evidence and policy freeze. It does not implement the supervisor. Its five
items turn owner intent, live execution carriers, provider probes and failure assumptions into a
validated bundle that P1 can convert into frozen contracts without reopening baseline choices.

Sources: `brief/00-brief.md`, `brief/01-refinements.md`, `findings/00-repo-recon-2026-08-03.md`,
`findings/01-external-agent-runtime-2026-08-03.md`,
`findings/03-preflight-2026-08-03.md`,
`findings/04-p0-design-verification-2026-08-03.md`, and `research/00`–`04`.

## Producer/consumer chain

| Item | Produces | Consumed by |
|:--|:--|:--|
| P0.1 | matched baseline policy, candidate catalog, honest unknowns, live-driver reuse/gap row | P0.5, P1.1, P1.5, P5.1–P5.4 |
| P0.2 | owner mandate input, precedence table and executable authority cases | P0.4, P0.5, P1.2–P1.4, P2.3 |
| P0.3 | current Codex/Claude capability and accounting matrix from bounded probes | P0.4, P0.5, P1.4–P1.5, P3.1–P3.4 |
| P0.4 | threat model, operating envelope, pre-mortem and failure/abuse cases | P0.5, P1.1–P1.4, P4.1–P4.5 |
| P0.5 | frozen acceptance rubric, executable verdict cases and P0→P1 crosswalk | every P1 item and P5 adjudication |

## Execution order and orchestration

The items are intentionally coupled: the rubric depends on the measured baselines, authority
cases, provider matrix and threat model. All five are manual high-effort evidence/design work;
none may be delegated to the existing `harness run` driver, whose driving right is limited to
literal `Exec = plan-exec`. P0 therefore does not meet the plan-protocol orchestration criterion:
it is a sequential series, not three independent deterministic slices and not a long autonomous
external-state chain.

## Artifact discipline

Every item emits a human-readable decision/evidence document, a normalized JSON carrier and a
small stdlib verifier. Raw transcripts, prompts, chain-of-thought, credentials and environment
dumps are excluded. Missing measurements use `unknown` plus `unknown_reason`; zero is never used
as an imputation. Provider raw streams may exist only in a permission-restricted temporary
directory while P0.3 minimizes them.

## P0 stop condition

P0 is executable when every item has finite reads/files, deterministic validation and an exact
failure behavior. P0 is complete only when P0.5 proves the producer/consumer crosswalk and all
P0 artifacts validate. A missing numeric baseline does not falsify the evidence-freeze item; it
remains `baseline_pending` and later blocks any economic GO branch that depends on it.

RAG:— (author synthesis from the cited owner, repository and verified findings).
