export const meta = {
  name: '{{PACK_PREFIX}}-dev-loop',
  description: 'Реализует список backend-срезов {{PACK_PREFIX}} (Python {{WEB_FRAMEWORK}}) последовательно на ОДНОЙ ветке: impl ({{PACK_PREFIX}}-slice-builder) → tests-to-green ({{PACK_PREFIX}}-test-writer) → type-check ({{PACK_PREFIX}}-type-checker) → review-gate ({{PACK_PREFIX}}-reviewer). Один branch, хард-кап переживает resume, circuit-breaker.',
  phases: [
    { title: 'Setup', detail: 'чистое дерево + одна feature-ветка от base' },
    { title: 'Build', detail: 'по срезу: impl → tests-to-green → type-check → review-gate' },
    { title: 'Verify', detail: 'ruff + mypy + полный сюит + отчёт' },
  ],
}

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
- Тесты/линт/типы ТОЛЬКО через '{{TEST_RUNNER_CMD}}' / '{{LINT_CMD}}' / '{{TYPECHECK_CMD}}' (venv-aware {{PY_BIN}}).
- НЕ править lockfile вручную; НЕ ставить пакеты глобально; миграции — отдельным шагом.
- НЕ git push, НЕ открывать/мержить PR, НЕ release.
- Все срезы — на ОДНОЙ ветке ${BRANCH}; агенты НЕ создают/не переключают ветки, дерево чистое.
- Работать строго внутри ${PROJECT_DIR}. Фреймворк: {{WEB_FRAMEWORK}}.`

if (SLICES.length === 0) {
  log('Нет срезов на вход (args.slices пуст). Передай { branch, base, max_slices, slices: [...] }.')
  return { built: [], note: 'no slices provided' }
}

phase('Setup')
await agent(
  `В ${PROJECT_DIR} подготовь рабочую ветку.
1. 'git status' — грязное дерево → стоп и отчёт.
2. Ветка ${BRANCH} есть → checkout; иначе checkout ${BASE} + checkout -b ${BRANCH}.
3. Подтверди ветку/чистоту/последний коммит.
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

  await agent(
    `Реализуй ОДИН backend-срез {{PACK_PREFIX}} на {{WEB_FRAMEWORK}} в ветке ${BRANCH}.
СРЕЗ:
${JSON.stringify(slice, null, 2)}
Дополнительно подгрузи: ${extraSkills}.
Построй тонкий путь (router/view → service → repository → схема). Тесты НЕ пиши. Коммить в текущую ветку, дерево чистое.
${HARD_GATES}`,
    { label: `impl:${slice.id}`, phase: 'Build', agentType: '{{PACK_PREFIX}}-slice-builder', effort: 'high' }
  )
  log(`срез ${sliceNo}/${SLICES.length}: ${slice.id} impl-ok`)  // heartbeat

  const result = await agent(
    `Ты в ветке ${BRANCH} в ${PROJECT_DIR}; срез реализован:
${JSON.stringify(slice, null, 2)}
Напиши pytest по acceptance_criteria и итерируй '{{TEST_RUNNER_CMD}}' до ЗЕЛЁНОГО.
- Зелено → закоммить, status='green', test_output = финальная строка.
- Честно не достиг → НЕ ослабляй: status='deferred', объясни; дерево чистое.
ЗАПАСНОЙ ПУТЬ (если строгую схему возврата 5× не удаётся заполнить — не срывай прогон): последней строкой выведи ровно '===SLICE-RESULT=== status=green' или '===SLICE-RESULT=== status=deferred'.
${HARD_GATES}`,
    { label: `test:${slice.id}`, phase: 'Build', agentType: '{{PACK_PREFIX}}-test-writer', schema: SLICE_RESULT_SCHEMA, effort: 'high' }
  )
  log(`срез ${sliceNo}/${SLICES.length}: ${slice.id} test=${result ? result.status : 'infra-failed(null)'}`)  // heartbeat

  let review = null
  if (result && result.status === 'green') {
    consecutiveFails = 0
    await agent(
      `Тайп-чек диффа среза "${slice.title}" в ${PROJECT_DIR}, ветка ${BRANCH}: прогони '{{TYPECHECK_CMD}}', классифицируй ошибки, предложи минимальные аннотации. Кода НЕ меняй.
${HARD_GATES}`,
      { label: `types:${slice.id}`, phase: 'Build', agentType: '{{PACK_PREFIX}}-type-checker', effort: 'high' }
    )
    review = await agent(
      `Read-only ревью среза "${slice.title}" в ${PROJECT_DIR}, ветка ${BRANCH}. Diff против ${BASE}. Проверь слои (тонкий handler, валидация на границе, service/repository), безопасность (SQL/секреты/bare except) и acceptance_criteria: ${JSON.stringify(slice.acceptance_criteria)}. Прогони '{{LINT_CMD}}'. Файлы НЕ меняй.
${HARD_GATES}`,
      { label: `review:${slice.id}`, phase: 'Build', agentType: '{{PACK_PREFIX}}-reviewer', effort: 'high' }
    )
    log(`срез ${sliceNo}/${SLICES.length}: ${slice.id} review-ok (${results.filter((r) => r.status === 'green').length + 1}/${SLICES.length} зелёных)`)
  } else {
    consecutiveFails++
  }
  results.push({ ...(result || { id: slice.id, status: 'infra-failed', summary: 'agent вернул null (терминальный infra-сбой рантайма)', assumptions: [], open_questions: [] }), review_findings: review })

  // Fail-fast на инфра-отказ: agent() вернул null = терминальный сбой (rate-limit/timeout,
  // ретраи исчерпаны). Дальше бессмысленно. НЕ маскируем под deferred (P4). Затяжной hang → supervisor.
  if (!result) {
    log(`Fail-fast: срез ${slice.id} infra-failed (agent вернул null) — стоп прогона, иду в Verify/отчёт.`)
    break
  }
}

phase('Verify')
const verify = await agent(
  `Финальная проверка в ${PROJECT_DIR}, ветка ${BRANCH}:
1. 'git status' — чисто, ветка ${BRANCH}.
2. '{{LINT_CMD}}' — чисто.
3. '{{TYPECHECK_CMD}}' — 0 ошибок.
4. Полный '{{TEST_RUNNER_CMD}}' — число/статус.
Краткий итог. Файлы не меняй, не push.
${HARD_GATES}`,
  { label: 'final-verify', phase: 'Verify', effort: 'high' }
)

const built = results.map((r) => ({ id: r.id, status: r.status }))
const infraN = built.filter((b) => b.status === 'infra-failed').length
log(`Готово: ${built.filter((b) => b.status === 'green').length}/${SLICES.length} зелёных${infraN ? `, ${infraN} infra-failed (инфра-отказ, НЕ дефект — см. <failures>)` : ''}. Ветка ${BRANCH}, ничего не запушено.`)
return { branch: BRANCH, base: BASE, max: MAX, results, verify }
