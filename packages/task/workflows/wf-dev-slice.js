// Шаблон 4: dev-slice — срез → impl → tests-to-green (loop с max-iteration) → risk-адаптивное review.
// Срезы идут последовательно (каждый строится на предыдущем); правила слотов — README.md рядом.
export const meta = {
  name: 'dev-slice', // SLOT: имя под конкретный запуск
  description: 'Разработка срезами: реализация, доведение тестов до зелёного, ревью глубиной по риску среза',
  whenToUse: 'Stage разработки по готовому ТЗ/плану; запускать через scriptPath (НЕ named-workflow — args приходит строкой)',
  phases: [
    { title: 'Impl', detail: 'реализация среза + тесты', model: 'sonnet' },
    { title: 'Green', detail: 'loop: прогон тестов → фикс, до зелёного или max-iteration', model: 'sonnet' },
    { title: 'Review', detail: 'ревью диффа среза, глубина по риску', model: 'opus' },
  ],
}

// ── Конфиг (embedded, НЕ через args-строку) ──────────────────────────────────
// SLOT: пути — репозиторий и ТЗ-SSOT (абсолютные: cwd субагента сбрасывается).
// ИНВАРИАНТ: абсолютный путь обязателен — assert ловит относительный на живом прогоне,
// не срабатывает на незаполненном шаблоне (плейсхолдер `/abs/path/to/…` сам абсолютен).
const REPO = '/abs/path/to/repo'
const SPEC = '/abs/path/to/spec.md'
if (!REPO.startsWith('/')) throw new Error(`REPO должен быть абсолютным путём: "${REPO}"`)
if (!SPEC.startsWith('/')) throw new Error(`SPEC должен быть абсолютным путём: "${SPEC}"`)

// SLOT: SLICES — вертикальные срезы, последовательно. Один срез = impl + green + review + коммит.
//   brief  — ТЗ среза со ссылкой на раздел SPEC (агент читает SPEC сам);
//   tests  — команда прогона тестов среза (и есть его validation);
//   risk   — low | medium | high: определяет глубину review (см. reviewFor);
//   commit — готовый subject Conventional Commits.
// cache-bust: `agent()` кэширует по (prompt, opts) — на `resumeFromRunId` ОДНОГО среза
// без глобального инвалидатора добавь опц. поле `asOf` (дата/тег) в объект среза и подмешай
// в `label` (см. README §Общие инварианты; паттерн — roadmap-заметка dterema-p4).
const SLICES = [
  {
    key: 'slice-1',
    brief: 'Срез 1: что реализовать, границы, чего НЕ трогать (раздел N спеки).',
    tests: 'cd REPO && ./vendor/bin/pest --filter=Slice1',
    risk: 'medium',
    commit: 'feat(scope): суть среза (PLAN-ID Pn.m)',
  },
]

// SLOT: GATES — гейты между срезами; прогоняются после review КАЖДОГО среза,
// красный гейт останавливает конвейер (следующие срезы не стартуют).
// Типовое: полный тест-сьют, статанализ, commit-гейт «рабочее дерево чистое».
const GATES = ['git -C REPO status --short — пусто (всё закоммичено)']

// SLOT: max-iteration для tests-to-green loop — ОБЯЗАТЕЛЕН (агент не должен
// крутиться бесконечно, подгоняя тесты под код). Исчерпание = стоп конвейера.
const MAX_GREEN_ITERATIONS = 3

// SLOT: model/effort — impl sonnet/medium; review по риску (см. reviewFor).
const IMPL_MODEL = { model: 'sonnet', effort: 'medium' }
const GREEN_MODEL = { model: 'sonnet', effort: 'medium' }
// Risk-адаптивное review: low — self-check автора достаточен (review пропускается);
// medium — один ревьюер свежим контекстом; high — opus/xhigh (для фискалки/платежей/
// tenant-isolation дополнительно судейская панель — шаблон wf-audit-adversarial).
// guarded-optional-args: срез без `risk` не должен молча получить дешёвый review — явный
// дефолт 'medium' (typeof-guard), не голое обращение к `s.risk` (паттерн wf-agentools-drive).
const riskOf = s => typeof s.risk === 'string' ? s.risk : 'medium'
const reviewFor = risk => risk === 'high'
  ? { model: 'opus', effort: 'xhigh' }
  : { model: 'opus', effort: 'medium' }

// ── Схемы structured-summary ─────────────────────────────────────────────────
const REPORT = {
  type: 'object',
  properties: {
    files_changed: { type: 'array', items: { type: 'string' } },
    commits: { type: 'array', items: { type: 'string' } },
    tests_green: { type: 'boolean', description: 'тесты среза зелёные (exit 0)' },
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
  `Репозиторий: ${REPO}. ТЗ-SSOT: ${SPEC} — прочитай раздел своего среза прежде чем писать код.`,
  `Дисциплина: минимальный дифф под срез, чужой код не рефакторить попутно; неясность в ТЗ — в issues, не импровизировать.`,
  `Финальный текст = данные по схеме, не сообщение человеку.`,
].join('\n')

const implPrompt = s => [
  COMMON,
  s.brief,
  `Реализуй срез вместе с тестами. Прогони: ${s.tests} — доведи до зелёного в рамках среза. Тесты проверяют ПОВЕДЕНИЕ из ТЗ; подгонка assertion'ов под фактический выход кода запрещена.`,
  `Коммит: ${s.commit} (только файлы среза, git status перед add).`,
].join('\n\n')

const greenPrompt = (s, prev, iter) => [
  COMMON,
  `Тесты среза «${s.key}» не зелёные (итерация ${iter}/${MAX_GREEN_ITERATIONS}). Прогони ${s.tests}, разбери падения, почини КОД (тесты правь только если тест противоречит ТЗ — тогда фиксируй это в issues).`,
  `Отчёт предыдущей попытки: ${prev.validation}`,
  `Дофиксируй коммитом fix(scope): тесты среза ${s.key} зелёные.`,
].join('\n\n')

const reviewPrompt = s => [
  `Read-only ревью среза «${s.key}» свежим контекстом (ты НЕ автор). Репозиторий: ${REPO}; ТЗ: ${SPEC} (раздел среза). Дифф среза: git log/show по коммитам с "${s.commit.slice(0, 30)}".`,
  `Ищи: несоответствие ТЗ, correctness-дефекты с конкретным failure_scenario, подгонку тестов под код. Severity Blocker/Major/Minor/Nit. Verdict FIX_REQUIRED при любом Blocker/Major.`,
  `НИЧЕГО не правь и не коммить. Финальный текст = данные по схеме.`,
].join('\n\n')

const gatePrompt = s => [
  `Прогони гейты после среза «${s.key}» в ${REPO}: ${GATES.join('; ')}. НИЧЕГО не чини — только факты (exit-коды) и вердикт в issues, если красное. Финальный текст = данные по схеме.`,
].join('\n')

// ── Оркестрация: срезы последовательно, внутри среза — loop-until-green с потолком ──
log(`dev-slice: ${SLICES.length} срезов, max green-итераций: ${MAX_GREEN_ITERATIONS}`)

// safeAgent — try/catch над **bare** `await agent()` (вне `parallel()`/`pipeline()`, где throw
// уже ловится рантаймом и отдаёт `null`): без обёртки бросок агента роняет весь прогон.
async function safeAgent(prompt, opts) {
  try { return await agent(prompt, opts) } catch (e) { log(`agent error (${opts.label || '?'}): ${e.message || e}`); return null }
}

const done = []
for (const s of SLICES) {
  let res = await safeAgent(implPrompt(s), {
    label: `impl:${s.key}`, phase: 'Impl', ...IMPL_MODEL, schema: REPORT,
  })
  if (!res) { log(`СТОП: impl:${s.key} без результата`); break }

  // tests-to-green loop — строго ограничен max-iteration (правило README).
  let iter = 0
  while (!res.tests_green && iter < MAX_GREEN_ITERATIONS) {
    iter++
    const fix = await safeAgent(greenPrompt(s, res, iter), {
      label: `green:${s.key}#${iter}`, phase: 'Green', ...GREEN_MODEL, schema: REPORT,
    })
    if (!fix) break
    res = { ...fix, commits: [...(res.commits || []), ...(fix.commits || [])] }
  }
  if (!res.tests_green) {
    log(`СТОП: срез ${s.key} не дошёл до зелёного за ${MAX_GREEN_ITERATIONS} итераций — эскалация в main loop`)
    done.push({ key: s.key, impl: res, review: null, stopped: 'tests-not-green' })
    break
  }

  // Risk-адаптивное review: low пропускает отдельного ревьюера.
  let review = null
  if (riskOf(s) !== 'low') {
    review = await safeAgent(reviewPrompt(s), {
      label: `review:${s.key}`, phase: 'Review', ...reviewFor(riskOf(s)), schema: REVIEW_SCHEMA,
    })
    if (review && review.verdict === 'FIX_REQUIRED') {
      log(`СТОП: review среза ${s.key} = FIX_REQUIRED (${review.findings.length} наход.) — фиксы в main loop, review-фиксы отдельными коммитами`)
      done.push({ key: s.key, impl: res, review, stopped: 'review-fix-required' })
      break
    }
  }

  // Гейты между срезами.
  const gate = GATES.length
    ? await safeAgent(gatePrompt(s), { label: `gate:${s.key}`, phase: 'Impl', model: 'sonnet', effort: 'low', schema: REPORT })
    : null
  if (gate && gate.issues && gate.issues.length) {
    log(`СТОП: гейт после ${s.key} красный: ${gate.issues.join('; ')}`)
    done.push({ key: s.key, impl: res, review, stopped: 'gate-red', gate })
    break
  }

  done.push({ key: s.key, impl: res, review, stopped: null })
}

const stopped = done.find(d => d.stopped)
log(`dev-slice завершён: ${done.filter(d => !d.stopped).length}/${SLICES.length} срезов чисто${stopped ? `, стоп на ${stopped.key} (${stopped.stopped})` : ''}`)

return {
  slices: done.map(d => ({
    key: d.key, stopped: d.stopped,
    commits: (d.impl && d.impl.commits) || [],
    review_findings: (d.review && d.review.findings) || [],
    issues: (d.impl && d.impl.issues) || [],
  })),
  all_green: done.length === SLICES.length && done.every(d => !d.stopped),
}
