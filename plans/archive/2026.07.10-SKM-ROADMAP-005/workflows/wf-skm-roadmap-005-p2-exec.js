export const meta = {
  name: 'wf-skm-roadmap-005-p2-exec',
  description: 'Исполнить фазу P2 (wf-status) плана SKM-ROADMAP-005: 5 items серийно, exec→validate→review→commit, risk-адаптивное ревью',
  whenToUse: 'Когда фаза P2 расписана (DoR пройден) и нужно провести её 5 items с коммит-гейтом и ревью без ручного дирижирования. Items правят один wf_status.py — строго серийно.',
  phases: [
    { title: 'P2.1 парсер', detail: 'защищённый парсер transcript-директории (journal+meta+скрипт)' },
    { title: 'P2.2 discovery', detail: 'поиск прогонов: свежие по mtime, --run, --project' },
    { title: 'P2.3 рендер', detail: 'фиксированный шаблон + --json + --watch' },
    { title: 'P2.4 CLI + фасад', detail: 'harness wf status + swissknifeman wf + фикстура (review opus)' },
    { title: 'P2.5 прошивка', detail: 'подсказка в скиллы task:* + конструктор + roadmap' },
  ],
}

// ─── Константы плана ──────────────────────────────────────────────────────────
const PLAN = 'SKM-ROADMAP-005'
const PLAN_DIR = `plans/${PLAN}`
// Cold-start reads — общие для каждого item'а (самодостаточность из холодной сессии).
const COMMON_READS = [
  `${PLAN_DIR}/plan.md`,
  `${PLAN_DIR}/phases/P2.md`,
  `${PLAN_DIR}/findings/P2-workflow-transcript-format.md`,
  'packages/harness/CLAUDE.md',
].join(' · ')

// Роутинг моделей — дефолт по plan.md ## 3. Routing: P2.* → sonnet/medium (нет opus-items).
// Ревью risk-адаптивно: P2.4 трогает КОРНЕВОЙ router (bin/swissknifeman) — регресс на другие
// группы + sed-диапазон usage → судит opus/high; остальное sonnet/high.
const ITEMS = [
  { id: 'P2.1', phase: 'P2.1 парсер',        model: 'sonnet', effort: 'medium', review: 'sonnet', reviewEffort: 'high', risk: 'фундамент всей команды; защищённость (degraded вместо трейсбека) и D18 (не додумывать per-phase)' },
  { id: 'P2.2', phase: 'P2.2 discovery',     model: 'sonnet', effort: 'medium', review: 'sonnet', reviewEffort: 'high', risk: 'slug-деривация ТОЧНО по findings; пустая база → [] без падения; детерминизм сортировки' },
  { id: 'P2.3', phase: 'P2.3 рендер',        model: 'sonnet', effort: 'medium', review: 'sonnet', reviewEffort: 'high', risk: 'плоский рендер (логика статуса — в P2.1); per-phase счётчики НЕ показывать (D18); детерминизм шаблона' },
  { id: 'P2.4', phase: 'P2.4 CLI + фасад',   model: 'sonnet', effort: 'medium', review: 'opus',   reviewEffort: 'high', risk: 'root-фасад passthrough; sed-диапазон usage() синхронен числу строк шапки; не сломать env)/maind) группы' },
  { id: 'P2.5', phase: 'P2.5 прошивка',      model: 'sonnet', effort: 'medium', review: 'sonnet', reviewEffort: 'high', risk: 'править ТОЛЬКО поверхности, уже упоминающие workflow (греп); НЕ создавать workflow-craft (это P3); скилл — SKILL.ru.md→regen' },
]

// Схема отчёта exec-агента (форсит структурированный возврат — без парсинга прозы).
const EXEC_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['status', 'committed', 'validate_green', 'summary', 'commits', 'escalation'],
  properties: {
    status: { type: 'string', enum: ['done', 'done_with_deviations', 'blocked'] },
    committed: { type: 'boolean', description: 'дифф item закоммичен (коммит-гейт)' },
    validate_green: { type: 'boolean', description: 'validate.sh затронутых пакетов зелёный ДО коммита' },
    summary: { type: 'string', description: '1-3 строки: что сделано' },
    commits: { type: 'array', items: { type: 'string' }, description: 'сабджекты коммитов item' },
    escalation: { type: 'string', description: 'причина ESCALATION-REQUIRED или пусто' },
  },
}

// Схема вердикта ревью.
const REVIEW_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['verdict', 'blockers', 'notes'],
  properties: {
    verdict: { type: 'string', enum: ['GREEN', 'ATTENTION', 'RED'] },
    blockers: { type: 'array', items: { type: 'string' }, description: 'что блокирует (RED); пусто для GREEN' },
    notes: { type: 'string' },
  },
}

// ─── Промпты ──────────────────────────────────────────────────────────────────
function execPrompt(item) {
  return `Ты package-implementer. Исполни item ${item.id} мастер-плана ${PLAN} СТРОГО по его ТЗ.

Cold-start reads (прочитай ПЕРЕД работой, в порядке): ${COMMON_READS}. В phases/P2.md найди раздел «### ${item.id}» и следуй ВСЕМ 16 полям — особенно Required Reads, Implementation Rules, Code Guidance (запреты и обязательные тесты), Validation.

Дом движка — packages/harness (D17), файл packages/harness/lib/harness/wf_status.py. Жёсткие рамки: stdlib-only (без внешних зависимостей); парсер ЗАЩИЩЁННЫЙ — несовпадение формата/битый journal → degraded-флаг + честная причина, НЕ трейсбек и НЕ тихий пустой ответ; запрещены eval/exec/импорт .js; НЕ додумывать per-agent→phase attribution — журнал его не несёт (D18), при соблазне «сопоставить агентов фазам» это Scope Excluded; источник формата transcript — findings-файл с датой сверки (формат меняется между версиями CC), НЕ доки. Читаем только локальную FS. Сообщения на русском.

КОММИТ-ГЕЙТ (plan-protocol §6) — обязателен для статуса done/done_with_deviations:
1. Напиши код + тесты из Code Guidance (юнит на рукотворной мини-директории в tmp — обязателен для P2.1-P2.4).
2. Прогони Validation-команды item'а. bash packages/harness/scripts/validate.sh ДОЛЖЕН быть зелёным ДО коммита.
3. Коммить атомарно по смыслу, Conventional Commits на русском (сабджекты — из поля Deliverables item'а). Заверши тело коммита строкой: Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
4. Диффа Scope item'а не должно остаться в дереве (git status чистый по затронутым файлам). Дифф ВНЕ Scope не коммить — вынеси в Pending Work.
5. Обнови статус item'а в phases/P2.md (Phase Status + поле Status) и Status Board в plan.md (строка P2) на 🟢/🟠; заполни Completion Notes.

ЭСКАЛАЦИЯ (plan-protocol §10): наткнулся на триггер (multi-package refactoring / unclear architecture / public contract·SemVer / protected generated assets / rule conflict / unclear acceptance) — НЕ импровизируй. Поставь Status 🔴 Blocked, оставь blockquote «> 🔴 ESCALATION ${item.id}: <причина> | trigger: <из enum>» в item'е, верни status=blocked с заполненным escalation. НЕ коммить полуфабрикат.

Риск среза: ${item.risk}.

Верни СТРОГО структурой EXEC_SCHEMA. Твой финальный текст — это данные, не сообщение человеку.`
}

function reviewPrompt(item, exec) {
  return `Ты invariant-auditor. Свежим контекстом (read-only) отревьюй ТОЛЬКО что закрытый item ${item.id} плана ${PLAN}.

Reads: ${COMMON_READS}; затем git-факты — «git log --oneline -5», «git show --stat HEAD», «git diff HEAD~${(exec.commits||[]).length||1}..HEAD» по затронутым файлам.

Свод от исполнителя: status=${exec.status}, committed=${exec.committed}, validate_green=${exec.validate_green}. Коммиты: ${(exec.commits||[]).join(' | ') || '—'}. Итог: ${exec.summary}.

Проверь адверсариально, НЕ доверяя своду:
- Соответствие Scope Included/Excluded item'а; нет ли scope drift или no-op-коммита.
- Code Guidance соблюдён: для P2.1/P2.3 — per-phase attribution НЕ додумана (D18), degraded вместо трейсбека реально работает; для P2.2 — slug-деривация точно по findings (ведущий -, все /→-), пустая база → [] без падения; для P2.4 — root-фасад passthrough БЕЗ логики, sed-диапазон usage() синхронен числу строк шапки (bin/swissknifeman --help содержит wf), существующие группы (env doctor) НЕ сломаны; для P2.5 — правлены ТОЛЬКО поверхности с упоминанием workflow (греп), скилл workflow-craft НЕ создан (это P3), правка скилла — через SKILL.ru.md→regen.
- Обязательные тесты из Code Guidance реально написаны и реально гоняются (не пустышки); для P2.4 интеграционный тест гоняет РЕАЛЬНЫЙ бинарь harness на фикстуре (subprocess), а не только импорт.
- validate.sh правда зелёный (прогони сам, если сомнения) и диффа item вне коммита не осталось.
- Статусы в plan.md/phases/P2.md обновлены; коммит-гейт соблюдён.

Риск среза: ${item.risk}. Верни СТРОГО структурой REVIEW_SCHEMA. RED только с конкретными blockers (файл+суть), которые обязан устранить fix-проход.`
}

function fixPrompt(item, review) {
  return `Ты package-implementer. Ревью item ${item.id} плана ${PLAN} вернуло RED. Устрани блокеры и НЕ более того (никакого scope creep).

Блокеры: ${review.blockers.map((b, i) => `(${i + 1}) ${b}`).join(' ')}

Reads: ${COMMON_READS} + «### ${item.id}» в phases/P2.md.
Правила: те же рамки (stdlib-only, парсер защищённый/degraded, D18 не додумывать per-phase, только локальная FS). Прогони Validation item'а до зелёного. Коммить ОТДЕЛЬНЫМ review-fix коммитом (НЕ amend — трассируемость: коммит должен показать, что поймало ревью), Conventional Commits на русском + строка Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>. Если блокер требует эскалации — не чини силой, верни status=blocked.

Верни СТРОГО структурой EXEC_SCHEMA.`
}

// ─── Оркестрация: строгая цепочка (P2.1-P2.4 правят один wf_status.py — НЕ параллелить) ──
const results = []
for (const item of ITEMS) {
  phase(item.phase)

  // 1) exec
  let exec = await agent(execPrompt(item), {
    label: `exec:${item.id}`, phase: item.phase, schema: EXEC_SCHEMA,
    model: item.model, effort: item.effort,
  })

  if (!exec) { // агент умер/пропущен — не молчим, останавливаем цепочку
    log(`⛔ ${item.id}: exec-агент не вернул результат — цепочка остановлена (downstream items зависят от этого файла)`)
    results.push({ id: item.id, status: 'aborted', reason: 'exec agent returned null' })
    break
  }

  if (exec.status === 'blocked') {
    log(`🔴 ${item.id}: ESCALATION — ${exec.escalation || 'без причины'}. Цепочка остановлена, нужен /task:plan-design.`)
    results.push({ id: item.id, ...exec })
    break
  }

  if (!exec.committed || !exec.validate_green) {
    log(`⚠ ${item.id}: коммит-гейт НЕ соблюдён (committed=${exec.committed}, validate_green=${exec.validate_green}) — останавливаю, статус 🟢 ставить нельзя (инцидент D12 SKM-AUDIT-004)`)
    results.push({ id: item.id, ...exec, gate: 'FAILED' })
    break
  }

  // 2) review (risk-адаптивный)
  const review = await agent(reviewPrompt(item, exec), {
    label: `review:${item.id}`, phase: item.phase, schema: REVIEW_SCHEMA,
    model: item.review, effort: item.reviewEffort,
  })

  // 3) fix при RED (один проход; повторный RED → стоп на человека)
  let fixed = null
  if (review && review.verdict === 'RED' && review.blockers.length) {
    log(`🔧 ${item.id}: ревью RED (${review.blockers.length} блокер(ов)) — запускаю fix-проход`)
    fixed = await agent(fixPrompt(item, review), {
      label: `fix:${item.id}`, phase: item.phase, schema: EXEC_SCHEMA,
      model: item.model, effort: item.effort,
    })
    if (!fixed || fixed.status === 'blocked' || !fixed.committed) {
      log(`🔴 ${item.id}: fix не закрыл блокеры — цепочка остановлена, нужен человек`)
      results.push({ id: item.id, exec, review, fixed, gate: 'FIX_FAILED' })
      break
    }
  }

  results.push({ id: item.id, status: exec.status, commits: exec.commits, review: review?.verdict || 'n/a', fixed: !!fixed })
  log(`✅ ${item.id}: ${exec.status}, ревью ${review?.verdict || 'n/a'}${fixed ? ' (после fix)' : ''}`)
}

const closed = results.filter(r => r.status === 'done' || r.status === 'done_with_deviations')
log(`Итог P2: закрыто ${closed.length}/${ITEMS.length} items`)
return { plan: PLAN, phase: 'P2', closed: closed.length, total: ITEMS.length, results }
