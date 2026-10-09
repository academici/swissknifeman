**Verdict: RED**

P8.1 has no reproduced defect. P8.2 has two Major defects and one Minor. `bash packages/skiller/scripts/test.sh` passed (829 tests). In a sandbox, `skiller registry --check` and `bash packages/skiller/scripts/validate.sh` both exited 0. `packages/skiller/buckets.json` and `configs/skiller-host.json` are unchanged.

## Major

### 1. P8.2 — a name clash installs the host skill while saying the library copy is used
`packages/skiller/lib/skiller/skillset.py:311`

`resolve_skillset` stores one flat entry per skill name and assigns `selected[entry["name"]] = entry` in `by_key` order. Library rows are inserted first, host rows after (`skillset.py:136`). Whichever bucket is listed last overwrites the other. The index warning at `skillset.py:147` still says the library copy is used. `include` by name does keep the library entry. `test_library_wins_a_name_clash` only checks `build_requires_index`.

With both copies named `sk-a` and bodies `FROM LIBRARY` / `FROM HOST`, `do_sync` on buckets `["lib-a", "env-skills"]` printed:

```text
WARN: skill name 'sk-a' exists in the library and in host plugin 'mod-a'; the library copy is used
INSTALLED HAS FROM HOST True
INSTALLED HAS FROM LIBRARY False
```

The same selection in the other order kept the library path `skills/lib-a/sk-a/SKILL.md`. The installed bytes follow bucket order.

Keep the non-host entry when both buckets are selected, independent of list order. Add a sync test that asserts the installed `SKILL.md` is the library body.

### 2. P8.2 — `exclude` of `<host bucket>/<rel>` loses to `requires` on vendor
`packages/skiller/lib/skiller/vendor.py:99`

`collect_skills` drops `env-skills/sk-b` (`vendor.py:44`). `resolve_requires` then puts it back. Its exclude tokens are only the skill name, the directory name, and `<plugin>/<rel>` (`mod-b/sk-b`). The host-bucket spelling is not one of them. Sync already adds that spelling in `_exclude_tokens`. `test_exclude_beats_requires` only uses the bare name `sk-b`.

`do_vendor` with `--buckets env-skills` and `--exclude env-skills/sk-b` printed:

```text
Exclude:     env-skills/sk-b
Skills:      2
Dependencies: 1 pulled via requires
Installed 2 skills -> …/.ai/skills
```

The tree contained both `mod-a/sk-a/SKILL.md` and `mod-b/sk-b/SKILL.md`.

Give the vendor lookup the same host-bucket tokens as sync (`<host bucket>` and `<host bucket>/<rel>`), and test that `env-skills/sk-b` stays out through `do_vendor`.

## Minor

### 3. P8.2 — `channel_overlap` does not expand a host bucket
`packages/skiller/lib/skiller/status.py:374`

Profile comparison expands a host bucket (`status.py:256`). The overlap check does not. `enabled` is the raw `enabledPlugins` name (`status.py:248`). A vendored module skill is attributed to the plugin via `source_plugin_of` (`status.py:291`), so `env-skills` and `mod-a` never meet.

Status for `env-skills@swissknifeman: true` plus a vendor manifest whose source is `packages/mod-a/skills/sk-a` printed `Included: env-skills keep` and the vendor channel, and did not print `DOUBLE CHANNELS`.

Expand host-bucket names on both sides before `channel_overlap`, and cover the stale `env-skills` key against a module source path.

## Checked, no finding

- **P8.1.** `core` imports, `plugins.py`, and `native_codex.py` are gone. Launchers no longer put the monorepo root on `PYTHONPATH`. The 829 tests include the foundation and boundary scans. No hub module names in the new module or its tests.
- **P8.2 connect.** Dry-run left `settings.local.json` byte-identical and wrote no `.bak`. A real write removed only `env-skills@swissknifeman`. `env-skills@other`, `other@elsewhere` (object), `keep@swissknifeman`, `lib-a@swissknifeman: false`, `model`, and `permissions` stayed.
- **P8.2 lock provenance.** A library managed record with a short `sha256` or `source: elsewhere` still returns `managed-provenance-invalid` when a well-formed module record sits beside it. `lock_problem` was not given a host exception.
- **P8.2 paths.** Vendor dry-run of plugin `mod-a` prints `packages/mod-a/skills/sk-a` and does not raise `relative_to`. A missing `skills/<plugin>` directory does not crash the support-file walk.
- **P8.2 standalone.** The new tests warn and return an empty expansion when the host file or `bucket_aliases` is absent. They passed inside the 829.
- **Golden.** Sandbox `registry --check` reported the artifacts relevant. Real bucket and host configs are not in the diff.
