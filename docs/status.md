# Capability status

Fleet Capability Maturity Matrix - not «is the command», a «proven to work». Values
`Maturity` — dictionary from `general/plan-protocol` § Statuses (EN-canon,
`packages/skiller/skills/general/plan-protocol/SKILL.md` § Capability maturity), byte-for-byte:
`available` · `experimental` · `behind-gate` · `disabled` · `superseded`. Checking
`scripts/status-check.py`; step `status-check` in CI-job `hygiene`.

## Matrix

| Package | Opportunity | Maturity | Evidence / boundary |
|:--|:--|:--|:--|
| swissknifeman (router) | `swissknifeman <group>` — fan-out in packages | available | `./bin/swissknifeman --help` prints all groups (skills/env/maind/analyst/setup/doctor/status/wf/release) |
| swissknifeman (router) | `swissknifeman doctor` — fleet diagnostics | available | fan-out in `doctor` of each package; checked by reading `bin/swissknifeman` |
| skiller | `connect` — distribution of skills through plugin marketplace | available | `packages/skiller/bin/skiller status --target .` — channel `marketplace`, enabled buckets visible in output |
| skiller | `vendor`/`sync` — physical. transferring skills to the project | experimental | is not used by this repo (channel - connect); covered in tests `packages/skiller/tests/test_skillset.py`, not tested on a real third-party project with this approach |
| skiller | `registry` — regeneration `skills.json`/marketplace/graph | available | `bash packages/skiller/scripts/validate.sh` drives away `registry --check` |
| skiller | `budget` — token budget for skill set | available | `packages/skiller/bin/skiller status --target .` prints the budget line (`⊕ always … · ↻ bodies …`) |
| skiller | `budget --first-turn --with-plugins` — full price of the first move | available | `packages/skiller/bin/skiller budget --first-turn --with-plugins --target .` prints project and plugin components; `broken`/`unparsed` are not masked by zero |
| skiller | native scope Claude Code for procedural skills | experimental | `context: fork` tested on four skills through explicit and auto-trigger; `paths:` is not deliberately rolled out, but `when_to_use` is undergoing a joint listing gate |
| skiller | `eval` — behavioral skill run (with-skill vs baseline) | behind-gate | requires `claude -p` (external model call) — does not race in CI; is turned on manually using a skill (`skiller eval <skill>`) |
| skiller | framework canon - gate for freshness of pack versions (`framework-overview.md` vs `pack.json`) | available | `bash packages/skiller/scripts/validate.sh` — «framework canon: table «pack → version» matches pack.json (10 packs)»; proven by both sides: real drift `_common 0.4.1` vs fact. `0.5.0` caught by this run and painted ERROR before editing the line |
| skiller | `budget --provider` — second (provider-aware) detection budget model | behind-gate | `packages/skiller/bin/skiller budget --target. --provider codex` — «BREAKTHROUGH (×1.1)» on this repo's profile; WARN-gate in `validate.sh` — structural search of listing, not «works without reservations» |
| harness | `permissions` — pour in presets in `.claude/settings*.json` | available | `packages/harness/bin/harness doctor` confirms the presence of all presets |
| harness | `mcp` — pour in MCP-presets in `.mcp.json` | available | `packages/harness/bin/harness doctor` — 9 MCP-presets in place |
| harness | `hooks` — installing hooks (auto-approve/memory/router/run-report) | experimental | `harness doctor` calls the border itself: «hook run-report rotten (`_lib.py`) — repeat `harness hooks --global`» — known drift, not hidden |
| harness | `agent-packs` — deterministic rendering of subagent packs | available | `packages/harness/bin/harness doctor` lists 10 installed packages |
| harness | `instructions` — canon of root instructions (`plan\|check\|adopt\|apply\|repair`) | available | `harness instructions check` — «OK — 12 targets», all `clean/noop`; live transaction acceptance on 12 targets has already been passed |
| core | provider control plane — provider-qualified support and no-write operator checks | available | `python3 scripts/provider-docs.py --check`, `harness doctor --provider-audit --json`, and P7.2 regression gates keep manifest, diagnostics, and generated reference aligned; `native`/`adapted`/`unsupported` stay distinct |
| core | provider release candidate — P7.3 evidence manifest | behind-gate | D88 defers live Claude efficacy and external P5/P6 rollout; the current non-empty release-blocker set makes the candidate explicitly non-releasable and grants no tag/push/publish authority |
| harness | `hooks --provider codex` — Codex lifecycle/context class observers and gates B | behind-gate | `harness hooks --target <repo> --provider codex --observer --safe-dirs --daemon-safety --trusted --dry-run` — plan is being built (`3 surface(s)`), but round-trip with live Codex CLI was not checked - the boundary is separately named in `configs/provider-capabilities.json` |
| harness | `execution-policy` — declarative execution policy (media + `execpolicy.py`) | available | `PYTHONPATH=packages/harness/lib python3 -m harness.execpolicy --check` — «OK — 7 checks»; step `[10/10]` in `validate.sh`; enforcement still through the consumer (grammar PLAN), not automatic |
| harness | `swissknifeman env run <PLAN-ID> Pn` — serial exec-wave | available | `packages/harness/bin/harness run --dry-run` builds a queue without an entry; through run P4.6 on an isolated fixture performed two item’and live workers |
| maind | `memory` — memory daemon (agentmemory) | available | `packages/maind/bin/maind status` — «memory: running - http://127.0.0.1:4111» |
| maind | `graph` — cross-project graph federation | available | `packages/maind/bin/maind status` — «graph: federation — 294 nodes, 1019 edges» (numbers float, command is reproducible) |
| maind | `agents` — register of living subagents | behind-gate | `maind status` — «agents: 0 alive / 0 total» at the time of editing: there is a mechanism, there are no live registrations now - requires an active registrant session |
| maind | `onboard`/`sync`/`deploy` — rolling out artifacts for fleet projects | available | `packages/maind/bin/maind status` — «projects: 25 (connected: 22)»; rollout is playing `maind sync --only <artefact> --dry-run` |
| analyst | `digest`/`review`/`promote` — pipeline continuous learning (human-gate) | available | `packages/analyst/bin/analyst status --project .` — 5 lessons in `ephemeral`, counters by stage |
| analyst | `scan`/`suggest` — cross-project patterns → skill draft | experimental | P2/P3 by roadmap package (`packages/analyst/CLAUDE.md`): there is a mechanism, cross-project running was not performed with this repo |
| task | `/task:plan-*` — executable master plans | available | same document - product `/task:plan-run`; `packages/task/scripts/validate.sh` green |
| task | `plan.py check` — plan integrity (schema, refs, cycles, completeness, fresh views) | available | `python3 packages/task/scripts/plan.py check <PLAN>`; `packages/task/tests/engine/` and `packages/task/scripts/validate.sh --plan <dir>` green |
| task | `plan.py start`/`finish` — route pool, dependency and acceptance gate | available | `python3 packages/task/scripts/plan.py start <PLAN> <item> --actor <provider>/<model>` refuses an undershoot route; `finish --status done` needs recorded acceptance checks; `packages/task/tests/engine/test_lifecycle.py` |
| core | `core.io` — atomic record (tmp + `os.replace`) | available | `PYTHONPATH=. python3 -m unittest discover -s core/tests` |
| core | `core.repo` — unified repo root search/monorepo | available | is used by the launchers of all five packages (`find_repo_root`/`find_monorepo_root`), covered `core/tests/test_core.py` |

## What risks are covered by the checks

This map associates the mechanism with the fault being tested. Status `available` above does not mean
that all properties are tested on a live client or when the power is turned off.

| Crash | Mechanism and automatic verification | Limit of proof / field check |
|:--|:--|:--|
| Someone else's file is overwritten by projection | `core.provider.lock` fails when ownership conflict and managed drift; `core/tests/provider/test_lock.py`, `packages/harness/tests/test_provider_instructions.py` | Checks are performed in isolated directories; see the actual active projection of a specific project via `skiller doctor --effective-source --json` and provider audit. |
| Two local writer'a or deceased holder left lock | `flock` serializes records; `core/tests/provider/test_lock.py` checks for contention and release after `SIGKILL` | This is the semantics of one Linux-host with local FS; NFS/SMB and the atomicity of several provider-files were not proven by this test. |
| Scheduled item closed incorrectly GREEN | `plan.py finish` records acceptance checks with exit codes and refuses `done` without them (`CHECKS_MISSING`/`CHECKS_RED`); `packages/task/tests/engine/test_lifecycle.py` | Tests do not replace live execution of the declared validation and checking the result by the user; direct tasks outside Task do not go through `finish`. |
| Release delivery diverged from tag | `verify-tag`, release attestation and `release-fleet` check local delivery; `packages/skiller/tests/test_release_attestation.py` | Publication GitHub Release — separate operation; presence of tag and local receipt does not prove it. |
| The secret was in the monitored file | `scripts/public-hygiene.py` prohibits names of keys and private artifacts | This is a check **file names**, not content. It does not prove the absence of secrets in JSON, shell-scripts or examples. |

## Known limitations

- **Visible CLI-group does not prove that its runtime is enabled.** Command presence in `--help`
  (for example, `skiller vendor` or `maind agents`) does not mean that the path was executed on real
  data from this repo - only that the interface exists. String `Evidence / boundary` obliged
  name WHAT exactly has been checked, rather than retelling the presence of the command.
- **The boundary of the matrix itself.** She catches dishonest maturity (stated `available`, but in reality no
  reproducible evidence) — but does NOT catch the missed opportunity: checking completeness with
  list of real package capabilities (reception D2, `Scope Excluded` this item'a) is delayed and not
  runs here. List of matrix rows - a selection of significant possibilities, not exhaustive
  directory.
