# Install profiles

`swissknifeman install` installs modules by profile. A profile is a list of module ids in
`configs/install-profiles.json` (`install-profiles/v1`); the order of installation follows `requires` in each
`unit.json` ([ADR 0074](architecture/decisions/0074-install-profiles.md)).

| Profile | Modules | For |
| --- | --- | --- |
| `minimal` | aicore, skiller, planner | skills and plans only |
| `standard` (default) | minimal + harness, brain, orch | the working environment |
| `full` | standard + maind, analyst | every module of the hub |

## Examples

Always look first; `--dry-run` writes nothing:

```bash
swissknifeman install --dry-run                       # standard profile into ~/.local/bin
swissknifeman install --profile minimal --dry-run
swissknifeman install --profile full --bin-dir ~/bin --dry-run
```

Install:

```bash
swissknifeman install --profile minimal               # skills and plans
swissknifeman install                                 # standard
swissknifeman install --profile full --force          # everything; replace foreign links
swissknifeman install --units skiller,brain           # an explicit list; requires are added (aicore)
swissknifeman install --profile full --option skiller=--no-codex-plugins   # extra argument for one module installer
swissknifeman install --profile standard --json       # umbrella-install/v1
```

`./install.sh` is a wrapper over `install --profile full` with the flags `--bin-dir`, `--force`, `--no-codex-plugins`
and `--no-grok-plugins`.

## What a step does

- A module with `provides.install` runs that command from its root, with `--bin-dir DIR` (and `--force` when it was given). With `--json` its output is captured and it gets no terminal on stdin, so it never waits for an answer.
- A module with only `provides.cli` gets a symlink `<bin-dir>/<name>` for each entry.
- A module with neither is listed and skipped (aicore is a library).
- Last, the `swissknifeman` link. A link made by an earlier install is replaced silently; a foreign file needs `--force`
  or an answer on a terminal (never asked with `--json`), otherwise the step is skipped with a warning. With `--force` a
  path that cannot be replaced (a folder) is skipped with a warning too.

Exit code 1 when a module installer fails, 2 for a usage or data error: `PROFILE_UNKNOWN`, `PROFILE_UNIT_UNKNOWN`,
`PROFILE_REQUIRES_MISSING`, `PROFILE_REQUIRES_CYCLE`, `UNIT_UNKNOWN`, `PROFILES_INVALID`; an empty `--units` list
(`--units ,`) is a usage error, not the default profile.

## Your own profile

A profile is data. Add one to `configs/install-profiles.json` of a checkout; the example
[`examples/install-profile-custom.json`](examples/install-profile-custom.json) shows the shape: `units` (every `requires`
of a listed module must be listed too), `options` (extra installer arguments per module) and `description`. The file is
checked by `configs/install-profiles.schema.json`. Without editing the file, `--units` and `--option` give the same
result for one run.

After installing, run [`swissknifeman doctor`](reference/doctor.md).
