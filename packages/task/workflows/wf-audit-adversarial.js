// Template 3: audit-adversarial — M finders (measurements) → dedup → adversarial verify → verdicts.
// Read-only: not a single agent edits or commits anything. Slot Rules - README.md nearby.
export const meta = {
  name: 'audit-adversarial', // SLOT: name for a specific launch
  description: 'Adversarial-artifact audit: parallel finder-measurements, deduplication, independent verification of findings',
  whenToUse: 'Plan Audit/docks/code/diff; run through scriptPath (NOT named-workflow — args comes as a string)',
  phases: [
    { title: 'Find', detail: 'by finder-agent for measurement, in parallel', model: 'sonnet' },
    { title: 'Dedup', detail: 'merging duplicates, normalization severity', model: 'sonnet' },
    { title: 'Verify', detail: 'adversarial verification of each find with fresh context', model: 'opus' },
  ],
}

// ── Config (embedded, NOT via args-line) ──────────────────────────────────
// SLOT: TARGET — that we are auditing (absolute paths: repo/plan/diff) + how to read.
// INVARIANT: absolute paths only (cwd subagent is reset between calls).
const TARGET = {
  paths: ['/abs/path/to/target'],
  readHint: 'read the entire plan; code - point by point according to the links from the plan', // how to read a target economically
}
for (const p of TARGET.paths) {
  if (!p.startsWith('/')) throw new Error(`TARGET.paths must be an absolute path: "${p}"`)
}

// SLOT: CONSTITUTION — conformity constitution (profile artifact-review, block 12):
// plan → diagram plan-protocol 2.0 + DoR; documentation → structure canon docs;
// code → stack skills (## Conformance). Paths to reference files, finder reads them.
const CONSTITUTION = ['/abs/path/to/constitution.md']

// SLOT: DIMENSIONS — audit dimensions; by finder'for measurement. Classic for code:
// correctness/security/perf + conformance-finder for each applicable skill.
// For the plan: RAG-groundedness, structural completeness, consistency D-log, Open Questions.
// cache-bust: `agent()` caches by (prompt, opts) — on `resumeFromRunId` specific
// measurements without global invalidator add opt. field `asOf` (date/tag) to object
// measurements and mix into `label`/prompt (see README §General invariants), without touching the others.
const DIMENSIONS = [
  { key: 'dimension-a', brief: 'What exactly to look for, what defect patterns, what is NOT a find.' },
]

// SLOT: SEVERITY — enum severity; canon artifact-review: Blocker/Major/Minor/Nit.
const SEVERITY = ['Blocker', 'Major', 'Minor', 'Nit']

// SLOT: judge-panel — ONLY for high-stakes stages (fiscal/payments/tenant-isolation/
// core of the ecosystem). false = one verify-agent; true = 3 independent verdict + consensus.
// guarded-optional-args: flag with explicit default (false), not a bare condition without a value by
// by default - pattern from `wf-agentools-drive` (cross-ref absolutely, do not vendor).
const JUDGE_PANEL = false

// SLOT: model/effort — finders sonnet/medium; verify more expensive (fresh context decides the verdict).
const FINDER_MODEL = { model: 'sonnet', effort: 'medium' }
const DEDUP_MODEL = { model: 'sonnet', effort: 'low' }
// SLOT: exact native model/effort from the selected or current captured native review route.
const VERIFY_MODEL = null // { model: '<exact-native-model-id>', effort: 'high' }
if (!VERIFY_MODEL || typeof VERIFY_MODEL.model !== 'string' || !VERIFY_MODEL.model.trim() ||
    !['low', 'medium', 'high', 'xhigh'].includes(VERIFY_MODEL.effort)) {
  throw new Error('REVIEWER_REQUIRED: fill VERIFY_MODEL from the selected/current native route before requested audit')
}

// ── Schemes structured-summary ─────────────────────────────────────────────────
const FINDING = {
  type: 'object',
  properties: {
    dimension: { type: 'string' },
    file: { type: 'string' },
    line: { type: 'integer' },
    summary: { type: 'string', description: 'Defect in one sentence' },
    failure_scenario: { type: 'string', description: 'Specific input/status → incorrect result' },
    severity: { type: 'string', enum: SEVERITY },
    risk_class: { type: 'string', enum: ['local', 'concurrency', 'transaction', 'auth', 'data-integrity'] },
    area: { type: 'string', description: 'shared subsystem/invariant, independent of file/driver' },
    rule_ref: { type: 'string', description: 'Link constitution/skill → rule (for conformance-finds)' },
  },
  required: ['dimension', 'file', 'summary', 'failure_scenario', 'severity', 'risk_class', 'area'],
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
          summary: { type: 'string', description: 'summary findings - matching key' },
          verdict: { type: 'string', enum: ['CONFIRMED', 'REJECTED', 'PLAUSIBLE'] },
          note: { type: 'string' },
          severity: { type: 'string', enum: SEVERITY, description: 'adjusted severity' },
        },
        required: ['summary', 'verdict', 'note'],
      },
    },
  },
  required: ['verdicts'],
}

// ── Prompts ──────────────────────────────────────────────────────────────────
function finderPrompt(d) {
  return [
    `Finder-measurement audit «${d.key}». Target: ${TARGET.paths.join(', ')} (${TARGET.readHint}).`,
    `Compliance Constitution - Read Before Searching: ${CONSTITUTION.join(', ')}.`,
    `Measurement: ${d.brief}`,
    `READ-ONLY: do not edit or commit anything. Each find is with file/line and specific failure_scenario; «could be bad» without script = is not a find. Severity strictly from ${JSON.stringify(SEVERITY)}. Empty array findings = purely by measurement, this is a valid result.`,
    `Return strictly according to the scheme. Final text = data, not a message to a person.`,
    `For systemic concurrency/transaction/auth/data-integrity risk, inspect the shared invariant model and all interfering operation/resource/driver pairs. Classify each finding by risk_class and stable area.`,
  ].join('\n')
}

function dedupPrompt(all) {
  return [
    `Deduplication of audit findings (${all.length} pcs. from ${DIMENSIONS.length} finder'ov). DO NOT look for new finds, DO NOT read the goal - only work with the list.`,
    `Rules: same defect from different measurements = one find (save all dimension separated by commas, take the maximum severity); adjacent symptoms of the same root = one find with common failure_scenario.`,
    `Findings:\n${JSON.stringify(all, null, 2)}`,
    `Return strictly according to the scheme (same format findings).`,
  ].join('\n')
}

function verifyPrompt(findings, judgeIdx) {
  return [
    `Adversarial verification of audit findings with fresh context${judgeIdx != null ? ` (independent judge #${judgeIdx + 1} — don't know other people's opinions)` : ''}. Target: ${TARGET.paths.join(', ')}.`,
    `Your task is to REJECT every finding: re-read the indicated passage yourself and try to prove that there is no defect. CONFIRMED only when I reproduced it myself failure_scenario by code/text; could neither confirm nor reject = PLAUSIBLE; finding is erroneous = REJECTED with explanation in note. Can be adjusted severity.`,
    `READ-ONLY: don't edit anything. Finds:\n${JSON.stringify(findings, null, 2)}`,
    `Return one owning continuation for confirmed defects. Never repair product or start another audit. Preserve risk_class/area and systemic model coverage across a recheck.`,
    `Return it strictly according to the scheme.`,
  ].join('\n')
}

// safeAgent — try/catch over **bare** `await agent()` (out `parallel()`/`pipeline()`, where throw
// is already caught by runtime and returns `null`): without a wrap, the agent's throw drops the entire run.
async function safeAgent(prompt, opts) {
  try { return await agent(prompt, opts) } catch (e) { log(`agent error (${opts.label || '?'}): ${e.message || e}`); return null }
}

// ── Orchestration ──────────────────────────────────────────────────────────────
log(`audit-adversarial: ${DIMENSIONS.length} measurements, judge-panel=${JUDGE_PANEL}`)

const found = await parallel(DIMENSIONS.map(d =>
  () => agent(finderPrompt(d), {
    label: `find:${d.key}`, phase: 'Find',
    ...FINDER_MODEL, schema: FINDINGS_SCHEMA,
  })
))

const raw = found.filter(Boolean).flatMap(r => r.findings || [])
if (!raw.length) { log('no finds - audit is clean'); return { findings: [], verdicts: [] } }

// Dedup is only needed when finder'there is more than one - otherwise there is nothing to merge.
const deduped = DIMENSIONS.length > 1 && raw.length > 1
  ? (await safeAgent(dedupPrompt(raw), { label: 'dedup', phase: 'Dedup', ...DEDUP_MODEL, schema: FINDINGS_SCHEMA }))?.findings || raw
  : raw

log(`finds: ${raw.length} → after dedup: ${deduped.length}`)

// Verify: one agent, or a panel of 3 independent judges (only high-stakes).
let verdicts
if (JUDGE_PANEL) {
  const panel = await parallel([0, 1, 2].map(i =>
    () => agent(verifyPrompt(deduped, i), {
      label: `judge:${i + 1}`, phase: 'Verify',
      ...VERIFY_MODEL, schema: VERDICTS_SCHEMA,
    })
  ))
  // Consensus: CONFIRMED when ≥2 votes CONFIRMED; ≥2 REJECTED = REJECTED; otherwise PLAUSIBLE.
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

log(`summary: ${confirmed.length} finds survived verification (from ${deduped.length})`)
return { findings: confirmed, rejected: deduped.length - confirmed.length }
