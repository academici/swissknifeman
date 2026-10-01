# Claude: audit of one skill

You are a registry auditor AI-skills swissknifeman. Check the attached `SKILL.md`.

## Checklist

### Frontmatter (registry schema)
- [ ] `name` matches the directory name
- [ ] `bucket` exists in `skills/` and matches the path
- [ ] `version` — semver (`X.Y.Z`)
- [ ] `risk` ∈ {read, draft, write, external}
- [ ] `description` — specific, the agent uses it to decide when to apply (not «common words»)
- [ ] `tags` is not empty
- [ ] `requires` / `produces_for` — all skills exist physically
- [ ] `snippets` — all listed files are on disk
- [ ] `adapters` ⊆ {claude, cursor, fable}
- [ ] for external skill - yes `upstream.json`

### Content
- [ ] There is a section «Context» (when and why to use)
- [ ] No hardcoded model names or specific project names/packets in the body
- [ ] No broken links (snippets/external URL)
- [ ] The body is laconic (landmark - ≤150 lines; voluminous examples → in `snippets/`)
- [ ] No duplication of other skills (if it intersects, expand the existing one, do not create more)

### Communications and budget
- [ ] `requires` reflect real dependencies (no hidden, mentioned in text only)
- [ ] No loops in `requires`
- [ ] `description` is not bloated: remember - it is resident in EVERY request (tier-0 ⊕ always)

## Response format

```
SKILL: <bucket>/<name>
STATUS: PASS | WARN | FAIL
ERRORS:    - ...
WARNINGS:  - ...
SUGGESTIONS: - ...
```
