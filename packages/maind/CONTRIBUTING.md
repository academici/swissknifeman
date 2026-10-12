# Contributing

Thanks for your contribution to **mAInd**. The package is based on several strict conventions - follow them.

## Environment

- **Python 3.8+** (core), **bash** (launcher/scripts), **Node** — for memory daemon only.
- Development installation: `./install.sh`, then `maind doctor`.

## Launch

```bash
scripts/test.sh          # unittest, no third party dependencies and no live daemon
scripts/test.sh -v       # verbose output
scripts/validate.sh      # py_compile + bash -n + JSON + tests (what drives CI)
```

## Code Conventions

- **Only stdlib in runtime.** No third parties Python-dependencies in `lib/maind/`.
  `networkx`/`graphify` are connected lazily and only if selected via `graph.adapter`.
- **Context via `Env`** (`common.Env`, frozen dataclass) — pass explicitly, without
  modular globals. All paths to state are properties `Env`.
- **Commands** — functions `cmd_X(env, argv)`, dictionary values `COMMANDS` in `cli.py`.
  Parsing arguments - `common.parse_args` (flags + positional), not argparse.
- **Atomic write JSON** — `common.atomic_write_json` (tmp + `os.replace`). Everyone
  storage file one writer.
- **Messages and docstrings are in Russian.** Errors via `die`, warnings via `warn`.
- **Memory is an external Node-demon.** maind orchestrates it, not rewrites it; tests
  never require a living demon (use `tests.fixtures.FakeMemoryServer`).
- **Ports are not hardcoded** — `memory.resolve_ports` (env → config → default).

## Tests

- Style - `unittest`; fixtures in `tests/fixtures.py` (`make_repo` gives isolated `Env`
  with temporary HOME). Each new module `lib/maind/X.py` is followed by `tests/test_X.py`.
- Tests do not touch the real node/demon or its state directory — everything is in temporary directories.

## Pull Request

- Before PR: `scripts/validate.sh` should be green.
- Update `CHANGELOG.md` (section `[Unreleased]`).
- Don't commit `config.json`, `.env`, `data/*` — they gitignored (machine-specific).
