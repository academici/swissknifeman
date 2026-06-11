---
name: inertia-vue
bucket: frontend
version: 0.1.0
description: "Develop Inertia + Vue pages/components and form flows in this Laravel app."
risk: write
persona: oss-dev
tags: [inertia, vue, laravel, frontend]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Inertia + Vue development

## When to use this skill
Use this skill when editing files under `resources/js/` (pages, shared components, form logic, navigation).

## Project expectations
- Use `<Link>` / `router.visit()` for navigation.
- Prefer Inertia form helpers (`useForm`, or `<Form>` if available) for submissions and error handling.
