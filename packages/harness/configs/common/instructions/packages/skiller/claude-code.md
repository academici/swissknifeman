<!-- instruction:skiller.claude-code.marketplace-connect -->
## skiller.claude-code.marketplace-connect
Claude Code `connect` writes `enabledPlugins` to `.claude/settings.local.json` and points the marketplace channel at the registry rather than copying skill bodies.
<!-- instruction:skiller.claude-code.vendor-targets -->
## skiller.claude-code.vendor-targets
Claude Code vendor sync writes managed copies to `.claude/skills/` and records ownership in `skills-lock.json`; those files are committed for disconnected consumers.
<!-- instruction:skiller.claude-code.agent-hub -->
## skiller.claude-code.agent-hub
Claude Code loads skill bodies itself; `hub.py` remains the managed agent-hub generator and Python does not maintain a skill-body loading cache.
