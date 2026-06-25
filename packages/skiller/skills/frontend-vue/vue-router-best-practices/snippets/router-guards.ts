// router-guards.ts — типовые навигационные гварды Vue Router 4
// Возврат-API вместо устаревшего next(): return undefined | false | string | RouteLocationRaw | Error.
import type {
  NavigationGuardWithThis,
  RouteLocationNormalized,
  RouteLocationRaw,
} from 'vue-router'
import { createRouter, createWebHistory, isNavigationFailure, NavigationFailureType } from 'vue-router'

// ---------------------------------------------------------------------------
// 1. Возврат-API: что возвращает гвард (заменяет третий аргумент next)
// ---------------------------------------------------------------------------
// return undefined / true        → пропустить навигацию
// return false                   → отменить, остаться на текущем маршруте
// return '/login'                → редирект по path
// return { name: 'login', ... }  → редирект объектом маршрута (типобезопасно)
// return new Error('reason')     → отменить + триггернуть router.onError()

// ---------------------------------------------------------------------------
// 2. Миграция next() → return (показано рядом)
// ---------------------------------------------------------------------------

// БЫЛО (Vue Router 3 / deprecated в 4): третий аргумент next, легко забыть/вызвать дважды
// router.beforeEach((to, from, next) => {
//   if (!isAuthed()) {
//     next('/login')        // забыл return — next() ниже вызовется повторно
//   }
//   next()                  // BUG: висящая или двойная навигация
// })

// СТАЛО (Vue Router 4): чистый возврат, две сигнатуры (to, from), без next
const requireAuth: NavigationGuardWithThis<undefined> = (to) => {
  if (!isAuthed()) {
    // сохраняем целевой путь, чтобы вернуть после логина
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  // ничего не возвращаем → навигация продолжается
}

// ---------------------------------------------------------------------------
// 3. Async-гвард: await вместо next() в колбэке
// ---------------------------------------------------------------------------
// БЫЛО: next() внутри .then/.catch — порядок гонок, next() мог вызваться дважды
// СТАЛО: гвард async, просто await + return
const ensureUserLoaded: NavigationGuardWithThis<undefined> = async (to) => {
  try {
    await loadCurrentUser() // идемпотентно: повторный вызов не дёргает сеть
  } catch (err) {
    const status = (err as { status?: number }).status
    if (status === 401) return { name: 'login', query: { redirect: to.fullPath } }
    if (status === 403) return { name: 'forbidden' }
    return new Error('Не удалось проверить доступ') // → router.onError()
  }
  // успех → return undefined → продолжаем
}

// ---------------------------------------------------------------------------
// 4. Защита от бесконечного редиректа: пропускаем целевой маршрут
// ---------------------------------------------------------------------------
const guardWithLoopBreak: NavigationGuardWithThis<undefined> = (to): RouteLocationRaw | void => {
  // КРИТИЧНО: не редиректим на login, если уже идём на login (иначе цикл)
  if (to.name === 'login' || to.name === 'forbidden') return
  if (!isAuthed()) return { name: 'login', query: { redirect: to.fullPath } }
  if (to.meta.roles && !hasAnyRole(to.meta.roles as string[])) return { name: 'forbidden' }
}

// ---------------------------------------------------------------------------
// 5. beforeEnter — per-route гвард (массив гвардов допустим)
// ---------------------------------------------------------------------------
const onlyAdmin = (to: RouteLocationNormalized): RouteLocationRaw | boolean => {
  return hasAnyRole(['admin']) ? true : { name: 'forbidden' }
}

// ---------------------------------------------------------------------------
// 6. beforeRouteLeave-логика: подтверждение ухода при несохранённых данных
//    (в SFC ставится через onBeforeRouteLeave из 'vue-router', тут — суть)
// ---------------------------------------------------------------------------
const confirmLeave = (hasUnsavedChanges: boolean): boolean => {
  if (!hasUnsavedChanges) return true
  return window.confirm('Есть несохранённые изменения. Уйти?') // false → отмена
}

// ---------------------------------------------------------------------------
// 7. Сборка роутера: глобальные гварды + onError + scrollBehavior
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
      beforeEnter: onlyAdmin, // per-route гвард
      meta: { requiresAuth: true, roles: ['admin'] },
    },
  ],
  // восстановление позиции скролла: savedPosition (Назад/Вперёд) → якорь → верх
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) return savedPosition
    if (to.hash) return { el: to.hash, behavior: 'smooth' }
    return { top: 0 }
  },
})

// порядок глобальных гвардов важен: проверка цикла/авторизации до загрузки данных
router.beforeEach(guardWithLoopBreak)
router.beforeEach(ensureUserLoaded)

// обработка отменённых/прерванных навигаций — не путать с реальными ошибками
router.afterEach((to, from, failure) => {
  if (isNavigationFailure(failure, NavigationFailureType.aborted)) {
    // навигация отменена гвардом (return false) — это норма, не ошибка
    return
  }
  if (failure) console.warn('Навигация не завершилась:', failure)
})

// ошибки из гвардов (return new Error(...)) и сбой загрузки lazy-чанка
router.onError((error) => {
  console.error('Ошибка роутера:', error)
})

// заглушки доменной логики (в реальном коде — из store/composable)
declare function isAuthed(): boolean
declare function hasAnyRole(roles: string[]): boolean
declare function loadCurrentUser(): Promise<void>

export { requireAuth, ensureUserLoaded, guardWithLoopBreak, onlyAdmin, confirmLeave }
