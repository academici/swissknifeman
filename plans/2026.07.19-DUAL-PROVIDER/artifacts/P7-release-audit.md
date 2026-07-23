# P7.4 adversarial release audit

**Observed:** 2026-07-23
**Session:** `gpt-5.6-sol/xhigh`
**Baseline:** `b8e2c12a1c3b050e296132110120dd5ab4e3fb59`
**Authority:** read-only release evidence audit under D126; no package/source repair, live
apply/repair/rollback, cleanup, publication, tag, push, fleet or FOREMAN action.

**Вердикт: ATTENTION**

The functional dual-provider bundle, rollback, protected-path, privacy and validator gates are
GREEN under D126's exact two no-launch exceptions.  GREEN is nevertheless forbidden because the
committed P7.3 cleanup evidence contains one independently reproduced inventory count error:
`artifacts/P7-bootstrap-cleanup.md` says `.agents/skills/**` contains `16`
`agents/openai.yaml`, while both the P7.3 commit and the current baseline contain `17`.  This is
a release-evidence/provenance defect owned by P7.3.  It is not an explained exception and is
not repaired by this audit.

## Cold-start and immutable inputs

| Gate | Independent observation |
|:--|:--|
| Runtime | Effective Codex model `gpt-5.6-sol`; routed session effort `xhigh`; approval `never`; filesystem `unrestricted`; network enabled. |
| Repository | CWD `/home/vostrikov/projects/packages/swissknifeman`; baseline exactly `b8e2c12a`; pre-existing unrelated worktree changes only `AGENTS.md` and `.serena/project.yml`. |
| Hooks | Effective SessionStart command exists, is executable and passed a synthetic JSON probe; no exit `127`. |
| mAInd | Worktree-local `./packages/maind/bin/maind health --cwd` resolved `project:swissknifeman`; all health rows GREEN. |
| Plan lint before audit | Exactly `2 ERROR / 2 WARN`, with `0` new findings against `HEAD`: the two D126 no-launch handoff errors plus the two accepted historical P5 warnings. |
| Required chain | P7 manifest/cleanup/E2E/docs, P6 cold restart, plan contracts, P0–P7, research 11/13, read-only FOREMAN plan/handoff, root and package guides were read. Five package `AGENTS.md` files and `.swissknifeman/provider-artifacts.lock.json` are absent as recorded by P7.3. |

## P0–P7 release evidence

| Phase | Audited contract/deliverable | Independent result |
|:--|:--|:--|
| P0 | Provider inventory and frozen capability/artifact/migration contracts | Terminal evidence retained; frozen lifecycle approvals D55/D59 and current contract hashes are committed. |
| P1 | Frozen provider-config contract and resolver boundary | `provider-config-contract.md` remains v1.0.0 at SHA-256 `4456c60713754034050d9ad6e19945b26a3a017ffcda8f3b21924727d7e98a03`. |
| P2 | Deterministic artifact/lock lifecycle | `P2-provider-artifact-conformance.md` SHA-256 `05238abee18b558935e8c12d58f6950ce22d0dafb98f78a305828ab61d88f5de`; current focused lock suite `28/28` GREEN. |
| P3 | Dual skill publication | `P3-skill-publication-conformance.md` SHA-256 `f4a94c1752add4ea82432c0225829d886b45d0220ccd9a9863c5eb527a407870`; focused parity `8/8` GREEN. |
| P4 | Provider-neutral task command/routing contract | `P4-command-parity-conformance.md` SHA-256 `f7d6c333c5a3939e1da8e263a801c157be69005c7c800be3da88d9f55fed2265`; focused parity/adapters `25/25` GREEN. |
| P5 | Harness surfaces and instruction projections | Harness/instruction artifacts SHA-256 `db11a95462e5c19ce5efb51f4511ada75a0f8a793cb8ee3bfec0023c23f64e46` / `de54cf00db8a41c7e27665caa30238fe03a56e34aadfaa62f82bff9aadb78be6`; public provider audit and independent instruction lifecycle GREEN. |
| P6 | mAInd deploy, neutral analytics, checkpoint/cold restart and D123 rollback seam | Integrated historical carrier SHA-256 `6a972b5a56f527fb826db4379843013d26f9394864375ee634d3c0026c85f9ee`; checkpoint `p6.5-bootstrap-b7373334` / payload `22a9c7a82f48ae0e27449ca1be240398b3b8ecd36fbfd50bc2f8bd3a56d60dc9`; focused provider/deploy `55/55` GREEN. Accepted P6.8/D107 debt remains explicit. |
| P7 | Generated docs, self-host apply/noop/rollback, bootstrap inventory and candidate manifest | P7.1 and P7.2 carrier hashes match the manifest; functional gates GREEN. P7.3 ownership classification is exhaustive by path family and its aggregate hash matches, but its `openai.yaml` member count is factually wrong, so the release evidence is ATTENTION. |

## Manifest and frozen hash reconciliation

Every release-manifest hash below was recomputed from current committed bytes:

| Carrier | Recomputed SHA-256 |
|:--|:--|
| `artifacts/P7-provider-docs-conformance.md` | `e75459ea5ab78ca9e7ac9c6b73c70e5f38e6b63f9379854eec98b1528c0f09e0` |
| `artifacts/P7-self-host-e2e.md` | `73ff73d11e0716327b81611609555913eda2a232df15df1bb8b1db8b9dc65bab` |
| `artifacts/P7-bootstrap-cleanup.md` | `e4be87a3e3b6209d73eebe491612c0ee59e903a8d08a2c3ab89dd09ee6c90bbe` |
| capability / config contracts | `b22e1df11bc31651a2f9a4e4eeaaa2996af1556eac656894e65712cb261c2d56` / `4456c60713754034050d9ad6e19945b26a3a017ffcda8f3b21924727d7e98a03` |
| harness / instruction / analytics contracts | `7309f3a4e80a2398b0fc7b84300c6cd1dd2a7d62d809b15e726ca78e790f1965` / `37ab85d0b0ccc6b59d0fa5b197e17d85c7a31e63381c5f57d7e876ce27251910` / `218cc703cdf23aa9501e74349c6902e59a2c04db6749d3cc6700527cdaf3451c` |
| capability manifest carrier / canonical JSON | `32975d675cf252bba87b06aaee53bfe37e63a9a97dc74cb7a12a8a2b0c0394eb` / `4c479c697c708cfea8d36589c435338094d894bcf428687709987975b13b6ce1` |
| `packages/skiller/skills.json` | `e74dcc269d7b0b43138730a1f71a2b0b0904aa1ea134683ebc1316c478f9c7d9` |
| instruction catalog | `83543c10f3f05a2ff01205c7256229b032144b0705315ab1c230961f5c711b0b` |

All values match `P7-release-manifest.md`.  The manifest remains explicitly
`candidate / not released`.

## Independent provider exact-set and production consumers

`scripts/provider-docs.py` was imported as a read-only conformance consumer and its expected
inventory was independently derived from task routing, the harness surface catalog, the
instruction requirement and the frozen analytics sections:

- contract/catalog `1.0.0/1.0.0`;
- `35` common capabilities × `2` providers = `70` support records;
- missing `0`, extra `0`, duplicate `0`, matrix missing `0`, matrix extra `0`;
- Native Extensions `0`; task mapping missing/extra `0/0` for both providers;
- `170` named production requirements, `0` requirement failures;
- requirement consumers: skiller publication, all task commands, harness provider audit,
  harness instructions, mAInd provider deploy and analyst provider readers.

`python3 scripts/provider-docs.py --check` and
`./packages/skiller/bin/skiller registry --check` passed.  Two independent public
`./packages/harness/bin/harness doctor --provider-audit --json` runs were byte-identical at
SHA-256 `2faee8e80b8b12f13184d979e8d2661de1beda8b8b976ec95fc0642f79e82782`,
`green=true`, diagnostics `0`.  Exact-set rows for agents, MCP, profiles and harness surfaces
have missing/extra/duplicates `0`; all four managed lifecycle samples prove
create→noop, drift refusal and explicit repair with outside-managed bytes preserved.

## Instruction chain, semantic equality and repair

The frozen chain is intact:
`provider-instruction-contract.md` → instruction catalog → pure harness renderer/public
operations → mAInd provisioner/checker.  An independent disposable-root run derived expected
IDs directly from catalog JSON and compared them to public plan results:

| Scope | Common IDs in both providers | Claude extension IDs | Codex extension IDs |
|:--|--:|--:|--:|
| root | 11 | 3 | 3 |
| skiller | 8 | 3 | 0 |
| harness | 8 | 3 | 0 |
| maind | 7 | 2 | 0 |
| analyst | 8 | 2 | 0 |
| task | 7 | 2 | 0 |

Totals are `49` common + `18` allowed provider extensions = `67` unique semantic IDs,
duplicates `0`, across `12` provider targets.  The disposable run then:

1. applied all twelve missing targets through public `apply_instructions`;
2. obtained a GREEN second public check with all actions `noop`;
3. introduced managed drift only in Codex root `AGENTS.md`, surrounded it with
   `outside-before` / `outside-after`;
4. reproduced non-green managed drift, then explicit public repair using the exact observed
   hash and adjacent-preimage authority;
5. obtained GREEN repair while both outside-marker sentinels survived.

The Claude root noop render hash was
`sha256:3da44c17059395baa7e9d2bfece8c01edf08427e7e63677285c75bed236faf37`;
the repaired Codex root render hash was
`sha256:f63bbc89584b45ca953eaada84a3dc9cbf7a5b76453111cd94d96ccd5d553a60`.

## Rollback reproduction and current state

The committed D123 seam was rerun in disposable tests:

- `core.tests.test_provider_lock`: `28/28` GREEN, including exact completed-state rollback,
  seven fail-closed state families, write-failure restoration and identical second plan;
- `packages.maind` provider/deploy suites: `55/55` GREEN, including D104/D108/D122/D123
  admission, no-op, rollback and changed-state refusal.

The live repository was only read:

- `.codex/hooks.json` is a regular restored preimage at
  `7d7538d021228e8e61d124f4b60b6db04434f8121de30b8672f05e4bf038c3db`;
- `.mcp.json` is regular and unchanged at
  `cf4537196c3fefd6fd3980221bd3677f74e7867392ad49364e1e891e1f7c8283`;
- `.swissknife.json`, `.swissknifeman/provider-artifacts.lock.json`,
  `.codex/hooks/lifecycle.py` and both named D121 backup residues are absent.

No live apply, repair or rollback command was run.

## Bootstrap ownership and finding

The aggregate and individual pre-hashes reproduce exactly:

| Carrier | Recomputed SHA-256 |
|:--|:--|
| `.agents` file manifest | `83b2c1c7cc09d15d52af475d2e37af6630cdc2b214a9c20c35e9bd61f1f19f19` |
| `.codex` non-runtime file manifest | `eacc69f610c80a492176724153747d79f8dcd09d5fa5990133c749b00dc2ff7c` |
| `.claude` file manifest | `56093c8d44654115cd284b86746ca0ab45d36e82dd630f4833a5efb9f1d23d54` |

Root and all five package `CLAUDE.md` hashes also match the P7.3 table.  Package
`AGENTS.md` targets and the provider lock are absent.  Marketplace count is `51`, Codex agent
TOML count is `10`, and the exact destructive cleanup action set remains `∅`: no path has both
managed provenance/source-hash equivalence and a without-file dual-provider proof.

### F1 — Major evidence defect · owning item P7.3

At both P7.3 item commit `d43f9549` and P7.4 baseline `b8e2c12a`,
`.agents/skills/**` contains:

- `30` `SKILL.md`;
- `17` tracked `agents/openai.yaml`;
- `2` ignored `SKILL.md.bak`.

The committed cleanup artifact says `16` `agents/openai.yaml`.  `git ls-tree` confirms `17`
at both anchors and no named exclusion exists.  The enclosing path-family ownership
classification still covers every file and the aggregate hash includes the seventeenth file,
so the finding does not demonstrate an unsafe deletion or functional failure.  It does make
the supposedly complete release inventory inaccurate; under the P7.4 anti-self-deception rule,
that provenance failure forbids GREEN.

## Package, lint, privacy and protected-path gates

| Gate | Result |
|:--|:--|
| skiller full validation | GREEN, `410` tests; registry current |
| harness full validation | GREEN, `412` tests |
| mAInd full validation | GREEN, `480` tests |
| analyst full validation | GREEN, `211` tests |
| core full validation | GREEN, `231` tests |
| task tests | GREEN, `228` tests |
| task package aggregate | Non-green only because all-plans lint reports the same exact two D126 handoff errors; no additional task/test failure |
| target plan lint | Exactly `2 ERROR / 2 WARN`, `0` new against `HEAD`; errors are D126 no-launch exceptions, warnings are accepted P5 debt |
| focused P3 / P4 / rollback | GREEN `8` / `25` / `28+55` tests |
| diff hygiene | `git diff --check` GREEN |

The privacy scan covered the release manifest, P7 docs/E2E/cleanup evidence, P6 cold restart,
capability carrier, README and provider guide.  High-confidence PEM private keys, OpenAI,
GitHub, AWS and Slack tokens, bearer tokens and literal JSON secret values: `0`.  No raw
transcript carrier is embedded.  Provider-deploy focused tests additionally preserve secret
references without resolving their values.

Relative to item baseline `b8e2c12a`, P7.4 touched only its audit/bookkeeping paths.
`plans/2026.07.18-FOREMAN/**`, `plans/ACTIVE.md` and fleet carriers have item delta `0`.
The pre-existing dirty `AGENTS.md` and `.serena/project.yml` remain unstaged and were not used as
release evidence.  FOREMAN tree bytes were read only; no FOREMAN command was run.

## Gate decision and bounded route

D126's two no-launch errors are accepted and create no new lint delta, but they do not exempt
F1.  Therefore:

- release verdict is `ATTENTION`;
- no Owner release D# is assigned;
- FOREMAN gate remains closed;
- no cold-start execution payload or launch block is emitted;
- publication, tag, push, fleet and cleanup remain unauthorized.

The bounded remediation proposal is evidence-only: reopen P7.3 to correct the audited
`.agents/skills/**` member count from `16` to `17`, independently re-run the ownership/count/hash
checks without source or live mutation, reclose P7.3, then run a fresh P7.4 release verdict.
This audit does not authorize or execute that route.
