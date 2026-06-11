# Contributing

## Adding a Skill

1. Copy `SKILL_TEMPLATE.md` → `skills/{bucket}/{name}/SKILL.md`
2. Add `snippets/` with `index.json` manifest
3. Run `./sync.sh --update-registry`
4. Open PR — CI validates frontmatter

## Buckets

| Bucket | Purpose |
|--------|---------|
| founder, pm, architect | Business & architecture |
| oss-dev, quality, operator | Engineering practices |
| devops, php | Infrastructure & Laravel |
| roles | Persona-based skills |
| imported | External super-skills |

## Snippet Guidelines

- Anonymize project namespaces: `namespace App\...`
- Add source comment: `// Source: {project}/{file} (anonymized)`
- Quality threshold for scanner: ≥ 60 (see `.skills-scanner.json`)

## Adapters

Provider-specific deltas go in `skills/{bucket}/{name}/adapters/` — never duplicate full SKILL.md.

Global adapter docs: `adapters/{cursor,claude-code,perplexity}/`.

Отдельного sync-скрипта для Obsidian нет. `sync.sh` пушит только в `academici/brain`.

## Scanner

```bash
./scripts/scan-skills.sh              # SCAN + ANALYZE
./scripts/scan-skills.sh --extract    # + EXTRACT to .scanner-output/
./scripts/scan-and-pr.sh              # + COMMIT + PR
```

## Sync to Brain

```bash
BRAIN_PATH=/path/to/brain ./sync.sh --update-registry
```

## Backlog

- [ ] Filament resource generator skill
- [ ] Deeper AzGuard snippet extraction via scanner
- [ ] Per-skill adapter deltas where providers diverge
