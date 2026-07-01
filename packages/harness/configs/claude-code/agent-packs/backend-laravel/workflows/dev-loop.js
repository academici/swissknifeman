export const meta = {
  name: '{{PACK_PREFIX}}-dev-loop',
  description: 'Реализует список backend-срезов {{PACK_PREFIX}} последовательно на ОДНОЙ ветке: для каждого среза impl ({{PACK_PREFIX}}-slice-builder) → tests-to-green ({{PACK_PREFIX}}-test-writer) → review-gate ({{PACK_PREFIX}}-reviewer). Уроки overnight-прогона зашиты: один branch на прогон, хард-кап срезов переживает resume, circuit-breaker. Скоуп срезов решает человек и передаёт через args.',
  phases: [
    { title: 'Setup', detail: 'чистое дерево + одна feature-ветка от base (НЕ per-slice ветки)' },
    { title: 'Build', detail: 'по срезу последовательно: impl → tests-to-green → review-gate' },
    { title: 'Verify', detail: 'полный сюит + pint + отчёт' },
  ],
}

// ---------------------------------------------------------------------------
// Вход (args):
//   { branch: 'feat/...', base?: 'main', max_slices?: 3,
//     slices: [ { id, title, domain, goal, surface?, acceptance_criteria, skills? } ] }
// Скоуп (какие срезы и в каком порядке) решает человек до запуска — этот workflow
// исполняет, а не придумывает продуктовый объём.
// ---------------------------------------------------------------------------

const PROJECT_DIR = '{{PROJECT_DIR}}'

// Урок overnight-прогона: хард-кап ДОЛЖЕН пережить resume. args на resume может не
// долететь → дефолт держим литералом В СКРИПТЕ, а не только в args.
// Урок throttling: батч = N срезов × (impl+test+review) — большой батч множит
// retry-поверхность под rate-limit. Дефолт 2 (не 3+); solo-fallback — дисциплина оркестратора.
const DEFAULT_MAX = 2

const BRANCH = (args && args.branch) || 'feat/dev-loop'
const BASE = (args && args.base) || 'main'
const MAX = (args && args.max_slices) || DEFAULT_MAX
const ALL_SLICES = (args && Array.isArray(args.slices)) ? args.slices : []

// Урок: один branch на весь прогон. Кап применяем ЗДЕСЬ (slice), а не через
// необязательный arg внутри агентов.
const SLICES = ALL_SLICES.slice(0, MAX)

const HARD_GATES = `ЖЁСТКИЕ ГЕЙТЫ {{PACK_PREFIX}} (не нарушать):
- PHP/тесты ТОЛЬКО через '{{PHP_RUNNER}}' ({{TEST_RUNNER_CMD}}), не bare 'php'.
- Если .env залочен хуком — не читать и не править; конфиг тестовой БД в phpunit.xml/tests/bootstrap.php ({{TEST_DB}}).
- Тест-фреймворк проекта — {{TEST_FRAMEWORK}}: зеркаль стиль существующих тестов. Схему/миграции меняй только если того требует срез. Статическая проверка (если настроена) — {{CHECK_CMD}}.
- НЕ git push, НЕ открывать/мержить PR, НЕ release. НЕ migrate:fresh/drop по чему-либо кроме тестовой БД.
- Все срезы строятся на ОДНОЙ ветке ${BRANCH}. Агенты НЕ создают и не переключают ветки — коммитят в текущую и оставляют дерево чистым.
- Работать строго внутри ${PROJECT_DIR}.`

if (SLICES.length === 0) {
  log('Нет срезов на вход (args.slices пуст) — нечего строить. Передай { branch, base, max_slices, slices: [...] }.')
  return { built: [], note: 'no slices provided' }
}

// ---------------------------------------------------------------------------
phase('Setup')

// Один агент устанавливает ветку: чистое дерево → ветка от base (создать или
// переключиться). Дальше НИКТО ветки не трогает.
await agent(
  `В ${PROJECT_DIR} подготовь рабочую ветку и проверь окружение ДО раздачи срезов.
1. 'git status' — если дерево грязное, останови и отчитайся (НЕ затирай чужие правки).
2. ENV-PREFLIGHT (блокер окружения ≠ баг кода): '{{PHP_RUNNER}} -v' (версия); '{{PHP_RUNNER}} -r "print_r(PDO::getAvailableDrivers());"' — нужный драйвер БД присутствует; пробный '{{TEST_RUNNER_CMD}} --filter=__preflight_nonexistent__' не падает фаталом окружения. Драйвер/версия/конфиг сломаны → ОСТАНОВИ прогон и отчитайся (chatom F3: php без рабочего pdo_sqlite всплывал лишь на первом DB-тесте).
3. Ветка: если ${BRANCH} существует — 'git checkout ${BRANCH}'. Иначе 'git checkout ${BASE}' затем 'git checkout -b ${BRANCH}'.
4. Подтверди: окружение ок, текущая ветка = ${BRANCH}, дерево чистое, последний коммит (subject).
НЕ push, НЕ удаляй ветки.
${HARD_GATES}`,
  { label: 'setup-branch', phase: 'Setup', model: 'sonnet', effort: 'low' }
)

// ---------------------------------------------------------------------------
phase('Build')

const SLICE_RESULT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['id', 'status', 'risk_level', 'summary', 'assumptions', 'open_questions'],
  properties: {
    id: { type: 'string' },
    status: { type: 'string', enum: ['green', 'deferred', 'failed', 'infra-failed'], description: 'green=тесты зелёные; deferred=честно не зелёный (реальный дефект); failed=агент отчитался о сбое; infra-failed=инфра-отказ (rate-limit/timeout/agent вернул null) — НЕ маскировать под deferred' },
    risk_level: { type: 'string', enum: ['LOW', 'MED', 'HIGH'], description: 'blast-radius среза (см. risk_markers)' },
    risk_markers: { type: 'array', items: { type: 'string', enum: ['concurrency', 'transactions', 'data-integrity', 'queue-semantics', 'connectors'] }, description: 'какие классы риска затронул срез' },
    summary: { type: 'string' },
    files_changed: { type: 'array', items: { type: 'string' } },
    tests_added: { type: 'array', items: { type: 'string' } },
    test_output: { type: 'string', description: 'финальная строка {{TEST_RUNNER_CMD}}' },
    test_coverage_pct: { type: 'number', description: 'покрытие изменённого поведения, % (оценка)' },
    workarounds: { type: 'array', items: { type: 'string' }, description: 'обходки/форс-конфиги ради зелёного — каждая = [POSSIBLE-DEFECT] для ревьюера' },
    assumptions: { type: 'array', items: { type: 'string' }, description: 'решения там, где ТЗ молчало' },
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
  // Durable-прогресс = число green-срезов (в песочнице нет shell → не git rev-list).
  // Затяжной hang одного agent() тут НЕ ловится (управление не вернулось) — это забота
  // внешнего supervisor (доклад оркестратора ~30 мин + PushNotification, см. orchestrator.md).
  if (consecutiveFails >= 2) {
    log(`Circuit-breaker: ${consecutiveFails} среза подряд не дошли до зелёного — стоп, иду в Verify/отчёт.`)
    break
  }

  const extraSkills = (slice.skills || []).join(', ') || '(дополнительных нет)'
  const lane = implLane(slice)
  // Durable-light handover: компактные сводки прошлых срезов (ТОЛЬКО поля схемы, не транскрипты).
  const priorSummary = results.length
    ? 'Прошлые срезы (сводка): ' + results.map((r) => `${r.id}=${r.status}/${r.risk_level || '?'} — ${r.summary || ''}`).join(' | ')
    : '(это первый срез)'

  // 1) Реализация среза в текущую ветку ({{PACK_PREFIX}}-slice-builder; модель/effort — по риску среза).
  await agent(
    `Реализуй ОДИН backend-срез {{PACK_PREFIX}} в текущей ветке ${BRANCH}.

СРЕЗ:
${JSON.stringify(slice, null, 2)}

${priorSummary}

Дополнительно к преднагруженным скиллам подгрузи и применяй: ${extraSkills}.
Построй тонкий полный путь (route → controller/Action → DTO/Resource → policy при необходимости) по канону access-layer. Тесты НЕ пиши — их пишет следующий агент. Коммить в текущую ветку, оставь дерево чистым.
${HARD_GATES}`,
    { label: `impl:${slice.id}`, phase: 'Build', agentType: '{{PACK_PREFIX}}-slice-builder', model: lane.model, effort: lane.effort }
  )
  log(`срез ${sliceNo}/${SLICES.length}: ${slice.id} impl-ok`)  // heartbeat: живость для supervisor/человека

  // 2) Тесты до зелёного (или чистая отсрочка). Test-writer ОЦЕНИВАЕТ риск и ЧЕСТНО репортит обходки.
  const result = await agent(
    `Ты в текущей ветке ${BRANCH} в ${PROJECT_DIR}; срез уже реализован:
${JSON.stringify(slice, null, 2)}

Напиши тесты ({{TEST_FRAMEWORK}}), доказывающие acceptance_criteria, и итерируй '{{TEST_RUNNER_CMD}}' до ЗЕЛЁНОГО.
- Зелено → закоммить тесты в ${BRANCH}, status='green', заполни test_output финальной строкой.
- Не достиг зелёного честно → НЕ ослабляй тесты: оставь дерево чистым, status='deferred', объясни в summary+open_questions (реализация остаётся в ${BRANCH}).
ОБЯЗАТЕЛЬНО заполни risk_level (LOW|MED|HIGH) и risk_markers (concurrency/transactions/data-integrity/queue-semantics/connectors) — оцени blast-radius среза; test_coverage_pct — оценку покрытия изменённого поведения.
ЧЕСТНОСТЬ (критично): любую обходку/форс-конфиг ради зелёного (форс config(...), штамповка timestamp перед пагинацией, sibling-класс в обход final) занеси в workarounds как [POSSIBLE-DEFECT] — за обходкой почти всегда реальный баг. ShouldQueue-job: если тест зовёт handle() напрямую — занеси в open_questions «queue-семантика (release/backoff/конкурентные воркеры) не покрыта».
Дерево всегда оставляй ЧИСТЫМ. Зафиксируй допущения.
ЗАПАСНОЙ ПУТЬ (если строгую схему возврата 5× не удаётся заполнить — не срывай прогон): последней строкой ответа выведи ровно '===SLICE-RESULT=== status=green' или '===SLICE-RESULT=== status=deferred'; коммит-дисциплина та же.
${HARD_GATES}`,
    { label: `test:${slice.id}`, phase: 'Build', agentType: '{{PACK_PREFIX}}-test-writer', schema: SLICE_RESULT_SCHEMA, effort: 'medium' }
  )
  log(`срез ${sliceNo}/${SLICES.length}: ${slice.id} test=${result ? result.status : 'infra-failed(null)'}`)  // heartbeat

  // 3) Risk-адаптивный review-gate только по зелёным. Глубина/модель/effort — под РИСК (не под размер).
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
      ? 'РЕЖИМ ADVERSARIAL (HIGH): сначала перечисли failure-modes (гонки/потерянные retry/двойная обработка/нарушенные инварианты/неверный auth/сломанный config-дефолт), затем для КАЖДОГО построй конкретный сценарий (входы + конкуренция + состояние), где дифф ломается. Свежий контекст: суди по диффу, не «полируй».'
      : risk === 'MED'
      ? 'РЕЖИМ MED: контракты, авторизация, целостность; conditional-чек-листы соответствующего слоя.'
      : 'РЕЖИМ LOW: style + N+1 + очевидная корректность (spot-check).'
    review = await agent(
      `Read-only ревью среза "${slice.title}" в ${PROJECT_DIR}, ветка ${BRANCH}. Diff против ${BASE} ('git diff ${BASE}...${BRANCH}').
RISK=${risk}; risk_markers: ${markers}. ${depth}
${workarounds}
Проверь канон access-layer (grep ::query/::create/::where/::all/::find по контроллерам домена — пусто), корректность, авторизацию и acceptance_criteria: ${JSON.stringify(slice.acceptance_criteria)}.
Репортить ВСЕ находки: severity ∈ {LOW,MED,HIGH,CRITICAL} + location(file:line) + failure_scenario; при сомнении — выше, сам не фильтруй (фильтрация/merge — по гейтам пакета). Прогони {{CHECK_CMD}} на изменённых файлах и '{{TEST_RUNNER_CMD}} --filter=${slice.domain || ''}'. Файлы НЕ меняй, дерево чистое.
${HARD_GATES}`,
      { label: `review:${slice.id}`, phase: 'Build', agentType: '{{PACK_PREFIX}}-reviewer', model: rl.model, effort: rl.effort }
    )
    log(`срез ${sliceNo}/${SLICES.length}: ${slice.id} review-ok (${results.filter((r) => r.status === 'green').length + 1}/${SLICES.length} зелёных)`)
  } else {
    consecutiveFails++
  }

  results.push({ ...(result || { id: slice.id, status: 'infra-failed', risk_level: RISK(slice), summary: 'agent вернул null (терминальный infra-сбой рантайма)', assumptions: [], open_questions: [] }), review_findings: review })

  // Fail-fast на инфра-отказ: agent() вернул null = терминальный сбой рантайма (rate-limit/
  // timeout, ретраи исчерпаны). Дальше бессмысленно — throttling сам не пройдёт от перехода
  // к следующему срезу. НЕ маскируем под deferred (P4). Затяжной hang (без null) ловит supervisor.
  if (!result) {
    log(`Fail-fast: срез ${slice.id} infra-failed (agent вернул null) — стоп прогона, иду в Verify/отчёт.`)
    break
  }
}

// ---------------------------------------------------------------------------
phase('Verify')

const verify = await agent(
  `Финальная проверка прогона в ${PROJECT_DIR}, ветка ${BRANCH}:
1. 'git status' — дерево чистое, текущая ветка ${BRANCH}.
2. grep -rnE '::query\\(|::create\\(|::where\\(|::all\\(|::find\\(' по app/Http/Controllers/Api и app/Actions — перечисли оставшиеся попадания (в контроллерах должно быть 0).
3. Полный '{{TEST_RUNNER_CMD}}' — число/статус.
4. 'vendor/bin/pint --test' — чисто.
Краткий итог: чист ли слой доступа, тесты (число/упало), что осталось. Файлы не меняй, не push.
${HARD_GATES}`,
  { label: 'final-verify', phase: 'Verify', effort: 'high' }
)

const built = results.map((r) => ({ id: r.id, status: r.status }))
const infraN = built.filter((b) => b.status === 'infra-failed').length
log(`Готово: ${built.filter((b) => b.status === 'green').length}/${SLICES.length} зелёных${infraN ? `, ${infraN} infra-failed (инфра-отказ, НЕ дефект — см. <failures>)` : ''}. Кап MAX=${MAX}, ветка ${BRANCH} (off ${BASE}). Ничего не запушено.`)

return { branch: BRANCH, base: BASE, max: MAX, results, verify }
