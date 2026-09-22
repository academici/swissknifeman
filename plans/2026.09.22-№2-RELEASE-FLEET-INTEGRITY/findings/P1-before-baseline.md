# P1 baseline

- 24 enabled projects; 8/24 selected Cursor; all Git worktrees had pre-existing changes, `axiomastudio` was not a Git worktree.
- 9 projects mixed marketplace and legacy vendor channels.
- Six Claude vendor trees contained 341 manifest-owned SKM skills; fleet delivery surfaces contained 9,983 files / 30,436,737 bytes.
- Task was `0.21.0` in both plugin manifests, Codex/Cursor locks, `v0.24.0` snapshot and provider caches while the owner-required version was `0.24.0`.
- maind runtime/plugin was `0.4.3/0.2.2`; analyst was `0.2.3/0.1.1`; skiller and maind npm locks lagged package versions.
- Ten projects exceeded the 8,000-character Codex/Cursor listing budget. Azguard: 72 skills, 10,448 chars, 8,425 first-turn tokens. Corex: 57, 7,379, 4,184.
- `maind sync --all --dry-run` reported 83 changes and three MCP failures while returning success in JSON mode.

