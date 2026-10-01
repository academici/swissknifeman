# Laravel-project from scratch

End-to-end scenario: new Laravel-project → completely ready AI-environment
for two teams.

## Starting point

```bash
laravel new shop && cd shop
# or: git clone git@github.com:me/shop.git && cd shop
```

## Step 1. Skills

```bash
skiller vendor --agent claude
```

Autodetect sees `artisan` + `composer.json` → profile `laravel-project` →
in `.claude/skills/` lay flat bucket-s **architect, php, devops,
quality, operator**: skills in architecture, Laravel-patterns, testing,
Docker, code review and incidents.

You can check what will be installed in advance:

```bash
skiller vendor --list
```

## Step 2. Permissions

```bash
~/projects/packages/swissknifeman/packages/skiller/scripts/apply-permissions.sh --target .
```

Auto detect by markers: `artisan` → `laravel`, `package.json` → `node`,
`Dockerfile`/`compose.yaml` → `docker`. B `.claude/settings.local.json`
pour in `base + laravel + node (+ docker)`:

- ✅ without prompts: `php artisan`, `composer`, `vendor/bin/pest`, `pint`,
  `phpstan`, `npm run`, `git` (except push), file operations;
- ❓ with confirmation: `git push`, `migrate:fresh`, `db:wipe`, `rm -rf`;
- 🚫 disabled: read `.env`, `*.pem`, `~/.ssh`, `sudo`.

## Step 3. Commit the configuration (optional)

So that any clone of the project restores the same environment:

```bash
cp ~/projects/packages/swissknifeman/packages/skiller/.swissknife.example.json .swissknife.json
# edit for the project and commit
```

Optional block `providers` in the example specifies provider selection v1: missing block
remains the same Claude Code-only result and does not change the file automatically. On the current
stage this block is only validated and resolved with provenance; he himself is not
sets Codex and does not generate provider-artifacts.

## Result

```
shop/
├── .claude/
│   ├── skills/                  # 31 skill under Laravel-development
│   ├── settings.local.json      # permissions: base+laravel+node
│   └── settings.local.json.bak  # backup if the file existed
├── .swissknife.json             # committed configuration (opt.)
└── ...
```

Open Claude Code — and the agent immediately knows how to: design a structure according to
skills architect, write tests according to `laravel-testing`, run `artisan`,
`composer` and linters without a single prompt.

## Typical improvements

```bash
# Eliminate irrelevant skills
skiller vendor --profile laravel-project --exclude botkit

# Add docker-preset, if the auto detector did not see it
~/projects/packages/swissknifeman/packages/skiller/scripts/apply-permissions.sh --target . --preset docker
```
