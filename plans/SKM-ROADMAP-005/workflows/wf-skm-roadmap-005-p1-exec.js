export const meta = {
  name: 'wf-skm-roadmap-005-p1-exec',
  description: 'Исполнить фазу P1 (settings-doctor) плана SKM-ROADMAP-005: 6 items серийно, exec→validate→review→commit, роутинг моделей per-item',
  whenToUse: 'Когда фаза P1 расписана (DoR пройден) и нужно провести её 6 items с коммит-гейтом и risk-адаптивным ревью без ручного дирижирования',
  phases: [
    { title: 'P1.1 ядро', detail: 'загрузчик слоёв + эффективная конфигурация' },
    { title: 'P1.2 проверки 1-3,5,9', detail: 'первый срез + снапшот ключей' },
    { title: 'P1.3 профили 4,11', detail: 'policy-профили + ключ .swissknife.json (opus)' },
    { title: 'P1.4 CLI + фасад', detail: 'harness doctor --settings + skiller фасад (opus)' },
    { title: 'P1.5 второй срез + VSCode', detail: 'проверки 6-8,10,12-13 + fieldcase' },
    { title: 'P1.6 fleet + закрытие', detail: 'maind --audit settings + статус спеки' },
  ],
}

// ─── Константы плана ──────────────────────────────────────────────────────────
const PLAN = 'SKM-ROADMAP-005'
const PLAN_DIR = `plans/${PLAN}`
// Cold-start reads — общие для каждого item'а (самодостаточность из холодной сессии).
const COMMON_READS = [
  `${PLAN_DIR}/plan.md`,
  `${PLAN_DIR}/phases/P1.md`,
  `${PLAN_DIR}/findings/P1-cc-settings-facts.md`,
  'packages/harness/CLAUDE.md',
].join(' · ')

// Роутинг моделей — отклонения от дефолта sonnet/medium заданы в plan.md ## 3. Routing.
// P1.3/P1.4 правят публичный контракт (конфиг skiller / контракт CLI+фасад) → opus/high.
// Ревью — risk-адаптивное: публичный контракт судит opus/high, остальное sonnet/high.
const ITEMS = [
  { id: 'P1.1', phase: 'P1.1 ядро',                 model: 'sonnet', effort: 'medium', review: 'sonnet', reviewEffort: 'high', risk: 'фундамент всех проверок — ошибка тиражируется' },
  { id: 'P1.2', phase: 'P1.2 проверки 1-3,5,9',     model: 'sonnet', effort: 'medium', review: 'sonnet', reviewEffort: 'high', risk: 'уровни находок; неизвестное hook-событие → info, не warn' },
  { id: 'P1.3', phase: 'P1.3 профили 4,11',         model: 'opus',   effort: 'high',   review: 'opus',   reviewEffort: 'high', risk: 'ПУБЛИЧНЫЙ контракт: CONFIG_KEYS + schema skiller' },
  { id: 'P1.4', phase: 'P1.4 CLI + фасад',          model: 'opus',   effort: 'high',   review: 'opus',   reviewEffort: 'high', risk: 'контракт --json/exit-code (на нём стоит fleet P1.6)' },
  { id: 'P1.5', phase: 'P1.5 второй срез + VSCode', model: 'sonnet', effort: 'medium', review: 'sonnet', reviewEffort: 'high', risk: 'проверка №10 обязана остаться info (D3); интеграционный fieldcase' },
  { id: 'P1.6', phase: 'P1.6 fleet + закрытие',     model: 'sonnet', effort: 'medium', review: 'sonnet', reviewEffort: 'high', risk: 'гейт закрытия: 🟢 в roadmap только после реального прогона' },
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

Cold-start reads (прочитай ПЕРЕД работой, в порядке): ${COMMON_READS}. В phases/P1.md найди раздел «### ${item.id}» и следуй ВСЕМ 16 полям — особенно Implementation Rules, Code Guidance (запреты и обязательные тесты), Validation.

Дом движка — packages/harness (D10). Жёсткие рамки: stdlib-only; doctor read-only (никакой записи на диск из проверок); факты, помеченные в findings как [UNVERIFIED] (семантика permissions.additionalDirectories, полнота списка hook-событий), НЕ додумывать — обходить дизайном по D15/правилу info. Сообщения на русском.

КОММИТ-ГЕЙТ (plan-protocol §6) — обязателен для статуса done/done_with_deviations:
1. Напиши код + тесты из Code Guidance.
2. Прогони Validation-команды item'а. validate.sh затронутых пакетов ДОЛЖЕН быть зелёным ДО коммита.
3. Коммить атомарно по смыслу, Conventional Commits на русском (сабджекты — из поля Deliverables item'а). Заверши тело коммита строкой: Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
4. Диффа Scope item'а не должно остаться в дереве (git status чистый по затронутым файлам). Дифф ВНЕ Scope не коммить — вынеси в Pending Work.
5. Обнови статус item'а в phases/P1.md (Phase Status + поле Status) и Status Board в plan.md на 🟢/🟠; заполни Completion Notes.

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
- Code Guidance соблюдён: запреты не нарушены (напр. для P1.2/P1.5 — проверка №10 и неизвестные hook-события остаются info, не warn; для P1.1 — нет Path.home()/сети/записи на диск; для P1.3 — CONFIG_KEYS и schema правлены ОДНИМ коммитом, contains-семантика deny).
- Обязательные тесты из Code Guidance реально написаны и реально гоняются (не пустышки-заглушки).
- validate.sh правда зелёный (прогони сам, если сомнения) и диффа item вне коммита не осталось.
- Статусы в plan.md/phases/P1.md обновлены; коммит-гейт соблюдён.

Риск среза: ${item.risk}. Верни СТРОГО структурой REVIEW_SCHEMA. RED только с конкретными blockers (файл+суть), которые обязан устранить fix-проход.`
}

function fixPrompt(item, review) {
  return `Ты package-implementer. Ревью item ${item.id} плана ${PLAN} вернуло RED. Устрани блокеры и НЕ более того (никакого scope creep).

Блокеры: ${review.blockers.map((b, i) => `(${i + 1}) ${b}`).join(' ')}

Reads: ${COMMON_READS} + «### ${item.id}» в phases/P1.md.
Правила: те же рамки (stdlib-only, doctor read-only, [UNVERIFIED] не додумывать). Прогони Validation item'а до зелёного. Коммить ОТДЕЛЬНЫМ review-fix коммитом (НЕ amend — трассируемость: коммит должен показать, что поймало ревью), Conventional Commits на русском + строка Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>. Если блокер требует эскалации — не чини силой, верни status=blocked.

Верни СТРОГО структурой EXEC_SCHEMA.`
}

// ─── Оркестрация: строгая цепочка (items правят один settings_audit.py — НЕ параллелить) ──
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
log(`Итог P1: закрыто ${closed.length}/${ITEMS.length} items`)
return { plan: PLAN, phase: 'P1', closed: closed.length, total: ITEMS.length, results }
