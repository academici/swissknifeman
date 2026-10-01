# Projects

Ecosystem Project Registry - in `config.json` (at root monorepo, superset brain
`.projects.json`).

## Load priority

```
config.json      (primary — at the root of the monorepo, if any)
    ↓ fallback
.maind.json      (legacy-name of the same config - backward compatibility)
    ↓ fallback
.projects.json   (legacy brain — read-only, with migration warning)
    ↓
empty config
```

`load_config` returns `(config, source)`, where `source ∈ {"config.json", ".maind.json",
"brain-fallback", "empty"}` — so that the origin can be seen.

## CLI

```bash
maind projects list [--namespace NS] [--json]
maind projects health [--project ID | --namespace NS | --all] --evidence-set FILE --json
maind projects sync --from brain [--path ~/Vaults/Brain]
maind namespaces [--json]            # namespace-groups and their member projects
```

`sync` idempotent: merge by `id`, updates brain-source fields
(`name`/`local_path`/`vault_path`/`type`/`enabled`/`docs_folders`) and **saves**
maind-only fields (`skills`/`tags`/`namespaces`/`dependencies`/`agents`/`repo`).

## Provider health

`projects health` — read-only exact-set check by frozen `provider-health-v1`. File
`--evidence-set` commits sealed project/provider/axis requirements and redacted evidence
identities; mAInd complements package-owned observations only through public worktree-local CLI with
limited timeout. Command does not read provider targets like intent and doesn't fix anything.

`aggregate=green` is only possible with an exact match project set and complete fresh coverage of all
required provider/axis rows. Missing/extra/duplicate project or provider, timeout, malformed JSON,
stale/unknown evidence, required unsupported capability and only one successful provider remain
explicit `non-green`. Well-constructed `non-green` report means that the check was completed, but not
is permission to rollout or repair.

Durable JSON contains only stable project/provider/axis/source/evidence identities and
diagnostics; absolute roots, secrets and raw subprocess output are rejected.

## Namespaces

Field `projects[].namespaces` groups projects and **isolates** cross-project links: edge
is built only between projects of the same group (`["*"]` — general infrastructure, communicates with
everyone). `--namespace NS` filters `projects list`/`status` and `sync`. More details -
[Architecture → Namespaces](../architecture#namespaces-bond-isolation).

## Mapping from brain

Actual diagram brain — `{name, enabled, vault_path, repo, folders}` (fields `id`/`local_path`/
`type` from the old description in brain missing - synthesized):

| brain | maind | rule |
|:--|:--|:--|
| `name` | `name`, `id` | `id` = slug from `name` |
| `repo` | `local_path` | path to code |
| `vault_path` | `vault_path` | as is |
| `folders` | `docs_folders` | as is |
| — | `type` | by repository markers (composer.json→php, package.json→node, .obsidian→vault) |

Next: [Migration →](./migration)
