# P1 measurement contract — 2026-09-20

## Purpose and unit

This contract is the single reducer for P2–P4. A measurement unit is one matched `A/B` task pair. `A` is the current baseline; `B` changes exactly one declared mechanism. P5 repeats the same pair definition before/after a retained slice. The programme seeks a practical engineering decision, not statistical generalization.

## Frozen corpus (maximum six task classes)

Each task starts from the named parent commit in a clean temporary worktree. The evaluator freezes a prompt from the target commit subject and declared outcome, withholds the target patch, and uses the target diff/tests only as an acceptance oracle. A later phase may select fewer tasks but may not substitute a new class after observing outcomes.

| Corpus ID / class | Start commit | Target evidence | Frozen task intent and acceptance oracle |
|:--|:--|:--|:--|
| T1 narrow fix | `559026fd7e3e6555bcee3915feb27f303f7b8f5c` | `e430beaf50e25967075807dfb19db937300f3536` | Fix raw-vendor hygiene and exclude maind-managed entries from name duplicates; affected Skiller tests plus target behavioral diff |
| T2 ordinary implementation | `1dfd703f26cf142fb547a89f7f371c8568f1bd14` | `f116cb9d62c54fd0d5114930dff5cb88b6d02551` | Add codegraph/run-report telemetry for Codex/Cursor; affected core/harness/maind tests plus target behaviors |
| T3 review/audit | `8a86f55e531caf5dcbd155dc383b2016492ad55a` | `3a6b4b70cab86ce676a0533515733ef2e75663cc` | Audit the recorded P1 plan state and freeze only demonstrated findings; plan evidence, lint and target audit disposition |
| T4 environment/provider fix | `bdf43d98297188497f9c87d86405665509a2fc03` | `eb038b2838bcd8b5407785eecbbb6197b9a60ad4` | Remove Perplexity API MCP and close fleet-sync tails; config generators/checks and affected package tests |
| T5 research/design | `7db3a9008ae624fe92cd497ff08021d075194937` | `355dcbde1b9fdce2f7c7d5e0010ec8a8e4b6cb9f` | Freeze the third-provider Cursor design from the recorded evidence; design carriers, citations and declared decision boundaries |
| T6 durable plan closure | `33d93220a3246a266fcaeb4ab030e891a02e92d5` | `39b0349058d412b321ceb367e1d4901b3f80b330` | Close the recorded P5 fleet-delivery item using its existing plan contract; plan lint/views/citations and target terminal state |

Before a run, record the full resolved SHAs, exact prompt hash, acceptance commands, selected corpus IDs and why the class exercises the mechanism. If a target commit or acceptance command is unavailable, that task is ineligible rather than silently replaced.

## A/B controls and run record

Both arms use the same start commit, prompt bytes, provider/model/effort, tools and tool permissions, sandbox/approval policy, timeout, environment variables, dependency cache, network policy, repository instructions, and acceptance commands. Use separate clean worktrees from the same object database. Alternate order `AB`, then `BA` across pairs. Do not reuse conversation context between arms.

Every arm records: pair/run ID, timestamps and monotonic wall time (elapsed seconds); start/end HEAD and status hash; prompt/config/mechanism digests; provider/model/effort; exit/outcome; acceptance commands; input/output tokens where the provider reports them; tool calls and file/content reads; owner interruptions; instruction violations; unrelated writes; mechanism activations and false activations; recovery events; and a usefulness anchor with evidence.

Usefulness is an anchored ordinal observation, not a substitute for acceptance: `0` no usable contribution, `1` relevant but no avoided work, `2` avoids at least one wrong turn/read with correct provenance, `3` necessary to locate/complete an accepted result. Recovery is successful only when the run returns to the declared task without owner intervention or an unrelated write.

## Metrics

Primary outcome is binary acceptance: all frozen behavioral checks pass and no required behavior is missing. Guardrails are zero new instruction violations, zero unrelated writes, no security/public/provider-parity regression, and no additional owner interruption. Efficiency metrics are elapsed time, observable input/output tokens, tool calls and content reads. Activation metrics are eligible activations, false activations and missed required activations. Missing provider metrics are `n/a`; they neither pass nor fail an effect threshold.

A metric delta is `(B - A) / A`; for costs, negative is improvement. If `A=0`, use the absolute difference and do not report a percentage. Predeclare one primary efficiency metric for each candidate before its first run: input tokens when both arms expose comparable counts, otherwise content reads, otherwise tool calls, otherwise elapsed time. Changing that choice after outcomes makes the pair invalid.

## Practical thresholds

- Non-inferiority: B must preserve acceptance on every valid pair and introduce no guardrail regression.
- Material efficiency: on both valid pairs for a P3/P4 mechanism, the predeclared primary cost improves by at least 15%, or by at least 1,000 input tokens when tokens are primary. At least one secondary cost must not worsen by more than 10%.
- Activation quality: zero false activations and zero missed required activations across the valid pairs. For mechanisms that are intentionally eligible only once, one correctly evidenced activation is enough; absence of an eligible opportunity is a coverage gap.
- Capability value: memory/codegraph usefulness must be at least `2` on both valid pairs and must preserve provenance/anchor correctness. Activity alone never meets this threshold.
- Small effects: changes below 10% and below the absolute token threshold are not material. The 10–15% band or conflicting metrics is mixed evidence.

The stricter phase contract wins: P3 and each P4 experiment require exactly two valid pairs; the general corpus ceiling remains six task pairs for any slice and does not authorize additional runs.

## Invalidity, exclusions and replacement

A run is infrastructure-invalid only for tool/provider outage, route mismatch, corrupted/missing dependency state, concurrent mutation of the worktree, missing primary metric in one arm, or an acceptance oracle that cannot execute on both arms. Record the reason before reading comparative outcomes. Product failure, extra writes, instruction violations, timeout caused by the candidate, or poor recovery are valid negative outcomes, not exclusions.

Exclude a corpus task before running if it leaks the target patch, lacks a reproducible parent/target, requires secrets or deployment, crosses the declared write boundary, or has no executable/inspectable acceptance oracle. One replacement pair per mechanism is allowed only for a documented infrastructure-invalid pair or a prompt ambiguity discovered before scoring. There is no replacement for an unfavorable result.

## Budget and stop rules

- P2 is observational and does not run A/B tasks; it uses this schema to report denominators and gaps.
- P3: two valid pairs for memory and two for codegraph, independently, plus at most one invalid replacement per mechanism.
- P4: at most four candidate experiments, exactly two valid pairs each, plus at most one invalid replacement per experiment.
- P5: one baseline/post comparison per admitted manifest row, then the row's own rollback/stop rule.
- Stop immediately on authority/safety boundary, persistent environment mismatch, guardrail breach that cannot be isolated, or exhausted cap. Do not expand the corpus to resolve ambiguity; return `defer`.

## Deterministic reducer

| Verdict | Required condition |
|:--|:--|
| `go` | Required valid pairs exist; every B arm is accepted; all guardrails are green; material-efficiency or capability-value threshold is met on every pair; measurement coverage is complete; the change is reversible and has a bounded downstream contract. |
| `keep` | Baseline is accepted and the candidate is non-inferior, but benefit is below the material threshold; or the current mechanism itself meets its value threshold without an identified cheaper replacement. |
| `defer` | Coverage is missing/`n/a`, results are mixed or in the 10–15% band, the valid-pair minimum cannot be reached within the cap, or dependencies prevent safe isolation. No implementation manifest is emitted. |
| `reject` | The hypothesis is falsified, any valid B arm fails acceptance or a guardrail, the candidate is dominated at equal quality, or the claimed mechanism never activates despite eligible opportunities. |

Apply the reducer per mechanism/slice; never average acceptance with cost and never combine memory with codegraph. P4 may emit a P5-ready row only for `go`. Thresholds and corpus provenance are frozen by this file; changing them requires an explicit plan decision, not post-hoc interpretation.
