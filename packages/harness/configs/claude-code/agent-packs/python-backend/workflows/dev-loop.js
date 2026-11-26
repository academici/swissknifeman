export const meta = {
  name: '{{PACK_PREFIX}}-dev-loop',
  description: 'Implements a list backend-slices {{PACK_PREFIX}} (Python {{WEB_FRAMEWORK}}) sequentially on ONE branch: impl ({{PACK_PREFIX}}-slice-builder) → tests-to-green ({{PACK_PREFIX}}-test-writer) → type-check ({{PACK_PREFIX}}-type-checker) → review-gate ({{PACK_PREFIX}}-reviewer). One branch, hardcap is experiencing resume, circuit-breaker.',
  phases: [
    { title: 'Setup', detail: 'pure tree + one feature-thread from base' },
    { title: 'Build', detail: 'by slice: impl → tests-to-green → type-check → review-gate' },
    { title: 'Verify', detail: 'ruff + mypy + full suite + report' },
  ],
}

const PROJECT_DIR = '{{PROJECT_DIR}}'
// hard cap literal (is worried resume). Lesson throttling: big batch multiplies
// retry-surface under rate-limit → default 2, not 3+ (solo-fallback — orchestrator discipline).
const DEFAULT_MAX = 2

// Named-workflow (Workflow({name,args})) delivers args BY LINE — SLICES would resolve to [],
// giving false no-op «no slices». Guard parses a string; broken JSON — explicit log-STOP with
// hint (P3.4/findings §4/§1.3), does not silently fall into an empty array.
if (typeof args === 'string' && args.trim()) {
  try {
    args = JSON.parse(args)
  } catch (e) {
    log(`args came as a string, but JSON.parse failed (${String((e && e.message) || e).slice(0, 160)}) — run via scriptPath (embedded args), not named-workflow.`)
    return { built: [], note: 'args parse failed' }
  }
}

const BRANCH = (args && args.branch) || 'feat/dev-loop'
const BASE = (args && args.base) || '{{BASE_BRANCH}}'
const MAX = (args && args.max_slices) || DEFAULT_MAX
const ALL_SLICES = (args && Array.isArray(args.slices)) ? args.slices : []
const SLICES = ALL_SLICES.slice(0, MAX)

const HARD_GATES = `HARD GATES {{PACK_PREFIX}} (do not violate):
- Tests/lint/types ONLY via '{{TEST_RUNNER_CMD}}' / '{{LINT_CMD}}' / '{{TYPECHECK_CMD}}' (venv-aware {{PY_BIN}}).
- DO NOT edit lockfile manually; DO NOT install packages globally; migration is a separate step.
- NOT git push, DO NOT open/flicker PR, NOT release.
- .claude/agents|workflows|hooks with generated-header DO NOT edit - overrides in .claude/rules/*-overrides.md.
- All cuts are on ONE branch ${BRANCH}; agents do NOT create/do not switch branches, the tree is clean.
- Work strictly inside ${PROJECT_DIR}. Framework: {{WEB_FRAMEWORK}}.`

if (SLICES.length === 0) {
  log('No input cuts (args.slices empty) — STOP. Pass on { branch, base, max_slices, slices: [...] } via scriptPath (embedded args), not named-workflow.')
  return { built: [], note: 'no slices provided' }
}

// Lesson overnight-run (azguard, plan-remainder): agent({schema}) may not return null,
// a THROW exception ('subagent completed without calling StructuredOutput'). Without wrapper
// throw dropped EVERYTHING workflow. safeAgent reduces throw to null — further standard degradation
// if(!result)/circuit-breaker.
async function safeAgent(prompt, opts) {
  try {
    return await agent(prompt, opts)
  } catch (e) {
    const label = (opts && opts.label) || '?'
    log(`agent ${label} threw an exception (${String((e && e.message) || e).slice(0, 160)}) — infra-failed, continue`)
    return null
  }
}

phase('Setup')
await safeAgent(
  `B ${PROJECT_DIR} prepare a working branch.
1. 'git status' — dirty tree → stop and report.
2. Thread ${BRANCH} yes → checkout; otherwise checkout ${BASE} + checkout -b ${BRANCH}.
3. Upvote the thread/cleanliness/last commit.
${HARD_GATES}`,
  { label: 'setup-branch', phase: 'Setup', model: 'sonnet', effort: 'low' }
)

phase('Build')
const SLICE_RESULT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['id', 'status', 'risk_level', 'summary', 'assumptions', 'open_questions'],
  properties: {
    id: { type: 'string' },
    status: { type: 'string', enum: ['green', 'deferred', 'failed', 'infra-failed'], description: 'green=green; deferred=honestly not green (defect); failed=agent reported failure; infra-failed=infra failure (rate-limit/timeout/null) — DO NOT disguise as deferred' },
    risk_level: { type: 'string', enum: ['LOW', 'MED', 'HIGH'], description: 'blast-radius slice (see risk_markers)' },
    risk_markers: { type: 'array', items: { type: 'string', enum: ['concurrency', 'transactions', 'data-integrity', 'migrations', 'auth', 'external-io'] }, description: 'what risk classes are affected by the cut' },
    summary: { type: 'string' },
    files_changed: { type: 'array', items: { type: 'string' } },
    tests_added: { type: 'array', items: { type: 'string' } },
    test_output: { type: 'string', description: 'final line {{TEST_RUNNER_CMD}}' },
    test_coverage_pct: { type: 'number', description: 'coverage of changed behavior, % (rating)' },
    workarounds: { type: 'array', items: { type: 'string' }, description: 'workarounds/force configs for the sake of green - each = [POSSIBLE-DEFECT] for reviewer' },
    tool_failures: { type: 'array', items: { type: 'string' }, description: 'engine/tool was not available when checking an external fact (perplexity-web locked/TIMEOUT, context7 empty, MCP lay down) → the fact remains unverified, a REPEATE PASS is needed. DO NOT guess, DO NOT mask' },
    assumptions: { type: 'array', items: { type: 'string' } },
    open_questions: { type: 'array', items: { type: 'string' } },
  },
}

// Lean-tiered lanes: model/effort at RISK of shearing. slice.risk/slice.model/slice.effort — tips
// person/orchestrator in args; no → default MED. Per-call model/effort interrupt frontmatter agent.
const RISK = (s) => String((s && s.risk) || 'MED').toUpperCase()
function implLane(slice) {
  const r = RISK(slice)
  return {
    model: slice.model || (r === 'LOW' ? 'haiku' : 'sonnet'),
    effort: slice.effort || (r === 'HIGH' ? 'high' : r === 'LOW' ? 'low' : 'medium'),
  }
}
function reviewLane(risk) {
  if (risk === 'LOW') return { model: 'sonnet', effort: 'medium' }  // cheap spot-check
  if (risk === 'HIGH') return { model: 'opus', effort: 'xhigh' }    // adversarial + fresh-context
  return { model: 'opus', effort: 'high' }
}

const results = []
let consecutiveFails = 0

for (const slice of SLICES) {
  const sliceNo = results.length + 1
  // Durable-progress = number green (not in the sandbox shell → not git rev-list). Lingering hang
  // one agent() is NOT caught here - this is a concern of the external supervisor (report ~30 min + PushNotification).
  if (consecutiveFails >= 2) {
    log(`Circuit-breaker: ${consecutiveFails} cuts in a row did not reach the green - stop.`)
    break
  }
  const extraSkills = (slice.skills || []).join(', ') || '(no additional)'
  const lane = implLane(slice)
  // Durable-light handover: compact summaries of past slices (Schema fields ONLY, not transcripts).
  const priorSummary = results.length
    ? 'Past slices (summary): ' + results.map((r) => `${r.id}=${r.status}/${r.risk_level || '?'} — ${r.summary || ''}`).join(' | ')
    : '(this is the first slice)'

  await safeAgent(
    `Implement ONE backend-slice {{PACK_PREFIX}} on {{WEB_FRAMEWORK}} in thread ${BRANCH}.
CUT:
${JSON.stringify(slice, null, 2)}

${priorSummary}

Additionally load: ${extraSkills}.
Build a subtle path (router/view → service → repository → diagram). DO NOT write tests. Commit to the current branch, the tree is clean.
${HARD_GATES}`,
    { label: `impl:${slice.id}`, phase: 'Build', agentType: '{{PACK_PREFIX}}-slice-builder', model: lane.model, effort: lane.effort }
  )
  log(`slice ${sliceNo}/${SLICES.length}: ${slice.id} impl-ok`)  // heartbeat

  const result = await safeAgent(
    `You're in the thread ${BRANCH} in ${PROJECT_DIR}; slice implemented:
${JSON.stringify(slice, null, 2)}
Write pytest by acceptance_criteria and iterate '{{TEST_RUNNER_CMD}}' to GREEN.
- Green → commit, status='green', test_output = final line.
- Honestly didn't reach it → DO NOT weaken: status='deferred', explain; the tree is clean.
MUST be completed risk_level (LOW|MED|HIGH) and risk_markers (concurrency/transactions/data-integrity/migrations/auth/external-io) — rate blast-radius slice; test_coverage_pct — behavior change coverage assessment.
HONESTY (critical): any workaround/force config for green (monkeypatch bypassing the real path, dummy transaction, validation disabled) put in workarounds like [POSSIBLE-DEFECT] — behind the workaround is almost always a real bug. If to check an external fact (version/API package, library behavior) engine was unavailable (perplexity-web locked/TIMEOUT, context7 empty) — put in tool_failures, DO NOT guess: the fact is unverified, a REPEATE is required.
EMERGENCY PATH (if strict return scheme 5× cannot be filled - do not disrupt the run): as the last line print exactly '===SLICE-RESULT=== status=green' or '===SLICE-RESULT=== status=deferred'.
${HARD_GATES}`,
    { label: `test:${slice.id}`, phase: 'Build', agentType: '{{PACK_PREFIX}}-test-writer', schema: SLICE_RESULT_SCHEMA, effort: 'medium' }
  )
  log(`slice ${sliceNo}/${SLICES.length}: ${slice.id} test=${result ? result.status : 'infra-failed(null)'}`)  // heartbeat

  let review = null
  if (result && result.status === 'green') {
    consecutiveFails = 0
    await safeAgent(
      `Type check of cutoff diff "${slice.title}" in ${PROJECT_DIR}, thread ${BRANCH}: drive away '{{TYPECHECK_CMD}}', classify errors, suggest minimal annotations. DO NOT change the code.
${HARD_GATES}`,
      { label: `types:${slice.id}`, phase: 'Build', agentType: '{{PACK_PREFIX}}-type-checker', model: 'sonnet', effort: 'medium' }
    )
    const risk = String(result.risk_level || RISK(slice)).toUpperCase()
    const rl = reviewLane(risk)
    const markers = (result.risk_markers || []).join(', ') || '(not specified)'
    const workarounds = (result.workarounds || []).length
      ? 'WORKBACKS IN TESTS (each is an indicator of a real defect, find out the source): ' + result.workarounds.join(' | ')
      : 'no workarounds reported in tests'
    const depth = risk === 'HIGH'
      ? 'MODE ADVERSARIAL (HIGH): list first failure-modes (racing/lost transactions/double processing/broken database invariants/is invalid auth/broken migration/external leak io), then build a specific scenario for EVERYONE (inputs + competition + status), where the diff breaks. Fresh context: judge by diff, not «polish».'
      : risk === 'MED'
      ? 'MODE MED: contracts, authorization, data integrity, transaction boundaries; conditional-checklists of the corresponding layer.'
      : 'MODE LOW: style + obvious correctness + bare except (spot-check).'
    review = await safeAgent(
      `Read-only slice review "${slice.title}" in ${PROJECT_DIR}, thread ${BRANCH}. Diff vs ${BASE} ('git diff ${BASE}...${BRANCH}').
RISK=${risk}; risk_markers: ${markers}. ${depth}
${workarounds}
Check layers (thin handler, boundary validation, service/repository), security (SQL/secrets/bare except) and acceptance_criteria: ${JSON.stringify(slice.acceptance_criteria)}.
Report ALL findings: severity ∈ {LOW,MED,HIGH,CRITICAL} + location(file:line) + failure_scenario; when in doubt, go higher, don’t filter it yourself. Drive away '{{LINT_CMD}}'. DO NOT change the files, the tree is clean.
${HARD_GATES}`,
      { label: `review:${slice.id}`, phase: 'Build', agentType: '{{PACK_PREFIX}}-reviewer', model: rl.model, effort: rl.effort }
    )
    log(`slice ${sliceNo}/${SLICES.length}: ${slice.id} review-ok (${results.filter((r) => r.status === 'green').length + 1}/${SLICES.length} green)`)
  } else {
    consecutiveFails++
  }
  results.push({ ...(result || { id: slice.id, status: 'infra-failed', risk_level: RISK(slice), summary: 'agent returned null (terminal infra-runtime failure OR agent() threw an exception - see log safeAgent)', assumptions: [], open_questions: [] }), review_findings: review })

  // Fail-fast for infra failure: agent() returned null = terminal failure (rate-limit/timeout,
  // retrays exhausted). Anything further is pointless. NOT disguised as deferred (P4). Lingering hang → supervisor.
  if (!result) {
    log(`Fail-fast: slice ${slice.id} infra-failed (agent returned null) — stop run, go to Verify/report.`)
    break
  }
}

phase('Verify')
const verify = await safeAgent(
  `Final check in ${PROJECT_DIR}, thread ${BRANCH}:
1. 'git status' — clean, thread ${BRANCH}.
2. '{{LINT_CMD}}' — clean.
3. '{{TYPECHECK_CMD}}' — 0 errors.
4. Full '{{TEST_RUNNER_CMD}}' — number/status.
Brief summary. Don't change the files, don't push.
${HARD_GATES}`,
  { label: 'final-verify', phase: 'Verify', model: 'sonnet', effort: 'medium' }
)

const built = results.map((r) => ({ id: r.id, status: r.status }))
const infraN = built.filter((b) => b.status === 'infra-failed').length
log(`Done: ${built.filter((b) => b.status === 'green').length}/${SLICES.length} green${infraN ? `, ${infraN} infra-failed (infra-failure, NOT defect - see <failures>)` : ''}. Thread ${BRANCH}, nothing is running.`)
return { branch: BRANCH, base: BASE, max: MAX, results, verify }
