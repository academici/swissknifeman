# Skills from packages (vendor-skills)

Skills get into the project in two ways, and they complement each other:

| Direction | Mechanism | Who is the source |
|---|---|---|
| **Registry → project** | `skiller vendor` | SwissKnifeMan: universal skills for the project type |
| **Package → application** | `vendor:publish` | Composer-package: domain skills about the package itself |

The first direction is described in [Installation](./installation). This page -
about the second: how the package carries its skills with it.

## Idea

Package that solves a domain problem (security, billing, integrations), knows
about its subject area more than any universal registry: patterns
usage, migration scenarios, common errors. It is logical that such
package **supplied the skills himself** for AI-consumer agent:

```
composer require acme/my-package
php artisan vendor:publish --tag=my-package-skills
# → application agent can work with the package
```

So the skills remain next to the code they describe and are versioned
along with the package and are updated when it is upgraded.

## Structure inside the package

```
vendor/acme/my-package/
└── resources/
    └── skills/
        └── my-package-security/      ← folder name with package prefix!
            ├── SKILL.md
            └── snippets/
                ├── threat-detection.php
                └── rbac-policy.php
```

::: warning Package prefix is required
Skill folder name - `<package>-<skill>`, not just `<skill>`. At the consumer
skills from different sources are in the same directory; the prefix eliminates collisions.
:::

## Publication in ServiceProvider

```php
// B PackageServiceProvider::boot()
if ($this->app->runningInConsole()) {
    // Option A: agent-neutral layout
    $this->publishes([
        __DIR__.'/../resources/skills' => base_path('.ai/skills/vendor/my-package'),
    ], 'my-package-skills');

    // Option B: flat layout for Claude Code
    $this->publishes([
        __DIR__.'/../resources/skills' => base_path('.claude/skills'),
    ], 'my-package-skills-claude');
}
```

For the consumer:

```bash
php artisan vendor:publish --tag=my-package-skills-claude

# after upgrading the package - update skills:
php artisan vendor:publish --tag=my-package-skills-claude --force
```

## Coexistence with skiller vendor

Both mechanisms work in the same project and do not interfere with each other:

- `skiller vendor` maintains the manifesto `.swissknifeman-manifest.json` and when
  reinstallation cleans **only yours** skills - published in batches
  are not touched;
- the package prefix in the folder name ensures there are no name collisions;
- in the project registry vendor-skill can be marked provenance-fields:

```json
{
  "name": "my-package-security",
  "path": ".claude/skills/my-package-security/SKILL.md",
  "source": "vendor",
  "package": "acme/my-package",
  "version": "1.2.0"
}
```

## How to add skills publication to your package

Ready recipe - skill `php-packages/laravel-packages` (is installed with profiles
`php-package` and `laravel-project`): scaffold package, snippet
`boost-skill-publisher.php` and a checklist with a full cycle check
`composer install → vendor:publish → agent sees SKILL.md`.

## Cycle of skills

The complete ecosystem cycle looks like this:

```
SwissKnifeMan ──skiller vendor──→ package project (skills for package development)
package project ──development──→ domain skills   (resources/skills/)
package ──vendor:publish──→ consuming applications (skills for using the package)
applications ──scanner──→ SwissKnifeMan             (new snippets from practice)
```

Scanner ([scanner](./scanner)) closes the cycle: successful patterns from combat
projects are returned to the registry.
