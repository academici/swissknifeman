# Security Policy

## Report a vulnerability

Found a security issue (leaked secret in snippet, malicious external skill,
hole in installation scripts)? Write privately to **dv.vostrikov@gmail.com** —
do not open public issue until approval.

Describe: affected file/skill, reproduction steps, potential impact.
The answer is within a few days; correction and disclosure - after agreement.

## Trust Model

The registry is maintained by provider-neutral `SKILL.md` + `snippets/`. Content Trust
arranged by priority: **project > source > registry**. The project can always
override registry-imposed behavior, source (for example Laravel Boost) —
registry core.

### External (imported) skills

Each external skill is accompanied by `upstream.json` next to `SKILL.md`:

- **`source` / `files[].url`** — where the file came from (github / http / file).
- **`files[].sha256`** — hash of the exact version imported into the registry. When
  synchronization (`scripts/update-upstreams.sh`) new upstream is downloaded, hash
  is recalculated and compared with the captured one.
- **`strategy`**:
  - `notify` (default) — hash divergence is not automatically applied,
    and gets into PR with diff for manual review (workflow `upstream-sync.yml`).
  - `replace` — trusted source, can be updated automatically.
- **`license`** — source license preserved; the registry does not erase it.

This means: external content **is not executed or updated silently** — changes
are visible as diff in PR before they get into anyone's projects.

### There are no secrets in snippets

Snippets are extracted from real projects by the scanner (`scripts/scan-skills.sh
--extract`), which anonymizes paths and namespaces. Before the merge
PR-checklist (`.github/PULL_REQUEST_TEMPLATE.md`) explicitly requires:

- no secrets/credits in snippets;
- namespaces are anonymized.

`scripts/validate.sh` checks the structure (frontmatter, manifests, graph
dependencies) on each PR; tests run on the matrix Python (`test.yml`).

## Installation and distribution

CLI is placed as a symlink on `bin/skiller` (`./install.sh`) — external
no dependencies, only stdlib Python 3. Installation scripts do not execute
network requests and do not require root. The state of connected projects is stored
locally in `~/.swissknifeman/projects.json`.

## Supported versions

Latest release supported `main`. Rollback: `git checkout <tag>` in
registry repositories + repeated `./install.sh`.
