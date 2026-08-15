"""maind ecosystem hub: memory, graph, project, and agent control planes.

`lib/maind` contains stdlib-only logic; `bin/maind` launches
`python3 -m maind <repo_root> <cmd> [args...]`. Modules receive an explicit
`common.Env`, avoiding mutable module globals and keeping tests isolated.
"""
