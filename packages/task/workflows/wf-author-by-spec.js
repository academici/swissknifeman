// Template 2: author-by-spec — spec → N file jobs × author → self-check (pipeline, without barrier).
// Prototype: working script ECOSYSTEM P5 (wf-p5-author.js). Slot Rules - README.md nearby.
export const meta = {
  name: 'author-by-spec', // SLOT: name for a specific launch
  description: 'Authoring by spec-SSOT: parallel file jobs + self-check of each result',
  whenToUse: 'Stage authoring after the finished spec; run through scriptPath (NOT named-workflow — args comes as a string)',
  phases: [
    { title: 'Author', detail: 'file jobs in parallel on the spec', model: 'sonnet' },
    { title: 'Self-check', detail: 'checking the result with the spec + validation', model: 'sonnet' },
  ],
}

// ── Config (embedded, NOT via args-line) ──────────────────────────────────
// SLOT: paths - repository-target and spec-SSOT (absolute: cwd subagent is reset).
// INVARIANT: absolute path is required - assert catches relative on a live run,
// does not fire on an empty template (placeholder `/abs/path/to/…` itself is absolute).
const REPO = '/abs/path/to/repo'
const SPEC = '/abs/path/to/spec.md'
if (!REPO.startsWith('/')) throw new Error(`REPO must be an absolute path: "${REPO}"`)
if (!SPEC.startsWith('/')) throw new Error(`SPEC must be an absolute path: "${SPEC}"`)

// SLOT: FILES — file jobs. One task = one agent = one commit.
//   files      — which files are edited/creates (discipline: ONLY them);
//   brief      — dense technical specification with reference to the spec block (the agent must read the spec himself);
//   validation — command/grep, which agent AND self-check check the result;
//   commit     — ready subject Conventional Commits (agent does not compose his).
// cache-bust: `agent()` caches by (prompt, opts) — on `resumeFromRunId` ONE job
// without global invalidator add opt. field `asOf` (date/tag) into the job object and mix
// in `label` (see README §General invariants; pattern - roadmap-note dterema-p4).
const FILES = [
  {
    key: 'block-1',
    files: ['path/inside/repo/file.md'],
    brief: 'TASK (block N specs): what to do, boundaries, what NOT to touch.',
    validation: 'grep -c "marker" path/inside/repo/file.md — pending ≥1',
    commit: 'feat(scope): essence (PLAN-ID block N)',
  },
]

// SLOT: pipeline commands - mandatory runs after editing (empty if not present).
// Example swissknifeman: check-translations.sh --stamp → skiller registry → validate.sh.
// guarded-optional-args: empty array - obvious default «no pipeline» (see `CONVEYOR.length ?
// … : null` below), not skipping a check - a pattern from `wf-agentools-drive` (cross-ref, do not vendor).
const CONVEYOR = []

// SLOT: model/effort — authoring usually sonnet/medium, self-check sonnet/low.
const AUTHOR_MODEL = { model: 'sonnet', effort: 'medium' }
const CHECK_MODEL = { model: 'sonnet', effort: 'low' }

// ── Schema structured-summary (single for author and self-check) ────────────────
const REPORT = {
  type: 'object',
  properties: {
    files_changed: { type: 'array', items: { type: 'string' } },
    commits: { type: 'array', items: { type: 'string' }, description: 'sha + subject of each commit; empty if commits are disabled' },
    validation: { type: 'string', description: 'that I ran and the results (exit-codes, greps)' },
    issues: { type: 'array', items: { type: 'string' }, description: 'which failed / deviations from specification with reason' },
    summary: { type: 'string', description: 'essence of what was done, 3-5 lines' },
  },
  required: ['files_changed', 'commits', 'validation', 'issues', 'summary'],
}

// General discipline of all author-agents - do not spread over brief'am.
const COMMON = [
  `Repository: ${REPO}. Speca-SSOT: read ${SPEC} ENTIRELY before editing.`,
  `Discipline: edit ONLY the files of your assignment; style - like the adjacent text of the file; do not invent anything beyond the specification - fix ambiguity in issues, don't improvise.`,
  `Commits: your files are a separate commit with a given subject (body - why, 1-3 lines). Before commit git status — DO NOT add other people's files (git add only your paths).`,
  `Final text = data according to the scheme, not a message to the person.`,
].join('\n')

function authorPrompt(f) {
  return [
    COMMON,
    f.brief,
    `Job files: ${f.files.join(', ')}`,
    CONVEYOR.length ? `Conveyor after editing (mandatory, in order): ${CONVEYOR.join(' → ')}` : null,
    `Pre-commit self-test: ${f.validation}`,
    `Commit: ${f.commit}`,
  ].filter(Boolean).join('\n\n')
}

function checkPrompt(f, res) {
  return [
    `Self-check jobs «${f.key}» fresh context (you are NOT the author). Repository: ${REPO}, spec: ${SPEC} — read the task block in the spec and the files themselves: ${f.files.join(', ')}.`,
    `Author's report: ${res.summary}\nReported commits: ${(res.commits || []).join('; ') || '—'}`,
    `Check: (1) the result corresponds to the spec block - nothing was thrown out or made up; (2) validation is really green - run it yourself: ${f.validation}; (3) commit contains only job files (git show --stat).`,
    `Don't edit or commit ANYTHING - just a verdict. Discrepancies - in issues (empty array = clean). Final text = schema data.`,
  ].join('\n\n')
}

// ── Orchestration: pipeline without barrier - self-check starts immediately after authoring the file ──
log(`author-by-spec: ${FILES.length} spec jobs ${SPEC}`)

const results = await pipeline(
  FILES,
  f => agent(authorPrompt(f), {
    label: `author:${f.key}`, phase: 'Author',
    ...AUTHOR_MODEL, schema: REPORT,
  }),
  (res, f) => {
    if (!res) return null
    return agent(checkPrompt(f, res), {
      label: `check:${f.key}`, phase: 'Self-check',
      ...CHECK_MODEL, schema: REPORT,
    }).then(chk => ({ key: f.key, author: res, check: chk }))
  }
)

const ok = results.filter(Boolean)
const failed = FILES.filter(f => !ok.some(r => r.key === f.key)).map(f => f.key)
const issues = ok.flatMap(r => [...(r.author.issues || []), ...((r.check && r.check.issues) || [])])
if (failed.length) log(`WARNING: tasks without result (rebuild to main loop): ${failed.join(', ')}`)
if (issues.length) log(`issues based on the results self-check: ${issues.length}`)

return {
  done: ok.map(r => ({ key: r.key, commits: r.author.commits, check_issues: (r.check && r.check.issues) || [] })),
  failed,
  issues,
}
