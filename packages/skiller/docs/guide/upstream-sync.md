# Upstream-sync: tracking external skills

External skills should not become obsolete without notice. Each imported skill
contains `upstream.json` next to `SKILL.md` — source passport and strategy
updates.

## upstream.json

```json
{
  "schema_version": 1,
  "source": "github",
  "repo": "get-zeked/research-knowledge-super-skill",
  "strategy": "notify",
  "files": [
    {
      "path": "SKILL.md",
      "url": "https://raw.githubusercontent.com/.../SKILL.md",
      "sha256": "…",
      "fetched_at": "2026-06-11"
    }
  ]
}
```

## Strategies

| Status | Behavior sync-tuling |
|---|---|
| No `upstream.json` | self-written skill - does not touch |
| `strategy: replace` | file is mirrored as is, updates are applied automatically |
| `strategy: notify` | local copy adapted; updates are only reported, the file is not overwritten |
| `strategy: fork` | fork with our changes: `files[].path` indicates **pristine-mirror** (e.g. `references/source.md`), edits live in the wrapper `SKILL.md`. Placed on drift `review_pending: true` (blocks distribution) — manual transfer, then `--resolve` |
| `strategy: merge` | **composite of ≥2 sources** (`origins[]`: one `base` + ≥1 `supplement`/«suggest»), molded into a single skill. Sink **manual under agent control**: on the drift of any origin `merge.review_pending: true` blocks distribution - the agent re-merges manually, then `--resolve`. Autooverwrite prohibited |

## Commands

```bash
# Report: what's outdated (exit-code 10 = there are changes - convenient for CI)
./scripts/update-upstreams.sh --check

# Apply replace-updates, write new ones sha; for fork — stage
# incoming and raise review_pending (mirror/SKILL.md do not touch)
./scripts/update-upstreams.sh --apply

# Force overwrite of a specific skill (conflict resolution, replace)
./scripts/update-upstreams.sh --apply --force --skill imported/research

# fork: after manually transferring edits - promote incoming in the mirror and remove the flag
./scripts/update-upstreams.sh --resolve --skill ai/ai-agents
```

## `fork`: fork with local changes

For the big external skill that we **we adapt and do not want to update
automatically** (a context-economy requires not loading the entire file into the context). Layout:

```
skills/<bucket>/<name>/
├── SKILL.md            # thin navigator wrapper (our edits live here)
├── upstream.json       # strategy: fork; files[].path = references/source.md
└── references/
    └── source.md       # pristine-upstream mirror = baseline (loaded on demand)
```

Mirror (`references/source.md`) **byte-to-byte** is equal to what it gives `url`, —
therefore `--check` compares the fresh upstream with the recorded one `sha256` and sees drift.
Our edits are isolated in a wrapper `SKILL.md`, means the mirror remains pristine, a
diff port - almost zero.

Drift tracking cycle:

1. `--check` → `[notify] … strategy=fork — needs manual modification` (exit 10, CI falls).
2. `--apply` → puts a fresh upstream in `upstream/<name>.incoming.md`, puts
   `review_pending: true`. Mirror and `SKILL.md` **do not touch**.
3. **Gate**: `validate.sh` falls while `review_pending: true` — release/`registry`
   are blocked.
4. Agent checks `diff references/source.md upstream/<name>.incoming.md`, when
   upstream restructuring rules routing in the wrapper `SKILL.md`.
5. `--resolve` → mirror := incoming, `sha256`/`fetched_at`/`last_review` updated,
   `review_pending: false`, incoming deleted. `validate.sh` is green again.

Blocking in effect **only in the registry**: to consumer projects `upstream.json`
not vendored (as for replace/notify) — the already verified copy goes there
(`SKILL.md` + `references/source.md`).

## `merge`: composite from multiple sources

When the skill is actually **is made from two+ external skills** into a single piece
format, provenance with roles is fixed in `origins[]`:

```json
{
  "schema_version": 1,
  "source": "github",
  "strategy": "merge",
  "origins": [
    {"repo": "antfu/skills",      "role": "base",       "url": "…", "ref": "main",
     "sha256": "…", "fetched_at": "2026-06-26", "note": "structure and core taken"},
    {"repo": "onmax/nuxt-skills", "role": "supplement", "url": "…",
     "sha256": "…", "fetched_at": "2026-06-26", "suggest": "sections added SEO/modules"}
  ],
  "merge": { "review_pending": false, "last_review": "2026-06-26" },
  "files": [ { "path": "references/base.md", "url": "…", "sha256": "…", "fetched_at": "2026-06-26" } ]
}
```

- **Roles.** Exactly one `base` (is used as a basis) + ≥1 `supplement` — complementary
  source-«suggest» (added what exactly - field `note`/`suggest`). So you can see who
  «foundation», and who came in addition.
- **Sync is manual only, under agent control.** Autooverwrite for composite
  is meaningless (it was assembled by a person/agent from pieces). On the drift of any `origin`
  is set `merge.review_pending: true` — **gate**: `validate.sh`/`registry`/release
  are blocked until the agent verifies fresh sources and re-merges them into
  `SKILL.md` and will not clear the flag.

Maintenance cycle:

1. `--check` → drift of one of `origins` (fresh sha ≠ recorded) → exit 10.
2. `--apply` → puts the latest versions of sources in `upstream/<name>.<repo>.incoming.md`,
   puts `merge.review_pending: true`. `SKILL.md` **does not touch**.
3. **Gate**: `validate.sh` falls (like fork), for now `review_pending: true`.
4. The agent checks the inkings against the current composite and **re-merge** hands: which
   changes from `base`, which of `supplement` move to a single `SKILL.md`.
5. `--resolve` → updates `sha256`/`fetched_at` all origin, `merge.last_review`,
   removes `review_pending`. `validate.sh` is green again.

As for other strategies, `upstream.json` and `origins`-mirrors **are not vendored**
to projects - a verified `SKILL.md`.

## `body_path`: upstream body out SKILL.md (thin-navigator, P7.3)

Top level additive field `upstream.json` — for `replace`/`notify`-skills,
which are translated into **thin-navigator**: compact `SKILL.md` (triggers + map
sections, written locally by the agent) instead of a full upstream mirror whose body
physically lies in `references/full.md` (usually, the name is not fixed by the schema).
`body_path` names which `files[].path`-entry is now «body» — exactly by
her (and not by `SKILL.md`, which is no longer tracked here) `update-upstreams.sh`
believes sha/drift:

```json
{
  "schema_version": 1,
  "source": "github",
  "strategy": "notify",
  "body_path": "references/full.md",
  "files": [
    { "path": "references/full.md", "url": "https://raw.githubusercontent.com/.../SKILL.md",
      "sha256": "…", "fetched_at": "2026-07-01" }
  ]
}
```

Missing field = body in `SKILL.md`, as before (back-compat, nothing changes).
Technically sha/drift has long been considered **anyway `files[].path`**, not only
`"SKILL.md"` — uses this `strategy=fork` for your pristine-mirrors (see
above). `body_path` does not add a new reconciliation mechanism, but only **explicitly documents**
and **gateitis** him: `validate.sh` checks that the path really exists, does not escape
from the skill catalog and **is being monitored** some `files[]`-entry (otherwise stated
«body» is not actually checked - a quiet hole), and for `strategy=replace` additional
prohibits keeping near `files[].path == "SKILL.md"` (otherwise `--apply` quiet
would overwrite the navigator). Provenance in `skills.json` (`registry.py`) also looks at
`body_path` first of all - `entry.upstream`/`fetched_at` are taken from the one named
record, and not from the first one that came up.

For `fork`/`merge` separate `body_path`, is usually redundant - the same role there
is already playing `files[].path`/`origins[].url`, indicating pristine-mirror.

## Download channel: gh api → urllib

For GitHub raw-URL (`raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}`)
and if available **GitHub CLI** script pulls the file point by point through
`gh api repos/{owner}/{repo}/contents/{path}?ref={ref}`:

- auto-authentication from `gh auth` — no need to pass `GITHUB_TOKEN`;
- respects rate-limit GitHub API;
- one file instead of a full download - saving traffic/context (the same
  principle that in the skill `oss-dev/gh-review`).

If `gh` is unavailable or the call has dropped — **silent rollback** on `urllib`
(with `GITHUB_TOKEN` from the environment, if specified). Force disable gh-path:
`UPSTREAM_NO_GH=1`. Behavior and format `upstream.json` do not change.

## Weekly CI

GitHub Action `upstream-sync.yml` checks all upstreams once a week and - if
there are changes - opens PR with diff. Changes from other people's repositories fall
in `main` **only after review**: no external commits are merged automatically.

## How to choose a strategy

- **`replace`** — when the upstream is of high quality and its format is directly compatible:
  valid frontmatter (`name`, `description`), no need to adapt.
  You receive updates for free.
- **`notify`** — when you rewrote frontmatter, translated, shortened or
  otherwise adapted the skill. Upstream remains the benchmark: CI will report that
  the source has changed, and the decision to port the edits is yours.
- **`fork`** — when the outer skill is large and you wrap it in thin
  navigator (content in `references/source.md`, edits in the wrapper) and/or you want
  hard gate: upstream drift **blocks distribution** before manual transfer.
  Stronger `notify` (which only reports): adds pristine-mirror for diff,
  flag `review_pending` and step `--resolve`.
- **`merge`** — when the skill is completed **from several sources** (`base` +
  `supplement`). How fork by gate (`review_pending` + `--resolve`), but with
  multi-source provenance `origins[]` and **must be manual** re-merge
  agent (auto-overwrite is prohibited - the composite cannot be mirrored in one file).

## When to transfer a skill to `fork`

Selecting a strategy **on import** described above («How to choose a strategy»). Separate question -
when to translate already **alive** `notify`-skill in `fork`. Practice (rOpenSci 2025, GitHub
fork-management) outright refuses to give a numerical threshold («There are few universal numeric
thresholds»); formulation of the form «≥N discrepancies ⇒ `fork`» is not allowed here. Instead of a threshold -
**operational criterion of two required axes**:

- **Axis A — whether the edit is reapplied mechanically.** «Can this change be re-applied
  **mechanically** after an upstream update, or does it require human judgment every time?»
  Regeneration from RU-source or script replacement frontmatter — it's mechanical; translation/
  manual adaptation on each drift - no.
- **Axis B — how much does the next sync cost?** «Once the marginal cost of staying current is
  routinely higher than the value of upstream compatibility, the fork has become the correct
  operational choice.» We observe this: how many times in a row `update-upstreams.sh --check`
  for this skill actually led to manual work and how much of it there was - **observation on history,
  not a forecast**.

**Rule: transfer to `fork` is only legal when both axes are aligned** — edit is not reapplied
mechanically And the sync was already worth manual work. One axis converges, the other does not → stay on `notify`,
recording the observation. Axes contradict each other (editing is mechanical, but for some reason the sync is expensive) →
the reason is being investigated, the strategy is not changing.

Third, **cut-off** axis - «diff surface» (minimize the diff surface): if our edits
spread across many files/abstractions, `fork` will not save the problem, but will fix it - first
  assemble the edits into one seam. We have a seam for this according to construction: canonical
`SKILL.md` + `references/` and separate `upstream.json`.

## Price `fork`

`fork` — this is not «we took control of the skill», a **«we signed up for manual merge on each
upstream drift, forever»**. Three parts price (RAG, verbatim):

- **permanent merge tax** — the longer you don't synchronize, the harder the merge;
- **drift** — the further the fork moves from the upstream, the more difficult it is to contribute changes back;
- **security backports** — upstream security patches do not arrive automatically, they need to be caught and
  carry by hand.

Our specificity beyond practice: `fork`/`merge` raise `review_pending`
(`merge.review_pending` for `merge`), and this flag **blocks `validate.sh`/`registry`/release
TOTAL repository**, not only a specific skill - that is, it is not only the author who pays the price of the solution
of the translated skill, but also anyone who closes unrelated work at that moment. Formulation
«`fork` gives us control» without mentioning this price is a defect in production, not just incompleteness.

## Source directory (what is accepted, what is rejected)

Solutions «take / adapt / reject / trust upstream» for each external
to the source repository are maintained in the directory
`references/README.md` relative to the Skiller package root
(table `Source | Value | Status`). This is the source of truth by selection; per-skill
passports - in `upstream.json` next to each imported `SKILL.md`.
