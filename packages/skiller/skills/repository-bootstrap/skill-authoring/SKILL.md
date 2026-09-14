---
name: skill-authoring
bucket: repository-bootstrap
version: 3.0.1
description: "Rules for creating or editing EN-only registry skills, references, snippets, metadata, provenance, tests, and generated projections."
when_to_use: "Activate for any change under packages/skiller/skills/ or the skill generator."
risk: write
persona: oss-dev
tags: [skill-authoring, en-only, upstream, root-bootstrap]
requires: []
produces_for: []
outputs: ["packages/skiller/skills/**/SKILL.md", "packages/skiller/skills/**/upstream.json", "packages/skiller/skills/**/snippets/"]
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill authoring

Local registry skills are EN-only. The canonical, human-edited source is `SKILL.md`; provider
adapters, registries, locks, marketplace manifests, and bootstrap projections are generated from
it. There is no parallel locale source and no source-hash marker.

## Activation and boundaries

Use this skill when adding, editing, moving, or deleting anything under
`packages/skiller/skills/**`, including `SKILL.md`, `references/`, `snippets/`, `adapters/`,
`evals/`, and `upstream.json`.

- Read the target skill, adjacent assets, package guide, and owning tests before editing.
- Preserve the skill's public identity unless the task explicitly changes it.
- Keep one semantic source. Provider files are additive projections, never competing canons.
- Do not compact unrelated skills during a focused task.
- Do not edit generated `skills.json`, publication locks, marketplace files, graph docs, or
  `.agents/skills` bootstrap projections by hand.

## Canonical layout

```text
skills/<bucket>/<name>/
├── SKILL.md          # required EN canon
├── upstream.json     # required provenance declaration
├── references/       # optional detailed normative/reference material
├── snippets/         # optional copyable templates + index.json
├── adapters/         # optional provider-specific additive guidance
└── evals/            # optional behavioral evals
```

Root-bootstrap identities live under `skills/repository-bootstrap/<id>/` and project into the
repository `.agents/skills/` bootstrap surface through the registry generator. The projection is
not the source of truth.

## Frontmatter

Every `SKILL.md` carries a YAML frontmatter block with:

- `name`, identical to the directory name;
- `bucket`;
- semantic `version`;
- concise `description` and operational `when_to_use`;
- `risk`, `persona`, and `tags`;
- `requires` and `produces_for`;
- `outputs`, `snippets`, and `adapters`;
- `sha256: ""` as the registry-owned placeholder where the schema requires it.

Keep descriptions discovery-oriented and under the registry limit. `when_to_use` names observable
triggers. Do not encode provider-specific model names in shared semantics.

## Body design

The selected skill is read in full, so its entry carrier must be focused:

1. identity and activation;
2. unconditional invariants and safety boundaries;
3. decision or routing map;
4. exact commands and validation;
5. navigation to references/snippets.

Move large tables, extended examples, migrations, and background into directly linked references.
References may be normative, but the entry carrier must say when to read them. Snippets copy the
canon and introduce no new rules. Prefer a measured weight budget over arbitrary no-growth rules.

Write for an agent that did not see the authoring conversation. Use imperative language for hard
requirements, distinguish machine gates from advice, and name the owning command for generated
artifacts. Avoid duplicated generic knowledge already supplied by platform instructions.

## Canon literals

If code compares exact human-language literals from a plan or document, register each required
literal in the canonical `SKILL.md` with:

```html
<!-- i18n-keep: <exact literal> -->
```

The literal must also appear in the body where its contract is explained. A directive-only
registry entry is not a rule. Heuristic prose detectors belong to the implementation's documented
heuristic registry, not to `i18n-keep`.

## Provenance (root-bootstrap, P1.2)

External provenance uses adjacent `upstream.json` with the actual registry strategies:
`replace`, `notify`, `fork`, or `merge`. Repository-authored skills do not need fabricated
external provenance. Preserve the declared upstream revision and license; describe local
adaptations honestly. Check the owning schema before selecting a strategy; `original` and
`vendor` are not supported strategy values.

Record source URL/revision/license and local transformation notes. External code is a design
source to rewrite unless explicit vendoring is authorized. Never vendor proprietary content.
Update `docs/reference.md` for external design sources that affect repository architecture.

## Overlap and dependencies

Before adding a skill, search names, descriptions, triggers, and referenced concepts. Extend an
existing owner when the responsibility is the same. A new skill needs a distinct activation
boundary and owner. `requires` names real prerequisites; do not manufacture dependency edges to
improve discovery. Cycles are defects.

## Provider parity

Shared `SKILL.md`, references, and snippets carry the meaning. Provider adapters may explain native
syntax or capability mapping without weakening gates or changing payload identity. Regenerate the
Codex projection and marketplace through `skiller registry`; Claude consumes the canonical plugin
carrier. A provider is `verified` only after its own replay/check, not because another provider
passed.

## Workflow

1. Inspect the target, applicable references/assets, overlaps, and provenance.
2. Edit canonical `SKILL.md` and owned handwritten assets.
3. Add/update focused tests or evals for new behavior and failure branches.
4. Run `bash packages/skiller/bin/skiller registry` to regenerate projections/manifests/locks.
5. Run `bash packages/skiller/bin/skiller registry --check`.
6. Run affected package validation; for repository changes also follow release discipline and
   update root `CHANGELOG.md` under `[Unreleased]` when user-visible.

Generated drift means the source was not regenerated; repair at the canonical source or generator,
then regenerate. Never patch the projection to make a check green.

## Review checklist

- [ ] Activation boundary and owner are explicit.
- [ ] `SKILL.md` is the only semantic source and is EN-only.
- [ ] Frontmatter is complete and identity matches the directory.
- [ ] Entry carrier is focused; details are routed to linked references.
- [ ] Exact literals are declared and used.
- [ ] `upstream.json` faithfully records provenance.
- [ ] Snippet index matches snippet files.
- [ ] Tests/evals distinguish success from fail-closed behavior.
- [ ] Registry was regenerated, not hand-edited, and `registry --check` passes.
- [ ] Provider verification status reflects actual replay evidence.
