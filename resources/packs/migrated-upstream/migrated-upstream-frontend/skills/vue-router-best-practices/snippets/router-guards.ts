// router-guards.ts — standard navigation guards Vue Router 4
// Return-API instead of the deprecated one next(): return undefined | false | string | RouteLocationRaw | Error.
import type {
  NavigationGuardWithThis,
  RouteLocationNormalized,
  RouteLocationRaw,
} from 'vue-router'
import { createRouter, createWebHistory, isNavigationFailure, NavigationFailureType } from 'vue-router'

// ---------------------------------------------------------------------------
// 1. Return-API: what guard returns (replaces the third argument next)
// ---------------------------------------------------------------------------
// return undefined / true        → skip navigation
// return false                   → cancel, stay on current route
// return '/login'                → redirect by path
// return { name: 'login', ... }  → redirect by route object (type safe)
// return new Error('reason')     → cancel + trigger router.onError()

// ---------------------------------------------------------------------------
// 2. Migration next() → return (shown next)
// ---------------------------------------------------------------------------

// WAS (Vue Router 3 / deprecated at 4): third argument next, easy to forget/call twice
// router.beforeEach((to, from, next) => {
//   if (!isAuthed()) {
//     next('/login')        // forgot return — next() below will be called again
//   }
//   next()                  // BUG: dangling or double navigation
// })

// NOW (Vue Router 4): clean return, two signatures (to, from), without next
const requireAuth: NavigationGuardWithThis<undefined> = (to) => {
  if (!isAuthed()) {
    // save the target path to return after login
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  // do not return anything → navigation continues
}

// ---------------------------------------------------------------------------
// 3. Async-guard: await instead next() in the callback
// ---------------------------------------------------------------------------
// WAS: next() inside .then/.catch — order of races, next() could be called twice
// NOW: guard async, just await + return
const ensureUserLoaded: NavigationGuardWithThis<undefined> = async (to) => {
  try {
    await loadCurrentUser() // idempotent: repeated calls do not affect the network
  } catch (err) {
    const status = (err as { status?: number }).status
    if (status === 401) return { name: 'login', query: { redirect: to.fullPath } }
    if (status === 403) return { name: 'forbidden' }
    return new Error('Access check failed') // → router.onError()
  }
  // success → return undefined → continue
}

// ---------------------------------------------------------------------------
// 4. Protection against endless redirect: skip the target route
// ---------------------------------------------------------------------------
const guardWithLoopBreak: NavigationGuardWithThis<undefined> = (to): RouteLocationRaw | void => {
  // CRITICAL: do not redirect to login, if we are already going to login (otherwise loop)
  if (to.name === 'login' || to.name === 'forbidden') return
  if (!isAuthed()) return { name: 'login', query: { redirect: to.fullPath } }
  if (to.meta.roles && !hasAnyRole(to.meta.roles as string[])) return { name: 'forbidden' }
}

// ---------------------------------------------------------------------------
// 5. beforeEnter — per-route guard (array of guards is valid)
// ---------------------------------------------------------------------------
const onlyAdmin = (to: RouteLocationNormalized): RouteLocationRaw | boolean => {
  return hasAnyRole(['admin']) ? true : { name: 'forbidden' }
}

// ---------------------------------------------------------------------------
// 6. beforeRouteLeave-logic: confirm leaving if data is not saved
//    (in SFC is placed via onBeforeRouteLeave from 'vue-router', here is the essence)
// ---------------------------------------------------------------------------
const confirmLeave = (hasUnsavedChanges: boolean): boolean => {
  if (!hasUnsavedChanges) return true
  return window.confirm('There are unsaved changes. Leave?') // false → cancel
}

// ---------------------------------------------------------------------------
// 7. Router assembly: global guards + onError + scrollBehavior
// ---------------------------------------------------------------------------
export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue') },
    { path: '/forbidden', name: 'forbidden', component: () => import('@/views/ForbiddenView.vue') },
    {
      path: '/admin',
      name: 'admin',
      component: () => import('@/views/AdminView.vue'),
      beforeEnter: onlyAdmin, // per-route guard
      meta: { requiresAuth: true, roles: ['admin'] },
    },
  ],
  // restore scroll position: savedPosition (Back/Forward) → anchor → top
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) return savedPosition
    if (to.hash) return { el: to.hash, behavior: 'smooth' }
    return { top: 0 }
  },
})

// order of global guards is important: loop check/authorization before loading data
router.beforeEach(guardWithLoopBreak)
router.beforeEach(ensureUserLoaded)

// processing canceled/broken navigations - not to be confused with real errors
router.afterEach((to, from, failure) => {
  if (isNavigationFailure(failure, NavigationFailureType.aborted)) {
    // navigation canceled by guard (return false) — this is normal, not an error
    return
  }
  if (failure) console.warn('Navigation failed:', failure)
})

// errors from guards (return new Error(...)) and loading failed lazy-chunk
router.onError((error) => {
  console.error('Router error:', error)
})

// domain logic stubs (in real code - from store/composable)
declare function isAuthed(): boolean
declare function hasAnyRole(roles: string[]): boolean
declare function loadCurrentUser(): Promise<void>

export { requireAuth, ensureUserLoaded, guardWithLoopBreak, onlyAdmin, confirmLeave }
