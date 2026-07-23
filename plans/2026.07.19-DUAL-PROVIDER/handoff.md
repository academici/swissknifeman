# HANDOFF — 2026-07-23 — after P7.2

**Next:** manual: implementation/high — P7.2 (§3 Routing: Exec = manual)

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | — |
| Native model | `gpt-5.6-terra` |
| Reasoning effort | `high` |
| Approval policy | `never` |
| Sandbox | `danger-full-access` |
| CWD | `/home/vostrikov/projects/packages/swissknifeman` |
| Context | same-session — item |
| Native context | `NEW SESSION` — neutral-shell ephemeral clean room after the current Codex session exits |
| Суть | Resume only the D118 RED native row with the D119 supported whole-executor state isolation; stop at the existing exact live-action Owner gate. |

```bash
(
  set -eu
  P72_AUTH_COUNT=0
  [ -n "${CODEX_ACCESS_TOKEN:-}" ] && P72_AUTH_COUNT=$((P72_AUTH_COUNT + 1))
  [ -n "${CODEX_API_KEY:-}" ] && P72_AUTH_COUNT=$((P72_AUTH_COUNT + 1))
  [ "$P72_AUTH_COUNT" -eq 1 ] || {
    echo 'P7.2 requires exactly one exported automation credential: CODEX_ACCESS_TOKEN or CODEX_API_KEY' >&2
    exit 64
  }
  P72_RUN_ROOT=$(mktemp -d /tmp/p72-codex-cleanroom.XXXXXX)
  mkdir -p "$P72_RUN_ROOT/home" "$P72_RUN_ROOT/codex-home" "$P72_RUN_ROOT/sqlite"
  env HOME="$P72_RUN_ROOT/home" \
    CODEX_HOME="$P72_RUN_ROOT/codex-home" \
    CODEX_SQLITE_HOME="$P72_RUN_ROOT/sqlite" \
    codex -C /home/vostrikov/projects/packages/swissknifeman \
      -m gpt-5.6-terra -c 'model_reasoning_effort="high"' \
      -c 'shell_environment_policy.exclude=["CODEX_ACCESS_TOKEN","CODEX_API_KEY"]' \
      -a never -s danger-full-access \
      exec --ephemeral --ignore-user-config \
      'Execute $ task:plan-run 2026.07.19-DUAL-PROVIDER P7.2. Read AGENTS.md, CLAUDE.md and plans/2026.07.19-DUAL-PROVIDER/{plan.md,handoff.md,roadmap.md,phases/P7.md,research/29-p7.2-native-codex-session-state-isolation.md,research/28-p7.2-native-codex-disposable-root.md,findings/P7-self-host-probes-2026-07-19.md,findings/P7-codex-session-isolation-docs-2026-07-23.md}. Resume only at the D118 RED native Codex row. First snapshot the explicit host path /home/vostrikov/.codex and the repository; never print or persist an automation credential. Rerun the native marketplace/plugin proof under the inherited task-specific HOME, CODEX_HOME and CODEX_SQLITE_HOME, then require zero host/repository delta. If green, reconcile the isolated aggregate and stop at the exact live path/action Approval Owner D# request; do not perform live apply/repair/rollback in this ephemeral run. Do not touch package source/tests, P7.3+, FOREMAN, fleet, tag, push, cleanup, owner AGENTS.md or unrelated dirt.'
)
```

**Done:** D119 supersedes only D118's failed nested execution carrier and D96's P7.2
within-session owner-gate clause. Current official Codex docs and the installed CLI confirm the
supported clean-room primitives. No P7.2 command, plugin install, package/source change or live
mutation occurred in this design pass.

**Remaining:** From a neutral owner shell after this session exits, rerun only the D118 RED
native row under the D119 clean room. If isolated evidence becomes GREEN, emit the exact
live path/action inventory and Owner D# request; any approved live action is a separate
self-contained session. P7.3 and P7.4 remain sequentially closed.

**Sources of truth:** `plans/2026.07.19-DUAL-PROVIDER/plan.md` D108–D119 ·
`phases/P7.md` P7.2 · `research/29-p7.2-native-codex-session-state-isolation.md` ·
`findings/{P7-self-host-probes-2026-07-19,P7-codex-session-isolation-docs-2026-07-23}.md`.

**Open risks:** Exactly one owner-provisioned automation credential and the routed model must
be available in the neutral launch shell. Missing/ambiguous auth or route availability stops
before P7.2; host auth reuse is forbidden. Historical P6.8/D107 debt remains accepted.

**Workarounds/Deferred/Open questions:**

- workarounds: none; active-session path exclusions and host-auth copying were rejected.
- deferred: live apply/repair/rollback and exact path/action approval remain P7.2-only.
- open_questions: —
