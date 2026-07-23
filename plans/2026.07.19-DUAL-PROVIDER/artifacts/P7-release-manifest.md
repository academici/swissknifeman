# P7 release manifest — committed candidate, not a publication

**Observed:** 2026-07-23
**Release state:** `candidate / not released` — no tag, push, publication, FOREMAN, or fleet
operation is authorized or implied.  This manifest uses committed evidence only; its own
commit is the anchor consumed by P7.4.

## Committed evidence set

| Concern | Committed carrier | SHA-256 / version / result |
|:--|:--|:--|
| P7.1 capability/docs | `d68ec94d`, `artifacts/P7-provider-docs-conformance.md` | `e75459ea5ab78ca9e7ac9c6b73c70e5f38e6b63f9379854eec98b1528c0f09e0`; manifest contract/catalog `1.0.0/1.0.0`; GREEN |
| P7.2 self-host and rollback | `460019a2`, `9057b3f4`, `098df29d`, `artifacts/P7-self-host-e2e.md` | `73ff73d11e0716327b81611609555913eda2a232df15df1bb8b1db8b9dc65bab`; D121 apply, second-plan noop, D123 rollback GREEN |
| P7.3 no-op cleanup inventory | `d43f9549`, `artifacts/P7-bootstrap-cleanup.md` | `e4be87a3e3b6209d73eebe491612c0ee59e903a8d08a2c3ab89dd09ee6c90bbe`; destructive action set `∅` |
| P6 bootstrap checkpoint | `35924d42`, `artifacts/P6-bootstrap-checkpoint.md` | checkpoint `p6.5-bootstrap-b7373334`; payload `22a9c7a82f48ae0e27449ca1be240398b3b8ecd36fbfd50bc2f8bd3a56d60dc9` |
| Artifact ownership/conformance | `artifacts/P2-provider-artifact-conformance.md` | `05238abee18b558935e8c12d58f6950ce22d0dafb98f78a305828ab61d88f5de` |
| Skill publication | `artifacts/P3-skill-publication-conformance.md` | `f4a94c1752add4ea82432c0225829d886b45d0220ccd9a9863c5eb527a407870` |
| Command parity | `artifacts/P4-command-parity-conformance.md` | `f7d6c333c5a3939e1da8e263a801c157be69005c7c800be3da88d9f55fed2265` |
| Harness/instructions | `artifacts/P5-{harness,instruction}-conformance.md` | `db11a95462e5c19ce5efb51f4511ada75a0f8a793cb8ee3bfec0023c23f64e46` / `de54cf00db8a41c7e27665caa30238fe03a56e34aadfaa62f82bff9aadb78be6` |
| Integrated P6 history | `artifacts/P6-integrated-conformance.md` | `6a972b5a56f527fb826db4379843013d26f9394864375ee634d3c0026c85f9ee`; historical RED retained, later checkpoint evidence is the terminal input |

## Frozen contracts and source catalogs

| Contract/catalog | Version or SHA-256 |
|:--|:--|
| provider-capability contract | `v1.0.0` / `b22e1df11bc31651a2f9a4e4eeaaa2996af1556eac656894e65712cb261c2d56` |
| provider-config contract | `v1.0.0` / `4456c60713754034050d9ad6e19945b26a3a017ffcda8f3b21924727d7e98a03` |
| provider-harness contract | `v1.0.0` / `7309f3a4e80a2398b0fc7b84300c6cd1dd2a7d62d809b15e726ca78e790f1965` |
| provider-instruction contract | `v1.0.0` / `37ab85d0b0ccc6b59d0fa5b197e17d85c7a31e63381c5f57d7e876ce27251910` |
| provider-analytics contract | `v1.0.0` / `218cc703cdf23aa9501e74349c6902e59a2c04db6749d3cc6700527cdaf3451c` |
| capability catalog | `packages/skiller/skills.json` / `e74dcc269d7b0b43138730a1f71a2b0b0904aa1ea134683ebc1316c478f9c7d9` |
| instruction catalog | `packages/harness/configs/common/instructions/catalog.json` / `83543c10f3f05a2ff01205c7256229b032144b0705315ab1c230961f5c711b0b` |

## P7.3 non-destructive validation

| Command | Result |
|:--|:--|
| `python3 scripts/provider-docs.py --check` | GREEN |
| `./packages/skiller/bin/skiller registry --check` | GREEN |
| `./packages/harness/bin/harness doctor --provider-audit --json` twice | byte-identical GREEN; `missing=extra=duplicates=0` |
| P3 focused publication parity | GREEN, `8` tests |
| P4 focused command parity | GREEN, `25` tests |
| skiller / harness / maind / analyst validations | GREEN: `410` / harness `validate: OK` / `480` / `211` tests |
| core validation | GREEN, `231` tests |
| task validation and target plan lint | non-green only for the two inherited D124 no-launch handoff-schema errors; target lint reports `0` new findings |

No cleanup occurred, so no regeneration/write or post-cleanup E2E rerun is claimed.  The
committed P7.2 E2E evidence remains the valid install/update/idempotence/rollback proof.

## Ownership, rollback, and protected-path result

- Every bootstrap/managed classification and its pre-hash is in
  `artifacts/P7-bootstrap-cleanup.md`; no ownership is guessed and no residual path is
  classified as removable.
- Rollback pointer: P7.2 D123 restores `.codex/hooks.json` to
  `7d7538d021228e8e61d124f4b60b6db04434f8121de30b8672f05e4bf038c3db` and keeps
  `.swissknife.json`, `.swissknifeman/provider-artifacts.lock.json`, and
  `.codex/hooks/lifecycle.py` absent.  No P7.3 rollback is needed because P7.3 wrote no
  provider target.
- Protected `plans/2026.07.18-FOREMAN/**`, `plans/ACTIVE.md`, fleet carriers,
  `.serena/project.yml`, and all bootstrap/Claude compatibility carriers have P7.3 delta 0.
  The only unrelated existing worktree changes are `AGENTS.md` and `.serena/project.yml`;
  neither is included in this candidate.

## Residual conditions

1. The bootstrap set is deliberately retained, not silently treated as generated or deleted.
2. P7.2's owner-required no-launch handoff schema remains two inherited lint errors.  It is
   visible and makes P7.3 `🟠`, not GREEN.
3. This candidate requires P7.4's independent adversarial verdict before any FOREMAN gate;
   no release claim is made here.
