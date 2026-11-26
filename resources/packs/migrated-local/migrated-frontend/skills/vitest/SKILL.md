---
name: vitest
description: "Use for Vue/Inertia-on-Laravel Vitest setup: jsdom, test layout, and generated-code exclusions."
---

# Skill: Vitest (Vue/Inertia on Laravel)

Frontend unit tests for Laravel + Inertia + Vue via Vitest.

Apply when: setting up Vitest in a Laravel/Inertia project; writing component/composable tests; alias resolution fails in tests; coverage shows junk percentages from autogen.

## Steps

1. `vitest.config.ts`: `vue()` plugin (same `transformAssetUrls` as vite.config); aliases `@/routes` → `resources/js/wayfinder/routes` and `@` → `resources/js` — identical to main build (else tests don't resolve imports).
2. `test` section: `environment: 'jsdom'`, `globals: true`, `include: ['resources/js/tests/**/*.{test,spec}.{ts,js}']`.
3. Test layout mirrors sources: `composables/document/useDocumentFilters.ts` → `tests/composables/document/useDocumentFilters.test.ts`. New source layer = new subdir under tests/.
4. Coverage: `provider: 'v8'`, reporter text/html/lcov, `include: ['resources/js/**/*.{ts,vue}']`; mandatory exclude: `tests/**`, entrypoints (`app.ts`, `bootstrap.ts`), all autogen — `actions/**`, `routes/**`, `wayfinder/**`.
5. Scripts: `test` (watch), `test:run`, `test:coverage` (`vitest run --coverage`).
6. Component tests — `@vue/test-utils` `mount()`; test composables as plain functions, wrap in a host component only when lifecycle/inject needed.

## Do NOT apply

- E2E / browser scenarios — Dusk/Playwright, not Vitest.
- PHP backend tests — Pest/PHPUnit (see php bucket).

## Which snippet

| Situation | File |
|:---|:---|
| Create/fix config: jsdom, aliases, include, coverage exclude | `snippets/vitest.config.ts` |
| Write first component or composable test | `snippets/component-test.ts` |

## Quality checklist

- [ ] vitest.config aliases identical to vite.config (`@/routes` before `@`)
- [ ] `environment: jsdom`, `globals: true`, include points to `resources/js/tests/**`
- [ ] Test lives in mirror subdir relative to source
- [ ] Coverage exclude contains `tests/**`, `actions/**`, `routes/**`, `wayfinder/**`, entrypoints
- [ ] package.json has `test`, `test:run`, `test:coverage`
- [ ] `vitest run` green locally before commit

## Links

- https://vitest.dev/config/
- https://vitest.dev/guide/coverage
- https://test-utils.vuejs.org/
- Related: `frontend-backend/inertia-vue` (resources/js layout), `frontend-wayfinder/wayfinder` (what counts as autogen), `frontend-vue/vue-composition-api` (composables tested as functions)
- `frontend-vue/vitest-vue` — generic Vitest API reference (test/describe/mock/coverage, upstream). This skill = config recipe for Laravel/Inertia; go there for general API.
- `quality/test-strategy` — pyramid strategy and coverage policy
- `quality/playwright-e2e` — browser/E2E scenarios (what Vitest doesn't cover)
