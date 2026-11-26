---
name: vue-testing-best-practices
description: "Use for Vue Test Utils 2 component/composable tests, Pinia fakes, async DOM, and emits."
---

# Skill: testing Vue-components (Vitest + Vue Test Utils 2)

## Context

Skill - about **what and how to test in Vue-components**: black box (input = props/slots/events
user, exit = DOM/emits/store calls), and not the insides. Stack: Vitest as runner
(`frontend-vue/vitest`, `frontend-vue/vitest-vue`), Vue Test Utils 2 (VTU) as mounter, optional
`@testing-library/vue` for user-centric style. We write to Composition API (`<script setup lang="ts">`),
Pinia — via `@pinia/testing`, async — via `flushPromises`/`nextTick`.

Config Vitest (jsdom, aliases, coverage) — NOT here, he's in `frontend-vue/vitest`. General API
expect/mock/vi — in `frontend-vue/vitest-vue`. This skill does not duplicate them, but builds on them Vue-specifics.

## When to activate

- You write/repairing `*.spec.ts`/`*.test.ts` for `.vue`-component or composable (`useX`).
- Tests break when internals are refactored, although the behavior has not changed.
- «injection Symbol(pinia) not found», falls async-setup, is not found Teleport/modal.
- Test flies at races (did not wait for the promise/tick); snapshots «green» with a broken feature.
- Need to decide mount vs shallowMount, soak the child/global, check emitter or slot.

## Algorithm

1. **Decide: component or composite.**
   - Clean `useX` without lifecycle/inject — test like a regular function: call, pull methods,
     check `.value` ref. None mount.
   - `useX` with `onMounted`/`inject`/`provide` — wrap in a carrier component
     (`defineComponent({ setup: () => useX(), template: '<div/>' })`) and `mount`. See
     `references/testing-composables-helper-wrapper.md`.

2. **Select mount vs shallowMount.**
   - `mount` — default: renders a real tree, checks a custom script.
   - `shallowMount` — mutes all children; take it only when the baby is heavy/external and its
     rendering is interfering. Don't use shallowMount «just in case» — it hides integration bugs.
   - Spot plug instead of total plug: `global.stubs: { HeavyChild: true }`.

3. **Selectors are persistent.** Search by `data-testid` (`wrapper.get('[data-testid="x"]')`), not by CSS-
   classes, text or position in the tree - otherwise refactoring the markup breaks the tests out of the blue.
   Black box style - `references/testing-component-blackbox-approach.md`.

4. **Connect dependencies via `global`.**
   - Pinia: `global.plugins: [createTestingPinia({ createSpy: vi.fn })]`. Default actions
     stabilized (`stubActions: true`) — check that the action is called. Need real logic
     actions - `stubActions: false`, and pointwise replace only the action on the border I/O (network
     call) via `vi.spyOn(store, 'action').mockResolvedValue(...)`. See
     `references/testing-pinia-store-setup.md`.
   - Router/i18n/global components - `global.plugins`/`global.components`/`global.mocks`.

5. **Async — wait explicitly.** After `trigger`/shifts props/resolve promise call
   `await flushPromises()` (microtasks: promises in actions/watch) and/or `await nextTick()`
   (DOM-update after synchronous reactivity change). `trigger`/`setProps` are already being returned
   promise — `await` them. See `references/testing-async-await-flushpromises.md`.

6. **Check the contract outside.**
   - Issuers: `wrapper.emitted('eventName')` → array of calls; payload — `emitted('e')[0]`.
   - Slots: `mount(C, { slots: { default: 'text', named: ComponentStub } })`, then assert
     rendered content.
   - DOM/text/visible result classes are not internal data().

7. **async setup / Suspense / Teleport / defineAsyncComponent** — special cases:
   `references/testing-suspense-async-components.md`, `references/async-component-testing.md`,
   `references/teleport-testing-complexity.md`.

8. **`@testing-library/vue` as an alternative** VTU, whenever you want user-centric API
   (`render` + `screen.getByRole`/`getByText` + `@testing-library/user-event`): less access to
   internals, tests closer to user behavior. Don't mix both styles in one file; for
   availability/roles `getByRole` more clearly `data-testid`. This is an alternative, not a replacement - pick one.

## What NOT to test

- **Reactivity and itself Vue/Pinia/VTU** — what `ref` is being updated, `computed` is recalculated,
  `watch` works: this has already been tested by the framework. Test YOUR logic on top.
- **Snapshots only** as a replacement for assertions - a large snapshot «green» with a broken feature and
  hides regressions behind noise. Snapshot - for a small stable output, not instead of checks.
  See `references/testing-no-snapshot-only.md`.
- **Private internals** (`wrapper.vm.someInternal`, method names) — implementation details.
- **Computed Styles/real DOM-browser events** in jsdom — for this browser runner
  (`@vitest/browser`/Playwright CT), see `references/testing-browser-vs-node-runners.md`. E2E —
  `references/testing-e2e-playwright-recommended.md`.

## When to open which snippet

| Situation | File |
|:---|:---|
| We need a spec standard: mount + Pinia + async + checking emitters + data-testid | `snippets/component.spec.ts` |
| Isolated composable test (with lifecycle — via carrier component) | `references/testing-composables-helper-wrapper.md` |
| Errors injection pinia / selection stubActions | `references/testing-pinia-store-setup.md` |
| Flak at the races, didn't wait for the promise/tick | `references/testing-async-await-flushpromises.md` |
| Tests break when refactoring internals | `references/testing-component-blackbox-approach.md` |
| async setup / Suspense / defineAsyncComponent / Teleport are not rendered | `references/testing-suspense-async-components.md`, `references/async-component-testing.md`, `references/teleport-testing-complexity.md` |
| Need real styles/DOM-events or E2E | `references/testing-browser-vs-node-runners.md`, `references/testing-e2e-playwright-recommended.md` |

## Quality checklist

- [ ] Test verifies behavior (DOM/emits/store calls), not the insides (`vm.*`, method names)
- [ ] Selected `mount` default; `shallowMount`/`stubs` — only for heavy/external children with justification
- [ ] Selectors by `data-testid` (or roles in testing-library), not by class/text/positions
- [ ] Pinia connected via `createTestingPinia`; solved `stubActions` true/false consciously
- [ ] Everyone async-transition waited `await flushPromises()`/`await nextTick()`, no «naked» promises
- [ ] Issues verified via `emitted()` with payload; slots - via `slots`
- [ ] No reactivity tests Vue / snapshot-only as the only assertion
- [ ] Composable without lifecycle is tested as a function; with lifecycle — via carrier component
- [ ] The file is a mirror image of the source; `vitest run` green locally

## Links

- `frontend-vue/vitest` — config Vitest specifically for Laravel/Inertia/Vue (jsdom, aliases, coverage exclude).
  Take the runner setup there, test practice here.
- `frontend-vue/vitest-vue` — generic reference API Vitest (test/describe/expect/mock/vi, coverage).
  General API do not duplicate - follow him there.
- `frontend-vue/vue` — Composition API / `<script setup>` / reactivity: what exactly are we testing.
- `frontend-vue/vue-best-practices` — architecture (when composable, when store), affects testability.
- `frontend-vue/pinia` / `frontend-vue/pinia-stores` — arrangement of stores that we mop through `createTestingPinia`.
- https://test-utils.vuejs.org/ · https://testing-library.com/docs/vue-testing-library/intro/ · https://pinia.vuejs.org/cookbook/testing.html
- `references/` — detailed notes on special cases (import from antfu/skills, see `upstream.json`).
