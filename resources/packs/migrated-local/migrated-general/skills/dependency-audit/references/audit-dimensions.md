# 5 audit dimensions

Skill reference `dependency-audit`.


### 1. Lockfile sanity

| Measurement | What to check |
|:---|:---|
| **Lockfile committed** | `package-lock.json` / `composer.lock` / `pubspec.lock` in git (for applications - yes; for libraries - debatable, see below) |
| **No phantom deps** | All imports match the dependencies in the manifest, no transitives «works randomly» |
| **No duplicates** | One version of each dependency where possible (`npm dedupe`, `composer why-not`) |
| **Pinned vs range** | `^1.2.3` for libraries OK, `=1.2.3` for applications / lockfile-tracking |
| **Resolutions / overrides** | Commit to manifest, not «magically» |

**Lockfile for libraries:** there are two schools.
- **Don't commit** (classic): package is tested with different versions of dependencies, catches conflicts before.
- **Commit** (current practice, especially for CI reproducibility): tests are deterministic, but dependabot updates.

**Recommendation:** commit + dependabot + CI matrix by `peerDependencies` major-versions.

### 2. Vulnerability scan

| Tool | Stack |
|:---|:---|
| `npm audit` / `pnpm audit` | JS |
| `composer audit` | PHP |
| `dart pub outdated --mode=security-fix` | Dart |
| `pip-audit` | Python |
| `osv-scanner` | universal, via CLI |
| GitHub Dependabot Alerts | repo level |
| Snyk / Socket.dev | extended supply-chain |

**Policy:**
- `critical` / `high` vulnerabilities - **fix required** before release
- `moderate` — fix desirable; if not possible, document it in `Dependency_Audit.md`
- `low` — log, do not block release

**Transitive vulnerabilities without public fix:**
- Try via `overrides` / `resolutions` force safe-version
- If impossible — document in SECURITY.md and rate exposure

### 3. License compatibility

Each dependency must have **known compatible license**. Checked automatically:

| Tool | Stack |
|:---|:---|
| `license-checker` | JS |
| `composer licenses` | PHP |
| `licensee` (gem) | universal for files |
| `fossa-cli` / `licensed` | enterprise-grade |

**What to look for:**

| Dependency License | Compatible with MIT/Apache project |
|:---|:---|
| MIT, BSD-2/3, ISC, 0BSD, Apache-2.0 | ✅ OK |
| MPL-2.0 | ✅ OK (file-level copyleft, can be linked) |
| LGPL-2.1+/3.0+ | ⚠️ Requires dynamic linking — for libraries is usually OK, check |
| GPL-2.0/3.0 | ❌ Will infect the entire project GPL |
| AGPL | ❌ Will infect, plus SaaS-obligations |
| BUSL, SSPL, Elastic | ❌ Not OSS — usually blocks commercial usage |
| Unknown / no SPDX | ⚠️ Request to maintainer or replacement |
| Custom proprietary | ❌ Usually not possible |

**Prohibited licenses for vault-OSS:** GPL, AGPL, BUSL, SSPL, any «source-available».

### 4. Supply-chain risk

Silently dangerous:

| Risk | How to check |
|:---|:---|
| **Typosquatting** | `npm-name-deputy`, manual name checking against popular ones |
| **Maintainer turnover** | How many active maintainers are there? If 1 - bus factor problem. |
| **Recent ownership transfer** | Smell-test: change ownership + new versions for < 30 days = red flag |
| **Postinstall scripts** | `npm install --ignore-scripts` for CI; explicit allowlist for prod |
| **Binary blobs** | Binaries in node_modules / vendor — check hashes |
| **Unusual dependencies** | `colors` / `faker` / `event-stream`-class incidents — track `socket.dev` levels |
| **Pre-1.0 dependencies in production paths** | Count; > 30% — risk |

**Protection:**
- Pin individual critical deps for a specific version
- `npm install` with `--ignore-scripts` in CI, scripts explicitly allow
- `npm:cache:max-age` to prevent surprise updates

### 5. SBOM (Software Bill of Materials)

**Why:** requirement for enterprise-consumers (SOC2, FedRAMP), and just good practice for transparency.

**Format:** CycloneDX (JSON) or SPDX. CycloneDX is more common in OSS.

```bash
# JS
cyclonedx-npm --output-format JSON --output-file SBOM.json

# PHP
cyclonedx-php-composer --output-format=JSON --output-file=SBOM.json

# Dart
# no official - generate manually from pubspec.lock or use syft
```

**What's in SBOM:**
- Package name, version
- License (SPDX)
- Hash
- Direct vs transitive dependencies
- Origin (registry / git URL)

**Release link:** SBOM is published as release artefact (next to tarball/zip). Updated with every release.

---
