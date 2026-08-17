# P7 release verdict

**Вердикт: RED**

P7.4 does not authorize release. D89 accepts the P7.3 document only as a truthful non-published,
non-releasable candidate and requires a non-GREEN verdict while required blockers remain.

Release blockers:

- P6 is `aggregate=non-green`, `p7_release_authorized=false`: 24 required-project blockers plus
  `P5_ROLLOUT_NOT_AUTHORIZED` (25 total).
- P7.1's 54-row provider replay is diagnostic; live efficacy and ablation remain deferred under
  D88. Its package verifier is green, but that is not release efficacy.
- The exact P7.4 acceptance and decision-crosswalk commands exit 2 because their frozen CLI
  arguments are not implemented; the release-tree interface is also incompatible.
- The only candidate anchor is HEAD `519af66def68027738a0158142cf7a19050d3983`, while P7.3 and
  later evidence are uncommitted in a shared dirty worktree.
- Task validation/plan lint is red, and the plan's human cold-start carriers are stale.

The complete severity ordering, exact-set proof, command results, worktree separation, scope
payload, and continuation are in `artifacts/P7-final-release-audit.md` and
`artifacts/P7-final-worktree-status.json`.

Owner disposition: D89 rejects GREEN and any implicit exception. Tag, push, publish, fleet rollout,
provider repair, and live-efficacy claims remain unauthorized.

Provider-neutral Semantic Next:

```text
$ task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE P7
```

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman \
  -m gpt-5.6-sol -c model_reasoning_effort=high \
  -a never -s danger-full-access \
  '$ task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE P7'
```

## P7.7 delta verdict — 2026-08-17

**Package candidate: RED. Release: RED. Release authorized: false.**

P7.5 repaired the acceptance and exact-decision interfaces, and P7.6 produced a real scope commit
whose tree matches its integration receipt. The independent successor nevertheless found four
remaining local closure defects:

- the exact P7.7 release-tree command names a Markdown document where the verifier requires the
  JSON `p7-candidate-paths/v1` carrier;
- the generated P7.7 bundle is outside the sealed candidate/foreign partition, while the required
  updated crosswalk differs from the P7.6 anchor by construction;
- six current foreign bytes no longer equal their sealed preimages, but the verifier compares only
  the static manifest-list digest and therefore cannot prove unchanged foreign state;
- plan lint remains RED on P7.5/P7.6 write-site/downstream bookkeeping and the invalid handoff.

The exact acceptance check, current D1–D90 crosswalk, verifier self-test, remediation manifest,
P7.6 commit/tree receipt, decision/state/bundle views, provider-doc generation and plan citations
are GREEN. Status projection was regenerated and rechecked GREEN.

D89 and the external blocker payload are byte-identical to the prior audit. No live provider/fleet
retry occurred, and no release operation is authorized.

Fix in order: bind release-tree validation to `P7-candidate-paths.json`; make the partition aware
of deterministic plan-runtime carriers and verify current foreign bytes; repair P7.5/P7.6
write-site/downstream records and regenerate handoff/index; then rerun only the targeted P7.7 gates
and `task:plan-close 2026.08.02-PROVIDER-CONTRACT-LOCALE P7`. External D89 blockers remain a
separate authorized operation and do not justify another design loop.
