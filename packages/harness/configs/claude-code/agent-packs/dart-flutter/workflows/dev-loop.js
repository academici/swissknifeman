export const meta = {
  name: '{{PACK_PREFIX}}-dev-loop',
  description: 'Реализует список Flutter-срезов {{PACK_PREFIX}} (цель {{TARGET_KIND}}, state {{STATE_MGMT}}) последовательно на ОДНОЙ ветке: impl ({{PACK_PREFIX}}-slice-builder) → tests-to-green ({{PACK_PREFIX}}-test-writer) → review-gate ({{PACK_PREFIX}}-reviewer). Один branch, хард-кап переживает resume, circuit-breaker.',
  phases: [
    { title: 'Setup', detail: 'чистое дерево + одна feature-ветка от base' },
    { title: 'Build', detail: 'по срезу: impl → tests-to-green → review-gate' },
    { title: 'Verify', detail: 'analyze + format + полный сюит + отчёт' },
  ],
}

const PROJECT_DIR = '{{PROJECT_DIR}}'
const DEFAULT_MAX = 3

const BRANCH = (args && args.branch) || 'feat/dev-loop'
const BASE = (args && args.base) || '{{BASE_BRANCH}}'
const MAX = (args && args.max_slices) || DEFAULT_MAX
const ALL_SLICES = (args && Array.isArray(args.slices)) ? args.slices : []
const SLICES = ALL_SLICES.slice(0, MAX)

const HARD_GATES = `ЖЁСТКИЕ ГЕЙТЫ {{PACK_PREFIX}} (не нарушать):
- Тесты/анализ ТОЛЬКО через '{{TEST_RUNNER_CMD}}' / '{{ANALYZE_CMD}}' / '{{FORMAT_CMD}}'.
- НЕ править pubspec.lock вручную; НЕ bump SDK.
- pos-embedded: не блокировать главный isolate; I/O периферии с timeout.
- НЕ git push, НЕ открывать/мержить PR, НЕ release.
- Все срезы — на ОДНОЙ ветке ${BRANCH}; агенты НЕ создают/не переключают ветки, дерево чистое.
- Работать строго внутри ${PROJECT_DIR}.`

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
    status: { type: 'string', enum: ['green', 'deferred', 'failed'] },
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
  if (consecutiveFails >= 2) {
    log(`Circuit-breaker: ${consecutiveFails} среза подряд не дошли до зелёного — стоп.`)
    break
  }
  const extraSkills = (slice.skills || []).join(', ') || '(дополнительных нет)'

  await agent(
    `Реализуй ОДИН Flutter-срез {{PACK_PREFIX}} (state {{STATE_MGMT}}, цель {{TARGET_KIND}}) в ветке ${BRANCH}.
СРЕЗ:
${JSON.stringify(slice, null, 2)}
Дополнительно подгрузи: ${extraSkills}.
Построй тонкий путь экрана (экран → виджеты → состояние → repository → роутинг). Тесты НЕ пиши. Коммить в текущую ветку, дерево чистое.
${HARD_GATES}`,
    { label: `impl:${slice.id}`, phase: 'Build', agentType: '{{PACK_PREFIX}}-slice-builder', effort: 'high' }
  )

  const result = await agent(
    `Ты в ветке ${BRANCH} в ${PROJECT_DIR}; срез реализован:
${JSON.stringify(slice, null, 2)}
Напиши flutter-тесты (widget+unit) по acceptance_criteria и итерируй '{{TEST_RUNNER_CMD}}' до ЗЕЛЁНОГО.
- Зелено → закоммить, status='green', test_output = финальная строка.
- Честно не достиг → НЕ ослабляй: status='deferred', объясни; дерево чистое.
${HARD_GATES}`,
    { label: `test:${slice.id}`, phase: 'Build', agentType: '{{PACK_PREFIX}}-test-writer', schema: SLICE_RESULT_SCHEMA, effort: 'high' }
  )

  let review = null
  if (result && result.status === 'green') {
    consecutiveFails = 0
    review = await agent(
      `Read-only ревью среза "${slice.title}" в ${PROJECT_DIR}, ветка ${BRANCH}. Diff против ${BASE}. Проверь состояние ({{STATE_MGMT}}), dispose/утечки, null-safety, для pos-embedded — неблокирование главного isolate, и acceptance_criteria: ${JSON.stringify(slice.acceptance_criteria)}. Прогони '{{ANALYZE_CMD}}' и '{{FORMAT_CMD}}'. Файлы НЕ меняй.
${HARD_GATES}`,
      { label: `review:${slice.id}`, phase: 'Build', agentType: '{{PACK_PREFIX}}-reviewer', effort: 'high' }
    )
  } else {
    consecutiveFails++
  }
  results.push({ ...(result || { id: slice.id, status: 'failed', summary: 'agent вернул null', assumptions: [], open_questions: [] }), review_findings: review })
}

phase('Verify')
const verify = await agent(
  `Финальная проверка в ${PROJECT_DIR}, ветка ${BRANCH}:
1. 'git status' — чисто, ветка ${BRANCH}.
2. '{{ANALYZE_CMD}}' — 0 ошибок.
3. '{{FORMAT_CMD}}' — чисто.
4. Полный '{{TEST_RUNNER_CMD}}' — число/статус.
Краткий итог. Файлы не меняй, не push.
${HARD_GATES}`,
  { label: 'final-verify', phase: 'Verify', effort: 'high' }
)

const built = results.map((r) => ({ id: r.id, status: r.status }))
log(`Готово: ${built.filter((b) => b.status === 'green').length}/${SLICES.length} зелёных. Ветка ${BRANCH}, ничего не запушено.`)
return { branch: BRANCH, base: BASE, max: MAX, results, verify }
