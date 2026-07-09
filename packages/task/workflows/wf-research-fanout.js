// Шаблон 1: research-fanout — N тем × research → adversarial verify (pipeline, без барьера).
// Прототип: рабочий скрипт ECOSYSTEM P5 (wf-p5-research.js). Правила слотов — README.md рядом.
export const meta = {
  name: 'research-fanout', // SLOT: имя под конкретный запуск, напр. 'p5-research-sweep'
  description: 'RAG-развед по N темам параллельно + адверсариальная проверка несущих утверждений',
  whenToUse: 'Stage research любого пайплайна; запускать через scriptPath (НЕ named-workflow — args приходит строкой)',
  phases: [
    { title: 'Research', detail: 'темы параллельно — perplexity-web', model: 'sonnet' },
    { title: 'Verify', detail: 'адверсариальная проверка load-bearing утверждений', model: 'sonnet' },
  ],
}

// ── Конфиг (embedded, НЕ через args-строку) ──────────────────────────────────
// SLOT: TOPICS — темы разведки; key = slug для label/отчёта, brief = плотное ТЗ
// с контекстом экосистемы, таймфреймом (год!), named tools и границами scope.
const TOPICS = [
  { key: 'topic-a', brief: 'Тема A: конкретный вопрос со стеком/версиями/таймфреймом 2025-2026, "X vs Y", named tools.' },
  { key: 'topic-b', brief: 'Тема B: …' },
]

// SLOT: контекст проекта — одна строка, подставляется в каждый промпт.
const PROJECT_CONTEXT = 'экосистема Axioma (Laravel/CoreX + Dart/Flutter, RU-рынок, 54-ФЗ)'

// SLOT: model/effort — research обычно sonnet/medium; opus только если темы
// требуют глубокого синтеза, а не сбора фактов.
const RESEARCH_MODEL = { model: 'sonnet', effort: 'medium' }
const VERIFY_MODEL = { model: 'sonnet', effort: 'medium' }

// SLOT: сколько load-bearing утверждений проверять на тему (verify — не бесплатный).
const VERIFY_TOP_N = 6

// ── Схемы structured-summary (агент возвращает данные, супервизор держит контекст) ──
// SLOT: FINDINGS_SCHEMA — расширять под задачу (напр. vendor_candidates для vendor-scan),
// но ядро claim/source_url/load_bearing не убирать: на нём стоит verify-стадия.
const FINDINGS_SCHEMA = {
  type: 'object',
  properties: {
    topic: { type: 'string' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          claim: { type: 'string', description: 'Факт/практика одним абзацем, конкретно' },
          source_url: { type: 'string' },
          source_title: { type: 'string' },
          load_bearing: { type: 'boolean', description: 'true если на этом стоит будущее решение' },
        },
        required: ['claim', 'source_url', 'source_title', 'load_bearing'],
      },
    },
    recommendations: { type: 'array', items: { type: 'string' } },
    open_questions: { type: 'array', items: { type: 'string' } },
  },
  required: ['topic', 'findings', 'recommendations', 'open_questions'],
}

const VERIFY_SCHEMA = {
  type: 'object',
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          claim: { type: 'string' },
          verdict: { type: 'string', enum: ['CONFIRMED', 'REFUTED', 'UNVERIFIED'] },
          note: { type: 'string' },
          counter_source_url: { type: 'string' },
        },
        required: ['claim', 'verdict', 'note'],
      },
    },
  },
  required: ['verdicts'],
}

// ── Промпты ──────────────────────────────────────────────────────────────────
function researchPrompt(t) {
  return [
    `RAG-research по теме «${t.key}». Контекст: ${PROJECT_CONTEXT}.`,
    `Тема: ${t.brief}`,
    `Инструменты: сначала ToolSearch с query "select:mcp__perplexity-web__search_deep,mcp__perplexity-web__search_advanced,mcp__perplexity-web__search" — загрузи схемы. Начни с ОДНОГО search_deep по теме целиком, затем 4–8 уточняющих search/search_advanced по дырам и спорным местам. Любое собственное сомнение — ещё один запрос, не догадка.`,
    `Дисциплина запросов (query-craft): конкретика вместо общих слов — версии/стек/таймфрейм, формат "X vs Y", named tools. Не задавать голые вопросы типа "best practices".`,
    `Каждое утверждение — с URL источника. Чего не нашёл в источниках — в open_questions, не выдумывать. load_bearing=true только для утверждений, на которых будет стоять проектное решение. Факт без источника = [UNVERIFIED] прямо в тексте claim.`,
    `Верни строго по схеме. Твой финальный текст = данные, не сообщение человеку.`,
  ].join('\n')
}

function verifyPrompt(t, res) {
  const loadBearing = res.findings.filter(f => f.load_bearing).slice(0, VERIFY_TOP_N)
  const claims = loadBearing.length ? loadBearing : res.findings.slice(0, 4)
  return [
    `Адверсариальная проверка research-находок по теме «${t.key}». Твоя задача — ОПРОВЕРГНУТЬ каждое утверждение свежим независимым поиском.`,
    `Инструменты: ToolSearch "select:mcp__perplexity-web__search_advanced,mcp__perplexity-web__search", затем 1-2 контрольных запроса на утверждение (другие формулировки, чем исходные).`,
    `Утверждения:`,
    ...claims.map((f, i) => `${i + 1}. ${f.claim} [источник: ${f.source_url}]`),
    `Вердикты: CONFIRMED только при независимом подтверждении; сомнение = UNVERIFIED; противоречие источникам = REFUTED с counter_source_url.`,
    `Верни строго по схеме.`,
  ].join('\n')
}

// ── Оркестрация: pipeline без барьера — verify темы стартует сразу после её research ──
log(`research-fanout: ${TOPICS.length} тем, verify без барьера (pipeline)`)

const results = await pipeline(
  TOPICS,
  t => agent(researchPrompt(t), {
    label: `research:${t.key}`, phase: 'Research',
    ...RESEARCH_MODEL, schema: FINDINGS_SCHEMA,
  }),
  (res, t) => {
    if (!res || !res.findings || !res.findings.length) return null
    return agent(verifyPrompt(t, res), {
      label: `verify:${t.key}`, phase: 'Verify',
      ...VERIFY_MODEL, schema: VERIFY_SCHEMA,
    }).then(v => ({ key: t.key, research: res, verify: v ? v.verdicts : [] }))
  }
)

const ok = results.filter(Boolean)
const dropped = TOPICS.filter(t => !ok.some(r => r.key === t.key)).map(t => t.key)
if (dropped.length) log(`ВНИМАНИЕ: темы без результата (пересобрать в main loop): ${dropped.join(', ')}`)

return { topics: ok, dropped }
