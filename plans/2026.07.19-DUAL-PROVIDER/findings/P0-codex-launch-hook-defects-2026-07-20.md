# Codex launch and hook defects — 2026-07-20

**Scope:** swissknifeman self-host bootstrap only

**Trigger:** visible `PreToolUse hook failed` with exit code `127`

**Owner decision:** D54 — fix observed hook/launch/command defects immediately; keep
recurring invariants compactly in root `AGENTS.md`; do not treat this as P0.3 contract approval.

## Observation

Effective project registry `.codex/hooks.json` registered the same project-local
`auto-approve.sh` for Bash and ExitPlanMode, but the referenced `.codex/hooks/auto-approve/`
directory did not exist. Shell command lookup therefore returned `127` before tool use.

The global registry `~/.codex/hooks.json` also contained repeated Bash logger groups and a
combined group that invoked the same logger again. A single Bash command could be logged
multiple times even though every referenced global script existed and was executable.

After the registry repair, the already-running Codex process invoked the removed project
command once more and surfaced the same `127`. This established a second, live-session cause:
hook registrations loaded at process start can outlive an on-disk registry correction.

## Root cause

Bootstrap projected Claude-style auto-approve registration into Codex without materializing
a matching provider-native project hook. The project already uses Codex-native
`approval_policy=never` plus `sandbox_mode=danger-full-access`, so that registration was both
dangling and redundant. Repeated merge-only global registration accumulated duplicate logger
entries without an exact-set/dedup pass.

## Remediation applied

- Project `.codex/hooks.json`: removed dangling/redundant PreToolUse auto-approve groups;
  preserved the working mAInd SessionStart hook.
- Global `~/.codex/hooks.json`: retained one Bash logger and one daemon-safety guard; removed
  repeated logger calls.
- Global `~/.codex/config.toml`: remapped trusted hook state to the remaining indices and
  removed trust records for deleted project/global registrations.
- Root `AGENTS.md`: added the explicit trusted launch command, effective-config/hook preflight,
  exit-127 diagnosis and field-evidence routing.
- Current-session compatibility: materialized an executable no-op shim at the previously
  cached project path. It only consumes the hook payload and exits successfully; it grants no
  permission and is absent from the corrected cold-start registry.

Long-lived managed Codex hook projection remains a P5/P6 deliverable. This local bootstrap
repair does not claim that Claude hook payload/permission semantics are a provider-neutral
contract.

## Verification

Completed after the edits:

1. project/global hook JSON and user TOML parse; trust-state keys exactly match current
   registry indices;
2. every registered command resolves to an executable script; logger and daemon guard occur
   once each;
3. synthetic safe Bash payload passes logger and daemon guard; logger writes its probe record;
4. synthetic destructive daemon payload is blocked with exit code `2` and the documented
   `BLOCKED (daemon-safety)` diagnostic;
5. `codex doctor` reports zero warn/zero fail; its overall security note is the expected
   explicitly unrestricted sandbox, with approval `Never`;
6. `maind health --cwd` is `connected` with memory round-trip; active plan-lint reports no
   errors or warnings and no new working-tree errors.
7. The exact root `AGENTS.md` launch flags (`-C`, `-m`, xhigh config, `-a never`,
   `-s danger-full-access`) were passed to `codex doctor`; it reported unrestricted
   filesystem/network and approval `Never` with no warnings or failures.
8. The cached-path compatibility shim is executable and returns zero for a synthetic payload;
   a fresh config read reports no project `PreToolUse` registration, while `codex doctor`
   reports `0 warn` and `0 fail`.

`skiller budget --first-turn` still reports the existing over-budget first-turn footprint.
The command currently describes Claude-oriented surfaces (`CLAUDE.md`, `.claude/agents` and
its MCP set), so it is not evidence that the new Codex `AGENTS.md` block fits a dual-provider
budget. That gap remains assigned to the plan's provider-aware P5/P7 validation; it is not
silently treated as a green Codex budget.
