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
// хард-кап литералом (переживает resume). Урок throttling: большой батч множит
// retry-поверхность под rate-limit → дефолт 2, не 3+ (solo-fallback — дисциплина оркестратора).
const DEFAULT_MAX = 2

// Named-workflow (Workflow({name,args})) доставляет args СТРОКОЙ — SLICES резолвился бы в [],
// давая ложный no-op «нет срезов». Guard парсит строку; битый JSON — явный log-STOP с
// подсказкой (P3.4/findings §4/§1.3), не молчаливое падение в пустой массив.
if (typeof args === 'string' && args.trim()) {
  try {
    args = JSON.parse(args)
  } catch (e) {
    log(`args пришёл строкой, но JSON.parse провалился (${String((e && e.message) || e).slice(0, 160)}) — запускай через scriptPath (embedded args), не named-workflow.`)
    return { built: [], note: 'args parse failed' }
  }
}

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
- .claude/agents|workflows|hooks с generated-header НЕ редактировать — оверрайды в .claude/rules/*-overrides.md.
- Все срезы — на ОДНОЙ ветке ${BRANCH}; агенты НЕ создают/не переключают ветки, дерево чистое.
- Работать строго внутри ${PROJECT_DIR}.`

if (SLICES.length === 0) {
  log('Нет срезов на вход (args.slices пуст) — STOP. Передай { branch, base, max_slices, slices: [...] } через scriptPath (embedded args), не named-workflow.')
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
1. 'git status' — грязное дерево → стоп и отчёт.
2. Ветка ${BRANCH} есть → checkout; иначе checkout ${BASE} + checkout -b ${BRANCH}.
3. Подтверди ветку/чистоту/последний коммит.
${HARD_GATES}`,
  { label: 'setup-branch', phase: 'Setup', model: 'sonnet', effort: 'low' }
)

phase('Build')
const SLICE_RESULT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['id', 'status', 'risk_level', 'summary', 'assumptions', 'open_questions'],
  properties: {
    id: { type: 'string' },
    status: { type: 'string', enum: ['green', 'deferred', 'failed', 'infra-failed'], description: 'green=зелёные; deferred=честно не зелёный (дефект); failed=агент отчитался о сбое; infra-failed=инфра-отказ (rate-limit/timeout/null) — НЕ маскировать под deferred' },
    risk_level: { type: 'string', enum: ['LOW', 'MED', 'HIGH'], description: 'blast-radius среза (см. risk_markers)' },
    risk_markers: { type: 'array', items: { type: 'string', enum: ['state-lifecycle', 'isolate-blocking', 'null-safety', 'dispose-leaks', 'peripheral-io'] }, description: 'какие классы риска затронул срез' },
    summary: { type: 'string' },
    files_changed: { type: 'array', items: { type: 'string' } },
    tests_added: { type: 'array', items: { type: 'string' } },
    test_output: { type: 'string', description: 'финальная строка {{TEST_RUNNER_CMD}}' },
    test_coverage_pct: { type: 'number', description: 'покрытие изменённого поведения, % (оценка)' },
    workarounds: { type: 'array', items: { type: 'string' }, description: 'обходки/форс-конфиги ради зелёного — каждая = [POSSIBLE-DEFECT] для ревьюера' },
    tool_failures: { type: 'array', items: { type: 'string' }, description: 'движок/инструмент был недоступен при проверке внешнего факта (perplexity-web залочен/TIMEOUT, context7 пусто, MCP лёг) → факт остался непроверенным, нужен ПОВТОРНЫЙ ПРОХОД. НЕ угадывать, НЕ маскировать' },
    assumptions: { type: 'array', items: { type: 'string' } },
    open_questions: { type: 'array', items: { type: 'string' } },
  },
}

// Lean-tiered лейны: модель/effort под РИСК среза. slice.risk/slice.model/slice.effort — подсказки
// человека/оркестратора в args; нет → дефолт MED. Per-call model/effort перебивают frontmatter агента.
const RISK = (s) => String((s && s.risk) || 'MED').toUpperCase()
function implLane(slice) {
  const r = RISK(slice)
  return {
    model: slice.model || (r === 'LOW' ? 'haiku' : 'sonnet'),
    effort: slice.effort || (r === 'HIGH' ? 'high' : r === 'LOW' ? 'low' : 'medium'),
  }
}
function reviewLane(risk) {
  if (risk === 'LOW') return { model: 'sonnet', effort: 'medium' }  // дешёвый spot-check
  if (risk === 'HIGH') return { model: 'opus', effort: 'xhigh' }    // adversarial + fresh-context
  return { model: 'opus', effort: 'high' }
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
  const lane = implLane(slice)
  // Durable-light handover: компактные сводки прошлых срезов (ТОЛЬКО поля схемы, не транскрипты).
  const priorSummary = results.length
    ? 'Прошлые срезы (сводка): ' + results.map((r) => `${r.id}=${r.status}/${r.risk_level || '?'} — ${r.summary || ''}`).join(' | ')
    : '(это первый срез)'

  await safeAgent(
    `Реализуй ОДИН Flutter-срез {{PACK_PREFIX}} (state {{STATE_MGMT}}, цель {{TARGET_KIND}}) в ветке ${BRANCH}.
СРЕЗ:
${JSON.stringify(slice, null, 2)}

${priorSummary}

Дополнительно подгрузи: ${extraSkills}.
Построй тонкий путь экрана (экран → виджеты → состояние → repository → роутинг). Тесты НЕ пиши. Коммить в текущую ветку, дерево чистое.
${HARD_GATES}`,
    { label: `impl:${slice.id}`, phase: 'Build', agentType: '{{PACK_PREFIX}}-slice-builder', model: lane.model, effort: lane.effort }
  )
  log(`срез ${sliceNo}/${SLICES.length}: ${slice.id} impl-ok`)  // heartbeat

  const result = await safeAgent(
    `Ты в ветке ${BRANCH} в ${PROJECT_DIR}; срез реализован:
${JSON.stringify(slice, null, 2)}
Напиши flutter-тесты (widget+unit) по acceptance_criteria и итерируй '{{TEST_RUNNER_CMD}}' до ЗЕЛЁНОГО.
- Зелено → закоммить, status='green', test_output = финальная строка.
- Честно не достиг → НЕ ослабляй: status='deferred', объясни; дерево чистое.
ОБЯЗАТЕЛЬНО заполни risk_level (LOW|MED|HIGH) и risk_markers (state-lifecycle/isolate-blocking/null-safety/dispose-leaks/peripheral-io) — оцени blast-radius среза; test_coverage_pct — оценку покрытия изменённого поведения.
ЧЕСТНОСТЬ (критично): любую обходку/форс-конфиг ради зелёного (pumpAndSettle в обход реального ожидания, мок состояния в обход провайдера, отключённый dispose-чек) занеси в workarounds как [POSSIBLE-DEFECT] — за обходкой почти всегда реальный баг. Если для проверки внешнего факта (версия/API пакета, поведение плагина) движок был недоступен (perplexity-web залочен/TIMEOUT, context7 пусто) — занеси в tool_failures, НЕ угадывай: факт непроверен, нужен ПОВТОРНЫЙ ПРОХОД.
ЗАПАСНОЙ ПУТЬ (если строгую схему возврата 5× не удаётся заполнить — не срывай прогон): последней строкой выведи ровно '===SLICE-RESULT=== status=green' или '===SLICE-RESULT=== status=deferred'.
${HARD_GATES}`,
    { label: `test:${slice.id}`, phase: 'Build', agentType: '{{PACK_PREFIX}}-test-writer', schema: SLICE_RESULT_SCHEMA, effort: 'medium' }
  )
  log(`срез ${sliceNo}/${SLICES.length}: ${slice.id} test=${result ? result.status : 'infra-failed(null)'}`)  // heartbeat

  let review = null
  if (result && result.status === 'green') {
    consecutiveFails = 0
    const risk = String(result.risk_level || RISK(slice)).toUpperCase()
    const rl = reviewLane(risk)
    const markers = (result.risk_markers || []).join(', ') || '(не указаны)'
    const workarounds = (result.workarounds || []).length
      ? 'ОБХОДКИ В ТЕСТАХ (каждая — индикатор реального дефекта, разбери источник): ' + result.workarounds.join(' | ')
      : 'обходок в тестах не заявлено'
    const depth = risk === 'HIGH'
      ? 'РЕЖИМ ADVERSARIAL (HIGH): сначала перечисли failure-modes (гонки жизненного цикла состояния, блокировка главного isolate, потерянный dispose/утечка, нарушенная null-safety, зависшее I/O периферии без timeout), затем для КАЖДОГО построй конкретный сценарий (входы + порядок событий + состояние), где дифф ломается. Свежий контекст: суди по диффу, не «полируй».'
      : risk === 'MED'
      ? 'РЕЖИМ MED: состояние ({{STATE_MGMT}}), dispose/утечки, null-safety, границы I/O; conditional-чек-листы соответствующего слоя.'
      : 'РЕЖИМ LOW: style + очевидная корректность + null-safety (spot-check).'
    review = await safeAgent(
      `Read-only ревью среза "${slice.title}" в ${PROJECT_DIR}, ветка ${BRANCH}. Diff против ${BASE} ('git diff ${BASE}...${BRANCH}').
RISK=${risk}; risk_markers: ${markers}. ${depth}
${workarounds}
Проверь состояние ({{STATE_MGMT}}), dispose/утечки, null-safety, для pos-embedded — неблокирование главного isolate, и acceptance_criteria: ${JSON.stringify(slice.acceptance_criteria)}.
Репортить ВСЕ находки: severity ∈ {LOW,MED,HIGH,CRITICAL} + location(file:line) + failure_scenario; при сомнении — выше, сам не фильтруй. Прогони '{{ANALYZE_CMD}}' и '{{FORMAT_CMD}}'. Файлы НЕ меняй, дерево чистое.
${HARD_GATES}`,
      { label: `review:${slice.id}`, phase: 'Build', agentType: '{{PACK_PREFIX}}-reviewer', model: rl.model, effort: rl.effort }
    )
    log(`срез ${sliceNo}/${SLICES.length}: ${slice.id} review-ok (${results.filter((r) => r.status === 'green').length + 1}/${SLICES.length} зелёных)`)
  } else {
    consecutiveFails++
  }
  results.push({ ...(result || { id: slice.id, status: 'infra-failed', risk_level: RISK(slice), summary: 'agent вернул null (терминальный infra-сбой рантайма ИЛИ agent() бросил исключение — см. лог safeAgent)', assumptions: [], open_questions: [] }), review_findings: review })

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
2. '{{ANALYZE_CMD}}' — 0 ошибок.
3. '{{FORMAT_CMD}}' — чисто.
4. Полный '{{TEST_RUNNER_CMD}}' — число/статус.
Краткий итог. Файлы не меняй, не push.
${HARD_GATES}`,
  { label: 'final-verify', phase: 'Verify', model: 'sonnet', effort: 'medium' }
)

const built = results.map((r) => ({ id: r.id, status: r.status }))
const infraN = built.filter((b) => b.status === 'infra-failed').length
log(`Готово: ${built.filter((b) => b.status === 'green').length}/${SLICES.length} зелёных${infraN ? `, ${infraN} infra-failed (инфра-отказ, НЕ дефект — см. <failures>)` : ''}. Ветка ${BRANCH}, ничего не запушено.`)
return { branch: BRANCH, base: BASE, max: MAX, results, verify }
