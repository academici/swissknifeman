# Profiles and auto-detection

Profile is a match «project type → set bucket-ov». Profiles are in
`profiles/*.json`, one file per project type.

## Built-in profiles

| Profile | Autodetect | Bucket-s (default) |
|---|---|---|
| `obsidian-vault` | `.obsidian/` | system, architect, pm, founder, operator, roles, finance, legal, marketing, sales, research, creative |
| `laravel-project` | `artisan` + `composer.json` | system, architect, **php** (core), laravel-testing, laravel-auth, laravel-data-layer, devops, quality, operator |
| `php-package` | `composer.json` without `artisan` | system, oss-dev, php, php-packages, laravel-testing, quality, devops |
| `node-frontend` | `package.json` (Vue/Vite) | system, architect, **frontend** (core), frontend-vue, frontend-vite, frontend-linting, frontend-tailwind, quality, devops |
| `standalone` | no markers | all + generate-skill |

> **`php` and `frontend` divided into thin buckets** (Filament/Livewire/Nuxt/Naive-UI etc. - separate
> plugins are not loaded by default). PHP: core `php` + `laravel-{testing,filament,livewire,data-layer,
> auth,architecture,extras}` (+ `php-packages`). Frontend: core `frontend` + `frontend-{vue,nuxt,tailwind,
> naive-ui,reka,vite,linting,animations,figma,wayfinder,backend}`. The profile gives a line default; the rest
> is connected point-by-point - with a separate bucket or [preset](./presets) (`laravel-admin`, `vue-spa`, …).

## Profile format

```json
{
  "name": "laravel-project",
  "description": "Large Laravel application development",
  "buckets": ["system", "architect", "php", "laravel-testing", "laravel-auth", "laravel-data-layer", "devops", "quality", "operator"],
  "include_meta": false
}
```

- `buckets` — what bucket-s put;
- `include_meta` — whether to enable meta-skill `generate-skill` (is needed only there,
  where you create new skills, usually `false`).

## How autodetect works

`skiller vendor` (like `connect`) checks tokens in the target directory
in order of specificity:

1. `.obsidian/` → `obsidian-vault`
2. `artisan` + `composer.json` → `laravel-project`
3. `composer.json` without `artisan` → `php-package`
4. nothing found → `standalone`

Can be overridden with the flag `--profile`, list `--buckets` or file
[`.swissknife.json`](./installation#commit-configuration-swissknife-json).

## Listing Budget

Claude Code drops descriptions of less frequently called skills when the listing exceeds
budget - ≈1% of the context window in TOKENS converted into symbols by the coefficient
×3: by 1M-models are **30 000** characters, 200K — **6 000** (not 10,000/2 000,
as the first run considered - repo fact `claude --debug-file` WARN «47021 chars >
30000 budget», see
§0). Table - active profile set symbols (buckets + supervised `core@`,
dedup by catalog), filmed 2026-07-28 by team `skiller budget` the same path,
which is going to connect-channel:

| Profile | Skills (+`core@`) | Symbol | ×budget 1M (30 000) | ×budget 200K (6 000) |
|:--|--:|--:|--:|--:|
| `blender` | 30 | 6 884 | 0,23 ✅ | 1,15 ❌ |
| `dart-flutter` | 44 | 9 762 | 0,33 ✅ | 1,63 ❌ |
| `node-package` | 46 | 9 519 | 0,32 ✅ | 1,59 ❌ |
| `python-backend` | 62 | 12 175 | 0,41 ✅ | 2,03 ❌ |
| `obsidian-vault` | 66 | 12 177 | 0,41 ✅ | 2,03 ❌ |
| `php-package` | 76 | 15 753 | 0,53 ✅ | 2,63 ❌ |
| `node-frontend` | 79 | 17 021 | 0,57 ✅ | 2,84 ❌ |
| `laravel-project` | 86 | 17 293 | 0,58 ✅ | 2,88 ❌ |
| `platform-service` | 110 | 23 003 | 0,77 ✅ | 3,83 ❌ |
| `standalone` | 227 | 49 458 | **1,65** ❌ | 8,24 ❌ |

**Nine out of ten profiles fit within the real budget 1M-models** (output
changes to the opposite of what was considered the first approach `research/20`
§1.1 for the wrong unit - the root of the discrepancy is there). **At 200K-models
overflow all ten** — this is NOT gated by the test (`test_profile_listing_budget.py`
prints warning at 200K, and does not crash: reset `blender` up to 2,000
character is impossible without losing the meaning of the profile).

**`standalone` — named exception, not a defect.** Profile means «markers
there is no stack - install the entire registry»; to narrow its composition would mean to cease to be
`standalone`. It remains CONSCIOUSLY crowded (1,65× budget 1M) —
named constraint (Implementation Rules P3.5), not what the test should
hide. In case of obvious overflow of listing on `standalone`-project - lever №2/№3
below (remove excess buckets via `--profile`/`--buckets` explicitly instead
`standalone`, or techniques from the recommendation card).

### Recommendation card for other people's configs

Our tooling does NOT write `enabledPlugins`/`skillOverrides`/`skillListingBudgetFraction`
other people's projects (does this `skiller connect`/`update` at the owner's command, not
automatic). If `claude --debug` of your project prints `Skill listing over
budget`, available levers - by price, from cheap to expensive:

1. **Narrow down the set** — less buckets/presets (`skiller connect --buckets …`),
   disable unused plugins (`skiller status` prints 0-usage
   candidates via `/doctor`).
2. **`skillOverrides: "name-only"`** in `.claude/settings.json` — for long
   of the tail of rarely called skills: the listing has a name without a description
   (description is not resident, but the skill is still visible by name):
   ```json
   {
     "skillOverrides": {
       "<bucket-or-skill>": { "descriptionMode": "name-only" }
     }
   }
   ```
3. **`skillListingBudgetFraction`** — raise the share of context under the listing (honestly:
   resident ⊕ tier-0 grows with her):
   ```json
   { "skillListingBudgetFraction": 0.02 }
   ```

Both keys are written by YOU to the project config - `skiller` does not generate or edit them.

## Your profile

Add `profiles/<name>.json` in the format above - it will immediately become available via
`--profile <name>`. Validator (`./scripts/validate.sh`) will check that everything
specified bucket-s exist.

::: tip Profiles and permissions
Uses the same auto-detection logic
[`apply-permissions.sh`](/harness/configs/claude-permissions#script-apply-permissions-sh) —
it selects permission presets based on stack markers (`artisan`, `package.json`,
`pyproject.toml`, `Dockerfile`).
:::
