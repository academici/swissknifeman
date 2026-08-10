# P3 provider adapter and fresh-worker design

## Sources and execution gate

This synthesis uses `findings/07-p3-provider-runtime-recon-2026-08-03.md`,
`findings/04-p0-design-verification-2026-08-03.md`, `research/01-target-architecture.md`,
`research/02-authority-and-conflict-policy.md`, `research/08-p2-prototype-design.md`, and the
planned P0 provider matrix/P1 worker envelope. P3 execution is forbidden until P0–P2 are terminal,
the P1 five-contract set and P2 prototype manifest validate, and the P0.3 installed-provider
matrix is still version-compatible. Planned files are preconditions, not evidence. RAG:—
(repo-grounded plan state).

## Ownership and dependency chain

| Item | Owns | Consumes | Produces for |
|:--|:--|:--|:--|
| P3.1 | pure shared adapter protocol plus Codex argv/event mapper | P0.3 matrix, P1.4 envelope, P2 activity request, Task routing carrier | P3.2–P3.4 |
| P3.2 | pure Claude Code argv/result mapper | P3.1 protocol, same frozen inputs, live Harness worker only as a donor crosswalk | P3.3–P3.4 |
| P3.3 | neutral parity/capability/exit crosswalk and independent cases/validator | both adapters and P0/P1 cases | P3.4, P4–P5 |
| P3.4 | one bounded subprocess runner, provider registry, P2 activity-port/CLI binding and aggregate smoke/manifest | P3.1–P3.3 and terminal P2 | P4–P6 |

P3.1 and P3.2 are not allowed to spawn a process. They build literal argv and normalize one
captured record into `worker-envelope-v1`. P3.4 is the only process owner, so timeout, byte/event
caps, process groups, redaction, binary discovery and orphan classification cannot drift between
providers. The phase is P3.1→P3.2→P3.3→P3.4: only two provider mappers are independently shaped,
while the parity freeze and live binding consume both. The plan-protocol N≥3-independent criterion
does not fire and no workflow is created. RAG:— (repo-grounded dependency graph).

## Adapter boundary

The neutral request carries run/slice/attempt IDs, provider ID, model class/effort, exact cwd,
scope/capability/permission/child/budget/timeout/output-schema policy and frozen source hashes.
Provider mappings may add argv/event fields but cannot change those semantics. Model selectors are
read from the pinned `packages/task/configs/command-routing.json`; P3 code contains no provider
model literals. Binary lookup reuses `SKM_CODEX_BIN`/`SKM_CLAUDE_BIN` then `PATH`.

Codex's pure mapper builds a list-form `codex exec` invocation with explicit cwd, model/effort,
strict config, sandbox, approval-policy override, `--ephemeral`, JSONL, output schema, user-config
isolation and disabled multi-agent capability where the terminal P0 matrix proves each surface.
Claude's mapper builds a list-form `claude -p` invocation with no persistence, structured output,
schema, model/effort, `dontAsk`, exact tool allow/availability, explicit setting sources, strict
MCP input and provider-native budget/turn controls where proven. Both take the prompt on a safe
stdin channel verified by P0.3; no prompt or schema body is placed in process listings. Unsupported
or unknown controls refuse before dispatch. RAG:✅ exact current controls in
`findings/07-p3-provider-runtime-recon-2026-08-03.md`; mapping policy is internal.

Every provider record is untrusted. Parsers retain only closed allowlisted identity, status,
usage/cost, denial and final-schema fields. Reasoning, intermediate assistant/tool text, raw
stdout/stderr, environment, credentials, prompts and transcripts are consumed under caps and
discarded. Exit code is corroborating evidence, never sufficient for success. Unknown event,
missing required terminal record, schema mismatch, cap overflow or contradictory exit/result
becomes a named neutral refusal; it never falls through to success or acceptance.

## Fresh worker and activity binding

P3.4 creates one OS process per attempt, never uses provider resume/continue/session IDs, and
never retries. It writes durable scheduler intent before calling the process runner, creates only
permission-0600 transient prompt/schema/config carriers inside the attempt directory, streams
bounded output, then durably records one minimized observation. POSIX timeout handling targets a
new process group, escalates TERM→KILL under fixed grace periods and records `orphan`/OWNER unless
death is verified; P4 later attacks every cut point.

Child-agent policy is `disabled` in the prototype. Claude's available tools exclude `Agent`; Codex
launch disables the native multi-agent feature. Any non-disabled child policy returns
capability-unsupported before dispatch until a future evidence-backed contract can enforce count,
scope and budget mechanically. This is stricter than the neutral envelope and therefore legal; it
does not reinterpret the P1 contract.

The P2 CLI keeps its six command names and no-provider default. P3.4 adds an explicit provider
selection only to the existing `start`/`resume` paths plus a hard `--max-slices 1` prototype cap;
omitting provider preserves P2's refusal/no-dispatch behavior. Scheduler selection, authority,
retry and acceptance remain in P2; the provider runner returns only an observation. This keeps
one state machine and makes every P3 live call owner-visible in argv/result evidence.

## Validation and live evidence form

Each pure adapter is tested with independently authored P0/P1-derived records and fake binaries;
no unit test invokes a real provider. P3.3's parity validator proves every neutral request/result,
exit and capability case has one explicit row per provider with `equivalent`, `degraded`,
`unsupported` or `unknown` evidence and no invented zero/default.

P3.4 then runs one bounded no-tool/no-write schema smoke per installed provider in a temporary Git
repository. The probe pins version, argv hash, source/contract hashes, exit classification,
terminal-schema verdict, usage field presence and project before/after delta. It stores no raw
stream or prompt. Binary/auth/quota absence is recorded exactly and blocks that provider's live
readiness; deterministic fake conformance alone cannot be called a live green.

## Alternatives rejected

1. Importing `harness.run.worker` would bind Artifex to a private Claude-only wave executor and
   inherit its ambient permission/raw-output boundary.
2. One adapter branching on provider IDs would make provider parity a switch statement instead of
   additive modules and would let one provider shape become neutral SSOT.
3. A subprocess runner in each adapter would duplicate timeout/orphan/redaction semantics at the
   reliability boundary.
4. `--bare`, bypass/yolo permission flags or ambient settings would either drop repository
   authority/hooks or widen it beyond the signed run mandate.
5. Reusing provider session IDs would save bootstrap tokens but violate the owner's fresh-worker
   isolation and make retry/resume depend on hidden provider transcript state.
6. Prompt-only child limits would be advisory, not authority; v1 disables children instead.

## Ecosystem-core pre-mortem

| Failure after 6–12 months | Early signal | Mitigation | Owner |
|:--|:--|:--|:--|
| Provider upgrade silently changes a terminal record | installed version/hash differs or an unknown record reaches parser | version gate, closed parser, unknown→refusal and P0.3 reprobe | P3.1/P3.2 |
| One provider becomes the neutral contract | parity case exists only for one adapter or provider field appears in scheduler | independent P1 cases plus two explicit mapping rows and production-source scanner | P3.3 |
| Headless permission waits forever or widens authority | approval request with no owner path, bypass flag or ambient mode in argv | explicit never/dontAsk mapping, no bypass, timeout and denial taxonomy | P3.1–P3.4 |
| Large stream exhausts coordinator memory or leaks prompts | raw stdout/result stored, unbounded read or forbidden key in evidence | streaming byte/event caps, allowlist normalization and forbidden-class scan | P3.4 |
| Timeout leaves a worker mutating after supervisor resumes | process group remains alive after timeout or session ID is reused | new process group, verified TERM→KILL, orphan→OWNER, no retry | P3.4/P4.2 |
| “Fresh” workers inherit prior hidden state | resume/continue/session reuse or provider transcript path appears in argv/evidence | non-persistence flags, new process per attempt and negative argv tests | P3.1/P3.2/P3.4 |
| Nested agents multiply cost or writes | Agent/multi-agent event appears under disabled child policy | native tool/feature disable, event refusal and capability-unsupported for child requests | P3.3/P3.4 |
| Dirty Hook/Harness state is mistaken for provider readiness | preflight warning/exception omitted from terminal report | preserve preflight defect in findings/handoff; P4/P5 live gate remains closed | P3.4/P4.4 |

## Stop condition

P3 design is ready when all four items have finite reads/files, terminal P0–P2 gates, literal argv
and parser tests, a two-provider parity bank, one process owner, explicit fresh/child/permission
policy, bounded live-smoke evidence and manual implementation/high routing. P4 remains closed until
P3.4's aggregate manifest and both required provider readiness rows are green or a new D# narrows
the pilot to a declared degraded provider set.

## Проверка (verification status)

- RAG: current official provider controls and limitations are carried by
  `findings/07-p3-provider-runtime-recon-2026-08-03.md`; repository donors were read directly.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: exact terminal/exit/quota/accounting shapes stay assigned to
  terminal P0.3 and P3's live smoke; no design sentence promotes them to fact.
- Обходки/[POSSIBLE-DEFECT]: no workaround is accepted. The relative-target Hook/Harness exception
  and absolute-target `stale-source` warning remain named preflight defects outside P3 design scope.
