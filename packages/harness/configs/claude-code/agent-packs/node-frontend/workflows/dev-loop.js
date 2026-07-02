export const meta = {
  name: '{{PACK_PREFIX}}-dev-loop',
  description: 'Реализует список frontend-срезов {{PACK_PREFIX}} (Vue/Vite, {{VUE_VARIANT}}) последовательно на ОДНОЙ ветке: для каждого среза impl ({{PACK_PREFIX}}-slice-builder) → tests-to-green ({{PACK_PREFIX}}-test-writer) → review-gate ({{PACK_PREFIX}}-reviewer). Один branch на прогон, хард-кап переживает resume, circuit-breaker. Скоуп срезов задаёт человек через args.',
  phases: [
    { title: 'Setup', detail: 'чистое дерево + одна feature-ветка от base' },
    { title: 'Build', detail: 'по срезу: impl → tests-to-green → review-gate' },
    { title: 'Verify', detail: 'typecheck + lint + полный сюит + отчёт' },
  ],
}

// Вход (args): { branch, base?, max_slices?, slices: [{id,title,goal,acceptance_criteria,skills?}] }
const PROJECT_DIR = '{{PROJECT_DIR}}'
// хард-кап литералом (переживает resume). Урок throttling: большой батч множит
// retry-поверхность под rate-limit → дефолт 2, не 3+ (solo-fallback — дисциплина оркестратора).
const DEFAULT_MAX = 2

const BRANCH = (args && args.branch) || 'feat/dev-loop'
const BASE = (args && args.base) || '{{BASE_BRANCH}}'
const MAX = (args && args.max_slices) || DEFAULT_MAX
const ALL_SLICES = (args && Array.isArray(args.slices)) ? args.slices : []
const SLICES = ALL_SLICES.slice(0, MAX)

const HARD_GATES = `ЖЁСТКИЕ ГЕЙТЫ {{PACK_PREFIX}} (не нарушать):
- Тесты/проверки ТОЛЬКО через '{{TEST_RUNNER_CMD}}' / '{{TYPECHECK_CMD}}' / '{{LINT_CMD}}'.
- НЕ править lockfile вручную; НЕ bump мажорных зависимостей; dist/build НЕ коммитить.
- НЕ git push, НЕ открывать/мержить PR, НЕ release.
- Все срезы — на ОДНОЙ ветке ${BRANCH}; агенты НЕ создают/не переключают ветки, коммитят в текущую, дерево чистое.
- Работать строго внутри ${PROJECT_DIR}. Вариант фронта: {{VUE_VARIANT}}.`

if (SLICES.length === 0) {
  log('Нет срезов на вход (args.slices пуст). Передай { branch, base, max_slices, slices: [...] }.')
  return { built: [], note: 'no slices provided' }
}

// Урок overnight-прогона (azguard, plan-remainder): agent({schema}) может не вернуть null,
// а БРОСИТЬ исключение ('subagent completed without calling StructuredOutput'). Без обёртки
// throw ронял ВЕСЬ workflow. safeAgent сводит throw к null — дальше штатная деградация
// if(!result)/circuit-breaker.
async function safeAgent(prompt, opts) {
  try {
    return await agent(prompt, opts)
  } catch (e) {
    const label = (opts && opts.label) || '?'
    log(`agent ${label} бросил исключение (${String((e && e.message) || e).slice(0, 160)}) — infra-failed, продолжаю`)
    return null
  }
}

phase('Setup')
await safeAgent(
  `В ${PROJECT_DIR} подготовь рабочую ветку.
1. 'git status' — грязное дерево → стоп и отчёт (не затирай чужое).
2. Ветка ${BRANCH} есть → 'git checkout ${BRANCH}'; иначе 'git checkout ${BASE}' + 'git checkout -b ${BRANCH}'.
3. Подтверди: ветка = ${BRANCH}, дерево чистое, последний коммит.
${HARD_GATES}`,
  { label: 'setup-branch', phase: 'Setup' }
)

phase('Build')
const SLICE_RESULT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['id', 'status', 'summary', 'assumptions', 'open_questions'],
  properties: {
    id: { type: 'string' },
    status: { type: 'string', enum: ['green', 'deferred', 'failed', 'infra-failed'], description: 'green=зелёные; deferred=честно не зелёный (дефект); failed=агент отчитался о сбое; infra-failed=инфра-отказ (rate-limit/timeout/null) — НЕ маскировать под deferred' },
    summary: { type: 'string' },
    files_changed: { type: 'array', items: { type: 'string' } },
    tests_added: { type: 'array', items: { type: 'string' } },
    test_output: { type: 'string', description: 'финальная строка {{TEST_RUNNER_CMD}}' },
    assumptions: { type: 'array', items: { type: 'string' } },
    open_questions: { type: 'array', items: { type: 'string' } },
  },
}

const results = []
let consecutiveFails = 0

for (const slice of SLICES) {
  const sliceNo = results.length + 1
  // Durable-прогресс = число green (в песочнице нет shell → не git rev-list). Затяжной hang
  // одного agent() тут НЕ ловится — это забота внешнего supervisor (доклад ~30 мин + PushNotification).
  if (consecutiveFails >= 2) {
    log(`Circuit-breaker: ${consecutiveFails} среза подряд не дошли до зелёного — стоп.`)
    break
  }
  const extraSkills = (slice.skills || []).join(', ') || '(дополнительных нет)'

  await safeAgent(
    `Реализуй ОДИН frontend-срез {{PACK_PREFIX}} (${SLICES.length ? '' : ''}{{VUE_VARIANT}}) в текущей ветке ${BRANCH}.
СРЕЗ:
${JSON.stringify(slice, null, 2)}
Дополнительно подгрузи: ${extraSkills}.
Построй тонкий путь страницы/фичи (route → page → store → api → композиция). Тесты НЕ пиши. Коммить в текущую ветку, дерево чистое.
${HARD_GATES}`,
    { label: `impl:${slice.id}`, phase: 'Build', agentType: '{{PACK_PREFIX}}-slice-builder', effort: 'high' }
  )
  log(`срез ${sliceNo}/${SLICES.length}: ${slice.id} impl-ok`)  // heartbeat

  const result = await safeAgent(
    `Ты в ветке ${BRANCH} в ${PROJECT_DIR}; срез реализован:
${JSON.stringify(slice, null, 2)}
Напиши Vitest+@vue/test-utils по acceptance_criteria и итерируй '{{TEST_RUNNER_CMD}}' до ЗЕЛЁНОГО.
- Зелено → закоммить тесты, status='green', test_output = финальная строка.
- Честно не достиг → НЕ ослабляй тесты: status='deferred', объясни в open_questions; дерево чистое.
ЗАПАСНОЙ ПУТЬ (если строгую схему возврата 5× не удаётся заполнить — не срывай прогон): последней строкой выведи ровно '===SLICE-RESULT=== status=green' или '===SLICE-RESULT=== status=deferred'.
${HARD_GATES}`,
    { label: `test:${slice.id}`, phase: 'Build', agentType: '{{PACK_PREFIX}}-test-writer', schema: SLICE_RESULT_SCHEMA, effort: 'high' }
  )
  log(`срез ${sliceNo}/${SLICES.length}: ${slice.id} test=${result ? result.status : 'infra-failed(null)'}`)  // heartbeat

  let review = null
  if (result && result.status === 'green') {
    consecutiveFails = 0
    review = await safeAgent(
      `Read-only ревью среза "${slice.title}" в ${PROJECT_DIR}, ветка ${BRANCH}. Diff против ${BASE}. Проверь типы (нет any), структуру (логика не в шаблоне, состояние в Pinia), доступность и acceptance_criteria: ${JSON.stringify(slice.acceptance_criteria)}. Прогони '{{TYPECHECK_CMD}}' и '{{LINT_CMD}}'. Файлы НЕ меняй.
${HARD_GATES}`,
      { label: `review:${slice.id}`, phase: 'Build', agentType: '{{PACK_PREFIX}}-reviewer', effort: 'high' }
    )
    log(`срез ${sliceNo}/${SLICES.length}: ${slice.id} review-ok (${results.filter((r) => r.status === 'green').length + 1}/${SLICES.length} зелёных)`)
  } else {
    consecutiveFails++
  }
  results.push({ ...(result || { id: slice.id, status: 'infra-failed', summary: 'agent вернул null (терминальный infra-сбой рантайма ИЛИ agent() бросил исключение — см. лог safeAgent)', assumptions: [], open_questions: [] }), review_findings: review })

  // Fail-fast на инфра-отказ: agent() вернул null = терминальный сбой (rate-limit/timeout,
  // ретраи исчерпаны). Дальше бессмысленно. НЕ маскируем под deferred (P4). Затяжной hang → supervisor.
  if (!result) {
    log(`Fail-fast: срез ${slice.id} infra-failed (agent вернул null) — стоп прогона, иду в Verify/отчёт.`)
    break
  }
}

phase('Verify')
const verify = await safeAgent(
  `Финальная проверка в ${PROJECT_DIR}, ветка ${BRANCH}:
1. 'git status' — чисто, ветка ${BRANCH}.
2. '{{TYPECHECK_CMD}}' — 0 ошибок.
3. '{{LINT_CMD}}' — чисто.
4. Полный '{{TEST_RUNNER_CMD}}' — число/статус.
Краткий итог. Файлы не меняй, не push.
${HARD_GATES}`,
  { label: 'final-verify', phase: 'Verify', effort: 'high' }
)

const built = results.map((r) => ({ id: r.id, status: r.status }))
const infraN = built.filter((b) => b.status === 'infra-failed').length
log(`Готово: ${built.filter((b) => b.status === 'green').length}/${SLICES.length} зелёных${infraN ? `, ${infraN} infra-failed (инфра-отказ, НЕ дефект — см. <failures>)` : ''}. Ветка ${BRANCH}, ничего не запушено.`)
return { branch: BRANCH, base: BASE, max: MAX, results, verify }
