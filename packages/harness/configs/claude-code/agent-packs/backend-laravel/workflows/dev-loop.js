export const meta = {
  name: '{{PACK_PREFIX}}-dev-loop',
  description: 'Implements a list backend-slices {{PACK_PREFIX}} sequentially on ONE branch: for each slice impl ({{PACK_PREFIX}}-slice-builder) → tests-to-green ({{PACK_PREFIX}}-test-writer) → review-gate ({{PACK_PREFIX}}-reviewer). Lessons overnight-protection run: one branch on the run, hard-cap cuts are experiencing resume, circuit-breaker. The scope of slices is decided by a person and transmitted via args.',
  phases: [
    { title: 'Setup', detail: 'pure tree + one feature-thread from base (NOT per-slice branches)' },
    { title: 'Build', detail: 'by slice sequentially: impl → tests-to-green → review-gate' },
    { title: 'Verify', detail: 'full suite + pint + report' },
  ],
}

// ---------------------------------------------------------------------------
// Login (args):
//   { branch: 'feat/...', base?: 'main', max_slices?: 3,
//     slices: [ { id, title, domain, goal, surface?, acceptance_criteria, skills? } ] }
// Scope (what slices and in what order) is decided by a person before launch - this workflow
// performs, and does not invent product volume.
// ---------------------------------------------------------------------------

const PROJECT_DIR = '{{PROJECT_DIR}}'

// Lesson overnight-run: hardcap MUST survive resume. args on resume may not
// fly → default we keep the literal IN THE SCRIPT, and not just in args.
// Lesson throttling: batch = N slices × (impl+test+review) — big batch multiplies
// retry-surface under rate-limit. Default 2 (not 3+); solo-fallback — orchestrator discipline.
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
const BASE = (args && args.base) || 'main'
const MAX = (args && args.max_slices) || DEFAULT_MAX
const ALL_SLICES = (args && Array.isArray(args.slices)) ? args.slices : []

// Lesson: one branch for the entire run. We apply the cap HERE (slice), and not through
// optional arg inside agents.
const SLICES = ALL_SLICES.slice(0, MAX)

const HARD_GATES = `HARD GATES {{PACK_PREFIX}} (do not violate):
- PHP/tests ONLY via '{{PHP_RUNNER}}' ({{TEST_RUNNER_CMD}}), not bare 'php'.
- If .env is locked with a hook - do not read or edit; test database config in phpunit.xml/tests/bootstrap.php ({{TEST_DB}}).
- Project test framework - {{TEST_FRAMEWORK}}: mirrors the style of existing tests. <!-- pack:if SCAFFOLDS_SCHEMA -->Backwaters of missing migrations/models on demand slice.<!-- pack:endif --><!-- pack:ifnot SCAFFOLDS_SCHEMA -->Scheme/change migrations only if the slice requires it.<!-- pack:endif --> Static check (if configured) — {{CHECK_CMD}}.
- NOT git push, DO NOT open/flicker PR, NOT release. NOT migrate:fresh/drop for anything other than the test database.
- .claude/agents|workflows|hooks with generated-header DO NOT edit - overrides in .claude/rules/*-overrides.md.
- All cuts are built on ONE branch ${BRANCH}. Agents DO NOT create or switch branches - they commit to the current one and leave the tree clean.
- Work strictly inside ${PROJECT_DIR}.`

if (SLICES.length === 0) {
  log('No input cuts (args.slices empty) — STOP. Pass on { branch, base, max_slices, slices: [...] } via scriptPath (embedded args), not named-workflow.')
  return { built: [], note: 'no slices provided' }
}

// Lesson overnight-run (azguard, plan-remainder): agent({schema}) may not return null,
// a THROW exception ('subagent completed without calling StructuredOutput' — subagent not
// called StructuredOutput even after the prompt). Without wrapper throw floated to the top and dropped
// WHOLE workflow (lost progress after the crash point). safeAgent reduces throw to null —
// the standard degradation continues to work if(!result)/circuit-breaker, without rewriting anything.
async function safeAgent(prompt, opts) {
  try {
    return await agent(prompt, opts)
  } catch (e) {
    const label = (opts && opts.label) || '?'
    log(`agent ${label} threw an exception (${String((e && e.message) || e).slice(0, 160)}) — infra-failed, continue`)
    return null
  }
}

// ---------------------------------------------------------------------------
phase('Setup')

// Single agent establishes branch: pure tree → thread from base (create or
// switch). Then NOBODY touches the branch.
await safeAgent(
  `B ${PROJECT_DIR} prepare a working branch and check the environment BEFORE distributing slices.
1. 'git status' — if the tree is dirty, stop and report (DO NOT overwrite other people's edits).
2. ENV-PREFLIGHT (environment blocker ≠ code bug): '{{PHP_RUNNER}} -v' (version); '{{PHP_RUNNER}} -r "print_r(PDO::getAvailableDrivers());"' — the required database driver is present; trial '{{TEST_RUNNER_CMD}} --filter=__preflight_nonexistent__' does not crash with environment fatality. Driver/version/config broken → STOP the run and report (chatom F3: php without worker pdo_sqlite popped up only on the first DB-test).
3. Thread: if ${BRANCH} exists - 'git checkout ${BRANCH}'. Otherwise 'git checkout ${BASE}' then 'git checkout -b ${BRANCH}'.
4. Confirm: environment ok, current branch = ${BRANCH}, tree is clean, last commit (subject).
NOT push, DO NOT delete branches.
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
    status: { type: 'string', enum: ['green', 'deferred', 'failed', 'infra-failed'], description: 'green=tests green; deferred=honestly not green (real defect); failed=agent reported failure; infra-failed=infra failure (rate-limit/timeout/agent returned null) — DO NOT disguise as deferred' },
    risk_level: { type: 'string', enum: ['LOW', 'MED', 'HIGH'], description: 'blast-radius slice (see risk_markers)' },
    risk_markers: { type: 'array', items: { type: 'string', enum: ['concurrency', 'transactions', 'data-integrity', 'queue-semantics', 'connectors'] }, description: 'what risk classes are affected by the cut' },
    summary: { type: 'string' },
    files_changed: { type: 'array', items: { type: 'string' } },
    tests_added: { type: 'array', items: { type: 'string' } },
    test_output: { type: 'string', description: 'final line {{TEST_RUNNER_CMD}}' },
    test_coverage_pct: { type: 'number', description: 'coverage of changed behavior, % (rating)' },
    workarounds: { type: 'array', items: { type: 'string' }, description: 'workarounds/force configs for the sake of green - each = [POSSIBLE-DEFECT] for reviewer' },
    tool_failures: { type: 'array', items: { type: 'string' }, description: 'engine/tool was not available when checking an external fact (perplexity-web locked/TIMEOUT, context7 empty, MCP lay down) → the fact remains unverified, a REPEATE PASS is needed. DO NOT guess, DO NOT mask' },
    assumptions: { type: 'array', items: { type: 'string' }, description: 'solutions where the technical specifications were silent' },
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
  // Durable-progress = number green-slices (not in the sandbox shell → not git rev-list).
  // Lingering hang one agent() is NOT caught here (control did not return) — is a concern
  // external supervisor (orchestrator report ~30 min + PushNotification, see orchestrator.md).
  if (consecutiveFails >= 2) {
    log(`Circuit-breaker: ${consecutiveFails} cuts in a row didn't reach the green - stop, I'm going to Verify/report.`)
    break
  }

  const extraSkills = (slice.skills || []).join(', ') || '(no additional)'
  const lane = implLane(slice)
  // Durable-light handover: compact summaries of past slices (Schema fields ONLY, not transcripts).
  const priorSummary = results.length
    ? 'Past slices (summary): ' + results.map((r) => `${r.id}=${r.status}/${r.risk_level || '?'} — ${r.summary || ''}`).join(' | ')
    : '(this is the first slice)'

  // 1) Implementation of a cut to the current branch ({{PACK_PREFIX}}-slice-builder; model/effort — by shear risk).
  await safeAgent(
    `Implement ONE backend-slice {{PACK_PREFIX}} in the current thread ${BRANCH}.

CUT:
${JSON.stringify(slice, null, 2)}

${priorSummary}

In addition to the preloaded skills, load and apply: ${extraSkills}.
Build a thin full path (route → controller/Action → DTO/Resource → policy if necessary) according to canon access-layer. DO NOT write tests - the next agent writes them. Commit to the current branch, leave the tree clean.
${HARD_GATES}`,
    { label: `impl:${slice.id}`, phase: 'Build', agentType: '{{PACK_PREFIX}}-slice-builder', model: lane.model, effort: lane.effort }
  )
  log(`slice ${sliceNo}/${SLICES.length}: ${slice.id} impl-ok`)  // heartbeat: liveliness for supervisor/person

  // 2) Tests to green (or pure deferment). Test-writer ASSESSES risk and HONESTLY reports workarounds.
  const result = await safeAgent(
    `You're in the current thread ${BRANCH} in ${PROJECT_DIR}; slice is already implemented:
${JSON.stringify(slice, null, 2)}

Write tests ({{TEST_FRAMEWORK}}), proving acceptance_criteria, and iterate '{{TEST_RUNNER_CMD}}' to GREEN.
- Green → commit tests to ${BRANCH}, status='green', fill in test_output with the final line.
- Didn't reach green honestly → DO NOT weaken the tests: leave the tree clean, status='deferred', explain in summary+open_questions (implementation remains in ${BRANCH}).
MUST be completed risk_level (LOW|MED|HIGH) and risk_markers (concurrency/transactions/data-integrity/queue-semantics/connectors) — rate blast-radius slice; test_coverage_pct — behavior change coverage assessment.
HONESTY (critical): any workaround/force config for green (force config(...), stamping timestamp before pagination, sibling-class bypass final) put in workarounds like [POSSIBLE-DEFECT] — behind the workaround is almost always a real bug. ShouldQueue-job: if the test calls handle() directly - enter it in open_questions «queue-semantics (release/backoff/competitive workers) not covered». If to check an external fact (version/API libraries, package behavior) engine was unavailable (perplexity-web locked/TIMEOUT, context7 empty) — put in tool_failures, DO NOT guess: the fact is unverified, a REPEATE is required.
Always leave the tree CLEAN. Record your assumptions. Print
EMERGENCY PATH (if strict return scheme 5× cannot be filled - do not disrupt the run): as the last line of the response exactly '===SLICE-RESULT=== status=green' or '===SLICE-RESULT=== status=deferred'; commit discipline is the same.
${HARD_GATES}`,
    { label: `test:${slice.id}`, phase: 'Build', agentType: '{{PACK_PREFIX}}-test-writer', schema: SLICE_RESULT_SCHEMA, effort: 'medium' }
  )
  log(`slice ${sliceNo}/${SLICES.length}: ${slice.id} test=${result ? result.status : 'infra-failed(null)'}`)  // heartbeat

  // 3) Risk-adaptive review-gate only on green ones. Depth/model/effort — at RISK (not true to size).
  let review = null
  if (result && result.status === 'green') {
    consecutiveFails = 0
    const risk = String(result.risk_level || RISK(slice)).toUpperCase()
    const rl = reviewLane(risk)
    const markers = (result.risk_markers || []).join(', ') || '(not specified)'
    const workarounds = (result.workarounds || []).length
      ? 'WORKBACKS IN TESTS (each is an indicator of a real defect, find out the source): ' + result.workarounds.join(' | ')
      : 'no workarounds reported in tests'
    const depth = risk === 'HIGH'
      ? 'MODE ADVERSARIAL (HIGH): list first failure-modes (racing/lost retry/double processing/violated invariants/is invalid auth/broken config-default), then build a specific scenario for EVERYONE (inputs + competition + status), where the diff breaks. Fresh context: judge by diff, not «polish».'
      : risk === 'MED'
      ? 'MODE MED: contracts, authorization, integrity; conditional-checklists of the corresponding layer.'
      : 'MODE LOW: style + N+1 + obvious correctness (spot-check).'
    review = await safeAgent(
      `Read-only slice review "${slice.title}" in ${PROJECT_DIR}, thread ${BRANCH}. Diff vs ${BASE} ('git diff ${BASE}...${BRANCH}').
RISK=${risk}; risk_markers: ${markers}. ${depth}
${workarounds}
Check canon access-layer (grep ::query/::create/::where/::all/::find by domain controllers - empty), correctness, authorization and acceptance_criteria: ${JSON.stringify(slice.acceptance_criteria)}.
Report ALL findings: severity ∈ {LOW,MED,HIGH,CRITICAL} + location(file:line) + failure_scenario; when in doubt - higher, do not filter yourself (filtering/merge — by packet gates). Drive away {{CHECK_CMD}} on modified files and '{{TEST_RUNNER_CMD}} --filter=${slice.domain || ''}'. DO NOT change the files, the tree is clean.
${HARD_GATES}`,
      { label: `review:${slice.id}`, phase: 'Build', agentType: '{{PACK_PREFIX}}-reviewer', model: rl.model, effort: rl.effort }
    )
    log(`slice ${sliceNo}/${SLICES.length}: ${slice.id} review-ok (${results.filter((r) => r.status === 'green').length + 1}/${SLICES.length} green)`)
  } else {
    consecutiveFails++
  }

  results.push({ ...(result || { id: slice.id, status: 'infra-failed', risk_level: RISK(slice), summary: 'agent returned null (terminal infra-runtime failure OR agent() threw an exception - see log safeAgent)', assumptions: [], open_questions: [] }), review_findings: review })

  // Fail-fast for infra failure: agent() returned null = terminal runtime failure (rate-limit/
  // timeout, retrays exhausted). Further is pointless - throttling itself will not go away from the transition
  // to the next slice. NOT disguised as deferred (P4). Lingering hang (without null) catches supervisor.
  if (!result) {
    log(`Fail-fast: slice ${slice.id} infra-failed (agent returned null) — stop run, go to Verify/report.`)
    break
  }
}

// ---------------------------------------------------------------------------
phase('Verify')

const verify = await safeAgent(
  `Final check of the run in ${PROJECT_DIR}, thread ${BRANCH}:
1. 'git status' — tree clean, current branch ${BRANCH}.
2. grep -rnE '::query\\(|::create\\(|::where\\(|::all\\(|::find\\(' by {{ACCESS_ROOT}}/Http/Controllers and {{ACCESS_ROOT}}/Actions — list remaining hits (in controllers should be 0).
3. Full '{{TEST_RUNNER_CMD}}' — number/status.
4. 'vendor/bin/pint --test' — clean.
Brief summary: is the access layer clean, tests (number/fell), what's left. Don't change the files, don't push.
${HARD_GATES}`,
  { label: 'final-verify', phase: 'Verify', effort: 'high' }
)

const built = results.map((r) => ({ id: r.id, status: r.status }))
const infraN = built.filter((b) => b.status === 'infra-failed').length
const toolFailN = results.reduce((n, r) => n + ((r.tool_failures || []).length), 0)
log(`Done: ${built.filter((b) => b.status === 'green').length}/${SLICES.length} green${infraN ? `, ${infraN} infra-failed (infra-failure, NOT defect - see <failures>)` : ''}${toolFailN ? `, ${toolFailN} tool_failures (engine was unavailable → fact unverified, REPEATE PASS is required)` : ''}. Cap MAX=${MAX}, thread ${BRANCH} (off ${BASE}). Nothing is running.`)

return { branch: BRANCH, base: BASE, max: MAX, results, verify }
