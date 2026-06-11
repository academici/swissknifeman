---
name: livewire
bucket: php
version: 0.1.0
description: "Build and test Livewire components in this Laravel application."
risk: write
persona: oss-dev
tags: [php, laravel, livewire]
requires: [laravel]
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Livewire development

## When to use this skill
Use this skill when creating or modifying Livewire components, handling Livewire actions/validation, or writing Livewire tests.

## Notes
- Prefer `php artisan make:livewire` to generate components.
- Treat Livewire actions like backend endpoints: validate input and authorize.
