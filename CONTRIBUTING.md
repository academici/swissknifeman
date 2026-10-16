# Contributing — swissknifeman (monorepo-umbrella)

Guide for monorepo root contributors. This **ecosystem umbrella academici**: one repository -
isolated modules in `packages/<id>/` (`aicore`, `skiller`, `planner`, `orch`, `maind`, `analyst`, `harness`, `brain`) + root router
`swissknifeman`. Detailed map - in [`CLAUDE.md`](CLAUDE.md) (root and each package).

## Layout

```
packages/aicore/      # foundation: stdlib-only util/provider/artifacts/usage, schemas, provider data
packages/skiller/     # skill registry            (CLI skiller)   — see packages/skiller/CONTRIBUTING.md
packages/harness/     # environment Claude Code      (CLI harness)
packages/maind/       # memory hub/column/coordination (CLI maind)   — see packages/maind/CONTRIBUTING.md
bin/swissknifeman     # root router (router + setup-facade)
install.sh            # umbrella installer (delegates install.sh packages)
```

## Development Installation

```bash
./install.sh                  # puts CLI packages + symlink swissknifeman in ~/.local/bin
```

- **Without pip, stdlib-only.** Runtime dependencies in Python no; a module imports only itself and `aicore`
  (found through `AICORE_ROOT` or `packages/aicore` of the hub) and reaches other modules only through their commands
  (`aicore.util.partners`). There is no `core/` folder. Nothing separately «install» for `aicore` is needed.
- **IDE-autocompletion `import aicore`:** for Pylance/pyright lies at the root
  `pyrightconfig.json` (`extraPaths`: `packages/*/lib`) — resolve works «from
  boxes», without pip. PyCharm: mark `.` and `packages/*/lib` like *Sources Root*.
- **`.mcp.json` and `config.json` machine-specific** (absolute paths) and do not commit
  (`.gitignore`); templates - `.mcp.json.example` / `packages/maind/configs/registry.example.json`. Real `.mcp.json` for
  of this repo generates `maind` (sync/deploy).

## Development prerequisites

Runtime needs only `python3` (>= 3.9) and `bash`; nothing is pip-installed. Contributing also needs:

| Tool | Why | Install |
|:--|:--|:--|
| `git` | the file list of `scripts/ecosystem-units.py` and `golden.py` comes from git | system package |
| `pipx` (or `ruff==0.15.19` on `PATH`) | `bash scripts/lint.sh` — the CI lint step (ruff F + B, `ruff.toml`) | `sudo apt install pipx` or `python3 -m pip install --user pipx` |

`scripts/lint.sh` fetches the pinned ruff on demand, prints `LINT_TOOL_MISSING` with the install hint when neither
pipx nor ruff is available, and is the single place that holds the ruff version and the linted paths (CI calls it).
Run it before a PR together with the validation below.

## Tests and validation

Before each PR — green validation on affected packages:

```bash
bash packages/skiller/scripts/validate.sh
bash packages/harness/scripts/validate.sh
bash packages/maind/scripts/validate.sh
bash packages/aicore/scripts/test.sh -v                        # foundation (aicore)
bash scripts/test-integration.sh                               # modules with their partners wired
python3 scripts/ecosystem-units.py check --strict             # module boundaries, no baseline
```

`validate.sh` of each packet runs `py_compile`, `bash -n`, checks JSON and unit tests
(`scripts/test.sh`). CI (`.github/workflows/modules.yml`, steps from `scripts/ci-matrix.py`) runs the same on
Python 3.9, 3.13 and 3.14; workflow supply-chain rules are in [SECURITY.md](SECURITY.md).

## Conventions

- **stdlib-only** in Python (`lib/`; minimum Python 3.9) — none pip-dependencies at runtime.
- **`Env` is passed explicitly** (frozen dataclass, heir `aicore.util.env.BaseEnv`) — without modular globals,
  everything is tested in tmpdir.
- **Atomic write** files/JSON — via `aicore.util.io.atomic_write_text` / `atomic_write_json`.
- **Messages - in Russian** (`die`, `warn`).
- **Commits - Conventional Commits in Russian** (e.g. `fix(aicore): ...`, `docs: ...`).

## Release discipline

- Content change → entry in `CHANGELOG.md` `[Unreleased]`.
- Skill edits/buckets/plugins → `skiller registry` (regenerates `skills.json`, marketplace,
  plugin-manifests, graph) — you don’t use your hands to straighten a genezhka.
- Annotated semver-tags: `git tag -a vX.Y.Z`; with tag `[Unreleased]` → `[X.Y.Z]`.
  Umbrella, package API and installable plugin units have their own versions.
- Provider caches are keyed by plugin version: changed content under an unchanged version is never
  re-fetched. Check with `python3 scripts/version-guard.py status --installed`, bump with
  `version-guard.py bump <unit>` (`task` follows the umbrella — `skiller release`); details in the
  `release-discipline` skill.
- Before tag: `skiller registry --check`, provider command generator `--check`,
  `skiller attest --release vX.Y.Z --previous vA.B.C`, then
  `python3 scripts/verify-tag.py vX.Y.Z`. Changed unit tree requires version bump.
  Tag only a commit on `main` (CI refuses another: `RELEASE_TAG_OFF_MAIN`).
  Attestation contains tag/date/digests; SHA is defined via a tag, without self-referencing release commit.
- After the tag: `skiller deliver --release vX.Y.Z --all --dry-run`, then the same command
  without `--dry-run`. Only receipt GREEN proves complete delivery; PARTIAL lists
  saved conflicting targets. Provider sessions require a restart.
- Git-tag and attestation fix the source version; `release-fleet` checks local
  delivery, but does not create GitHub Release. Page GitHub Releases is published separately and
  may lag tags. To select a version, check the tags and release attestation, and not
  read the mark Latest on GitHub Releases proof of current delivery.
- API tags are used `packages/<name>/vX.Y.Z`; plugin tags - `<name>--vX.Y.Z`.

## PR

1. Thread from `main` (on `main` do not commit directly).
2. Validation of affected packages is green (`python3 scripts/affected-tests.py --run`).
3. PR in Russian, description - what and why. CI will run the same validation.

Package-specific (skills, upstreams, memory/graph) — in `packages/<pkg>/CONTRIBUTING.md` and `CLAUDE.md`.
