"""swissknifeman — CLI skill registry.

Logic taken from bin/skiller (before - Python-heredoc inside bash).
The binary is now a thin launcher: checks the environment and calls
`python3 -m skiller <repo_root> <cmd> [args...]`.

Modules:
  common    — die/warn/now_iso/confirm, parsing frontmatter and flag'ov
  config    — .swissknife.json, profiles, autodetect, resolve_selection
  state     — ~/.swissknifeman/projects.json, registry_git_state
  hub       — root hub generation, artifact detection
  boost     — sync boost.json::skills for Laravel Boost
  connect   — channel plugin marketplace
  vendor    — vendor channel
  update    — connection update/vendor (disk - the source of truth)
  status    — read-only report
  projects  — list registered projects
  registry  — regeneration skills.json + manifests (maintainer)
  doctor    — environment diagnostics
  cli       — command manager (entry point __main__)

Entry point for tests: import the necessary functions directly, environment
is passed through the object Env (common.Env), without modular globals.
"""
