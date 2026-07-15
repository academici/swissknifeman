// Шаблон 3: audit-adversarial — M finders (измерения) → dedup → adversarial verify → вердикты.
// Read-only: ни один агент ничего не правит и не коммитит. Правила слотов — README.md рядом.
export const meta = {
  name: 'audit-adversarial', // SLOT: имя под конкретный запуск
  description: 'Adversarial-аудит артефакта: параллельные finder-измерения, дедупликация, независимая верификация находок',
  whenToUse: 'Аудит плана/доков/кода/диффа; запускать через scriptPath (НЕ named-workflow — args приходит строкой)',
  phases: [
    { title: 'Find', detail: 'по finder-агенту на измерение, параллельно', model: 'sonnet' },
    { title: 'Dedup', detail: 'слияние дублей, нормализация severity', model: 'sonnet' },
    { title: 'Verify', detail: 'адверсариальная проверка каждой находки свежим контекстом', model: 'opus' },
  ],
}

// ── Конфиг (embedded, НЕ через args-строку) ──────────────────────────────────
// SLOT: TARGET — что аудируем (абсолютные пути: репо/план/дифф) + как читать.
// ИНВАРИАНТ: только абсолютные пути (cwd субагента сбрасывается между вызовами).
const TARGET = {
  paths: ['/abs/path/to/target'],
  readHint: 'прочитай план целиком; код — точечно по ссылкам из плана', // как экономно читать цель
}
for (const p of TARGET.paths) {
  if (!p.startsWith('/')) throw new Error(`TARGET.paths должен быть абсолютным путём: "${p}"`)
}

// SLOT: CONSTITUTION — конституция соответствия (профиль artifact-review, блок 12):
// план → схема plan-protocol 2.0 + DoR; документация → канон структуры docs;
// код → скиллы стека (## Conformance). Пути к файлам-эталонам, finder их читает.
const CONSTITUTION = ['/abs/path/to/constitution.md']

// SLOT: DIMENSIONS — измерения аудита; по finder'у на измерение. Классика для кода:
// correctness/security/perf + conformance-finder на каждый применимый скилл.
// Для плана: RAG-groundedness, структурная полнота, непротиворечивость D-лога, Open Questions.
// cache-bust: `agent()` кэширует по (prompt, opts) — на `resumeFromRunId` конкретного
// измерения без глобального инвалидатора добавь опц. поле `asOf` (дата/тег) в объект
// измерения и подмешай в `label`/промпт (см. README §Общие инварианты), не трогая остальные.
const DIMENSIONS = [
  { key: 'dimension-a', brief: 'Что именно искать, какие паттерны дефектов, что НЕ является находкой.' },
]

// SLOT: SEVERITY — enum severity; канон artifact-review: Blocker/Major/Minor/Nit.
const SEVERITY = ['Blocker', 'Major', 'Minor', 'Nit']

// SLOT: judge-panel — ТОЛЬКО для high-stakes стадий (фискалка/платежи/tenant-isolation/
// ядро экосистемы). false = один verify-агент; true = 3 независимых вердикта + консенсус.
// guarded-optional-args: флаг с явным дефолтом (false), не голое условие без значения по
// умолчанию — паттерн из `wf-agentools-drive` (cross-ref абс.путём, не вендорить).
const JUDGE_PANEL = false

// SLOT: model/effort — finders sonnet/medium; verify дороже (свежий контекст решает вердикт).
const FINDER_MODEL = { model: 'sonnet', effort: 'medium' }
const DEDUP_MODEL = { model: 'sonnet', effort: 'low' }
const VERIFY_MODEL = { model: 'opus', effort: 'high' }

// ── Схемы structured-summary ─────────────────────────────────────────────────
const FINDING = {
  type: 'object',
  properties: {
    dimension: { type: 'string' },
    file: { type: 'string' },
    line: { type: 'integer' },
    summary: { type: 'string', description: 'Дефект одним предложением' },
    failure_scenario: { type: 'string', description: 'Конкретный вход/состояние → неверный результат' },
    severity: { type: 'string', enum: SEVERITY },
    rule_ref: { type: 'string', description: 'Ссылка конституция/скилл → правило (для conformance-находок)' },
  },
  required: ['dimension', 'file', 'summary', 'failure_scenario', 'severity'],
}

const FINDINGS_SCHEMA = {
  type: 'object',
  properties: { findings: { type: 'array', items: FINDING } },
  required: ['findings'],
}

const VERDICTS_SCHEMA = {
  type: 'object',
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          summary: { type: 'string', description: 'summary находки — ключ соответствия' },
          verdict: { type: 'string', enum: ['CONFIRMED', 'REJECTED', 'PLAUSIBLE'] },
          note: { type: 'string' },
          severity: { type: 'string', enum: SEVERITY, description: 'скорректированная severity' },
        },
        required: ['summary', 'verdict', 'note'],
      },
    },
  },
  required: ['verdicts'],
}

// ── Промпты ──────────────────────────────────────────────────────────────────
function finderPrompt(d) {
  return [
    `Finder-аудит по измерению «${d.key}». Цель: ${TARGET.paths.join(', ')} (${TARGET.readHint}).`,
    `Конституция соответствия — прочитай прежде чем искать: ${CONSTITUTION.join(', ')}.`,
    `Измерение: ${d.brief}`,
    `READ-ONLY: ничего не правь и не коммить. Каждая находка — с file/line и конкретным failure_scenario; «может быть плохо» без сценария = не находка. Severity строго из ${JSON.stringify(SEVERITY)}. Пустой массив findings = чисто по измерению, это валидный результат.`,
    `Верни строго по схеме. Финальный текст = данные, не сообщение человеку.`,
  ].join('\n')
}

function dedupPrompt(all) {
  return [
    `Дедупликация находок аудита (${all.length} шт. от ${DIMENSIONS.length} finder'ов). НЕ ищи новые находки, НЕ читай цель — работай только со списком.`,
    `Правила: одинаковый дефект из разных измерений = одна находка (сохрани все dimension через запятую, возьми максимальную severity); соседние симптомы одного корня = одна находка с общим failure_scenario.`,
    `Находки:\n${JSON.stringify(all, null, 2)}`,
    `Верни строго по схеме (тот же формат findings).`,
  ].join('\n')
}

function verifyPrompt(findings, judgeIdx) {
  return [
    `Адверсариальная верификация находок аудита свежим контекстом${judgeIdx != null ? ` (независимый судья #${judgeIdx + 1} — не знаешь мнений других)` : ''}. Цель: ${TARGET.paths.join(', ')}.`,
    `Твоя задача — ОТКЛОНИТЬ каждую находку: перечитай указанное место сам и попробуй доказать, что дефекта нет. CONFIRMED только когда сам воспроизвёл failure_scenario по коду/тексту; не смог ни подтвердить, ни отклонить = PLAUSIBLE; находка ошибочна = REJECTED с объяснением в note. Можно скорректировать severity.`,
    `READ-ONLY: ничего не правь. Находки:\n${JSON.stringify(findings, null, 2)}`,
    `Верни строго по схеме.`,
  ].join('\n')
}

// safeAgent — try/catch над **bare** `await agent()` (вне `parallel()`/`pipeline()`, где throw
// уже ловится рантаймом и отдаёт `null`): без обёртки бросок агента роняет весь прогон.
async function safeAgent(prompt, opts) {
  try { return await agent(prompt, opts) } catch (e) { log(`agent error (${opts.label || '?'}): ${e.message || e}`); return null }
}

// ── Оркестрация ──────────────────────────────────────────────────────────────
log(`audit-adversarial: ${DIMENSIONS.length} измерений, judge-panel=${JUDGE_PANEL}`)

const found = await parallel(DIMENSIONS.map(d =>
  () => agent(finderPrompt(d), {
    label: `find:${d.key}`, phase: 'Find',
    ...FINDER_MODEL, schema: FINDINGS_SCHEMA,
  })
))

const raw = found.filter(Boolean).flatMap(r => r.findings || [])
if (!raw.length) { log('находок нет — аудит чист'); return { findings: [], verdicts: [] } }

// Dedup нужен только когда finder'ов больше одного — иначе нечего сливать.
const deduped = DIMENSIONS.length > 1 && raw.length > 1
  ? (await safeAgent(dedupPrompt(raw), { label: 'dedup', phase: 'Dedup', ...DEDUP_MODEL, schema: FINDINGS_SCHEMA }))?.findings || raw
  : raw

log(`находок: ${raw.length} → после dedup: ${deduped.length}`)

// Verify: один агент, либо панель из 3 независимых судей (только high-stakes).
let verdicts
if (JUDGE_PANEL) {
  const panel = await parallel([0, 1, 2].map(i =>
    () => agent(verifyPrompt(deduped, i), {
      label: `judge:${i + 1}`, phase: 'Verify',
      ...VERIFY_MODEL, schema: VERDICTS_SCHEMA,
    })
  ))
  // Консенсус: CONFIRMED при ≥2 голосах CONFIRMED; ≥2 REJECTED = REJECTED; иначе PLAUSIBLE.
  const votes = panel.filter(Boolean).map(p => p.verdicts)
  verdicts = deduped.map(f => {
    const v = votes.map(vs => vs.find(x => x.summary === f.summary)).filter(Boolean)
    const count = t => v.filter(x => x.verdict === t).length
    const verdict = count('CONFIRMED') >= 2 ? 'CONFIRMED' : count('REJECTED') >= 2 ? 'REJECTED' : 'PLAUSIBLE'
    return { summary: f.summary, verdict, note: v.map(x => x.note).join(' | '), severity: f.severity }
  })
} else {
  const v = await safeAgent(verifyPrompt(deduped, null), {
    label: 'verify', phase: 'Verify',
    ...VERIFY_MODEL, schema: VERDICTS_SCHEMA,
  })
  verdicts = (v && v.verdicts) || []
}

const confirmed = deduped
  .map(f => ({ ...f, ...(verdicts.find(v => v.summary === f.summary) || { verdict: 'PLAUSIBLE' }) }))
  .filter(f => f.verdict !== 'REJECTED')
  .sort((a, b) => SEVERITY.indexOf(a.severity) - SEVERITY.indexOf(b.severity))

log(`итог: ${confirmed.length} находок пережили верификацию (из ${deduped.length})`)
return { findings: confirmed, rejected: deduped.length - confirmed.length }
