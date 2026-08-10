# Terminal input provenance capsule — P6.2/P6.5/P6.6

This reader-specific capsule replaces repeated full historical sources on executor paths of
already terminal items. It does not replace their evidence or completion history; every full
carrier remains in the repository and is reachable below. Digests were computed over ordered
`sha256sum` output on 2026-08-09.

## P2.9

The terminal P2.9 diagnostic inventory remains at `artifacts/p2-weight-after.json`, SHA-256
`3233bfac9e7b03492a133d0bab7439f9404d795189e585b9784f96b3c8d44ff9`, schema `plan-weight-v1`.
Its historical totals were 47 items, 61 gaps, maximum item weight 154036, with gap counts
missing-file 42, oversized-file 17, unresolved-entry 2 and unreadable-root 0. P2.9 consumed that
inventory to implement stage-aware admission; loading the 28k-token raw diagnostic on every
terminal executor path is not required to reproduce the terminal contract or current measurement.

## P6.2

P6.2's only externally sourced load-bearing statements are `R10.3` (the gate may answer `unknown`)
and `R17.2` (a production rehearsal, not green prose/CI alone, proves the mechanism). The item now
selects those exact sections. Its contracts, commands and implementation files remain declared as
working inputs; no code carrier is hidden by this capsule.

## P6.5

P6.5 was terminalized after producing EN-only authoring, plan-protocol v2, fail-closed canon
checks, generated Codex projection/locks, two-threshold canon weight gate, docs and registry. The
22 contract prose/schema carriers remain under `root/contracts/`; their ordered source-set digest
is `83519378dac3391e353423abf220b2e7800c81bedc08d76c3e9cfb0037f80566`. D30, D32–D34, D43 and
D67–D78 remain under `decisions/`; ordered digest
`a692a7b8b51340d07a92b80c8ee7325b60d03ef9f7a55a4529b6a2e5fe4866c5`.

The two preserved pre-v2 canon slices have ordered digest
`e715359aa568b8bb1bb86866e55fa7ef832e01cc6ddca863e0496ff550f388fa`.
Owner EN-only direction remains in `brief/01-refinements.md` (full-file SHA-256
`1a774944ceef3799b9902719a7a4e45566448be7131ceb012ebcbbe493e1d32d`); recalibration pre-mortem
remains in `research/02-p0-measurement-design.md` (SHA-256
`6f30a72c66f5d449f725110c7f9c51adc008cc0732e75cb55a4141ebaaaf72ac`). The terminal executor
needs the outcome/provenance above plus the exact rollout/canon sections retained in its Required
Reads, not all historical source bytes again.

## P6.6

P6.6 consumed the registered plan-protocol, authority frame and migration CLI. Their ordered
source-set digest is `554f27a97f2f505eacae84cbd37c4f04692c5740e7a3b395bbc30f393945a792`.
The generated registry's `plan-protocol` row is: bucket `general`, path
`skills/general/plan-protocol/SKILL.md`, version `2.24.0`, source `local`, registry entry SHA-256
`5ceaec0bb853f0616274f53e3fedd9f286dfa16028dd032e655eb111cd111765`, content SHA-256
`ded5c3f615b89e32623fab0ca62374d3833cb5e72060fbe270e25f9a0b72264c`. Loading the entire 53k-token
registry to prove this one row is unnecessary and was the observed D2(b) defect; the full generated
registry remains governed by `skiller registry --check`.

## Anti-displacement answer

Could this have passed exclusively by splitting, moving, caching, deferring, or excluding work?
**No.** No item, five-slot carrier, admission state, declared deliverable or terminal evidence was
removed. Only repeated historical source bytes on terminal executor paths were replaced with exact
section selectors or this digest-and-fact capsule; full sources remain available and their
integrity/registry generators remain independently checkable.
