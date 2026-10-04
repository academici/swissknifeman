# Plan tooling: verification gates `plans/`

## Independent review transport

Execution and review are separate sessions, not necessarily separate owner commands.
For automatic review of every implementation item in your requested phase/workset:

```text
task:plan-run <PLAN-ID> P1 --reviewer grok/grok-4.7
```

The reviewer argument accepts flexible suffixes and an optional trailing slash:

```text
--reviewer grok/grok-4.7/high/
--reviewer grok/grok-4.7/hight/
--reviewer grok/grok-4.7/500k/
--reviewer grok/grok-4.7/500k/high/
```

`hight` normalizes to high; context and effort may appear in either order. Context accepts
positive integer counts, k or m (500k = 500000); effort accepts low/medium/high/xhigh.
Suffix effort overrides the default, but conflicting explicit effort flags are rejected.
Equivalent spellings normalize to the same durable route; original launch text is retained.
The number requires **at least** that context capacity, not a token-spend limit and not a promise
that Task can enlarge the model. With explicit context, Grok uses a new native ACP session,
sets the requested model/context/effort, and checks the session's effective route in its native
`summary.json` before sending the digest-bound packet. A configuration acknowledgement alone
is not proof. The terminal ACP response must attest the same session/model, `end_turn`, and
complete positive usage. Internal accounting model names do not replace the effective model ID.
Unknown/insufficient capacity cannot produce GREEN and does not trigger a second identical
attempt. Native providers need captured context evidence too.
Read-only/tool boundaries remain unchanged. Explicit context does not enlarge the review packet.

The root implements/tests an item, launches fresh read-only Grok, and consumes the receipt.
GREEN closes and continues to the next item; FINDINGS permits one owning correction, affected tests,
and a second review. No manual `task:review` is needed. Only completed verdict rounds consume
review budget; incomplete transport receipts have no separate attempt cap. Diagnose/repair a failed
transport before retrying and preserve its history. A real stall/cancellation, missing capability or
completed-round exhaustion preserves the checkpoint; never reset history on resume.
`--review-effort high` is independent of executor effort. Each item `prepare` receives the selection
and persists `owner-review-request/v1` under its review artifacts. Close enforces this request even
when frozen Validation contains no owner-review carrier; conflicting prior selections fail closed.
The same root can launch transport, but only a separate reviewer session can certify the product.
With a phase-scoped command, prepare also takes `--phase P1` while `--item`/`--request` identify
the current admitted batch. Route evidence retains the actual phase command; no other phase is authorized.
Grok has a built-in headless runner; other providers require a supported independent native launch
and `review-record`. An unavailable launcher is explicit, never an automatic model substitution.

Without that explicit requirement normal execution uses self-check and affected tests;
a phase/slice review is a dedicated read-only item. An explicit owner requirement may declare
`owner-review: grok/grok-4.7` in Validation. Review commands require the exact route:

```text
task:review <PLAN-ID> P1.2 --reviewer grok/grok-4.7 --effort high
task:plan-audit <PLAN-ID> design --reviewer codex/<exact-model-id> --effort xhigh
```

The selected provider/model must actually run in a different session. Review/audit frontmatter
does not pin a competing model/effort; captured route validation enforces the arguments. Standalone
review remains a separate deliverable. Automatic mode orchestrates the bounded handoff in one root.

```bash
python3 packages/task/scripts/plan-work.py review-packet \
  --plan-dir plans/<PLAN-ID> --item P1.2 --reviewer grok/grok-4.7 \
  --executor-session <executor-session-id> --base <pre-implementation-commit> \
  --evidence <repository-relative-test-log>
```

Make one bounded attempt from the review stream or the automatically authorized orchestrating root:

```bash
python3 packages/task/scripts/plan-work.py review-run \
  --plan-dir plans/<PLAN-ID> --manifest <returned-review-route.json> \
  --reviewer grok/grok-4.7/500k --timeout 600 --heartbeat-interval 30
```

Native ACP publishes `owner-review/live-progress.json` and archives `heartbeats.jsonl` with
process/native-route/activity probes. Its timeout measures inactivity; streamed activity from the
selected session extends waiting without an elapsed limit. Transport/config noise does not hide a
stall. The default Task turn cap is absent; optional `--max-turns N` uses native terminal usage.
Legacy non-ACP headless transport retains its elapsed timeout until its liveness carrier is migrated.

Grok transport limits tools to reading, denies shell/edit/write/MCP, disables nested agents,
uses JSON output and checks actual model/session, completion and usage. Other providers review in
an independently routed native session, then use `review-record --output <verdict.json>
--invocation 'task:review <PLAN-ID> P1.2 --reviewer <provider/model>'` with the same plan-dir,
manifest and reviewer. That operation captures the current provider route.

Packets bind declared Files (plus optional adjacent `--path`), spec, model, self-check and evidence
to a SHA-256 candidate. The 80,000-byte cap uses full repository references when code is large;
required context is never clipped. Changed relevant bytes invalidate GREEN; bookkeeping and
foreign changes do not. Raw output, errors and immutable attempt receipts remain under
`artifacts/P1.2/owner-review/`. `review-status --plan-dir <dir> --item P1.2 --reviewer <provider/model>`
verifies the latest current GREEN carrier before item close.

For concurrency, transactions, auth and data integrity, Implementation Rules declares
`risk-class` and `invariant-model: <plan-relative-path>`; Inputs/Required Reads includes the model.
Validation declares `self-check: <plan-relative-json>`. Design covers all affected operation pairs,
resources and drivers; executor self-check records invariant evidence and every fixed/deferred risk.
Re-review checks the affected risk class/model. A second finding with the same class/area after repair
requires a shared-model tactic change. Two completed rounds exhaust the item review budget;
incomplete transport does not consume a round or a separate retry budget. Repair authority
remains; further completed rounds after exhaustion require an explicit bounded owner decision. There is no silent
close or budget reset. Exact schemas and recovery are in the canonical review-mode reference.

An extra round uses `review-packet --budget-decision D#`: an accepted item-scoped owner decision
must include `[REVIEW-EXTRA-ROUND:Pn.m:<candidate-sha256>:<next-round-number>]`. It grants exactly
one completed round for that candidate and is then consumed; earlier review history remains.

## Lean lifecycle selection

`task.plan_lifecycle.select(LifecycleInput(...))` - recommendation for the assessed impact,
is not a workflow engine or a gate. The unknown risk name is rejected with the diagnosis.
The permitted work procedure is chosen by the performer; Scope/Acceptance/authority rules apply.

Read-only snapshot preparation via existing launcher:

```bash
python3 packages/task/scripts/plan-session.py prepare --plan-dir plans/<ID> --item P1.1 --risk none
```

`none` means an assessment carried out without hard risk, and not the absence of inputs. Can be repeated
`--risk security-auth --risk public-api-schema`. Snapshot combines context, evidence graph,
producer readiness and Validation prerequisites; it does not replace route/admission before the entry.

```bash
bash packages/task/scripts/validate.sh --plan plans/<ID>
bash packages/task/scripts/validate.sh --fleet
python3 packages/task/scripts/plan-session.py installed --source packages/task --installed <selected-task-cache>
```

Without `--plan`/`--fleet` the validator qualifies the packet. Repeat `--plan` for affected dependency
closure; `--fleet` left CI/release. Alien red is visible; intersection with scope remains gating.
`installed` compares version/path/digest of the selected copy with the sources, returning non-zero
exit during drift. Check Task and core separately; then update via provider plugin manager
and check with a new launch. Checkout `--check` does not prove the freshness of the installed package.

## Native launch-block for handoff

Launch-block selects native syntax based on the active provider adapter: Claude Code - slash,
Codex - `codex ...`, Cursor - `agent ...`. These native forms do not mix. The table stores
only Batch/Model class/Effort/Context/Essence; the command always comes after it as a separate fenced block,
so that Markdown cell transfers do not break copying. One physical line is preferred;
If the shell command is broken intentionally, each continued line ends with `\`.

When actually final, the general renderer retains the Next recommendation regardless of the optional lease.
The Native block is required for a fresh-session boundary, including at the explicit request of the owner.
Completion of the ordered scope can leave `continue-root`: the result contains successor as
recommendation for the current chat and does not require a new process. Details - in
[continue-first](../continue-first.md#continue-root-without-extra-session).

`plan-run` supports two peer inputs. In an already open CLI session, the operator can execute
`/clear`, select the required Routing model/effort and insert provider-neutral `$ task:…` command.
Or you can open a new process with a native command with explicit cwd, model, effort, approval and
sandbox. Therefore handoff preserves both forms; for `plan-run` the route is always taken from Routing
next item:

```bash
codex -C <repo-cwd> -m <model-selector> -c 'model_reasoning_effort="<effort-selector>"' -a never -s danger-full-access '$ task:plan-run <PLAN-ID> <Pn.m>'
```

Provider-neutral form is convenient for `/clear`, the native block makes a separate launch reproducible.

### Cursor

Model Pins - [Provider model roles](./provider-model-roles). `auto` does not replace fixed
frontier/implementation pin (fail-closed).

| Model class | Cursor pin | Effort | Run Mode / CLI |
|:--|:--|:--|:--|
| `economy` | `composer-2.5-fast` | from Routing | allowlist / without `--force` |
| `implementation` | `composer-2.5` | from Routing | trusted: Run Everything + flags below |
| `frontier` | `claude-opus-5-thinking-high` | from Routing | trusted: Run Everything + flags below |

Trusted cold-start (self-host only):

```bash
agent --workspace <repo-cwd> --model <model-selector> --force --sandbox disabled --trust --approve-mcps 'task:plan-run <PLAN-ID> <Pn.m>'
```

IDE checklist: workspace root → **Run Everything** → `maind health --cwd` → pinned model.
Approval mode is not project-configurable; `deny` floor in `.cursor/cli.json` experiences `--force`.

### Codex

Before any plan command (`plan-design`, `plan-run`, `plan-audit`,
`plan-close`) Codex projection receives current-route provenance automatically before the first
product-journal mutations. The command below is shown for `plan-run`; projection substitutes exact
current Task command and its arguments:

```bash
export TASK_CODEX_ROUTE_EVIDENCE="$(PYTHONPATH=packages/task/lib \
  python3 -m task.route_evidence_codex capture \
  --expected-invocation '$ task:plan-run <PLAN-ID> <Pn.m>' \
  --expected-cwd "$PWD")"
```

Adapter first associates `CODEX_THREAD_ID` with a single active rollout and reads the last one
provider-written `turn_context`: model, effort, cwd, approval, sandbox and exact Task prompt.
Evidence receives `source=provider-thread-state`; so change `/model`/`/reasoning` and new chat
after `/clear` are checked against the current state, not against the argv of the old process. If thread state
is really missing, what remains is compatibility fallback: exact native argv with `-m`,
`model_reasoning_effort`, `-C`, `-a never`, `-s danger-full-access` and Task prompt. Malformed or
mismatched state fails-closed and is not replaced by `codex doctor`, config file, actor prose
or agent memory.

Codex runtime passes this JSON object directly to both `task_contract` gate
(`pre-mutation` and `pre-final`). Therefore, the same provider-written record, and not repeatedly
entered model/effort placeholders, determines the resolution. Old recipe
`provider-doctor`/`self-certified` is not allowed in Codex projection; regression test checks this
for all five plan commands.

Two stdlib scripts in `plans/` (not in `packages/task/lib/`, not built in `plan_lint.py` -
each has its own subject): `cross-plan-files.py` (interplane intersections `Files`) and
`verify-citations.py` (evidence links are resolved before the fact). Both are CLIs of the same form:
human-readable report always, `--strict` switches only the exit code. The third gate lives
In `plan_lint.py` itself (`packages/task/lib/task/plan_lint.py` + launcher
`packages/task/scripts/plan-lint.py`) - `--conflicts` mode, documented below.

## Next plan number: `plan-id.py`

`python3 packages/task/scripts/plan-id.py --codename <CODE-NAME> [--date YYYY.MM.DD] [--plans-root plans]`
(launcher above `task.plan_numbering`, stdlib, read-only) scans `plans/` and `plans/archive/` and prints
JSON: `plan_id` (`YYYY.MM.DD-№N-CODE-NAME`), `ordinal` (`№N`, unique within the date, maximum for living and
archived + 1), `short_id` (`PLAN<N>`, maximum Short ID per repository + 1, never reused),
`title_prefix` (`Plan No. N -`) and counters `scanned`. The agent substitutes the values as is and re-runs
utility right before creating the plan directory; collisions Short ID catches `plan-lint`. Errors - JSON to stderr,
exit 1 (`PLAN_NUMBER_DATE_INVALID`, `PLAN_NUMBER_CODENAME_INVALID`, `PLAN_NUMBER_COLLISION`).

## Token Upper Valuation Calibration v2

`packages/task/scripts/calibrate-token-estimate.py` manually freezes active
`configs/token-estimate-calibration.json` only after a bounded Codex run. The team requires
explicitly name provider and model; network and provider CLI are used only here, never in
offline `task.token_estimate` or CI:

```bash
python3 packages/task/scripts/calibrate-token-estimate.py \
  --provider codex --model gpt-5.6-terra --smoke-probe
python3 packages/task/scripts/calibrate-token-estimate.py \
  --provider codex --model gpt-5.6-terra
```

The adapter runs `codex exec --json` in an empty temporary cwd and normalizes only
`turn.completed.usage.input_tokens`; cache fields remain diagnostic and are not added to
total. A full run takes exactly 8 different real-source samples (≤16 KiB each, ≤128 KiB
total) via bracket-controls (no more than 3 payload between controls, ≤12 provider calls). Artifact
carries provider/model/protocol/classifier provenance and fail-closed rejects v1 or mismatch
classifier. Historical Claude v1 artifact and probe-log remain plan-owned snapshots; future
Claude adapter - separate additive provider projection.

## Hard-gate budget reading for layout v2

Normal `plan-lint.py plans/<ID>` applies frozen `read-budget` v1 only to plan with
`Layout | v2`. For each `ready` item it fails if D2(a) is exceeded, unreadable or
an unresolved required input and a file exceeding either of the two read limits. Absence
calibration, `read-limit` or plan-owned threshold contract is also ERROR; retired layout not
receives neither opt-in nor warning branches. Diagnostic details and calculation owners -
[`plan-read-budget-gate.md`](plan-read-budget-gate.md).

## Downstream gate producer→consumer

`plan-downstream.py` mechanically removes consumers from the declared paths, drives away the applicable
a subset of their `Validation` and stores the three-digit result with the version key of the technical assignment and the item commit
producer. Record availability check is disabled until P6. CLI, exit codes and the finding form are described in
[`plan-downstream-gate.md`](plan-downstream-gate.md).

## `packages/task/scripts/verify-plan-citations.py`

Checks proof links of the form `` `path:line` ``/`` `path::symbol` `` in ALL living prose
plan: `plan.md`, `handoff.md`, `roadmap.md`, `phases/*.md`, `findings/**/*.md`,
`research/**/*.md`, `brief/**/*.md` (recursive; `artifacts/`, `closure/`, `root/` deliberately
off-surface - raw measurements/generated reports/moves to `docs/` project). File
exists, line number inside the file, character after `::` occurs in the file (search by name,
WITHOUT AST parsing).

```bash
python3 packages/task/scripts/verify-plan-citations.py # all live plans
python3 packages/task/scripts/verify-plan-citations.py plans/<PLAN-ID> # one plan (path OR bare ID)
python3 packages/task/scripts/verify-plan-citations.py plans/<PLAN-ID> --strict # exit 1 on any find
python3 packages/task/scripts/verify-plan-citations.py --include-archive # + archive plans
python3 packages/task/scripts/verify-plan-citations.py --selftest                 # embedded unittest
```

**Read exit code:** without `--strict` the script always returns `0` (report - for reading with eyes
or CI log, not gate); with `--strict` — `1`, if at least one link did not resolve, otherwise `0`.

**Verifiable forms** (link - ONE token inside single backticks):
- `` `path/to/file.ext:123` `` - line inside the file;
- `` `path/to/file.ext:123-145` `` - range of strings;
- `` `path/to/file.ext:123,145` `` - a pair of non-adjacent lines;
- `` `path/to/file.ext::symbol` `` - the name of the symbol is in the file. `a::B::c` — the gate rattles
  ONLY sheet `c` (without parsing class/method nesting) - a tool boundary, not a bug:
  "character validation" here means "name occurs in file", not "signature matches".
- `` `path/to/file.json::a.b.c` `` - the path of the keys INSIDE the JSON file. Resolves
  `json.load` + **greedy-bypass**: at each level the LONGEST subsidized prefix is taken
  remainder, which is the key of the current object (for a list - an integer index). Greedy
  not a decoration: the plan artifact keys themselves contain dots (`owners.P2.2` = key
  `"P2.2"` inside `owners`) - naive `split(".")` gives a false find. File, no
  parsed as JSON, - finding “JSON is not parsed” (not a silent pass, not a fallback to
  grep). The boundary is the same as for `::symbol`: **“key exists” ≠ “value matches”** —
  the gate does not check the value by key.

**The path must contain `/`.** A bare path-mention without a suffix is not checked at all (class
rejected by 16% noise measurement, D128). The resolution is TWO-STEP and the order of the bases is FIXED: (1)
repository root, (2) source plan directory (`plans/<PLAN-ID>/`) - the first base under which
the file exists, defines the resolve, the suffix is checked against HER. Short
intraplane form (for example, `` `phases/P1.md:80` `` as a continuation of the enumeration after
full path a little earlier in prose) will be resolved by the SECOND base - this is not “restoration
implied prose context”, and the second deterministic base, known to the script by
construction (it bypasses `plans/<PLAN-ID>/`). A file not found from either of the two databases is
found, report both attempted bases. The machine never guesses a third base such as a package root,
and it still ignores bare paths without a suffix.

**Known exceptions** - links to paths OUTSIDE the repository (for example, npm dependency file,
read directly during RAG verification) or to the deliverable of the FUTURE item'a, which is on
this tree is not yet built. Data, not code: `packages/task/configs/verify-citations-known-exceptions.json`
(if there is no file, there are no exceptions, which means an empty report by default); list
global (by quote line, not by plan), started and replenished by gate triage, not edited
code:

```json
{
  "exceptions": [
    {"citation": "path/to/file.ext:123", "reason": "why is this not a defect"}
  ]
}
```

Started P11.5 (`research/27-P11-citation-gate-target-design.md` §3) for four MECHANICAL
rules of finding triage (not eye judgment): **R1** - short form in `findings/`/
`research/`/`plan.md`/`handoff.md`/`roadmap.md` of your plan, the full path is restored
UNIQUELY (exactly one file in `git ls-files` with such a suffix) → the quote is COMPLETE
path; **R2** - zero candidates (external file outside the repository) or more than one (path
ambiguous) → entry into the list with an address reason; **R3** - quote in ALIEN'S plan →
only entry into the list (other people’s prose is not corrected here); **R4** - quote
inside the CLOSED item'a (TK) fields of your plan (including quotes inside verbatim
transcripts of findings-documents referring to the positions of that item'a) → entry in the list +
Pending Work (editing technical specifications of closed items outside the triage scope).

**Tests** — `python3 packages/task/scripts/verify-plan-citations.py --selftest` (embedded `unittest`;
there is no separate file in `packages/task/tests/`). The script is stdlib-only and self-contained, like
`packages/task/scripts/cross-plan-files.py`).

## `packages/task/scripts/cross-plan-files.py`

See file docstring - reconciliation `Files` between live plans, `--strict` baseline mode vs
`cross-plan-known-intersections.json`.

## `plan-lint.py --conflicts`

Third leg of the conflict scan `plan-audit-loop.md` §A.1 - deterministic
reconciliation “EN-only canon (`SKILL.md`) ↔ implementation (constant registers `plan_lint.py`)”, **without plan argument**
(artifact check, not lint of specific `plans/<ID>`; `path`, if passed, ignored):

```bash
python3 packages/task/scripts/plan-lint.py --conflicts
```

Exact literals are declared by `i18n-keep` directives in the same EN canon. Seven reconciled
classes, each find - both sides with `file:line`
(“canon says X → implementation says Y”):

1. six canonical statuses (`STATUSES`) ↔ SKILL.md §4;
2. 16 item'a fields and their order (`REQUIRED_ITEM_FIELDS`) ↔ SKILL.md §3;
3. closed enum forms `Next` (alternation `SEMANTIC_NEXT_RE`) ↔ SKILL.md §6;
4. three values layout-v2 `Context` (`CONTEXT_VALUES`) ↔ SKILL.md §6;
5. literals `i18n-keep` (`CANON_LITERALS`) ↔ directives `<!-- i18n-keep: … -->` in SKILL.md (that
   same predicate as T2 `packages/task/tests/test_canon_literals.py`, accessible from CLI without unittest);
6. launch-block'a form: `LAUNCH_TABLE_ROW_RE` ↔ metadata table without command,
   provider-native fenced command block is required, and `LAUNCH_COMMAND_ROW_RE` remains only
   reader-side compatibility of old plans;
7. mandatory carrier literals of the block `Layout v2 carrier contract`.

If the monorepo should carry canon, but `SKILL.md` has disappeared, the reconciliation fail-closed. Only real
standalone package layout can skip literal unittest without turning repo test into
vacuous pass. Registered by stage `packages/task/scripts/validate.sh` and the first,
the cheapest conflict scan command `packages/task/commands/plan-audit.md` (§1).

Separately, in PLAN MODE (without `--conflicts`, normal `plan-lint.py plans/<ID>`) - diagnostics
**repeat field** inside item body'a: line `**Field:** value`, randomly matched
form inside the free prose of another field (for example, `**Validation:** …`, added as
inline note in Completion Notes), silently replaced the EARLIER legitimate value of the field - and
`plan_lint`, and `task_contract`, both take the LAST entry. ERROR calls item, field and both
lines (`file:line` each).
