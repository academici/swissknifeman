// Workflow-исполнитель мастер-плана 2026.07.12-CONTEXT-ECONOMY (D14).
// Скопирован из конструктора packages/task/workflows/wf-dev-slice.js (шаблон 4: dev),
// слоты заполнены под план. Единственное расширение слот-механики (осознанное, D14):
// per-slice override модели impl (`s.impl`) — Routing плана пинит P2.1 на opus/high.
// Пролёт: P1→P5 + P7 (код в репо, автономно). СТОП-ГРАНИЦЫ (не автоматизируются):
//   • P6 (rollout) — baseline/живые сессии/per-project подтверждения Owner;
//   • P8 — P8.2 требует закрытых P6/P7, P8.4 — approve Owner на тег.
// После зелёного пролёта: человек ведёт P6 (/task:plan-exec … P6.1…P6.4), затем P8.
// Запуск СТРОГО через scriptPath (named-workflow отдаёт args строкой — known bug).
export const meta = {
  name: 'context-economy-exec',
  description: 'Исполнение плана 2026.07.12-CONTEXT-ECONOMY: P1→P5+P7 срезами, стоп перед Owner-гейтами P6/P8',
  whenToUse: 'Автономный пролёт кодовых фаз плана context-economy; запускать через scriptPath',
  phases: [
    { title: 'Impl', detail: 'исполнение item по ТЗ phases/Pn.md + коммит', model: 'sonnet' },
    { title: 'Green', detail: 'loop: прогон Validation → фикс, до зелёного или max-iteration', model: 'sonnet' },
    { title: 'Review', detail: 'ревью диффа item, глубина по риску', model: 'opus' },
  ],
}

// ── Конфиг (embedded, НЕ через args-строку) ──────────────────────────────────
const REPO = '/home/vostrikov/projects/packages/swissknifeman'
const PLAN = '2026.07.12-CONTEXT-ECONOMY'
const SPEC = `${REPO}/plans/${PLAN}`

// SLICES — items плана в порядке зависимостей (P3.1→P3.2; P5 после P1; P7 — исключение
// phase-first D14). brief отсылает к 16-полевому ТЗ item'а — агент читает phases/Pn.md сам.
// impl — override модели исполнителя (Routing плана); отсутствие = IMPL_MODEL.
// P1–P4 закрыты и закоммичены (2026-07-12, отдельная сессия) — SLICES обрезан до остатка,
// чтобы новая сессия не тратила agent()-вызовы на «уже сделано, ничего не меняю» верификацию.
// История среза — в git log (7cfa22c..cece125) и Update Log plan.md. Полный список items —
// в git-истории этого файла, если понадобится перезапуск с нуля.
// P5 ЗАКРЫТА ЦЕЛИКОМ вне workflow (2026-07-12, main loop): P5.3 gate-red — post-review фикс
// commit 92706de (trend-warn несмежные недели); P5.4 — ⛔ Skipped by decision (D7,
// Owner-подтверждение), roadmap/otel-preset.md. SLICES обрезан до P7 — не переисполнять.
const SLICES = [
  {
    key: 'P5.1',
    brief: `Item P5.1 (${SPEC}/phases/P5.md): skiller budget --first-turn — first_turn_report (skills meta + agents + CLAUDE.md + живой прогон SessionStart-хуков fail-soft/timeout + MCP-оценка), пороги 3–7K/10K, --json/--strict, ≥5 тестов на tmpdir-фикстуре.`,
    tests: `cd ${REPO} && bash packages/skiller/scripts/validate.sh`,
    risk: 'medium',
    commit: `feat(skiller): budget --first-turn — замер always-on футпринта проекта (${PLAN} P5.1)`,
  },
  {
    key: 'P5.2',
    brief: `Item P5.2 (${SPEC}/phases/P5.md): maind doctor --context — флот-агрегация subprocess'ом skiller budget --first-turn --json (без кросс-импортов, паттерн doctor --audit settings), fail-soft context·n/a, ≥3 теста (subprocess mocked).`,
    tests: `cd ${REPO} && bash packages/maind/scripts/validate.sh`,
    risk: 'low',
    commit: `feat(maind): doctor --context — футпринт первого хода по флоту (${PLAN} P5.2)`,
  },
  {
    key: 'P5.3',
    brief: `Item P5.3 (${SPEC}/phases/P5.md): run-report.py — блок usage из jsonl сессии (first_turn_overhead, суммы, turns; хук-безопасно); analyst sessions --project/--weeks — недельные медианы + тренд-warn >20% w-o-w; encoded-cwd проверить на живых каталогах, НЕ угадывать (неясно → эскалация); ≥6 тестов на синтетическом jsonl.`,
    tests: `cd ${REPO} && bash packages/analyst/scripts/validate.sh && bash packages/harness/scripts/validate.sh`,
    risk: 'medium',
    commit: `feat(analyst,harness): сессионная токен-аналитика — usage в run-report + analyst sessions (${PLAN} P5.3)`,
  },
  {
    key: 'P7.1',
    brief: `Item P7.1 (${SPEC}/phases/P7.md): scripts/bootstrap-machine.sh + роут swissknifeman setup --machine — тонкий идемпотентный оркестратор (install.sh → harness hooks/permissions --global → MCP → демон maind → doctor), --dry-run/--skip-projects; ГЕЙТ: двойной прогон на чистом окружении (второй = no-op), лог обоих в Completion Notes.`,
    tests: `cd ${REPO} && bash -n scripts/bootstrap-machine.sh && bash packages/maind/scripts/validate.sh`,
    risk: 'medium',
    commit: `feat(root): bootstrap-machine.sh — развёртывание машины одной командой (${PLAN} P7.1)`,
  },
  {
    key: 'P7.2',
    brief: `Item P7.2 (${SPEC}/phases/P7.md): манифест проектов (~/.swissknifeman/machine-manifest.json, .example в docs) + шаг --projects (clone отсутствующих + setup, идемпотентно) + doc-страница «Развёртывание: новая машина/команда» + roadmap/cross-machine-memory.md (D12: запрет shared-папки для state_store.db, 2 безопасных варианта).`,
    tests: `cd ${REPO} && bash -n scripts/bootstrap-machine.sh`,
    risk: 'low',
    commit: `feat(root): манифест проектов + доки развёртывания + roadmap межмашинной памяти (${PLAN} P7.2)`,
  },
]

// GATES — после review КАЖДОГО среза; красный гейт останавливает конвейер.
const GATES = [
  `git -C ${REPO} status --short — пусто (всё закоммичено)`,
  `python3 ${REPO}/packages/task/scripts/plan-lint.py ${SPEC} — OK (статусы/handoff обновлены plan-exec-дисциплиной)`,
]

const MAX_GREEN_ITERATIONS = 3
const GATE_ATTEMPT = 5 // бампать при ручном resume после фикса вне item'а — иначе gate-агент отдаёт кэш (P5.3 post-review фикс 92706de)

const IMPL_MODEL = { model: 'sonnet', effort: 'medium' }
const GREEN_MODEL = { model: 'sonnet', effort: 'medium' }
const reviewFor = risk => risk === 'high'
  ? { model: 'opus', effort: 'xhigh' }
  : { model: 'opus', effort: 'medium' }

// ── Схемы structured-summary ─────────────────────────────────────────────────
const REPORT = {
  type: 'object',
  properties: {
    files_changed: { type: 'array', items: { type: 'string' } },
    commits: { type: 'array', items: { type: 'string' } },
    tests_green: { type: 'boolean', description: 'Validation item зелёная (exit 0)' },
    validation: { type: 'string', description: 'команды и exit-коды' },
    issues: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string', description: 'суть сделанного, 3-5 строк' },
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
        },
        required: ['file', 'summary', 'failure_scenario', 'severity'],
      },
    },
    verdict: { type: 'string', enum: ['APPROVE', 'FIX_REQUIRED'] },
  },
  required: ['findings', 'verdict'],
}

// ── Промпты ──────────────────────────────────────────────────────────────────
const COMMON = [
  `Репозиторий: ${REPO}. Мастер-план: ${SPEC}/plan.md (D-лог — несущие решения); ТЗ item'а — его 16 полей в ${SPEC}/phases/Pn.md: Required Reads прочитай ДО кода, Implementation Rules и Code Guidance обязательны.`,
  `Дисциплина plan-exec: по завершении обнови Status item'а в phase-файле и Status Board в plan.md, допиши строку в Update Log (канон ≤2 строк), перепиши ${SPEC}/handoff.md. Незакрытый гейт item'а → статус 🟡/🔴 + Pending Work, НЕ 🟢.`,
  `Дисциплина кода: минимальный дифф под item, чужой код не рефакторить попутно; stdlib-only; неясность в ТЗ — в issues, не импровизировать.`,
  `Финальный текст = данные по схеме, не сообщение человеку.`,
].join('\n')

const implPrompt = s => [
  COMMON,
  s.brief,
  `Реализуй item вместе с тестами. Прогони: ${s.tests} — доведи до зелёного в рамках item. Тесты проверяют ПОВЕДЕНИЕ из ТЗ; подгонка assertion'ов под фактический выход кода запрещена.`,
  `Коммит: ${s.commit} (только файлы item, git status перед add).`,
].join('\n\n')

const greenPrompt = (s, prev, iter) => [
  COMMON,
  `Validation item «${s.key}» не зелёная (итерация ${iter}/${MAX_GREEN_ITERATIONS}). Прогони ${s.tests}, разбери падения, почини КОД (тесты правь только если тест противоречит ТЗ — тогда фиксируй это в issues).`,
  `Отчёт предыдущей попытки: ${prev.validation}`,
  `Дофиксируй коммитом fix: item ${s.key} зелёный.`,
].join('\n\n')

const reviewPrompt = s => [
  `Read-only ревью item «${s.key}» свежим контекстом (ты НЕ автор). Репозиторий: ${REPO}; ТЗ: ${SPEC}/phases/ (16 полей item — сверь Scope/Implementation Rules/Code Guidance/Validation). Дифф: git log/show по коммитам с "${s.commit.slice(0, 40)}".`,
  `Ищи: несоответствие ТЗ, correctness-дефекты с конкретным failure_scenario, подгонку тестов под код, нарушение рамок репо (stdlib-only, дубли примитивов вне core/). Severity Blocker/Major/Minor/Nit. Verdict FIX_REQUIRED при любом Blocker/Major.`,
  `НИЧЕГО не правь и не коммить. Финальный текст = данные по схеме.`,
].join('\n\n')

const gatePrompt = s => [
  `[попытка ${GATE_ATTEMPT}] Прогони гейты СЕЙЧАС, свежий git-статус (не полагайся на прошлые прогоны), после item «${s.key}» в ${REPO}: ${GATES.join('; ')}. НИЧЕГО не чини — только факты (exit-коды).`,
  `tests_green = ОБА гейта завершились exit 0 (даже если stdout содержит непустые WARN). issues — ТОЛЬКО блокирующие ошибки (exit≠0, ERROR); неблокирующие WARN/заметки в issues НЕ класть — упомяни их в summary. Финальный текст = данные по схеме.`,
].join('\n')

// ── Оркестрация: items последовательно, внутри — loop-until-green с потолком ──
log(`${PLAN}: автономный пролёт ${SLICES.length} items (P1→P5 + P7); стоп-границы: P6 и P8 — Owner-гейты`)

const done = []
for (const s of SLICES) {
  let res = await agent(implPrompt(s), {
    label: `impl:${s.key}`, phase: 'Impl', ...(s.impl || IMPL_MODEL), schema: REPORT,
  })
  if (!res) { log(`СТОП: impl:${s.key} без результата`); break }

  let iter = 0
  while (!res.tests_green && iter < MAX_GREEN_ITERATIONS) {
    iter++
    const fix = await agent(greenPrompt(s, res, iter), {
      label: `green:${s.key}#${iter}`, phase: 'Green', ...GREEN_MODEL, schema: REPORT,
    })
    if (!fix) break
    res = { ...fix, commits: [...(res.commits || []), ...(fix.commits || [])] }
  }
  if (!res.tests_green) {
    log(`СТОП: item ${s.key} не дошёл до зелёного за ${MAX_GREEN_ITERATIONS} итераций — эскалация в main loop`)
    done.push({ key: s.key, impl: res, review: null, stopped: 'tests-not-green' })
    break
  }

  let review = null
  if (s.risk !== 'low') {
    review = await agent(reviewPrompt(s), {
      label: `review:${s.key}`, phase: 'Review', ...reviewFor(s.risk), schema: REVIEW_SCHEMA,
    })
    if (review && review.verdict === 'FIX_REQUIRED') {
      log(`СТОП: review item ${s.key} = FIX_REQUIRED (${review.findings.length} наход.) — фиксы в main loop, review-фиксы отдельными коммитами`)
      done.push({ key: s.key, impl: res, review, stopped: 'review-fix-required' })
      break
    }
  }

  const gate = GATES.length
    ? await agent(gatePrompt(s), { label: `gate:${s.key}`, phase: 'Impl', model: 'sonnet', effort: 'low', schema: REPORT })
    : null
  if (gate && gate.issues && gate.issues.length) {
    log(`СТОП: гейт после ${s.key} красный: ${gate.issues.join('; ')}`)
    done.push({ key: s.key, impl: res, review, stopped: 'gate-red', gate })
    break
  }

  done.push({ key: s.key, impl: res, review, stopped: null })
}

const stopped = done.find(d => d.stopped)
log(`Пролёт завершён: ${done.filter(d => !d.stopped).length}/${SLICES.length} items чисто${stopped ? `, стоп на ${stopped.key} (${stopped.stopped})` : ''}`)
if (!stopped && done.length === SLICES.length) {
  log(`Дальше ЧЕЛОВЕК: P6 (baseline → sync-волны → бакеты с Owner → after-замер) через /task:plan-exec ${PLAN} P6.1…P6.4, затем P8 (доктрина+скиллы/доки+релиз, тег — approve Owner)`)
}

return {
  slices: done.map(d => ({
    key: d.key, stopped: d.stopped,
    commits: (d.impl && d.impl.commits) || [],
    review_findings: (d.review && d.review.findings) || [],
    issues: (d.impl && d.impl.issues) || [],
  })),
  all_green: done.length === SLICES.length && done.every(d => !d.stopped),
  next_human_steps: (done.length === SLICES.length && done.every(d => !d.stopped))
    ? [`/task:plan-exec ${PLAN} P6.1 (baseline)`, 'P6.2 sync-волны', 'P6.3 бакеты (AskUserQuestion Owner)', 'P6.4 after-замер', 'P8.1–P8.4 (тег — approve Owner)']
    : ['разобрать stopped-item в main loop, перезапустить workflow с resumeFromRunId'],
}
