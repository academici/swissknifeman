# CI/CD

Five GitHub Actions automate validation, synchronization and replenishment
registry.

| Workflow | Trigger | Purpose |
|---|---|---|
| `validate.yml` | push / PR | `scripts/validate.sh`: frontmatter, upstream.json, profiles, manifests |
| `upstream-sync.yml` | weekly | checking upstreams → PR with diff |
| `sha256-update.yml` | push | recalculation of registry hashes |
| `scanner-pr.yml` | weekly | PR with scanner candidates |

## Principle: everything through PR

No automatic process writes to `main` directly meaningful
changes:

- external skill updates (`upstream-sync.yml`) — PR with diff, merge after review;
- scanner candidates (`scanner-pr.yml`) — PR, manual selection;
- validation (`validate.yml`) — mandatory gate for any PR.

## Local = in CI

`./scripts/validate.sh` — the same script locally and in CI. If it's green
locally, `validate.yml` will also pass. Run before each PR.

## Exit-codes for automation

`update-upstreams.sh --check` returns `10`, if there are outdated upstreams, -
this is what the weekly workflow:

```bash
./scripts/update-upstreams.sh --check
# exit 0  — everything is relevant
# exit 10 — there are changes → CI opens PR
```
