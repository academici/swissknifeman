---
name: pennant-development
description: "Laravel Pennant feature flags: define/active/for-scope, the @feature directive, activation/deactivation, A/B and gradual rollouts. Adapted from laravel/boost (strategy=notify)."
---

# Pennant Features

> Source: `laravel/boost` (`.ai/pennant/skill/pennant-development/SKILL.md`),
> adapted for the registry swissknifeman (frontmatter bucket; strategy=notify).
> Pennant — stable API without a version fork, so the skill is transferred as
> self-contained for projects without Boost.

## When to activate

- Create, check or switch feature-flags.
- Managing gradual feature rollouts (rollouts).
- Implementation A/B-testing.
- Working with the directive `@feature` in Blade.

## Basic Use

### Feature definition

```php
use Laravel\Pennant\Feature;

Feature::define('new-dashboard', function (User $user) {
    return $user->isAdmin();
});
```

### Feature check

```php
if (Feature::active('new-dashboard')) {
    // Feature active
}

// With scope
if (Feature::for($user)->active('new-dashboard')) {
    // Feature is active for this user
}
```

### Blade-directive

```blade
@feature('new-dashboard')
    <x-new-dashboard />
@else
    <x-old-dashboard />
@endfeature
```

### Activation / deactivation

```php
Feature::activate('new-dashboard');
Feature::for($user)->activate('new-dashboard');
```

## Verification

1. Feature defined (`Feature::define`).
2. Behavior tested on different scopes/users.

## Common errors

- Forgot to save a feature for a specific user/entity (`Feature::for(...)`).
- Does not follow existing flag naming conventions in the project.

## Links

- Documentation: https://laravel.com/docs/pennant
- In projects with Laravel Boost version-specific themes are given away Boost;
  Pennant is version stable - no conflict.
