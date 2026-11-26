// Template 4: dev-slice — slice → impl → tests-to-green (loop with max-iteration) → optional requested review (REVIEW slot, off by default).
// The slices are sequential (each one builds on the previous one); slot rules - README.md nearby.
export const meta = {
  name: 'dev-slice', // SLOT: name for a specific launch
  description: 'Development by slices: implementation, bringing tests to green, optional requested read-only review',
  whenToUse: 'Stage development based on ready-made technical specifications/plan; run through scriptPath (NOT named-workflow — args comes as a string)',
  phases: [
    { title: 'Impl', detail: 'slice implementation + tests', model: 'sonnet' },
    { title: 'Green', detail: 'loop: running tests → fix, until green or max-iteration', model: 'sonnet' },
    { title: 'Review', detail: 'optional requested review; depth by risk', model: 'opus' },
  ],
}

// ── Config (embedded, NOT via args-line) ──────────────────────────────────
// SLOT: paths - repository and technical specificationsSSOT (absolute: cwd subagent is reset).
// INVARIANT: absolute path is required - assert catches relative on a live run,
// does not fire on an empty template (placeholder `/abs/path/to/…` itself is absolute).
const REPO = '/abs/path/to/repo'
const SPEC = '/abs/path/to/spec.md'
if (!REPO.startsWith('/')) throw new Error(`REPO must be an absolute path: "${REPO}"`)
if (!SPEC.startsWith('/')) throw new Error(`SPEC must be an absolute path: "${SPEC}"`)

// SLOT: SLICES — vertical slices, sequentially. One slice = impl + green + review + commit.
//   brief  — Slice specification with a link to the section SPEC (agent reads SPEC himself);
//   tests  — command to run slice tests (is his validation);
//   risk   — low | medium | high: defines the depth review (see reviewFor);
//   commit — ready subject Conventional Commits.
// cache-bust: `agent()` caches by (prompt, opts) — on `resumeFromRunId` ONE slice
// without global invalidator add opt. field `asOf` (date/tag) into the slice object and mix
// in `label` (see README §General invariants; pattern - roadmap-note dterema-p4).
const SLICES = [
  {
    key: 'slice-1',
    brief: 'Slice 1: what to implement, boundaries, what NOT to touch (section N specs).',
    tests: 'cd REPO && ./vendor/bin/pest --filter=Slice1',
    risk: 'medium',
    commit: 'feat(scope): essence of the slice (PLAN-ID Pn.m)',
  },
]

// SLOT: GATES — gates between slices; chased away after review EACH slice,
// red gate stops the conveyor (the following slices do not start).
// Typical: full test suite, statistical analysis, commit-gate «working tree is clean».
const GATES = ['git -C REPO status --short — empty (everything is committed)']

// SLOT: REVIEW — enable only for an explicit owner review request, never from risk alone.
const REVIEW = false

// SLOT: max-iteration for tests-to-green loop — REQUIRED (agent should not
// spin endlessly, adjusting the tests to the code). Exhaustion = conveyor stop.
const MAX_GREEN_ITERATIONS = 3

// SLOT: model/effort — impl sonnet/medium; REVIEWER is filled from explicit owner selection.
const IMPL_MODEL = { model: 'sonnet', effort: 'medium' }
const GREEN_MODEL = { model: 'sonnet', effort: 'medium' }
// SLOT: exact native model/effort from --reviewer provider/model; no silent default reviewer.
// The author resolves the selected/current native route; cross-provider work needs its native handoff.
const REVIEWER = null // { model: '<exact-native-model-id>', effort: 'high' }
// Risk adapts review depth; only REVIEW admits a fresh read-only reviewer.
// guarded-optional-args: cut without `risk` should not silently get cheap review — explicit
// default 'medium' (typeof-guard), not a bare call to `s.risk` (pattern wf-agentools-drive).
const riskOf = s => typeof s.risk === 'string' ? s.risk : 'medium'
if (REVIEW &&
    (!REVIEWER || typeof REVIEWER.model !== 'string' || !REVIEWER.model.trim() ||
     !['low', 'medium', 'high', 'xhigh'].includes(REVIEWER.effort))) {
  throw new Error('REVIEWER_REQUIRED: fill model/effort from the explicitly selected reviewer before execution')
}

// ── Schemes structured-summary ─────────────────────────────────────────────────
const REPORT = {
  type: 'object',
  properties: {
    files_changed: { type: 'array', items: { type: 'string' } },
    commits: { type: 'array', items: { type: 'string' } },
    tests_green: { type: 'boolean', description: 'slice tests green (exit 0)' },
    validation: { type: 'string', description: 'commands and exit-codes' },
    issues: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string', description: 'essence of what was done, 3-5 lines' },
  },
  required: ['files_changed', 'commits', 'tests_green', 'validation', 'issues', 'summary'],
}

const REVIEW_SCHEMA = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          file: { type: 'string' },
          summary: { type: 'string' },
          failure_scenario: { type: 'string' },
          severity: { type: 'string', enum: ['Blocker', 'Major', 'Minor', 'Nit'] },
          risk_class: { type: 'string', enum: ['local', 'concurrency', 'transaction', 'auth', 'data-integrity'] },
          area: { type: 'string', description: 'stable subsystem/invariant across files and drivers' },
        },
        required: ['file', 'summary', 'failure_scenario', 'severity', 'risk_class', 'area'],
      },
    },
    verdict: { type: 'string', enum: ['APPROVE', 'FIX_REQUIRED'] },
  },
  required: ['findings', 'verdict'],
}

// ── Prompts ──────────────────────────────────────────────────────────────────
const COMMON = [
  `Repository: ${REPO}. TZ-SSOT: ${SPEC} — read the section of your slice before writing the code.`,
  `Discipline: minimal diff under the cut, do not refactor other people's code along the way; ambiguity in the technical specifications - in issues, don't improvise.`,
  `Final text = data according to the scheme, not a message to the person.`,
].join('\n')

const implPrompt = s => [
  COMMON,
  s.brief,
  `Implement a slice along with tests. Drive away: ${s.tests} — bring it to green within the cut. Tests check BEHAVIOR from the technical specifications; adjustment assertion'ov under the actual code output is prohibited.`,
  `Don't commit until complete tests-to-green${REVIEW ? ', independent review' : ''} and interslice gates.`,
  `Execution owns implementation/self-check/tests only. Do not launch reviewers or start a fix/re-review loop; the orchestrator owns the separate reviewer call.`,
].join('\n\n')

const greenPrompt = (s, prev, iter) => [
  COMMON,
  `Slice tests «${s.key}» not green (iteration ${iter}/${MAX_GREEN_ITERATIONS}). Drive away ${s.tests}, sort out the crashes, fix the CODE (edit tests only if the test contradicts the technical specifications - then record this in issues).`,
  `Report from previous attempt: ${prev.validation}`,
  `Don't commit before${REVIEW ? ' independent review and' : ''} interslice gates.`,
].join('\n\n')

const commitPrompt = s => [
  COMMON,
  `All checks${REVIEW ? ', review' : ''} and slice gates «${s.key}» passed. Before commit do git status --short and git diff --name-only.`,
  `Stage only files modified by you in this slice; never use git add -A/-u. Unrelated or foreign dirty-do not touch the bytes and point to issues.`,
  `Create one commit: ${s.commit}.`,
].join('\n\n')

const reviewPrompt = s => [
  `Read-only ${riskOf(s)}-risk slice review «${s.key}» fresh context (you are NOT the author). Repository: ${REPO}; Terms of reference: ${SPEC} (slice section). Before commit check current scoped diff via git status --short and git diff; unrelated/strangers dirty-bytes should not be included in the verdict.`,
  `Look for: inconsistency with technical specifications, correctness-defects with specific failure_scenario, fitting tests to the code. Severity Blocker/Major/Minor/Nit. Verdict FIX_REQUIRED for any Blocker/Major.`,
  `Don't edit or commit ANYTHING. Final text = schema data.`,
  `For concurrency/transactions/auth/data-integrity, check the shared invariant model against all affected operation/resource/driver pairs. Return risk_class and stable area for each demonstrated finding. Do not start repairs or another review.`,
].join('\n\n')

const gatePrompt = s => [
  `Run the gates after the cut «${s.key}» in ${REPO}: ${GATES.join('; ')}. Don't fix ANYTHING - just the facts (exit-codes) and the verdict in issues, if red. Final text = schema data.`,
].join('\n')

// ── Orchestration: slices sequentially, inside a slice - loop-until-green with ceiling ──
log(`dev-slice: ${SLICES.length} slices, max green-iterations: ${MAX_GREEN_ITERATIONS}`)

// safeAgent — try/catch over **bare** `await agent()` (out `parallel()`/`pipeline()`, where throw
// is already caught by runtime and returns `null`): without a wrap, the agent's throw drops the entire run.
async function safeAgent(prompt, opts) {
  try { return await agent(prompt, opts) } catch (e) { log(`agent error (${opts.label || '?'}): ${e.message || e}`); return null }
}

const done = []
for (const s of SLICES) {
  let res = await safeAgent(implPrompt(s), {
    label: `impl:${s.key}:${s.asOf || ''}`, phase: 'Impl', ...IMPL_MODEL, schema: REPORT,
  })
  if (!res) {
    log(`STOP: impl:${s.key} without result`)
    done.push({ key: s.key, impl: null, review: null, stopped: 'impl-missing' })
    break
  }

  // tests-to-green loop — is strictly limited max-iteration (rule README).
  let iter = 0
  while (!res.tests_green && iter < MAX_GREEN_ITERATIONS) {
    iter++
    const fix = await safeAgent(greenPrompt(s, res, iter), {
      label: `green:${s.key}:${s.asOf || ''}#${iter}`, phase: 'Green', ...GREEN_MODEL, schema: REPORT,
    })
    if (!fix) {
      done.push({ key: s.key, impl: res, review: null, stopped: 'green-missing' })
      break
    }
    res = { ...fix, commits: [...(res.commits || []), ...(fix.commits || [])] }
  }
  if (done.find(d => d.key === s.key && d.stopped === 'green-missing')) break
  if (!res.tests_green) {
    log(`STOP: cut ${s.key} didn't reach green for ${MAX_GREEN_ITERATIONS} iterations - escalation in main loop`)
    done.push({ key: s.key, impl: res, review: null, stopped: 'tests-not-green' })
    break
  }

  // Review is opt-in; a requested review covers every selected slice, with risk-adapted depth.
  let review = null
  if (REVIEW) {
    review = await safeAgent(reviewPrompt(s), {
      label: `review:${s.key}:${s.asOf || ''}`, phase: 'Review', ...REVIEWER, schema: REVIEW_SCHEMA,
    })
    if (!review) {
      log(`STOP: review:${s.key} without result`)
      done.push({ key: s.key, impl: res, review: null, stopped: 'review-missing' })
      break
    }
    if (review && review.verdict === 'FIX_REQUIRED') {
      log(`STOP: review slice ${s.key} = FIX_REQUIRED (${review.findings.length} find.) — return one owning correction; do not automatically restart review`)
      done.push({ key: s.key, impl: res, review, stopped: 'review-fix-required' })
      break
    }
  }

  // Gates between slices.
  const gate = GATES.length
    ? await safeAgent(gatePrompt(s), { label: `gate:${s.key}:${s.asOf || ''}`, phase: 'Impl', model: 'sonnet', effort: 'low', schema: REPORT })
    : null
  if (GATES.length && !gate) {
    log(`STOP: gate:${s.key} without result`)
    done.push({ key: s.key, impl: res, review, stopped: 'gate-missing' })
    break
  }
  if (gate && gate.issues && gate.issues.length) {
    log(`STOP: gate after ${s.key} red: ${gate.issues.join('; ')}`)
    done.push({ key: s.key, impl: res, review, stopped: 'gate-red', gate })
    break
  }

  const committed = await safeAgent(commitPrompt(s), {
    label: `commit:${s.key}:${s.asOf || ''}`, phase: 'Impl', ...IMPL_MODEL, schema: REPORT,
  })
  if (!committed) {
    log(`STOP: commit:${s.key} without result`)
    done.push({ key: s.key, impl: res, review, stopped: 'commit-missing' })
    break
  }
  res = { ...res, commits: [...(res.commits || []), ...(committed.commits || [])],
          issues: [...(res.issues || []), ...(committed.issues || [])] }

  done.push({ key: s.key, impl: res, review, stopped: null })
}

const stopped = done.find(d => d.stopped)
log(`dev-slice completed: ${done.filter(d => !d.stopped).length}/${SLICES.length} cuts clean${stopped ? `, stop on ${stopped.key} (${stopped.stopped})` : ''}`)

return {
  slices: done.map(d => ({
    key: d.key, stopped: d.stopped,
    commits: (d.impl && d.impl.commits) || [],
    review_findings: (d.review && d.review.findings) || [],
    issues: (d.impl && d.impl.issues) || [],
  })),
  all_green: done.length === SLICES.length && done.every(d => !d.stopped),
}
