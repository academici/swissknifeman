## Summary

<!-- What is changing and why. This is a monorepo-umbrella `swissknifeman`: some
     independent packages under a common roof. -->

## Affected packages

<!-- Check all, what touches PR -->

- [ ] `skiller` — skill register (skills/, registry, connect/vendor)
- [ ] `harness` — setting up the environment Claude Code (permissions/MCP/hooks)
- [ ] `maind` — memory + graph + coordination
- [ ] `core` — general stdlib-foundation (affects all packages at once)
- [ ] docs / infrastructure (docs/, install.sh, CI, marketplace)

## Type of change

<!-- feat | fix | refactor | docs | chore — Conventional Commits, in Russian -->

## Checklist

- [ ] `scripts/validate.sh` green in each affected packet
      (`bash packages/<pkg>/scripts/validate.sh`)
- [ ] Changes in `core/` — both dependent packages (skiller + maind) pass validate
- [ ] Skills: `SKILL.md` has frontmatter (name·bucket·version·description);
      snippets — `index.json`; no specific project names/secrets
- [ ] Plugins/buckets/teams changed → driven away `skiller registry`
      (regenerate `.claude-plugin/marketplace.json`, skills.json, index, graph)
- [ ] New package/team → yes `.claude-plugin/plugin.json` with non-empty description
- [ ] Content change → updated `docs/` and affected `CLAUDE.md`

## Test plan

- [ ] CI / validate passes for affected packages
- [ ] Installation: `./install.sh --bin-dir <tmp>` puts `skiller` · `harness` · `maind`
- [ ] (if appropriate) manual check: teams CLI / slash-plugin commands
