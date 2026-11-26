# [1.1.0] - 2025-12-10

Skill reference `release-engineering`.

...
```

**Automation** — I recommend one of:
- `changesets` (JS): PR-driven, contributor writes changeset in PR
- `release-please` (Google, supports many languages): commit-conventional, auto-generation
- Manual - for very small packages

Do not use «dump git log» — this is not changelog.

### 4. Release pipeline (CI/CD)
Minimum for `v1.0+`:

```yaml
# .github/workflows/release.yml (diagram, not final)
on:
  push:
    tags: ['v*']

jobs:
  test:
    # full test matrix (all versions runtime + OS)
  build:
    needs: test
    # artifact assembly
  publish:
    needs: build
    # publish on npm / Packagist / pub.dev
    # requires secret (NPM_TOKEN etc.) via OIDC if possible
  sign:
    # GPG-release signature in GitHub Releases
  changelog:
    # section [Unreleased] → new version in CHANGELOG.md
```

**Rules:**
- Release only from tags, not from main-branches (prevents accidental publish)
- Provenance (npm `--provenance`, GitHub OIDC) — required for `v1.0+`
- 2FA for publishing the package - required for all maintainers

### 5. Deprecation policy
When something needs to be deleted - **do not delete immediately**. Standard flow:

| Step | When | Action |
|:---|:---|:---|
| 1. Mark deprecated | MINOR | JSDoc `@deprecated`, console warn when used |
| 2. Wait | minimum 1 MAJOR cycle (≥ 6 months) | users are migrating |
| 3. Remove | next MAJOR | breaking change in CHANGELOG |

**Exception - security**: vulnerable API can be removed earlier with an explicit notice + migration guide.

---
