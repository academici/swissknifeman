---
type: contract
plan: 2026.07.29-HARNESS-AGNOSTIC
contract: codex-parity-verdicts
status: sealed (P2.1)
version: v1
basis: "plans/archive/2026.07.29-HARNESS-AGNOSTIC/root/contracts/provider-parity-definition.md (sealed P0.4) §1 verdict enum, §2 evidence bar, §5 both-provider outcome, §7 self-check; plans/archive/2026.07.29-HARNESS-AGNOSTIC/research/06-codex-parity-triage-groundwork.md §1-§5 candidate map; plans/archive/2026.07.29-HARNESS-AGNOSTIC/findings/03-rag-codex-capability-surfaces-2026-07-29.md Ф9/Ф10/Ф11/Ф12; plan.md D3/D18-D22/D56 and D86-D89"
consumers: "P2.2 (class A observers), P2.3 (class B gates), P2.4 (class C carriers and honest claude-only records), P2.5 (conformance artifact and drift gate), P5.1 (release maturity wording), P5.3 (parity acceptance); evidence[] rows of configs/provider-capabilities.json cite this file by its non-archive path (D19)"
verdict: "RAG:— (repo-grounded, tree 2640e8cf: configs/provider-capabilities.json — 35 capabilities, 17 codex unsupported, 3 claude-code unsupported; scripts/provider-docs.py production_requirements() — 170 requirement rows, 0 strict consumers over all 17; packages/harness/lib/harness/hooks.py:84-230; packages/harness/lib/harness/provider_audit.py:244-260,341-382; core/provider_manifest.py:331-383; packages/harness/configs/claude-code/settings.global.json; packages/harness/scripts/apply-permissions.sh:61-73; packages/harness/lib/harness/{wf_status,settings_audit,agentpacks,safedirs}.py; .github/workflows/test.yml:15) · RAG:✅ 2026-07-29 findings/03 Ф9/Ф10/Ф11 (first-party learn.chatgpt.com/docs/**) · RAG:✅ 2026-07-30 code.claude.com/docs/en/hooks (WebFetch — Stop/SubagentStop exit-2 semantics, see §5)"
---

# Contract: Codex parity verdicts (v1)

**Purpose.** One verdict per `unsupported` support record of the frozen capability catalog,
drawn from the closed enum of `provider-parity-definition` §1 — `closed-by-adapter` ·
`claude-only` · `intent-withdrawn` — together with the named native Codex carrier, the
evidence the executing item must produce, and a draft `limitations` text that can be pasted
into the manifest as is. The document also seals the single decision every class A and class
B adapter of this phase depends on: where the logic of Codex lifecycle handlers lives (§1).

**Why it exists.** "Catch up on Codex parity" (D3) is only executable record by record.
Without a per-record verdict the phase degrades into closing whatever is cheap, and the
remaining `unsupported` rows keep the boilerplate cause text "no committed native binding or
deterministic adapter satisfies the frozen surface intent" — which is false for at least two
records (§4) and unfalsifiable for the rest.

**What this document does not do.** It changes no manifest level, no binding, no code and no
generated document; it introduces no capability ID, no fourth support level and no change of
`contract_version`/`catalog_version`/provider precedence. Every row names the item that
executes it.

## 0. Measured scope

Anchor tree `2640e8cf` (worktree `swissknifeman-next`, branch `next/harness-agnostic`).

| Measurement | Command | Result |
|:--|:--|:--|
| catalog size, unsupported per provider | `python3 -c "import json; m=json.load(open('configs/provider-capabilities.json')); print(len(m['capabilities']), sum(c['support']['codex']['level']=='unsupported' for c in m['capabilities']), sum(c['support']['claude-code']['level']=='unsupported' for c in m['capabilities']))"` | `35 17 3` |
| catalog and generated documents coherent before the triage | `python3 scripts/provider-docs.py --check` | exit 0 |
| consumer requirement rows (probe C3 of the sealed definition) | `production_requirements()` of `scripts/provider-docs.py` | 170 rows total; for each of the 17 records: 2 rows (`harness.provider-audit`, or `analyst.provider-reader` for `analytics.legacy-migration`), **strict rows 0** |

The C3 result is load-bearing in one direction only: zero strict consumers make
`claude-only` and `intent-withdrawn` *structurally legal* for all 17 records
(`provider-parity-definition` §1, enforcement rule). It does not make them *honest* — the
anti-fitting rule of this item forbids a `claude-only` verdict wherever a carrier exists,
regardless of what the consumer probe permits. That is why 12 of 17 rows below are
`closed-by-adapter`.

Scope of the triage is the 17 Codex `unsupported` records. The third Claude-side
`unsupported` record, `context.observer` (`native` at Codex), is a mirror gap outside D3 and
is deliberately not triaged here (`phases/P2.md` Phase Context). The two records that are
`unsupported` at *both* providers are triaged for both halves, because their Claude half
turned out to be false rather than empty (§4).

Verdict distribution: **`closed-by-adapter` 12 · `claude-only` 5 · `intent-withdrawn` 0**.

## 1. Where the logic of Codex lifecycle handlers lives (OQ-6 → D86)

**Decision: variant A — the self-contained generated dispatcher is the home**, with two
binding rules and one named exception.

1. **One generator, one dispatcher.** `render_codex_hook_handler()` becomes a single
   generator function with a per-surface handler table; a copy of the argument parsing,
   payload validation or exit discipline per surface is a defect, not an implementation.
   The rendered artifact stays exactly one file, `.codex/hooks/lifecycle.py`, invoked as
   `--surface <id>` by `render_codex_hooks` (`hooks.py:183-197`), and it remains fail-closed:
   unknown surface, malformed JSON or a missing field required for the event → `sys.exit(2)`
   with no side effect.
2. **Divergence is recorded, never hidden.** Where the generated handler cannot reproduce
   what the installed Claude-side script does, the loss is named in `limitations` of that
   record. Silence is what makes a `adapted` record decorative.
3. **Named exception — a verdict core that already exists once in the repository is called,
   not copied.** Today this is exactly one surface: `security.safe-dirs`, whose allowlist
   verdict core is `packages/harness/configs/claude-code/hooks/auto-approve/lib/safedirs.py`
   (355 lines) and is already reused by the CLI manager through module loading
   (`lib/harness/safedirs.py` docstring: "ПОЛНОСТЬЮ переиспользует containment-код хука
   (`_hook_module`) — не второй source of truth"). The Codex handler resolves the monorepo
   root the same way that core itself does (realpath of the launcher on `PATH`) and calls it;
   the config search ladder is untouched, and an unresolvable core means `sys.exit(2)`.

**Why not the alternatives** (`research/06` §4, `plan.md` § Обсуждение №5):

- **Variant B — a thin adapter over the installed Claude implementation** (`~/.claude/hooks/**`)
  is rejected: it makes the second provider depend on the first provider's installed tree,
  which is the exact one-sidedness this plan repairs, and it breaks wherever the Claude hooks
  were never installed.
- **Variant C — a neutral home `configs/common/hooks/<surface>/` called by both sides** is
  rejected for this phase: it changes paths of already installed Claude hooks, which
  `packages/harness/CLAUDE.md` forbids (`harness.cross-package-boundaries` — "never break
  paths already installed on consumers"). Rule 3 above reaches the same single-source-of-truth
  property for the only surface that owns a real verdict core, without moving anything.

Rule 3 is not variant B in disguise: the called path leads into a repository file that the
harness package owns, not into a provider-installed directory, and no installed Claude path
is added, moved or removed. It is also forced by `phases/P2.md` P2.3 Implementation Rules,
which already demand that the Codex handler call "ту же реализацию" of the safe-dirs verdict.

## 2. Verdict table (17 records)

`adapter_id` column is the identifier the executing item must write into the manifest;
`level` after execution is `adapted` for every `closed-by-adapter` row (no row earns
`native`, because every one of them is a deterministic harness adapter rather than a provider
configuration binding) and stays `unsupported` for every `claude-only` row (D20 — that is not
a level).

| # | Capability | Class | Verdict | Native Codex carrier | `adapter_id` after closure | Item |
|:--|:--|:--|:--|:--|:--|:--|
| 1 | `lifecycle.command-log` | A | `closed-by-adapter` | `PreToolUse`, matcher `^Bash$`, fields `tool_name`/`tool_input` (Ф9) | `harness.codex.lifecycle.command-log` | P2.2 |
| 2 | `lifecycle.run-report` | A | `closed-by-adapter` | `SessionEnd`, fields `reason`/`transcript_path` (Ф9) | `harness.codex.lifecycle.run-report` | P2.2 |
| 3 | `lifecycle.router` | A | `closed-by-adapter` | `UserPromptSubmit`, field `prompt` (Ф9) | `harness.codex.lifecycle.router` | P2.2 |
| 4 | `lifecycle.memory` | A | `closed-by-adapter` | `SessionStart`, field `source` (Ф9) | `harness.codex.lifecycle.memory` | P2.2 |
| 5 | `lifecycle.pack-guard` | B | `closed-by-adapter` | `PreToolUse`, matcher `^apply_patch$` (Ф9 — Codex tool names) | `harness.codex.lifecycle.pack-guard` | P2.3 |
| 6 | `lifecycle.changelog-gate` | B | `closed-by-adapter` | `PreToolUse`, matcher `^Bash$`, refusal `permissionDecision: "deny"` or exit 2 (Ф9) | `harness.codex.lifecycle.changelog-gate` | P2.3 |
| 7 | `lifecycle.review-gate` | B | `closed-by-adapter` | `SubagentStop`, exit 2 = "prevents the subagent from stopping" (Ф9 + §5) | `harness.codex.lifecycle.review-gate` | P2.3 |
| 8 | `security.safe-dirs` | B | `closed-by-adapter` | `PreToolUse` deny over the single allowlist verdict core (§1 rule 3); the `sandbox_workspace_write` half is declined with a reason (§3.8) | `harness.codex.security.safe-dirs` | P2.3 |
| 9 | `lifecycle.daemon-safety` | B (was E) | `closed-by-adapter` (both providers — §4) | Codex: `PreToolUse`, matcher `^Bash$`; Claude: the already shipped global registration, described by a binding | `harness.codex.lifecycle.daemon-safety` · `harness.claude-code.lifecycle.daemon-safety` | P2.3 |
| 10 | `lifecycle.git-guardrails` | B (was E) | `closed-by-adapter` at Codex; Claude half brought to honest form (§4) | Codex: `PreToolUse`, matcher `^Bash$` | `harness.codex.lifecycle.git-guardrails` | P2.3 |
| 11 | `settings.audit` | C | `closed-by-adapter`, bounded (§6) | documented Codex configuration layers `~/.codex/config.toml` → `.codex/config.toml` → profile, plus `projects.<path>.trust_level` (Ф10) | `harness.codex.settings.audit` | P2.4 |
| 12 | `agent-packs.lifecycle` | C | `closed-by-adapter`, bounded (§6) | `.codex/agents/*.toml` (Ф11) through the existing `project_agent_role`/`plan_agent_artifact`/`classify_agent_projection` machinery | `harness.codex.agent-packs.lifecycle` | P2.4 |
| 13 | `lifecycle.notification` | C | `claude-only` | none inside project scope: no `Notification` event (Ф9) and `notify` is user-scope only (Ф10) | — | P2.4 |
| 14 | `workflows.status` | C | `claude-only` | none: the reported object does not exist at Codex (§3.14) | — | P2.4 |
| 15 | `analytics.legacy-migration` | C | `claude-only` | none, and the intent does not apply to the second provider (§3.15) | — | P2.4 |
| 16 | `context.output-style` | D | `claude-only` | none: no such key in the configuration reference (Ф10) | — | P2.4 |
| 17 | `context.plans-directory` | D | `claude-only` | none: no such key in the configuration reference (Ф10) | — | P2.4 |

Class reassignment of rows 9 and 10 from E to B is the substance of §4; classes of the other
15 rows are unchanged from `research/06` §1.

## 3. Per-record detail: evidence to produce and draft `limitations`

Each block gives what the executing item must put into the manifest. `verified_at` is the
date of that item's own run, never copied from here. Every `source` below exists in the tree
at the moment of this verdict (probe C5: `test -e` over each path — all green), and the
canonical `source` of a verdict row is this file's non-archive path (D19).

### 3.1 `lifecycle.command-log` — `closed-by-adapter` (P2.2)

- carrier: `PreToolUse`, matcher `^Bash$`; the payload carries `tool_name`/`tool_input`.
- evidence: `source` = `plans/archive/2026.07.29-HARNESS-AGNOSTIC/root/contracts/codex-parity-verdicts-v1.md`;
  `scope` = "codex lifecycle.command-log surface, hook-native binding on PreToolUse";
  `claim` = "the deterministic adapter `harness.codex.lifecycle.command-log` writes one
  provider-qualified command-log line per matched Bash tool call and is observed as a green
  `surface_map` row for codex".
- draft `limitations`: ["records only tool calls Codex exposes as `Bash`; a shell invocation
  routed through another tool name is out of the log", "writes to a Codex-qualified log path;
  the Claude-side log at `~/.claude/logs/bash-commands.jsonl` is untouched"].

### 3.2 `lifecycle.run-report` — `closed-by-adapter` (P2.2)

- carrier: `SessionEnd`; payload has `reason` (currently always `"other"`) and
  `transcript_path`.
- known cost measured, not guessed: the Claude implementation extracts the run outcome by
  reading the transcript line by line
  (`packages/harness/configs/claude-code/hooks/run-report/run-report.py` docstring), and the
  Codex transcript format is `[UNVERIFIED]` in `findings/03`. The Codex report therefore
  captures the session boundary facts, and the outcome depth stays with the analytics layer,
  which already accepts Codex input: `analytics.normalized-events` is `adapted` at Codex
  through `analyst.codex-capture-reader`, `analytics.run-report` is `adapted` at Codex
  through `analyst.neutral-run-report`, and the capture bundle
  `.codex/hooks/analytics-capture.py` is already rendered by
  `plan_codex_capture_artifact` (`hooks.py:311-337`).
- evidence: `scope` = "codex lifecycle.run-report boundary capture at SessionEnd, without
  transcript-derived outcome extraction"; `claim` = "the deterministic adapter
  `harness.codex.lifecycle.run-report` writes one provider-qualified run record per session
  end from the documented `SessionEnd` payload; the transcript is not parsed".
- draft `limitations`: ["captures the session boundary only: the Codex transcript format is
  unverified, so no outcome is extracted from `transcript_path`", "`reason` is currently
  always `other` in Codex payloads, so the report cannot distinguish end causes", "outcome
  depth comparable to the Claude report requires the neutral analytics path
  (`analytics.run-report`), not this hook"].
- named debt for the phase handoff: measuring the Codex transcript format is the single
  input that would lift this limitation; it is not created by this item and belongs in
  `roadmap/` (it requires a live Codex run, excluded by D3).

### 3.3 `lifecycle.router` — `closed-by-adapter` (P2.2)

- carrier: `UserPromptSubmit` with field `prompt`.
- machine defect this row exposes, to be fixed by P2.2 inside its own scope:
  `adapt_codex_hook_payload` demands `user_input` for `UserPromptSubmit` (`hooks.py:175-176`)
  while the documented Codex field is `prompt` (Ф9), and it demands `permission_mode`
  unconditionally (`hooks.py:168`) while the documentation promises it "for most events". Both
  are already inside P2.2 Scope Included.
- evidence: `scope` = "codex lifecycle.router bias injection on UserPromptSubmit";
  `claim` = "the deterministic adapter `harness.codex.lifecycle.router` emits at most one
  non-authoritative routing bias line per prompt from the shared router catalog and never
  refuses a turn".
- draft `limitations`: ["delivers the bias as `systemMessage`, the form the generated Codex
  handler already uses, not as Claude's `hookSpecificOutput.additionalContext`", "the
  `SessionStart` half of the Claude pair (static policy) is not part of this surface at
  Codex, where `SessionStart` is owned by `context.observer`"].

### 3.4 `lifecycle.memory` — `closed-by-adapter` (P2.2)

- carrier: `SessionStart` (field `source`).
- invariant М10 check required by `plan.md` §2, because the deliverable touches shared state:
  the memory state stays owned by `skiller` under `~/.swissknifeman` and the path is not
  changed; the Codex handler calls the same `maind memory`/`skiller` entry points the Claude
  hook delegates to (`configs/claude-code/hooks/memory/memory.sh` — `MODE=maind` delegates to
  `maind memory`). The item must show that the Claude contour is intact after the change.
- evidence: `scope` = "codex lifecycle.memory activation at SessionStart against unchanged
  `~/.swissknifeman` state ownership"; `claim` = "the deterministic adapter
  `harness.codex.lifecycle.memory` activates the selected memory backend for a Codex session
  without writing memory state itself and without changing state paths owned by skiller".
- draft `limitations`: ["per-project overrides are read from the Codex-side project files;
  Claude's `.claude/memory.*` overrides do not apply to a Codex session", "the backend, its
  groups and its state remain owned by skiller/maind: this surface only activates them"].

### 3.5 `lifecycle.pack-guard` — `closed-by-adapter` (P2.3)

- carrier: `PreToolUse`, matcher `^apply_patch$` (the Codex tool that covers file edits;
  transliterating Claude's `Edit|Write|MultiEdit|NotebookEdit` produces a silently dead hook).
- ordering fact that removes a false dependency: the guard reads the pack lock already
  present in the project (`.claude/agent-pack.lock.json`,
  `configs/claude-code/hooks/pack-guard/pack-guard.py`), so its Codex closure does not wait
  for the Codex pack lifecycle of row 12. A Codex session editing managed assets of a
  Claude-onboarded project is exactly the gap this row closes.
- evidence: `scope` = "codex lifecycle.pack-guard refusal over managed pack assets recorded
  in the project's pack lock"; `claim` = "the deterministic adapter
  `harness.codex.lifecycle.pack-guard` refuses an `apply_patch` over a managed generated
  asset in mode `strict`, warns in `warn`, and is inactive by default".
- draft `limitations`: ["inactive by default; the operator enables a mode explicitly, as on
  the Claude side", "matches only the Codex `apply_patch` tool: a mutation performed through
  a shell command is out of this gate", "any internal error means pass-through, never a
  refusal"].

### 3.6 `lifecycle.changelog-gate` — `closed-by-adapter` (P2.3)

- carrier: `PreToolUse`, matcher `^Bash$`; refusal as `permissionDecision: "deny"` or exit 2
  with a reason on stderr.
- evidence: `scope` = "codex lifecycle.changelog-gate refusal on release-sensitive commits";
  `claim` = "the deterministic adapter `harness.codex.lifecycle.changelog-gate` refuses a
  `git commit` of a release-sensitive type without a staged changelog edit in mode `strict`,
  warns in `warn`, and is inactive by default".
- draft `limitations`: ["inactive by default", "reads the commit type only from a `-m`
  message: an editor-composed message is not inspected", "the non-blocking warning is
  delivered in the Codex output form, which is not byte-identical to Claude's
  `hookSpecificOutput.additionalContext`"].

### 3.7 `lifecycle.review-gate` — `closed-by-adapter` (P2.3)

- carrier: `SubagentStop`. See §5: refusal is expressed as exit 2, whose documented effect is
  identical on both providers — the subagent is prevented from stopping and continues with
  the feedback. The gate is therefore a direct, not an approximated, projection of the Claude
  surface.
- evidence: `scope` = "codex lifecycle.review-gate enforcement at SubagentStop by preventing
  the subagent from stopping"; `claim` = "the deterministic adapter
  `harness.codex.lifecycle.review-gate` runs the project-declared check at SubagentStop and,
  in mode `strict`, exits 2 so the subagent continues with the violation text instead of
  finishing".
- draft `limitations`: ["enforcement means forced continuation with feedback, not
  cancellation of the subagent: neither provider can cancel it from this event", "the
  loop-guard counter lives in the dispatcher, because `stop_hook_active` is documented at
  neither provider as reliable", "inactive by default, and the check command comes only from
  the machine-owned hook configuration"].

### 3.8 `security.safe-dirs` — `closed-by-adapter` (P2.3)

- carrier: `PreToolUse` with a deny verdict, calling the single allowlist verdict core (§1
  rule 3). The config search ladder is unchanged and `<monorepo>/safe-dirs.json` stays
  machine-owned.
- the second, declarative half is **declined here with a reason**, which the sealed
  definition allows explicitly (`phases/P2.md` P2.3: "тест fail-closed на обеих половинах
  либо явный отказ от одной с причиной"): `sandbox_workspace_write.writable_roots` is a
  configuration key of the sandbox axis, and that axis already belongs to a different
  surface — `lifecycle.auto-approval` is `config-native` at Codex with kill switch
  `approval_policy/sandbox_mode`
  (`configs/codex/hooks/lifecycle-context-bindings.json:3`). Projecting `writable_roots` from
  the same allowlist is an additive change of *that* surface, and the frozen bindings schema
  gives one event per surface, so it cannot be carried by this record at all. Deriving it
  from a second source would produce exactly the divergence the rule forbids.
- evidence: `scope` = "codex security.safe-dirs fail-closed refusal over the machine-owned
  allowlist, hook half only"; `claim` = "the deterministic adapter
  `harness.codex.security.safe-dirs` reaches its verdict by calling the single allowlist
  verdict core used by the Claude hook, refuses fail-closed on any doubt, and does not
  project the sandbox configuration half".
- draft `limitations`: ["covers the hook half only: `sandbox_workspace_write.writable_roots`
  is not projected, because the sandbox axis belongs to `lifecycle.auto-approval`", "requires
  the harness checkout reachable from the project, since the verdict core is called rather
  than copied; an unreachable core is a refusal, not a pass", "the allowlist itself stays
  machine-owned and is never written by this surface"].

### 3.9 `lifecycle.daemon-safety` — `closed-by-adapter`, both providers (P2.3)

- Codex carrier: `PreToolUse`, matcher `^Bash$`, reading `tool_input.command` — the same
  shape the shipped implementation already consumes
  (`configs/claude-code/hooks/daemon-safety/block-daemon-ops.sh`).
- Claude half: the implementation is installed by
  `packages/harness/scripts/apply-permissions.sh:71-73` and registered by
  `packages/harness/configs/claude-code/settings.global.json` on `PreToolUse`/`Bash`, so the
  record's current claim "no committed native binding or deterministic adapter satisfies the
  frozen surface intent" is false. The correction is *descriptive* and behaviour-neutral: a
  binding entry that states the registration which already ships, exactly as its three
  siblings from the same preset already do (`lifecycle.command-log`,
  `lifecycle.notification`, `lifecycle.review-gate` — all `global-hook` in
  `_claude_lifecycle_bindings`, all `adapted` in the manifest). No installed path is added,
  moved or removed, and no fleet behaviour changes.
- evidence (Codex): `scope` = "codex lifecycle.daemon-safety refusal on destructive shared-daemon
  commands"; `claim` = "the deterministic adapter `harness.codex.lifecycle.daemon-safety`
  refuses a matched destructive daemon command with exit 2 and a reason, from the same pattern
  set as the shipped Claude hook".
- evidence (Claude): `scope` = "claude-code lifecycle.daemon-safety registration already
  shipped by the harness global preset"; `claim` = "`settings.global.json` registers
  `~/.claude/hooks/daemon-safety/block-daemon-ops.sh` on PreToolUse/Bash and
  `apply-permissions.sh` installs it, so the surface is satisfied by a committed deterministic
  adapter".
- draft `limitations` (both halves): ["pattern-based refusal over declared destructive daemon
  operations: an operation phrased outside the pattern set passes", "the escape hatch stays
  the documented environment kill switch, not a project override"].
- Codex-side extra limitation: ["the pattern set is embedded into the generated dispatcher,
  so a change of the Claude-side patterns requires regenerating the Codex artifact"].

### 3.10 `lifecycle.git-guardrails` — `closed-by-adapter` at Codex; honest Claude half (P2.3)

- Codex carrier: `PreToolUse`, matcher `^Bash$`, inactive by default with an explicit
  operator mode, like the other Codex gates of this phase.
- Claude half stays `unsupported`, and its cause text is corrected to the measured truth: the
  implementation is committed
  (`configs/claude-code/hooks/git-guardrails/block-dangerous-git.sh`, derived from
  `mattpocock/skills`, MIT) but nothing registers or installs it — it appears in no preset, in
  no `apply-permissions.sh` branch and behind no `harness hooks` flag
  (`grep -rn 'git-guardrails' packages/harness/{configs,lib,scripts}` returns only the hook
  directory itself). Shipping a fleet-wide registration would start refusing `git push`,
  `reset --hard` and friends for 25 onboarded projects — a behaviour change of the live
  contour, outside this phase and outside D3.
- evidence (Codex): `scope` = "codex lifecycle.git-guardrails refusal on declared dangerous
  version-control commands"; `claim` = "the deterministic adapter
  `harness.codex.lifecycle.git-guardrails` refuses a matched dangerous git command in mode
  `strict`, warns in `warn`, and is inactive by default".
- draft `limitations` (Claude half, staying `unsupported`): ["the implementation is committed
  but no registration ships: no preset, install branch or operator flag activates it, so the
  surface fails closed", "activating it fleet-wide is a behaviour change of the live contour
  and is not part of the parity phase"].
- named debt for the phase handoff: an opt-in operator flag for the Claude half (the shape
  `--pack-guard`/`--changelog-gate` already use). Home is `roadmap/`, not this phase.

### 3.11 `settings.audit` — `closed-by-adapter`, bounded (P2.4)

- carrier: the documented layer stack `~/.codex/config.toml` → `.codex/config.toml` →
  profile, plus `projects.<path>.trust_level` and `features.hooks` (Ф10). The intent — "read
  layered settings and report named policy conformance" — is closable, because the layers and
  their override boundaries are documented, and Ф10 even supplies a machine-checkable rule of
  its own: a project-scoped file may not override provider, auth, notification, profile
  selection or telemetry keys, so an attempt to do so is a finding.
- the price is measured, not assumed. The Claude auditor is 1 146 lines of Claude-specific
  taxonomy over 13 named checks (`lib/harness/settings_audit.py`, `CHECKS`), and its rules are
  not transferable; the Codex auditor gets its own smaller named check set over the Codex
  layers. Second measured constraint: reading TOML needs `tomllib`, which is stdlib only from
  Python 3.11, while `.github/workflows/test.yml:15` runs the matrix over
  `3.9 … 3.13`, and the repository forbids new runtime dependencies. Therefore the reader is
  fail-soft in the same way the Claude reader is: where the interpreter cannot parse a layer,
  that is reported as an explicit finding, never as conformance. Inventing a second TOML
  parser is out of scope, and raising the interpreter floor is a repository-wide decision this
  item does not take.
- evidence: `scope` = "codex settings.audit over the documented Codex configuration layers,
  Codex-specific check set"; `claim` = "the deterministic adapter
  `harness.codex.settings.audit` reads the documented Codex layers, reports named conformance
  findings with layer provenance, and reports an unreadable layer as a finding instead of
  asserting conformance".
- draft `limitations`: ["the check set is Codex-specific and smaller than the Claude one: the
  13 Claude checks are permission- and settings-shape rules with no Codex counterpart", "layer
  content is parsed only where the interpreter provides `tomllib` (Python 3.11+); on 3.9 and
  3.10 the layer is reported as unreadable, never as conforming", "read-only, like the Claude
  auditor: nothing in `~/.codex` or `.codex` is written"].

### 3.12 `agent-packs.lifecycle` — `closed-by-adapter`, bounded (P2.4)

- carrier: `.codex/agents/*.toml` (Ф11 — one file per agent, mandatory `name`,
  `description`, `developer_instructions`), which the repository already renders:
  `project_agent_role(..., provider_id="codex")` produces exactly that target
  (`agentpacks.py:1113-1122`), `plan_agent_artifact` wraps it with adapter identity, and
  `classify_agent_projection` compares bytes, so drift and ownership do not need a TOML
  reader at all. `agents.catalog` is already `adapted` at Codex, which is the same machinery.
- the boundary is where the pack files stop being provider-neutral. Pack manifests live under
  `configs/claude-code/agent-packs/*/pack.json` with `.claude/**` targets, the lock source
  string is `harness:configs/claude-code/agent-packs/<pack>`
  (`agentpacks.py:_pack_lock_entry`), and some pack members are Claude-runtime artifacts with
  no Codex equivalent by our own frozen renderer: `.claude/workflows/*.js` is refused for
  Codex both by `project_agent_role` (`HARNESS_ACTIVATION_UNSUPPORTED:codex:command.workflow-carrier`,
  `agentpacks.py:1097-1098`) and by `command_render._CODEX_RUNTIME_FORBIDDEN`
  (`claude-workflow-carrier`). The verdict closes the role-projection lifecycle
  (render/check/remove/diagnose over `.codex/agents/*.toml` with a provider-qualified lock)
  and names the excluded members instead of pretending they are covered.
- evidence: `scope` = "codex agent-packs.lifecycle over role projections `.codex/agents/*.toml`
  with a provider-qualified lock, excluding Claude-runtime pack members"; `claim` = "the
  deterministic adapter `harness.codex.agent-packs.lifecycle` renders, checks, diagnoses and
  removes locked Codex role projections through the same semantic role catalog and the same
  byte-level classification the Claude projection uses".
- draft `limitations`: ["covers role projections only: pack members that are Claude-runtime
  artifacts (`.claude/workflows/*.js`, `.claude/rules/*`, the review-gate shell hook and its
  ini) have no Codex projection and are excluded", "a role that requires
  `command.workflow-carrier` is refused for Codex by the frozen renderer, so such roles are
  absent from the Codex projection", "interview answers and pack versions stay shared with the
  Claude projection: the Codex lifecycle does not fork the pack catalog"].

### 3.13 `lifecycle.notification` — `claude-only` (P2.4)

- cause class: **the carrier exists but lies outside project scope.** Two independent
  first-party facts: the Codex event set has no `Notification` event (Ф9 — 11 events named),
  and notifications are delivered through the `notify` key, which Ф10 quotes as
  non-overridable by a project-scoped configuration ("Project-scoped config can't override
  machine-local provider, auth, host-owned app request metadata, **notification**,
  configuration **profile selection**, or telemetry routing keys"). Harness manages project
  artifacts, so the surface cannot be closed by a managed artifact by construction.
- evidence: `scope` = "codex lifecycle.notification within the managed-project-artifact
  model"; `claim` = "Codex exposes no `Notification` hook event and delivers notifications
  only through the user-scope `notify` key, which a project-scoped configuration may not
  override, so no managed project artifact can satisfy this surface".
- draft `limitations`: ["Codex has no `Notification` hook event", "notifications are
  user-scope `notify` only, which a project-scoped configuration may not override, so the
  surface stays fail-closed under the managed-artifact model", "replacement inside project
  scope: none; the operator may configure `notify` at machine level by hand"].

### 3.14 `workflows.status` — `claude-only` (P2.4)

- cause class: **the reported object does not exist at the second provider.** The Claude
  implementation is a parser of the internal, undocumented Claude Code run directory —
  `<config_dir>/projects/<slug>/<session>/subagents/workflows/wf_*` with `journal.jsonl` and
  a sibling run script, discovered empirically, keyed on `$CLAUDE_CONFIG_DIR` or `~/.claude`
  (`lib/harness/wf_status.py` docstring). Codex has no such run store: its documented
  surfaces (Ф9 hooks, Ф10 configuration reference, Ф11 subagents) contain no workflow-run
  artifact, and our own frozen renderer forbids the Claude workflow runtime in Codex
  projections (`command_render._CODEX_RUNTIME_FORBIDDEN` → `claude-workflow-carrier`), which
  is why `command.workflow-carrier` at Codex is `adapted` as a *rendered instruction carrier*
  rather than a runtime with a run directory. What is absent is the object to report, not a
  reader for it.
- honest note about the evidence class: this is absence by enumeration over three read
  first-party references plus a repository-declared prohibition, not a quoted "there is none"
  sentence. Recorded as such, so a later Codex release that introduces a run store makes this
  an additive change rather than a contradiction.
- evidence: `scope` = "codex workflows.status as a reader of workflow run state";
  `claim` = "the Claude surface parses the internal Claude Code workflow run directory, and
  the documented Codex surfaces expose no workflow-run store to read, so the surface has no
  Codex object to report".
- draft `limitations`: ["the Claude surface reads an internal, undocumented Claude Code run
  directory; Codex documents no equivalent run store", "the Codex orchestration carrier is a
  rendered instruction, not a runtime that leaves a run directory", "session-level reporting
  for Codex is covered by `analytics.run-report`, which is `adapted` for both providers"].

### 3.15 `analytics.legacy-migration` — `claude-only` (P2.4)

- cause class: **the intent does not apply to the second provider.** The surface migrates a
  frozen legacy Claude analytics source into the neutral store; Codex never had a legacy
  store, and new Codex writes already land in the neutral store through
  `analyst.codex-capture-reader` (`analytics.normalized-events` is `adapted` at Codex). The
  record's current text already says this; the triage keeps the wording and adds the causal
  class plus the verdict reference, so that the row stops reading as an unmet gap.
- coverage note (`provider-parity-definition` §6.2): this is the one record of the 17 that
  lies outside the `surface_map` of `harness doctor --provider-audit`. Its verdict therefore
  rests on C1 plus C6, and a green audit must not be cited as proof for it.
- evidence: `scope` = "codex analytics.legacy-migration applicability";
  `claim` = "no committed Codex legacy analytics carrier exists to migrate, and new Codex
  evidence is normalized into the neutral store directly, so the migration intent does not
  apply to this provider".
- draft `limitations`: ["the intent does not apply to Codex: there is no legacy Codex
  analytics carrier to migrate", "new Codex writes already target the neutral store", "a
  future Codex legacy source would be an additive change, not a reopened verdict"].

### 3.16 `context.output-style` — `claude-only` (P2.4)

- cause class: **no carrier at the provider.** The Codex configuration reference documents no
  output-style key (Ф10, explicit absence row).
- evidence: `scope` = "codex context.output-style configuration key";
  `claim` = "the Codex configuration reference documents no output-style key, so no
  configuration binding or deterministic adapter can satisfy this surface".
- draft `limitations`: ["Codex documents no output-style configuration key", "session style
  at Codex is a provider-owned behaviour with no project-scoped key to bind", "if such a key
  appears, raising the level is an additive change"].

### 3.17 `context.plans-directory` — `claude-only` (P2.4)

- cause class: **no carrier at the provider.** Same explicit absence row of Ф10.
- evidence: `scope` = "codex context.plans-directory configuration key";
  `claim` = "the Codex configuration reference documents no plan-directory key, so no
  configuration binding or deterministic adapter can satisfy this surface".
- draft `limitations`: ["Codex documents no plan-directory configuration key", "plan location
  for a Codex session is a repository convention, not a provider-bound setting", "if such a
  key appears, raising the level is an additive change"].

## 4. The two records `unsupported` at both providers (OQ-3 → D87)

The plan's framing of these two records was **an unrealized intent** ("объявленная, но
нереализованная интенция", `plan.md` §1 and § Обсуждение №3, `research/06` class E, D56). The
premise was checked before answering the question, as invariant И8 requires, and it does not
hold:

| Fact | Source |
|:--|:--|
| `lifecycle.daemon-safety` has a committed implementation | `packages/harness/configs/claude-code/hooks/daemon-safety/block-daemon-ops.sh` (PreToolUse, blocks destructive daemon operations) |
| it is installed on the machine by the harness installer | `packages/harness/scripts/apply-permissions.sh:71-73` |
| it is registered by a harness-shipped preset | `packages/harness/configs/claude-code/settings.global.json` — `PreToolUse`/`Bash` |
| its capability record nonetheless says `unsupported` at both providers with the boilerplate cause | `configs/provider-capabilities.json` |
| `lifecycle.git-guardrails` has a committed implementation | `packages/harness/configs/claude-code/hooks/git-guardrails/block-dangerous-git.sh` (PreToolUse, blocks dangerous git commands; MIT provenance in its header) |
| nothing registers or installs it | `grep -rn 'git-guardrails' packages/harness/{configs,lib,scripts}` → only its own directory; no `--git-guardrails` flag in `cmd_hooks` (`hooks.py:589-600`) |
| three of the four hooks of the same preset do carry capability bindings; daemon-safety is the only one that does not | `_claude_lifecycle_bindings` (`hooks.py:87-98`) versus `settings.global.json` |

**Verdict.** The intent is not withdrawn and was never unrealized: both surfaces are
implemented, and one of them is live on the Claude side. `intent-withdrawn` is therefore
applied to zero of the 17 records — not because the outcome is unavailable (probe C3 gives
zero strict consumers for both, so it would have been structurally legal), but because it
would have been false. Both are reclassified from class E to class B and closed at Codex by
their real carrier (rows 9 and 10), while the Claude halves are handled as described in §3.9
and §3.10: a descriptive, behaviour-neutral binding for `daemon-safety`, and an honest cause
text for `git-guardrails` whose activation is a fleet behaviour change outside this phase.

This supersedes the "unrealized intent" wording of `plan.md` §1, § Обсуждение №3, D56 and
`research/06` class E. Following the precedent of D82 and D84, those texts are not rewritten:
the D-log is append-only and the historical wording stays as evidence of what was believed.

## 5. The "inverted `SubagentStop` semantics" premise is false (D88)

`research/06` row 7 and `phases/P2.md` P2.3 carry the premise that Codex inverts the meaning
of a block on `Stop`/`SubagentStop` relative to Claude Code, and rate `lifecycle.review-gate`
as high risk for that reason. Both sides were checked first-party:

| Provider | Documented effect of blocking at `SubagentStop` | Source |
|:--|:--|:--|
| Codex | `decision: "block"` forces continuation rather than rejecting the turn | `findings/03` Ф9 (first-party `learn.chatgpt.com/docs/hooks`, 2026-07-29) |
| Claude Code | exit 2 → "Prevents the subagent from stopping"; top-level `decision: "block"` with `reason` has the same effect | `code.claude.com/docs/en/hooks`, WebFetch 2026-07-30 (RAG:✅) |
| our own Claude implementation relies on exactly that | "это НЕ прерывание субагента, а ПРИНУЖДЕНИЕ его продолжать с фидбеком в stderr … петля «нашли нарушение → субагент чинит → снова проверка»" | `configs/claude-code/hooks/review-gate/review-gate.sh` header |

The two providers therefore share one semantics, and the Claude review-gate is built on it
deliberately. The consequence for this phase is a *reduction* of risk, not a new one: row 7
is a direct projection, and its `limitations` records the property both providers share —
enforcement means forced continuation with feedback, and neither provider can cancel a
subagent from this event. The loop guard stays in the dispatcher, because `stop_hook_active`
is documented as unreliable at both providers.

Same treatment as §4: the false premise is superseded by this document and D88, and the
prose of P2.3 is not rewritten (it lies outside this item's `Files`, and editing a neighbour
item's spec without a decision record is scope drift). The executor of P2.3 must read row 7
here as authoritative over the "инвертирована" sentence of its own `Why`/Implementation
Rules.

## 6. Bounded closure as a legal form (D89)

Two rows — `settings.audit` (3.11) and `agent-packs.lifecycle` (3.12) — close the intent
inside a *named* boundary rather than for every property the Claude side has. This is the
frozen `adapted` form used as designed, not a fourth support level: the level is `adapted`,
`adapter_id` is stable, and the boundary is the content of `limitations`, which
`core/provider_manifest.py:372-375` requires to be non-empty. A row whose `limitations` said
"minor restrictions" would be the defect; a row that names what is outside the closure is the
honest instrument.

Two consequences the executing items must carry:

1. **Volume.** Rows 11 and 12 are the largest work of the phase, and both land on P2.4, whose
   remaining rows (13–17) are text-only. If P2.4 cannot carry all five rows in one item, the
   answer is a split recorded by `plan-design`, not a downgrade of rows 11 or 12 to
   `claude-only` — that downgrade is forbidden by this item's anti-fitting rule and would
   contradict the measured carriers.
2. **Interpreter floor.** The `tomllib` constraint of row 11 (stdlib from Python 3.11, matrix
   from 3.9 in `.github/workflows/test.yml:15`) is a repository-wide fact. Its named cost is
   inside row 11's `limitations`; raising the floor or vendoring a parser are both outside
   this phase, and the second is forbidden outright (no new runtime dependencies).

## 7. Self-check against `provider-parity-definition` §7

| # | Condition | State here |
|:--|:--|:--|
| 1 | verdict is one of the three, no "in-between" wording | met: 12 `closed-by-adapter`, 5 `claude-only`, 0 `intent-withdrawn`; the enum literals are the only verdict tokens in this file |
| 2 | level belongs to the frozen three | met: no level is written by this item; rows prescribe `adapted` or unchanged `unsupported` only |
| 3 | level form respected (`adapted` → `adapter_id` + `limitations` + `evidence`) | prescribed per row (§3) and enforced by C4 at the executing item |
| 4 | `evidence[]` carries four keys, falsifiable `claim`, bounded `scope` | `scope` and `claim` drafted per row; `verified_at` is stamped by the executing item on its own run |
| 5 | every new `evidence[].source` exists in the tree at verdict time | met: the canonical source is this file (non-archive path, D19); probe C5 over every path cited in §3 is green on `2640e8cf` |
| 6 | `claude-only`/`intent-withdrawn` have no strict consumer | met by probe C3: 0 strict rows for all 17 (§0) |
| 7 | `intent-withdrawn` only for both-provider `unsupported`, with a recorded reason | not applicable: the outcome is used zero times, and §4 records why |
| 8 | no capability ID removed, catalog not narrowed | met: this item touches no catalog |
| 9 | `closed-by-adapter` rows inside `surface_map` end at `activation_state: supported` | deferred to the executing item, which must show C2 green for its rows (16 of the 17 records are inside `surface_map`) |
| 10 | records outside `surface_map` rest on C1 + C6, never on "green audit" | met and named: `analytics.legacy-migration` is the only such record (§3.15) |
| 11 | refusal diagnostics not softened, fail-closed token kept and observable | met for the 5 `claude-only` rows: their `diagnostic` keeps `HARNESS_ACTIVATION_UNSUPPORTED`, and only `limitations` gain the causal class |
| 12 | `contract_version`, `catalog_version`, precedence untouched; change additive | met: nothing here is a catalog change; every prescribed change is additive |
| 13 | generated documents regenerated by their generator | deferred to P2.2–P2.5; `provider-docs.py --check` is exit 0 on `2640e8cf` before the triage |
| 14 | the verdict is recorded in this file, not only in the catalog | met |
| 15 | no verdict condition required a live Codex run | met: every carrier is named from a first-party document or from repository code, and row 2 records the one place where a live run would be needed (transcript depth) as a limitation, not as a condition |

## 8. Hand-off to the executing items

- **P2.2** (rows 1–4): the dispatcher of §1 plus four observer bindings. Two payload defects
  named in §3.3 are inside its scope and must be fixed with it. No observer prints a decision
  field.
- **P2.3** (rows 5–10): six gate rows, each with the two-test pair its spec demands. Row 7 is
  a direct projection (§5), row 8 declines the sandbox half with the reason of §3.8, rows 9
  and 10 additionally carry the Claude-half treatment of §3.9 and §3.10 — a descriptive
  binding for `daemon-safety` and honest cause text for `git-guardrails`, with no change of
  Claude activation.
- **P2.4** (rows 11–17): two bounded closures (§6) and five honest `claude-only` records
  whose `limitations` gain the causal class and whose `evidence` points at this file.
- **P2.5**: the conformance artifact must show, per record, verdict → level → observed
  activation; the drift gate goes to `hygiene.yml` (D21).
- **Named debts created by this triage, all outside the phase**: the Codex transcript format
  measurement (§3.2), an opt-in operator flag for the Claude half of `git-guardrails`
  (§3.10), and the `writable_roots` projection of the allowlist as an additive change of
  `lifecycle.auto-approval` (§3.8). Home for all three is `roadmap/`; none is created by this
  item, whose `Files` is this document alone.
