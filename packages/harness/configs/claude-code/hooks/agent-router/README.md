# agent-router — opt-in project feature tips

Planner is launched only by explicitly calling a command or skill. Regular request for
does not activate implementation, design or review planner.

`router.py` (UserPromptSubmit) by explicit inclusion router evaluates local
agents and skills by keywords. Planner-commands and planner-skills are excluded from
generation and scoring, including old ones project catalogs. The hint remains
optional; it does not allow calling a command or changing a target.

`session-policy.py` left as empty compatibility entrypoint for previously
installed SessionStart registrations. It does not add context at startup,
including with old `POLICY=propose` and `POLICY=auto_dispatch`.

Default `POLICY=off`. Old values `propose`/`auto_dispatch` save
optional only non-planner hints; automatic start planner is no more.
Per-project override: `[harness.hooks.agent_router] policy` in `.swissknifeman/config.toml` (rendered to `AGENT_ROUTER_POLICY` in `.swissknifeman/hooks.env`; the legacy `.claude/agent-router.env.ini` is still read); directory:
`.claude/agent-router.config.json`.

```bash
harness hooks --global
harness hooks --target . --router propose
harness router --generate --target .
```

`THRESHOLD` sets the minimum sum of weights, `ESCAPE_PREFIX` disables tooltip
for one message. Hook accepts JSON on stdin and prints one line
`additionalContext` or nothing. Invalid input does not block work.
