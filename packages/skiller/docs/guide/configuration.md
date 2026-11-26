# Configuration, host buckets and metadata

## Project settings

skiller reads two tables of the project file `.swissknifeman/config.toml`:

```toml
[skiller]
project_type = "laravel"
buckets = ["quality"]
plugins = []
exclude = []
presets = []
agent = "claude"
skills_path = ".claude/skills"

[skiller.sync]
agent = "claude"
skills_path = ".claude/skills"
presets = ["laravel-admin"]
include = ["architect/api-design"]
buckets = ["quality"]
exclude = []
gitignore_managed = true
```

| Table | Used by | Keys |
|---|---|---|
| `[skiller]` | `connect` and the legacy `vendor` | `project_type`, `buckets`, `plugins`, `exclude`, `presets`, `agent`, `skills_path` |
| `[skiller.sync]` | `sync` (skill-granular vendor mode) | `agent`, `skills_path`, `presets`, `include`, `buckets`, `exclude`, `gitignore_managed` |

The schema is `configs/config.schema.json`. Selecting skills is a property of the project, so the machine file
cannot set these keys. `skiller init` and the first `skiller sync` write `[skiller.sync]` for a new project, and
`config.toml` also marks the project root.

### Legacy files

A project with only the older files keeps working: `.swissknife.json` fills `[skiller]` and
`.swissknifeman/config.json` fills `[skiller.sync]`. Each section is read from its legacy file as a whole unless
`config.toml` sets a key of that section (then the legacy file is ignored for the section). A legacy file is read
with a warning until the project is upgraded. Keys of other modules in `.swissknife.json` (`providers`,
`memory_brain`) stay where they are.

## Host-provided buckets

A bucket marked `"provided_by": "host"` in `buckets.json` has no catalog in the library. The host config key
`bucket_aliases` maps it to host plugins, and skiller reads their skills from the plugin directories the host names
in `plugin_dirs`:

```json
{"plugin_dirs": ["packages/*"], "bucket_aliases": {"system": ["maind", "harness", "analyst", "brain"]}}
```

- `connect` expands the bucket into those plugins and replaces the old `<bucket>@<marketplace>` key (merge-only; an
  explicit `false` is respected).
- `vendor` and `sync` copy the module skills with their `requires`; `exclude` works by skill name.
- `budget`, `status`, `doctor`, `registry` and `validate` understand the bucket.
- Without a host, the bucket is empty and skiller only warns.

The skills themselves live in the modules (`packages/<module>/skills/`), so a module is edited and released with
its own skills. See [Installation](./installation#host-configuration-and-standalone-installs) for the host config.

## Skill metadata

`skills.json` entries carry `license` (resolved from the skill frontmatter, then `upstream.json`, then the package
license) and, when a skill declares them, `compatibility` and `allowed_tools`. `skiller describe SKILL [--json]`
prints the full `skill-descriptor/v1` of a library or host-module skill. `scripts/validate.sh` checks that the
descriptor builds, that upstream skills name a license, and that the fields stay inside the Agent Skills standard
limits.
