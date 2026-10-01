# Observer — session parsing recipes (jq/grep)

Specific commands for each measurement. Logs Claude Code: project directory -
path with `/`→`-` (`~/.claude/projects/-home-...-<project>/`), inside `<session>.jsonl`
and `<session>/subagents/agent-*.jsonl`. Anonymized: generic paths.

## 0. Toggle-gate (before everything)

```bash
INI=".claude/observer.env.ini"
EN=$(grep -E '^[[:space:]]*ENABLED' "$INI" 2>/dev/null | sed -E 's/^[^=]*=[[:space:]]*//; s/[[:space:]#].*//' | tr -d "\"'")
[ "$EN" = "true" ] || { echo "Observer disabled (ENABLED!=true). Enable: /observe on"; exit 0; }
```

## Find current session log

```bash
PROJ_DIR=$(printf '%s' "$PWD" | sed 's#/#-#g')
LOGDIR="$HOME/.claude/projects/$PROJ_DIR"
MAIN=$(ls -t "$LOGDIR"/*.jsonl 2>/dev/null | head -1)
SUBS=$(ls -t "$LOGDIR"/*/subagents/agent-*.jsonl 2>/dev/null)
```

## Axis 1 - agents

```bash
# SKILL_COMPLIANCE: violations in actually modified code (example - Laravel).
git diff --name-only -- 'app/Http/Controllers/*' \
  | xargs -r grep -nE '::(query|create|where|all|find)\(' || echo "controllers clean"

# LOOP_DETECTION: one file read N+ times.
jq -r 'select(.message.content[]?.type=="tool_use" and .message.content[]?.name=="Read")
       | .message.content[] | select(.name=="Read") | .input.file_path' "$MAIN" 2>/dev/null \
  | sort | uniq -c | awk '$1>=3{print "LOOP read x"$1": "$2}'

# INTER_AGENT_ERRORS: tool_result with error + reviewer needs-work.
jq -rc 'select(.type=="user") | .message.content[]? | select(.is_error==true) | .tool_use_id' "$MAIN" 2>/dev/null | wc -l
grep -l 'needs-work' $SUBS 2>/dev/null
```

## Axis 2 - skills

```bash
# Which skills were actually loaded (Skill tool calls) — for DEAD/THIN/GAP.
jq -r 'select(.message.content[]?.name=="Skill") | .message.content[] | select(.name=="Skill") | .input.skill' $MAIN $SUBS 2>/dev/null | sort | uniq -c
# THIN_SKILL: skill loaded, but SKILL_COMPLIANCE-the grep above still found a violation.
# DEAD_SKILL: is declared in the agent (skills:), but in the output jq does not appear above.
# SKILL_GAP: task domain without a loaded skill.
```

## Axis 3 - settings

```bash
# HOOK_MISCONFIG: gate is disabled.
grep -E '^[[:space:]]*MODE' .claude/review-gate.env.ini 2>/dev/null
# PERMISSION_FRICTION: repeated permission requests (Notification-events / failures).
jq -rc 'select(.type=="user") | .message.content[]? | select(.type=="text") | .text' "$MAIN" 2>/dev/null \
  | grep -iE 'no|wrong|wrong|use |actually|cancel|return' | head   # CORRECTION_LOG
```

## Record learnings (via memory-hook, not your own file)

```bash
~/.claude/hooks/memory/memory.sh remember --type project \
  "<axis>:<find> — <why> (session $(date +%F))"
# Promotion (by human approval): .claude/rules/<topic>.md | proposal skill | memory.
```
