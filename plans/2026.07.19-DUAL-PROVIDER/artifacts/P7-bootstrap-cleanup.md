# P7.3 bootstrap ownership and cleanup inventory — read-only

**Observed at:** `29f8d537e71a9d823f5669be4a2348ddd86aa523` plus only this item's
uncommitted plan bookkeeping.  **Session:** `gpt-5.6-terra/high`.
**Authority:** D125 permits inventory only.  No delete, move, generated write, live
apply, repair, rollback, FOREMAN/fleet action, tag, or push has been performed.

## Preconditions and evidence

- P7.2 is accepted as the predecessor: functional self-host evidence is GREEN; its only
  orange condition is the Owner's no-launch handoff-schema override.
- The live D121 cycle was explicitly rolled back.  The current preimage is
  `.codex/hooks.json` SHA-256
  `7d7538d021228e8e61d124f4b60b6db04434f8121de30b8672f05e4bf038c3db`;
  `.swissknife.json`, `.swissknifeman/provider-artifacts.lock.json`, and
  `.codex/hooks/lifecycle.py` are absent, as required by the recorded rollback.
- The frozen P5 instruction contract classifies root `AGENTS.md` as an unmanaged bootstrap
  compatibility input until an explicit marker-and-lock migration.  All five package
  `AGENTS.md` targets are currently absent and therefore `missing`, not cleanup candidates.

## Complete ownership table

| Path set | Current owner/class | Pre-hash / replacement proof | Exact action |
|:--|:--|:--|:--|
| `.agents/plugins/marketplace.json` | P3.3 generated Codex marketplace, added by `302a5f0a`; not a bootstrap duplicate. | `11cb0fdabf5a3f1e0d70a83983eb0a43412b25b799882a94ef7dbf22bba6f197`; 51 plugins point directly at canonical `packages/skiller/**` / `packages/task`. | retain |
| `.agents/skills/**` (30 `SKILL.md`, 17 `agents/openai.yaml`, 2 ignored `SKILL.md.bak`) | Repository-native bootstrap from `e8f5b477`; no P2 lock record.  The `SKILL.md` files are adapters or direct bootstrap copies, not a P2-managed generated target set. | Tree pre-hash `83b2c1c7cc09d15d52af475d2e37af6630cdc2b214a9c20c35e9bd61f1f19f19`.  Pointer adapters name a canonical source, but their hashes differ by design; direct copies and `openai.yaml` have no matching P3/P5 replacement record. | retain; no eligible removal |
| `.codex/agents/*.toml` (10 files) | Bootstrap native-agent configuration from `e8f5b477`; no P2/P5 lock/provenance record names these files. | Included in `.codex` tree pre-hash below; no generated replacement path/hash. | retain |
| `.codex/config.toml` | Bootstrap trusted-host configuration from `e8f5b477`, not the P5 managed projection. | `68df0b5bcc069ce64c24aeb63c2bb08773219dff83526398ddba247dee6fb2bc`; the nominal P5 target is also `.codex/config.toml`, but no matching source/render hash plus lock exists, so ownership cannot be inferred. | retain |
| `.codex/hooks.json` and `.codex/hooks/auto-approve/auto-approve.sh` | Bootstrap hook preimage / legacy hook.  P7.2 temporarily used only the sealed D121 chain and restored this state. | file hashes `7d7538d021228e8e61d124f4b60b6db04434f8121de30b8672f05e4bf038c3db` and `642eb9dc53d1835c7c8e7166ae941c19efb93cccc9916c76871fc5145698971c`; no current lock. | retain |
| `.codex/hooks/__pycache__/lifecycle.cpython-312.pyc` | Ignored runtime cache, outside tracked/bootstrap ownership. | excluded from tree digest and all actions. | preserve |
| `.claude/**` and `.claude-plugin/marketplace.json` | Claude compatibility/user or legacy managed carriers; P7.3 explicitly excludes deletion of legacy `.claude` data. | `.claude` tree pre-hash `56093c8d44654115cd284b86746ca0ab45d36e82dd630f4833a5efb9f1d23d54`; marketplace `6af913ba72f7164c5473f430ac5879cbffa80e06a81827790d013bdb41b422c1`. | retain, delta must remain zero |
| `AGENTS.md` | Existing root Codex compatibility input, unmanaged until a separately approved P5-marker/P2-lock migration.  It was already dirty before this item and is not owned by P7.3. | Observed worktree hash `16abc14b2398a311adac2f77dcaae965b5690f267245e6d1543ea9c25c16cea2`; no matching marker/lock. | preserve, do not stage |
| `CLAUDE.md` and `packages/{skiller,harness,maind,analyst,task}/CLAUDE.md` | Frozen Claude compatibility inputs/targets. | Current hashes are recorded in the pre-hash manifest below. | retain, delta must remain zero |
| `packages/{skiller,harness,maind,analyst,task}/AGENTS.md` | Contract-defined Codex targets, all absent.  `missing` is not a superseded bootstrap path. | `ABSENT` for each; no current P2 lock after D123 rollback. | no create, move, or delete |
| `.swissknifeman/provider-artifacts.lock.json` | Absent by the accepted D123 rollback; recreating it would be a live/provider mutation, not cleanup. | `ABSENT`; P7.2’s temporary three-record hash was `56f9d44063ae261d151b504259a0e950d6f5ae5b0a17c0e08015773c5c20bcf9`. | retain absent |

## Replacement and semantic-hash check

The P3 marketplace is a replacement *delivery route*, not proof that any bootstrap file can
be deleted.  The exact P7 rule requires a generated replacement with matching semantic ID and
source hash **and** successful Claude and Codex smoke runs without the candidate.  Neither is
available for any deletion candidate on this anchored tree.

| Bootstrap family | Nominal canonical/generated route | Result |
|:--|:--|:--|
| Core pointer adapters (`anti-drift`, `architecture`, `codebase-design`, `context-economy`, `domain-modeling`, `package-contribution-protocol`, `plan-protocol`, `query-craft`, `session-handoff`, `verify-claims`, `workflow-craft`) | Named `packages/skiller/skills/**/SKILL.md` canonical sources; P3 marketplace references package sources. | Adapter bytes are deliberately different from source bytes; no per-artifact generated lock/source hash proves replacement. |
| Task bootstrap adapters (`task-design`, `task-plan-audit`, `task-plan-close`, `task-plan-design`, `task-plan-exec`, `task-plan-run`) | `packages/task/adapters/codex/skills/<id>/SKILL.md` and `command.md`, published by the P3 marketplace task plugin. | Every bootstrap/published adapter hash differs; a semantic-ID/source-hash equivalence and without-file smoke are not yet evidenced. |
| Direct bootstrap skills and `openai.yaml` metadata | No catalog record or P2 lock identifies an independently generated replacement. | Unknown for destructive purposes; retain. |
| `.codex` agent/config/hook bootstrap | P5 has nominal provider projections, but the current tree lacks the matching P2 provenance/source/render lock. | Unmanaged for cleanup; retain. |

Selected published hashes: `packages/task/adapters/codex/skills/task-design/SKILL.md`
`4ca8c7bf547bab9c9efb8ef0cdd415c3ca19ca1f8c980b861c70dc713b6a0b0c`,
`task-plan-audit` `ee11e57072c2b0e778e9c8dae66e8b0dfcebdaaf03b00c39b3fcb0196c6e5d23`,
`task-plan-close` `974679e4f9fcc86568043ffbdc0b77ce4e72cb7c888af52706e82ec8acbbc93c`,
`task-plan-design` `4276e2dd18acf09a93633098618264b5b4c6b0111605f5aea5bfbae253b1e7c9`,
`task-plan-exec` `3198d3a4aaf6fac6a2071214466a400253dbc3367be7dd069574a09c2ce6f7b1`, and
`task-plan-run` `84d02d6f3fab5732092f79ec13d0a8893660364434c0980f4347fa0b6c1892f6`.

## Exact reversible action set and smoke plan

**Proposed destructive action set:** `∅`.  Therefore no backup directory, move command, or
post-mutation smoke is authorized or required in this preparation pass.  This is
deterministic: every possible bootstrap carrier fails at least one mandatory deletion
predicate (matching managed provenance/source hash, both-provider without-file smoke, or
current owner authorization).

If a later D# names a candidate after a contract-owned equivalence repair, the executor must
first record the individual pre-hash, move only that explicit path into a task-specific backup,
then run these post-smokes before considering deletion permanent:

1. P3 publication parity twice: `PYTHONPATH=packages/skiller/lib:packages/skiller:. python3 -m unittest tests.test_provider_publication_parity tests.test_channel_parity` from `packages/skiller`.
2. P4 command parity: `PYTHONPATH=packages/task/lib:. python3 -m unittest packages.task.tests.test_provider_command_parity packages.task.tests.test_plan_command_routing packages.task.tests.test_claude_command_adapter packages.task.tests.test_codex_command_adapter`.
3. P7.1 provider-doc check and the full P7.2 Claude/Codex self-host E2E, including the second no-op and explicit rollback; then all six package/core validations and protected-path delta checks.

Any failure restores the one captured path and stops at the owning P3/P4/P5 contract; P7 must
not patch a replacement or infer ownership.

## Pre-hash manifest and protected state

Reproduce the two bootstrap aggregate pre-hashes with:

```bash
find .agents -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum
find .codex -type f ! -path '*/__pycache__/*' -print0 | sort -z | xargs -0 sha256sum | sha256sum
```

| Carrier | SHA-256 |
|:--|:--|
| `.agents` file manifest | `83b2c1c7cc09d15d52af475d2e37af6630cdc2b214a9c20c35e9bd61f1f19f19` |
| `.codex` tracked/non-runtime file manifest | `eacc69f610c80a492176724153747d79f8dcd09d5fa5990133c749b00dc2ff7c` |
| `.claude` file manifest | `56093c8d44654115cd284b86746ca0ab45d36e82dd630f4833a5efb9f1d23d54` |
| root `CLAUDE.md` | `737015db73b7c90011e37904dd8dad00859dccce7f1f31da7b254a62105bedc4` |
| `packages/skiller/CLAUDE.md` | `b9a059d94843730bfb9b865e3c6abb1290cab28e9ac0db95fe1f5c88d93f7d82` |
| `packages/harness/CLAUDE.md` | `fa1b0a9ad335df5bc7a7bb886441509836e93baa99998a1c158b366f6a3beb0b` |
| `packages/maind/CLAUDE.md` | `7de822d87c9afb06751adbb3efe2001483aeafa588a88e2672f966eeebbf3883` |
| `packages/analyst/CLAUDE.md` | `b3d2c4b1268a8499bf1f1ce3ab126f66d7b969ad398e22d9b3b85fe59241be1d` |
| `packages/task/CLAUDE.md` | `158b1de45365e5a3a4e8c94b5997a16cbbe37f605169d8b48b2516460f9f9a9d` |

`plans/2026.07.18-FOREMAN/**`, `plans/ACTIVE.md`, fleet carriers, `.serena/project.yml`, and
the pre-existing dirty `AGENTS.md` are protected and have no proposed delta.

## Owner approval boundary

No cleanup mutation is currently admissible.  P7.3 stops here pending this exact Owner reply:

```text
APPROVE P7.3 D126 NO-CLEANUP-INVENTORY: retain all listed bootstrap, unmanaged, compatibility, and absent carriers; authorize no delete, move, repair, or lock creation; permit only non-release draft manifest work anchored to committed evidence.
```

Without that D#, P7.3 remains `🟡 In progress`; P7.4, FOREMAN, fleet, tagging, pushing, and
release claims remain closed.

## Preparation validation

- `git diff --check` — passed.
- `python3 packages/task/scripts/plan-lint.py plans/2026.07.19-DUAL-PROVIDER --baseline HEAD`
  — `2 ERROR / 2 WARN`, with `0` new findings from this preparation.  Both errors are the
  accepted P7.2 no-launch handoff-schema condition recorded by D125; neither is hidden or
  treated as green.
