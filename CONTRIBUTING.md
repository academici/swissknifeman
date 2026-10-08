# Contributing — swissknifeman (monorepo-umbrella)

Guide for monorepo root contributors. This **ecosystem umbrella academici**: one repository -
three independent packages (`skiller`, `harness`, `maind`) + general `core` + root router
`swissknifeman`. Detailed map - in [`CLAUDE.md`](CLAUDE.md) (root and each package).

## Layout

```
packages/aicore/      # foundation: stdlib-only util/provider/artifacts/usage, schemas, provider data
core/                 # transitional shim over aicore (until the hub modules move onto aicore)
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

- **Without pip, stdlib-only.** Runtime dependencies in Python no; `core` connects via
  `PYTHONPATH` — launchers (`packages/*/bin/*`) add monorepo root automatically
  (fallback on standalone-package layout). Nothing separately «install» for `core` is not needed.
- **IDE-autocompletion `from core import ...`:** for Pylance/pyright lies at the root
  `pyrightconfig.json` (`extraPaths`: repo root `.` + `packages/*/lib`) — resolve works «from
  boxes», without pip. PyCharm: mark `.` and `packages/*/lib` like *Sources Root*.
- **`.mcp.json` and `config.json` machine-specific** (absolute paths) and do not commit
  (`.gitignore`); templates - `.mcp.json.example` / `config.example.json`. Real `.mcp.json` for
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

Before each PR — green validation on affected packages + smoke `core`:

```bash
bash packages/skiller/scripts/validate.sh
bash packages/harness/scripts/validate.sh
bash packages/maind/scripts/validate.sh
bash packages/aicore/scripts/test.sh -v                        # foundation (aicore)
PYTHONPATH=. python3 -m unittest discover -s core/tests -v   # transitional core shim
```

`validate.sh` of each packet runs `py_compile`, `bash -n`, checks JSON and unit tests
(`scripts/test.sh`). CI (`.github/workflows/test.yml`) runs the same on Python 3.9–3.13.

## Conventions

- **stdlib-only** in Python (`lib/`, `core/`; minimum Python 3.9) — none pip-dependencies at runtime.
- **`Env` is passed explicitly** (frozen dataclass, heir `aicore.util.env.BaseEnv`) — without modular globals,
  everything is tested in tmpdir.
- **Atomic write** files/JSON — via `core.atomic_write_text` / `atomic_write_json`.
- **Messages - in Russian** (`die`, `warn`).
- **Commits - Conventional Commits in Russian** (e.g. `fix(core): ...`, `docs: ...`).

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
2. Validation of affected packages is green; `core`-tests pass.
3. PR in Russian, description - what and why. CI will run the same validation.

Package-specific (skills, upstreams, memory/graph) — in `packages/<pkg>/CONTRIBUTING.md` and `CLAUDE.md`.
