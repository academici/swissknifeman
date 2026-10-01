# Diagnostics and update

The first step for any problem is `skiller doctor`: it checks the version
Python, symlink, `PATH`, integrity `~/.swissknifeman/projects.json`, that registry
— git-repository and without uncommitted skills that profiles are read.

## Composed effective-source doctor (`--effective-source`)

`skiller doctor --effective-source [--json]` — read-only composition from already
existing sources (does not start any new ownership logic): active
semantic owner/provenance/collisions are reused P1.4-gate
(`--effective-runtime`), plus cache/reference/capability/hook/trace-quality status.
Each diagnostician carries owner/source/status/evidence/quality/next_command; status -
`ok`/`degraded`/`unknown`/`n/a` (n/a only for structural facts, e.g. cache —
repo detectionderived and cold under contract D44, live profile/provider cache not
is readable). `--json` prints exactly one versioned document
(`schema_version: effective-source-doctor/v1`). Printed quality measured: there,
where the source is incomplete (e.g. `trace-quality`, there is no project trace storage yet),
diagnostic prints named space `unknown`, and not «ok». Nothing
does not write - proven `git status --porcelain=v1` to/after in Validation item'a P4.2.

## Common problems

### `swissknifeman: command not found`

The symlink has not been created or its directory is not in `PATH`.

```bash
cd ~/projects/packages/swissknifeman && ./install.sh
```

If the installer warned that `~/.local/bin` not in `PATH` — add (example
for bash):

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && exec bash
```

Have you migrated the registry repository? Just restart `./install.sh` from new
places - the symlink and path will update themselves.

### Claude Code doesn't see skills

Marketplace only picks up **committed** changes. Check:

1. `skiller status` in the project - section «Channel marketplace» shows
   plugins enabled and whether the source is marked as `[MOVED]`.
2. There are no uncommitted edits in the registry (`doctor` this will show): `git add … &&
   git commit` in the registry repository.
3. Restart the session Claude Code or execute in it
   `/plugin marketplace update swissknifeman`.

If the source is marked `[MOVED]` (registry repository changed path) — fix it
link: `skiller update`.

### Conflict `settings.json`

`connect` writes in `.claude/settings.local.json` (or `settings.json` with `--file`)
and before changing it puts a backup next to it `*.bak`. Explicitly disabled plugins
(`"<bucket>@swissknifeman": false`) are saved - `connect` does not grind them.
If something went wrong, restore from `.bak`.

### Name collisions during vendoring

`vendor` copies skills and flattens names. If names from different
buckets CLI prints `WARN: collision: 'deploy' -> 'devops-deploy'` and adds
bucket prefix. This is expected; names in manifest (`.swissknifeman-manifest.json`)
— source of truth for future updates and cleaning.

### `projects.json` damaged

When broken JSON CLI will rename the file to `projects.json.corrupt.<date>` and will start with
clean state - records will be restored when `skiller update` in projects.
Outdated entries (directory deleted) are removed: `skiller list --prune`.

## Update

### Update registry

```bash
cd ~/projects/packages/swissknifeman && git pull
```

- **Claude Code (marketplace):** changes are visible immediately after the commit in the registry -
  no copying. Restart your session Claude Code, if the plugins are not picked up.
- **Cursor / generic (vendor):** skills have been copied to the project, so please update
  explicitly: `skiller update` (current project) or `skiller update --all`
  (all registered). `update` itself determines the channel based on markers on the disk and
  plays the saved selection of plugins/buckets.

Check what exactly will work without touching the disk: `skiller update --dry-run`.

### Changing the registry schema

If `projects.json` is overwritten by a newer version CLI, than installed, `doctor`
and the commands will ask you to update the registry repository (`git pull`) and restart
`./install.sh`. Rollback to a specific version: `git checkout <tag>` in the registry +
repeated `./install.sh`.
