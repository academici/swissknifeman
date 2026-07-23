# P6.12 D108 independent conformance — GREEN after D115

**Observed:** 2026-07-22  
**Tree:** `d1a7c6ea` (P6.11 bookkeeping anchor)  
**Mode:** frozen-input oracle, disposable roots, then real-root read-only planning with a
writer spy. No live apply, repair or rollback was invoked.

## Independent oracle

Before running the P6.11 implementation, the frozen D108 inputs require all of the following:

- project carrier adds/enables `claude-code` and `codex` at
  `.swissknife.json#/providers` only;
- the exact live `.mcp.json` preimage is
  `cf4537196c3fefd6fd3980221bd3677f74e7867392ad49364e1e891e1f7c8283`;
- the exact live D104 hooks preimage is
  `7d7538d021228e8e61d124f4b60b6db04434f8121de30b8672f05e4bf038c3db`;
- planning must form both provider projections, D104 and the chained three-record lock before
  a writer is reachable; a dry reader must therefore classify this root or fail only at a
  frozen candidate check, never at package-root identity or a missing Codex projection.

The P2.7 public regression suite independently passed `26` tests at this worktree:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 -m unittest discover -v -s core/tests -p 'test_provider_lock.py'
```

It includes the exact D108 chained-admission mutation, stale-precondition, every-write-boundary
rollback, ordered-three-record-lock and second-plan-noop cases. The P6.11 package-local suite
also passed `46` tests:

```text
cd packages/maind
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=../..:lib:../harness/lib \
  python3 -m unittest -v tests.test_provider_deploy tests.test_deploy
```

Those passing disposable-root regressions do not make the real-root reader conformant.

## Real-root dry-reader reproduction — RED

The following read-only reproducer uses the effective project configuration and the public
P6 provision facade. `dry=True` suppresses `apply_d108_operation`; a mock at that writer seam
records its call count. The explicit inventory is hashed before and after.

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/maind/lib:packages/harness/lib:. python3 -c '<see P6.12 Completion Notes for the exact command carrier>'
```

Observed results:

| Reader | Result | Writer calls | Protected inventory |
|:--|:--|:--:|:--|
| direct `plan_d108_operation(..., expected_root=<repo root>)` | `MAIND_PROVIDER_DEPLOY_REFUSED` | 0 | unchanged |
| public `deploy_project(..., d108=True, dry=True)` | `MAIND_D108_FOREIGN_PROJECT` | 0 | unchanged |

The direct decomposition proves two independent owning-seam faults before any write:

1. `provider_projection_context` resolves the current root before the planned D108 carrier.
   It supplies only `claude-code`; after the carrier correctly selects both providers,
   `plan_provider_deploy` has no Codex base projection and returns a failed row. This becomes
   `MAIND_PROVIDER_DEPLOY_REFUSED`.
2. The public facade passes `expected_root=env.root`; under the worktree-local maind launcher
   that value is `packages/maind`, not the selected project root
   `/home/vostrikov/projects/packages/swissknifeman`. The canonical-project gate consequently
   returns `MAIND_D108_FOREIGN_PROJECT` before it can classify the exact candidate.

The before/after sorted SHA-256 inventory was identical:

```text
.codex/config.toml 68df0b5bcc069ce64c24aeb63c2bb08773219dff83526398ddba247dee6fb2bc
.codex/hooks.json 7d7538d021228e8e61d124f4b60b6db04434f8121de30b8672f05e4bf038c3db
.mcp.json cf4537196c3fefd6fd3980221bd3677f74e7867392ad49364e1e891e1f7c8283
```

Absent before and after: `.swissknife.json`, `.codex/hooks/lifecycle.py`, and
`.swissknifeman/provider-artifacts.lock.json`.

## Attempt 2 after D112 — RED

**Observed:** 2026-07-22  
**Tree:** `279f1a54` (D112 P6.11 handoff correction)  
**Mode:** the same independent frozen-input oracle; disposable-root tests plus one real-root
`dry=True` public-facade reader. No live apply, repair, or rollback was invoked.

The frozen D108 candidate still has the exact `.mcp.json` preimage
`sha256:cf4537196c3fefd6fd3980221bd3677f74e7867392ad49364e1e891e1f7c8283`, whole-file
boundary and server IDs `maind`, `perplexity-web`, `serena`. D112 is independently visible:
the carrier plans the dual Claude Code + Codex tuple from the configured canonical root.
The composed chain nevertheless refuses before a writer because the Claude artifact rendered by
the P6 semantic inventory has SHA-256
`07a033b440f0d2d3031b4b656601b648f33a238cc138e5a9dee95485fe342c95` and server IDs
`maind`, `codegraph`, `perplexity`, rather than the sealed D108 expected bytes and IDs.
`plan_chained_bootstrap_transfer` therefore returns
`chained-bootstrap-mcp-expected-invalid` for all three records; the public reader reports
`MAIND_D108_CHAIN_REFUSED`.

Focused committed regressions remain green: the P2.7 provider-lock suite passed 26 tests and
the P6.11 provider/deploy suites passed 49 tests. The real-root reader patched
`apply_d108_operation`; its writer count was `0`, and the before/after protected inventory was
identical: `.mcp.json` `cf4537196c3fefd6fd3980221bd3677f74e7867392ad49364e1e891e1f7c8283`,
`.codex/hooks.json` `7d7538d021228e8e61d124f4b60b6db04434f8121de30b8672f05e4bf038c3db`, and
`.codex/config.toml` `68df0b5bcc069ce64c24aeb63c2bb08773219dff83526398ddba247dee6fb2bc`.

**Required bounded repair:** reopen only the P6.11 semantic-inventory/render seam so its
planned Claude `.mcp.json` artifact is byte-identical to the sealed D108 candidate and exposes
exactly `maind`, `perplexity-web`, `serena`; preserve D112 canonical-root and planned-dual
behavior. No frozen D108 value, P2 ownership rule, live carrier, P7, FOREMAN, fleet, tag, push,
or cleanup authority changes.

## Required bounded repair

Reopen only P6.11's project-operation seam. Its fix must construct provider base projections
for the D108 planned dual selection before asking `plan_d108_operation`, and pass the canonical
project root (not the maind package root) as `expected_root`. Add a focused real-facade
temporary-root regression that proves the exact D108 plan reaches the three-record chain,
fault injection still restores bytes, and dry live reading returns the exact candidate with
writer count `0`. Do not change P2 ownership, frozen D108 values, live carriers, P7.2, FOREMAN,
fleet, tag or push.

## Attempt 3 after D114 — RED

**Observed:** 2026-07-22
**Tree:** `c5d9490b` (D114 P6.11 bookkeeping anchor)
**Mode:** the frozen-input oracle was rerun on disposable suites, then once against the
real root through `deploy_project(..., d108=True, dry=True)` with a spy on
`apply_d108_operation`. No live apply, repair, rollback or carrier write was invoked.

The two focused disposable suites passed: maind provider/deploy `50` tests and P2.7
provider-lock `26` tests. The real-root candidate still refuses before the writer:
`MAIND_D108_CHAIN_REFUSED`, writer calls `0`, and the sorted protected inventory is identical
before and after: `.mcp.json` =
`cf4537196c3fefd6fd3980221bd3677f74e7867392ad49364e1e891e1f7c8283`,
`.codex/hooks.json` =
`7d7538d021228e8e61d124f4b60b6db04434f8121de30b8672f05e4bf038c3db`,
`.codex/config.toml` =
`68df0b5bcc069ce64c24aeb63c2bb08773219dff83526398ddba247dee6fb2bc`; the project carrier,
lifecycle handler and provider lock remain absent.

D114 corrected the required server identities: both planned and sealed candidates contain
exactly `maind`, `perplexity-web`, `serena`. The remaining byte mismatch is structural and
isolated to the `maind` binding/order, not any secret value:

| Field | Planned Claude artifact | Sealed live preimage |
|:--|:--|:--|
| SHA-256 / bytes / newline | `3511535210edfd79586c7ca47239c14bae36d03bca80f3ff1e7d5f8889bf7518` / 711 / no | `cf4537196c3fefd6fd3980221bd3677f74e7867392ad49364e1e891e1f7c8283` / 725 / no |
| `mcpServers` order | `maind`, `serena`, `perplexity-web` | `maind`, `perplexity-web`, `serena` |
| `maind.command` | `maind` | `${MAIND_BIN:-maind}` |
| `maind.args` | `mcp`, `--scope`, `project:swissknifeman` | identical |
| `perplexity-web` binding | identical command/args/keys | identical command/args/keys |
| `serena` binding | identical command/args/keys | identical command/args/keys |

The P2 chain consequently emits `ownership-conflict / chained-bootstrap-mcp-expected-invalid`
for all three declared targets before any transaction write. The smallest owning seam is P6.11
semantic inventory/rendering of the D108 Claude `.mcp.json` candidate: it must reproduce the
sealed preimage bytes (including the existing `maind` command form and ordering) in a disposable
real-binding regression, without changing D108/P2 constants, the live carrier or authority.

## Attempt 4 after D115 — GREEN

**Observed:** 2026-07-22
**Tree:** `822234be` (D115 P6.11 exact unchanged-MCP repair)
**Mode:** targeted frozen-input tests plus one real-root public dry reader with a writer spy.

D115 keeps ordinary rendering unchanged. Only the sealed D108 transaction projects the existing
regular `.mcp.json` bytes as its explicit `NOOP` artifact and refreshes the immutable provenance
rendered hash; the closed P2 planner still rejects every digest, server set, path or boundary
other than D108. A changed-byte temporary candidate is refused before write.

Targeted validation is GREEN:

- maind provider/deploy: `51/51` passed;
- core P2.7 provider-lock: `26/26` passed, including every-write-boundary rollback and second-run
  noop;
- `py_compile` and `git diff --check`: passed.

The public real-root `deploy_project(..., d108=True, dry=True)` reader returned:

| Check | Result |
|:--|:--|
| writer calls | `0` |
| protected SHA inventory | unchanged |
| bootstrap status | `admitted` |
| provider plan | `GREEN` |
| Claude server IDs | `maind`, `serena`, `perplexity-web` (exact set) |
| Claude rendered SHA-256 | `cf4537196c3fefd6fd3980221bd3677f74e7867392ad49364e1e891e1f7c8283` |
| sealed `.mcp.json` SHA-256 | `cf4537196c3fefd6fd3980221bd3677f74e7867392ad49364e1e891e1f7c8283` |

No `.swissknife.json`, lifecycle handler, provider lock or other live target was created or
changed. P6.12 is therefore GREEN for the D108 rollback/no-write boundary. Phase close, final
audit and every P7/live action remain separate work.

## D122 independent post-apply proof — RED

**Observed:** 2026-07-23
**Source anchor:** `5830e631` (`fix(maind): принять точный D104 post-apply noop`)
**Mode:** independently constructed disposable roots, followed by one public real-root
`dry=True` reader with its D108 writer patched to a spy. No real-root apply, repair,
rollback, cleanup, or P7.2 retry was invoked.

The frozen root inputs still match their sealed bytes: `.codex/hooks.json` SHA-256 is
`7d7538d021228e8e61d124f4b60b6db04434f8121de30b8672f05e4bf038c3db` and `.mcp.json`
SHA-256 is `cf4537196c3fefd6fd3980221bd3677f74e7867392ad49364e1e891e1f7c8283`. The
current carrier, lifecycle handler and canonical provider lock are absent.

### Disposable-root oracle — GREEN

The oracle seeded only those two sealed preimages, constructed the frozen
`claude-code` + `codex` project selection and exact server set `maind`,
`perplexity-web`, `serena`, then performed the first D108 operation.

| Case | Result |
|:--|:--|
| exact managed two-group post-apply form | second chain actions are `noop`, `noop`, `noop`; `apply_d108_operation` called its writer `0` times and the complete temporary-root SHA inventory was identical before/after |
| reordered groups | `MAIND_PROVIDER_DEPLOY_REFUSED`; writer `0`; inventory identical |
| extra observer group | `MAIND_PROVIDER_DEPLOY_REFUSED`; writer `0`; inventory identical |
| changed observer command | `MAIND_PROVIDER_DEPLOY_REFUSED`; writer `0`; inventory identical |
| malformed observer group | `MAIND_PROVIDER_DEPLOY_REFUSED`; writer `0`; inventory identical |
| changed memory command | `MAIND_D108_CHAIN_REFUSED`; writer `0`; inventory identical |
| changed handler, lock, or MCP preimage | `MAIND_D108_CHAIN_REFUSED`; writer `0`; inventory identical |

The changed-memory and protected-artifact cases retain the pre-existing D108 chained-plan
refusal diagnostic; none reaches a writer. This preserves the D104/D108 fail-closed boundary.

Focused committed regressions also passed at `5830e631`:

```text
cd packages/maind
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=../..:lib:../harness/lib \
  python3 -m unittest -v tests.test_provider_deploy tests.test_deploy
# Ran 53 tests — OK

cd ../..
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  python3 -m unittest discover -v -s core/tests -p 'test_provider_lock.py'
# Ran 26 tests — OK

PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile \
  packages/maind/lib/maind/provider_deploy.py \
  packages/maind/lib/maind/provision/deploy.py
```

### Real-root dry reader — RED, fail-closed with zero writes

The public `deploy_project(..., d108=True, dry=True)` reader was invoked with the canonical
configured `swissknifeman` root and a spy on `apply_d108_operation`. It refused before that
writer: `plan_d104_bootstrap_transfer` returned `bootstrap-backup-present` for both D104
records, so the composed public result is `MAIND_D108_CHAIN_REFUSED`. Writer count is `0` and
the protected inventory before/after is identical.

The exact blockers are ignored rollback residue, not a changed sealed target or lock:

```text
.codex/hooks.json.provider-artifact.bootstrap-transfer.bak
  mtime 2026-07-23 08:54:59 +0300
  sha256 7d7538d021228e8e61d124f4b60b6db04434f8121de30b8672f05e4bf038c3db
  byte-identical to .codex/hooks.json
.mcp.json.provider-artifact.bootstrap-transfer.bak
  mtime 2026-07-23 08:54:59 +0300
  sha256 cf4537196c3fefd6fd3980221bd3677f74e7867392ad49364e1e891e1f7c8283
  byte-identical to .mcp.json
```

Both names are ignored by `.gitignore:52` (`*.bak`) and timestamped inside the D121 first
apply/rollback window. They are outside the P7 evidence's listed restored target inventory,
but their existence is an explicit P2 admission predicate. Do not delete, adopt, or normalize
them in P6.12. The owning rollback/backup-lifecycle seam requires bounded fix-forward design
before a fresh P7.2 first-preflight run.

**Verdict:** RED — D122 itself proves exact post-apply idempotence and fail-closed mutations,
but the real-root D108 initial candidate cannot be admitted while the D121 rollback backups
remain. P7.2 remains blocked; no phase close or audit follows this result.

## D123 independent rollback replay — GREEN

**Observed:** 2026-07-23
**Source anchor:** `52374d40` (`fix: закрыть lifecycle rollback D108`)
**Mode:** an independent literal oracle seeded task-scoped `TemporaryDirectory` roots with the
sealed D104 hooks preimage SHA-256
`7d7538d021228e8e61d124f4b60b6db04434f8121de30b8672f05e4bf038c3db` and the sealed unchanged
MCP preimage SHA-256
`cf4537196c3fefd6fd3980221bd3677f74e7867392ad49364e1e891e1f7c8283`. The only disposable
mutation was one planned D108 apply followed by the new explicit rollback entry point. The real
repository was inspected only through `deploy_project(..., d108=True, dry=True)` with its
`apply_d108_operation` seam patched to a spy.

### Disposable-root explicit rollback — GREEN

The oracle starts from the two sealed files plus a sibling-bearing
`.swissknife.json`, constructs the exact three-server tuple `maind`, `perplexity-web`, `serena`,
and records a sorted SHA-256 inventory. After apply, exactly these two and no other `*.bak`
paths exist:

```text
.codex/hooks.json.provider-artifact.bootstrap-transfer.bak
.mcp.json.provider-artifact.bootstrap-transfer.bak
```

Each has the SHA-256 of its respective sealed preimage. The independently replanned second D108
operation has a unchanged carrier and three `noop` actions; applying that second plan calls its
writer `0` times and preserves the inventory. The explicit rollback then restores the complete
initial inventory byte-for-byte, including the original project-carrier bytes, and leaves both
named backup paths absent.

The same oracle mutates one completed state at a time: missing hook backup, extra handler
backup, byte-different MCP backup, symlinked hook backup, changed lock, changed handler, and
changed carrier. Each explicit rollback refuses before its first core writer call (`0`) and
leaves the complete malformed-state inventory unchanged. This proves a closed exact set, not
a glob, adoption, or normalization path.

### Focused regressions — GREEN

At `52374d40`, the focused P2.7 provider-lock carrier passed `28/28` and the package-local
mAInd provider/deploy carrier passed `55/55`:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  python3 -m unittest discover -v -s core/tests -p 'test_provider_lock.py'

cd packages/maind
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=../..:lib:../harness/lib \
  python3 -m unittest -v tests.test_provider_deploy tests.test_deploy
```

`PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile` for the D123 core/mAInd modules and both
`git diff --check 52374d40..HEAD` and the current worktree passed.

### Real-root dry reader — GREEN, zero writes and no residue

The public dry reader used the effective `config.json` project record whose canonical local path
is this repository. Its writer spy recorded `0` calls. Its sorted before/after protected
inventory was identical, the bootstrap projection was `admitted`, and the dual provider plan
was `GREEN`. Neither named backup path existed before or after.

```text
.codex/config.toml  68df0b5bcc069ce64c24aeb63c2bb08773219dff83526398ddba247dee6fb2bc
.codex/hooks.json   7d7538d021228e8e61d124f4b60b6db04434f8121de30b8672f05e4bf038c3db
.mcp.json           cf4537196c3fefd6fd3980221bd3677f74e7867392ad49364e1e891e1f7c8283
.codex/hooks/lifecycle.py                         absent
.swissknife.json                                  absent
.swissknifeman/provider-artifacts.lock.json       absent
.codex/hooks.json.provider-artifact.bootstrap-transfer.bak  absent
.mcp.json.provider-artifact.bootstrap-transfer.bak           absent
```

**Verdict:** GREEN for the D123 P6.12 independent replay. This evidence does not run P7.2,
authorize a live apply/repair/rollback, or authorize P7.3+, FOREMAN, fleet, tag, push or
cleanup. P6.11 bookkeeping and the subsequent phase gates remain separate work.
