# P6 field reconciliation

## Outcome

P6 performed the frozen preflight before creating any temporary worktree or model
session. All three pairs are `invalid-prerequisite`, so the protocol forbids scoring,
retrying with an easier task, or claiming a candidate advantage. No consumer source
worktree was mutated.

| Project | Frozen identity | Preflight result | Action |
|:--|:--|:--|:--|
| Corex | commit `9608b488bc1ab1fcf635cf08254b5f6687e0d60a`; P6.1 spec `643017bdcf8a25e1ff16bff50d757edd6094e685f6c9e209665c6ffe347ae0d3` | Spec matches, but the committed handoff names P2.5, not P6.1; P6.1 therefore is not the frozen ready task. | `invalid-prerequisite`; neither arm started. |
| Agentools | commit `87dbb5500eaf48c13ef9160e4ee11afdf2942371`; P11.1 spec `b7478eca553a2445e2b22eb60699edb0fa5cde6b360d01f59db97c9679a1e8d1` | Spec matches, but the committed handoff requires `plan-design AGENTOOLS finish` before P11.1. | `invalid-prerequisite`; neither arm started. |
| Edufy | commit `11bbed76ada4cd7077ab388228227b9f33b1f224`; expected P14.3 spec `5095da298c4f86deefeb5a125502e4cc2d5656fa988c40387bb557237238575b` | Committed spec is `12c04c6bf17f449dedb821076211608fad2ab6dfe80bd734a52b3599de01da94`; committed handoff names P9.2. | `invalid-prerequisite`; neither arm started. |

Observed source checkouts remained read-only: Corex HEAD matched the frozen commit,
Agentools HEAD matched and was clean, and Edufy remained on its newer dirty checkout.
Dirty-entry counts are observational only and were not used as identity or acceptance.

## Candidate ledger

| Candidate | Defect / mechanism | Exact surface and observable result | Gate / rollback | Verdict |
|:--|:--|:--|:--|:--|
| Additive public recovery taxonomy | P2–P5 leave precise module diagnostics that require consumer-specific parsing. A stable recovery category can be added without discarding the internal code. | `task_contract.evaluate()` / CLI `check` add `reason_codes.{pre_mutation,pre_final}` with one of eight public codes, the original diagnostic and a concise recovery message. | Focused API/CLI tests, full Task validator and compatibility note; rollback removes only the additive field/helper and retains internal diagnostics. | retained |
| Rewrite Task commands / plan-protocol prompts | No valid paired run demonstrated that current wording caused a behavioral failure or that proposed copy changes behavior. | Would touch canonical prompts and generated provider projections without an observable field outcome. | Non-code candidate gate rejects style/consistency-only changes. | dropped |
| Change bundle/privacy policy wording again | P5 already synchronized the executable templates; no later relevant implementation changed that field result. | No distinct consumer behavior to test. | Keep P5 semantics; no duplicate P6 edit. | dropped |

The retained code candidate is verified structurally and by real CLI behavior, but this
report makes no comparative model-performance claim. The three invalid pairs are preserved
as limitations, not converted into wins.

## Privacy and external-evidence boundary

Only commit IDs, spec digests, handoff predicates, commands and aggregate checkout state are
recorded. No transcript, chain-of-thought, secret, raw tool payload or temporary worktree is
stored. A new Perplexity connector was unavailable in this Codex session; P6 introduced no new
external premise and relied only on the already closed P1/P2 external sanity evidence plus
repository bytes.
