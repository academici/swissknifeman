# 6 artifacts governance (by priority)

Skill reference `oss-governance`.


### 1. LICENSE (required before publication)

| License | When to choose | Pros | Cons |
|:---|:---|:---|:---|
| **MIT** | Default for libraries | Maximum adopt-rate, simple | No copyleft, does not protect against forks-to-proprietary |
| **Apache-2.0** | If important patent-grant | Explicit patent grant, protection against submarine patents | A little more complicated, it requires NOTICE |
| **BSD-3-Clause** | Analogue MIT with no-endorsement clause | Simple, BSD-family | Likewise MIT by adopt |
| **MPL-2.0** | If you want file-level copyleft | You can link to a proprietary one, but changes in files MPL remain open | Less known |
| **AGPL-3.0** | SaaS-service that you host yourself | Protects against competitive hosting | Many companies prohibit AGPL in the product - sharply reduces adopt |
| **GPL-3.0** | Completely copyleft library | Strong protection of openness | Infectivity - the end adoption in commercial |
| **BUSL-1.1 / SSPL** | source-available, not OSS | Protecting the business model | **This is not OSS** — cannot be called OSI-compliant |

**Default for vault-projects:** MIT. **Exceptions:**
- If there are patents or strong risk patent troll → Apache-2.0
- If SaaS-competition (type Elastic) → think about AGPL or BUSL, but this is no longer OSS

**Inside the file LICENSE — full license text**, is not a link. SPDX-identifier in `package.json`/`composer.json` is required.

### 2. CODE_OF_CONDUCT.md
Standard - **Contributor Covenant v2.1** (https://www.contributor-covenant.org). Don't make up your own.

What to add from myself:
- Email for reporting violations (separate, not personal)
- Reporting flow (anonymity, confidentiality)
- Enforcement ladder (warning → temp ban → permanent ban)

### 3. CONTRIBUTING.md
**Structure:**

```markdown
# Contributing to [ProjectName]
