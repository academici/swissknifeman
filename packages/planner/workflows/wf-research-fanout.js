// Template 1: research-fanout — N topics × research → adversarial verify (pipeline, without barrier).
// Prototype: working script ECOSYSTEM P5 (wf-p5-research.js). Slot Rules - README.md nearby.
export const meta = {
  name: 'research-fanout', // SLOT: name for a specific launch, for example. 'p5-research-sweep'
  description: 'RAG-reconnaissance N topics in parallel + adversarial verification of carrier statements',
  whenToUse: 'Stage research any pipeline; run through scriptPath (NOT named-workflow — args comes as a string)',
  phases: [
    { title: 'Research', detail: 'topics in parallel - perplexity-web', model: 'sonnet' },
    { title: 'Verify', detail: 'advertorial check load-bearing statements', model: 'sonnet' },
  ],
}

// ── Config (embedded, NOT via args-line) ──────────────────────────────────
// SLOT: TOPICS — intelligence topics; key = slug for label/report, brief = dense technical specification
// with ecosystem context, timeframe (year!), named tools and boundaries scope.
// cache-bust: `agent()` caches by (prompt, opts) — on `resumeFromRunId` ONE topic without
// global invalidator add opt. field `asOf` (date/tag) into the topic object and mix into
// `label`/prompt (see README §General invariants; pattern - roadmap-note dterema-p4).
const TOPICS = [
  { key: 'topic-a', brief: 'Topic A: specific stack issue/versions/timeframe 2025-2026, "X vs Y", named tools.' },
  { key: 'topic-b', brief: 'Topic B: …' },
]

// SLOT: project context - one line, inserted into each prompt.
const PROJECT_CONTEXT = 'ecosystem Axioma (Laravel/CoreX + Dart/Flutter, RU-market, 54-FZ)'

// SLOT: model/effort — research usually sonnet/medium; opus only if topics
// require deep synthesis rather than fact-gathering.
const RESEARCH_MODEL = { model: 'sonnet', effort: 'medium' }
const VERIFY_MODEL = { model: 'sonnet', effort: 'medium' }

// SLOT: how much load-bearing statements check for topic (verify — not free).
// guarded-optional-args: if load-bearing no statements, fallback to the first 4 (see `claims`
// in verifyPrompt) — explicit default, non-empty verification list; wf-agentools-drive cross-ref.
const VERIFY_TOP_N = 6

// ── Schemes structured-summary (agent returns data, supervisor holds context) ──
// SLOT: FINDINGS_SCHEMA — expand to suit the task (e.g. vendor_candidates for vendor-scan),
// but the kernel claim/source_url/load_bearing do not remove: there is a verify-stage.
const FINDINGS_SCHEMA = {
  type: 'object',
  properties: {
    topic: { type: 'string' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          claim: { type: 'string', description: 'Fact/practice in one paragraph, specifically' },
          source_url: { type: 'string' },
          source_title: { type: 'string' },
          load_bearing: { type: 'boolean', description: 'true if this is the future solution' },
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

// ── Prompts ──────────────────────────────────────────────────────────────────
function researchPrompt(t) {
  return [
    `RAG-research on topic «${t.key}». Context: ${PROJECT_CONTEXT}.`,
    `Subject: ${t.brief}`,
    `Tools: first ToolSearch with query "select:mcp__perplexity-web__search_deep,mcp__perplexity-web__search_advanced,mcp__perplexity-web__search" — download schematics. Start with ONE search_deep on the entire topic, then 4–8 clarifying ones search/search_advanced on holes and controversial places. Any self-doubt is another request, not a guess.`,
    `Query discipline (query-craft): specifics instead of general words - versions/stack/timeframe, format "X vs Y", named tools. Don't ask naked questions like "best practices".`,
    `Each statement is with URL source. What I didn’t find in the sources - in open_questions, don't make things up. load_bearing=true only for statements on which the design decision will be based. Fact without source = [UNVERIFIED] directly in the text claim.`,
    `Return strictly according to the scheme. Your final text = data, not a message to a person.`,
  ].join('\n')
}

function verifyPrompt(t, res) {
  const loadBearing = res.findings.filter(f => f.load_bearing).slice(0, VERIFY_TOP_N)
  const claims = loadBearing.length ? loadBearing : res.findings.slice(0, 4)
  return [
    `Adversarial check research-finds on the topic «${t.key}». Your task is to REFUTE each statement with a fresh, independent search.`,
    `Tools: ToolSearch "select:mcp__perplexity-web__search_advanced,mcp__perplexity-web__search", then 1-2 control requests for approval (different wording than original).`,
    `Statements:`,
    ...claims.map((f, i) => `${i + 1}. ${f.claim} [source: ${f.source_url}]`),
    `Verdicts: CONFIRMED only with independent confirmation; doubt = UNVERIFIED; conflicting sources = REFUTED with counter_source_url.`,
    `Return it strictly according to the scheme.`,
  ].join('\n')
}

// ── Orchestration: pipeline without barrier - verify topic starts immediately after it research ──
log(`research-fanout: ${TOPICS.length} those verify without barrier (pipeline)`)

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
if (dropped.length) log(`WARNING: topics with no results (rebuild to main loop): ${dropped.join(', ')}`)

return { topics: ok, dropped }
