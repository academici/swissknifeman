---
name: js-code-style
description: "JS/TS style per Spatie: 4 spaces, width 120, single quotes, const-first, strict ===, function for named functions, destructuring, named imports."
---

# Skill: JS/TS code style (Spatie)

## Context

Single style JavaScript/TypeScript according to guidelines Spatie. Different from Prettier-defaults: indentation **4 space** (not 2), line width **120** (not 80), single quotes. Apply when creating, editing, reviewing and refactoring `.js/.ts/.jsx/.tsx/.vue` files and when setting up Prettier/ESLint. Outside the scope: PHP, CSS-only, server configs.

## Algorithm

1. **Formatting**: 4 space, print width 120, single quotes. Pin to Prettier-config and `.editorconfig`, do not rely on defaults.
2. **Announcements**: `const` default; `let` — only if the variable is actually reassigned; `var` — never. Mutation of object properties under `const` is valid - the link does not change.
3. **Comparisons**: always `===`/`!==`. If the type is not guaranteed, cast explicitly (`parseInt`, `String()`, `Boolean()`) before comparison rather than relying on `==`.
4. **Functions**: `function` for named functions (is clearly read as a function); arrows - for callbacks, one-liners and higher-order; do not use arrows where your own is needed `this`. Object methods - shorthand-syntax.
5. **Data**: destructuring instead of accessing by indexes/properties; parameters-objects with defaults through destructuring in the signature.
6. **Names**: without abbreviations in multiline functions - full descriptive names; short ones are only allowed in one-line arrows with obvious context.
7. **Imports**: named (tree-shaking), not default and not namespace-imports entire modules unnecessarily.

## When NOT to use

- Project with a different style already fixed (Airbnb, Standard) — do not reformat someone else's code «along the way».
- Auto-generated files (wayfinder, lock-files) — do not touch, exclude from Prettier/ESLint.

## When to open which snippet

| Situation | File |
|:---|:---|
| Configure Prettier in the project (indent, width, quotes) | `snippets/prettier-config.json` |
| Controversial point in the review - show «to/after» by specific rule | `snippets/style-examples.ts` |

## Quality checklist

- [ ] Prettier-config: tabWidth 4, printWidth 120, singleQuote true
- [ ] No `var`; `let` only for real reassignment
- [ ] No `==`/`!=`; non-obvious types are cast explicitly before comparison
- [ ] Named functions via `function`, callbacks are arrows, object methods are shorthand
- [ ] Destructuring instead `parts[0]` / repeated calls to properties
- [ ] Fully qualified variable names in multiline functions
- [ ] Named imports

## Links

- https://spatie.be/guidelines/javascript
- https://prettier.io/docs/options
- https://eslint.org/docs/latest/rules/eqeqeq
- Related skills: `frontend-vue/vue-composition-api`, `frontend-backend/inertia-vue`
