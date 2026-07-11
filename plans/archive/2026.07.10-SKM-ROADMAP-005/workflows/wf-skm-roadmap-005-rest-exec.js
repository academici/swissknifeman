export const meta = {
  name: 'wf-skm-roadmap-005-rest-exec',
  description: 'Исполнить фазы P3→P6 плана SKM-ROADMAP-005 серийно, phase-first: per-item exec→validate→commit-гейт→review→fix + phase-close. P6.4 (тайм-гейт D41) и P7 (интервью D7) НЕ исполняются.',
  whenToUse: 'Ночной прогон после детального дизайна P3-P6 (DoR пройден). Строго серийно (общие plan.md/plan_lint/скиллы), стоп на escalation/провале гейта.',
  phases: [
    { title: 'P3 workflow-craft', detail: 'скилл + команда make-workflow + ревьюер (P3.3/P3.4 opus)' },
    { title: 'P4 канон планов', detail: 'plan-protocol + plan_lint (публичный контракт, opus)' },
    { title: 'P5 changelog-discipline', detail: 'release-engineering + commit-гейт + skm release' },
    { title: 'P6 ecosystem-glossary', detail: 'domain-modeling + Glossary-impact + term-index (P6.4 SKIP)' },
  ],
}

const PLAN = 'SKM-ROADMAP-005'
const PD = `plans/${PLAN}`

// Дефолт роутинга — sonnet/medium (plan.md 3). Отклонения (opus/high) — по Routing-строкам.
// review — risk-адаптивно: публичный контракт/opus-item судит opus/high, остальное sonnet/high.
const S = { model: 'sonnet', effort: 'medium', review: 'sonnet', reviewEffort: 'high' }
const O = { model: 'opus', effort: 'high', review: 'opus', reviewEffort: 'high' }

const PHASES = [
  { key: 'P3', phase: 'P3 workflow-craft', items: [
    { id: 'P3.1', ...S, risk: 'скилл-указатель: двуязычная модель SKILL.ru.md→regen, description-триггер матчит свободные формулировки, НЕ копия шаблонов' },
    { id: 'P3.2', ...S, risk: 'править ТОЛЬКО поверхности с упоминанием workflow (греп); не менять model/effort frontmatter' },
    { id: 'P3.3', ...O, risk: 'команда-гейт opus/high: интервью по spec-interview, генерация=копия шаблона+слоты, не кодогенератор' },
    { id: 'P3.4', ...O, risk: 'выходной СТАТИЧЕСКИЙ ревьюер (не исполняет скрипт); критерии=зеркало README конструктора; RED блокирует выдачу' },
    { id: 'P3.5', ...S, risk: 'разведение design-only vs dev; эталоны — cross-ref по пути vault (НЕ вендорить); roadmap/README только ч.1 внедрена' },
  ]},
  { key: 'P4', phase: 'P4 канон планов', items: [
    { id: 'P4.1', ...O, risk: 'ПУБЛИЧНЫЙ контракт plan-protocol: Home-дефолт + visibility + supersedes; SKILL.ru.md→regen; back-compat' },
    { id: 'P4.2', ...O, risk: 'ПУБЛИЧНЫЙ контракт: раздел plans/<ID>/workflows/ + канон имён; SKILL.ru.md→regen синхронно с plan_lint' },
    { id: 'P4.3', ...O, risk: 'ВАЛИДАТОР plan_lint: regex ID (union, D24) + место/имя скрипта + supersedes — ВСЕ warning-only; back-compat (plan-lint plans/ зелёный ПОСЛЕ правки)' },
    { id: 'P4.4', ...O, risk: 'новая скилл-карта ecosystem-map в бакете axioma (D26), ≤50 строк, двуязычная; registry regen' },
    { id: 'P4.5', ...S, risk: 'правка ДВУХ CLAUDE.md (vault §8 + корневой), merge-only; провижионер во флот — ВНЕ scope (D30)' },
    { id: 'P4.6', ...O, risk: 'DoR-клауза workflow-как-готовность УСЛОВНА (D29): только фазы с заявленной оркестрацией; не сломать SKM-ROADMAP-005' },
  ]},
  { key: 'P5', phase: 'P5 changelog-discipline', items: [
    { id: 'P5.1', ...S, risk: 'секция повседневной дисциплины в release-engineering (SKILL.ru.md→regen); пакеты vs проекты; major всегда вручную' },
    { id: 'P5.2', ...S, rag: true, risk: 'opt-in PreToolUse-хук changelog-gate (D32/D33): warning В КОНТЕКСТ, НЕ блок; hook-API верифицировать RAG (routing P5.2, UNVERIFIED)' },
    { id: 'P5.3', ...S, risk: 'опц. skiller release (D34): umbrella-тег vX.Y.Z, major НЕ выводит, авто-push НЕ делает; тест на tmp-фикстуре CHANGELOG' },
  ]},
  { key: 'P6', phase: 'P6 ecosystem-glossary', items: [
    { id: 'P6.1', ...S, risk: 'domain-modeling: секция Conformance, Rule of Two + формат строки — SSOT одного места (D42); SKILL.ru.md→regen' },
    { id: 'P6.2', ...S, risk: 'строка «Glossary impact?» в 5 reviewer.md ВНЕ shared-регионов (D43, иначе test_agentpacks_shared покраснеет) + измерение conformance-finder Stage B' },
    { id: 'P6.3', ...S, risk: 'скилл axioma/axioma-glossary (D39, requires domain-modeling) + каркас Ecosystem_Glossary.md в Brain (D38, пустая таблица)' },
    // P6.4 — НЕ исполняется: тайм-гейт D41 (наполнение после dev-волны ECOSYSTEM P4), остаётся ⬜.
  ]},
]

const EXEC_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['status', 'committed', 'validate_green', 'summary', 'commits', 'escalation'],
  properties: {
    status: { type: 'string', enum: ['done', 'done_with_deviations', 'blocked'] },
    committed: { type: 'boolean' }, validate_green: { type: 'boolean' },
    summary: { type: 'string' }, commits: { type: 'array', items: { type: 'string' } },
    escalation: { type: 'string' },
  },
}
const REVIEW_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['verdict', 'blockers', 'notes'],
  properties: { verdict: { type: 'string', enum: ['GREEN', 'ATTENTION', 'RED'] }, blockers: { type: 'array', items: { type: 'string' } }, notes: { type: 'string' } },
}

const reads = k => `${PD}/plan.md (Meta, раздел 3 Routing, раздел 5 Decision Log) · ${PD}/phases/${k}.md (ТЗ фазы)`

function execPrompt(it, k) {
  return [
    `Ты package-implementer. Исполни item ${it.id} мастер-плана ${PLAN} СТРОГО по его ТЗ.`,
    ``,
    `Cold-start reads (ПЕРЕД работой): ${reads(k)}. В phases/${k}.md найди раздел "### ${it.id}" и следуй ВСЕМ 16 полям — особенно Required Reads (прочитай их), Implementation Rules, Code Guidance (запреты, обязательные тесты, if-then), Validation. Обоснования-решения — в plan.md раздел 5 (D-лог).`,
    ``,
    `ЖЁСТКИЕ РАМКИ:`,
    `- stdlib-only во всём python; сообщения на русском (writing-style).`,
    `- Правка ЛЮБОГО скилла — двуязычная модель: источник SKILL.ru.md, SKILL.md РЕГЕНЕРИРУЕТСЯ из RU (ручная правка только SKILL.md = дефект). Новый скилл → полный frontmatter + проверка на пересечение + regen + "skiller registry".`,
    `- ВНИМАНИЕ: CHANGELOG.md ЗАБЛОКИРОВАН permission-deny этой среды (Read/Bash по пути CHANGELOG.md отклоняются харнесом). НЕ пытайся читать/писать реальный корневой CHANGELOG.md — деливери "строка [Unreleased]" вынеси в Pending Work item'а с этой причиной (прецедент P2.4). Тулинг, оперирующий changelog (P5.2/P5.3), тестируй на tmp-ФИКСТУРЕ, не на реальном файле.`,
    `- Дом движков: P3 скилл — бакет general skiller + команда packages/task/commands/; P4 — plan-protocol (skiller general) + plan_lint (packages/task/lib); P5 — release-engineering скилл + харнес-хук (packages/harness) + skiller release; P6 — domain-modeling/axioma скиллы + reviewer.md паков (packages/harness) + Brain vault.`,
    ``,
    `КОММИТ-ГЕЙТ (plan-protocol §6) — обязателен для done/done_with_deviations:`,
    `1. Код + тесты из Code Guidance. 2. Прогони Validation item'а; validate.sh затронутых пакетов + (если правился план) "plan-lint plans/${PLAN}" ДОЛЖНЫ быть зелёными ДО коммита. 3. Коммить атомарно, Conventional Commits на русском, тело завершай: Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>. 4. Дифф Scope закоммичен, git status чистый по затронутым; дифф вне Scope → Pending Work. 5. Обнови phases/${k}.md (Phase Status + поле Status) и Status Board plan.md (строка ${k}) на done + Completion Notes. 6. Строку в plan.md раздел 6 Update Log — КРАТКО (≤2 строк, канон "${it.id} закрыт: <1 строка сути> — детали см. phases/${k}.md ${it.id} Completion Notes"), НЕ пересказ.`,
    ``,
    `ЭСКАЛАЦИЯ (plan-protocol §10): триггер (multi-package refactoring / unclear architecture / public contract·SemVer / protected assets / rule conflict / unclear acceptance) — НЕ импровизируй. ${it.id.startsWith('P4') ? 'P4 правит ПУБЛИЧНЫЙ контракт протокола: если правка plan_lint/plan-protocol ломает back-compat (ERROR на живом плане) или требует решения вне D24–D31 — ' : ''}Status Blocked, blockquote "> ESCALATION ${it.id}: <причина> | trigger: <enum>", верни status=blocked+escalation, НЕ коммить полуфабрикат.`,
    it.rag ? `\nRAG: несущий внешний факт (hook-API Claude Code) верифицируй ДО фиксации — context7/perplexity-web/claude-code-guide (ты НЕ параллелишь, лестница доступна); UNVERIFIED сними или оставь честно.` : ``,
    `Риск среза: ${it.risk}.`,
    `Верни СТРОГО структурой EXEC_SCHEMA. Финальный текст — данные, не сообщение человеку.`,
  ].join('\n')
}

function reviewPrompt(it, k, exec) {
  return [
    `Ты invariant-auditor. Read-only, свежим контекстом отревьюй ТОЛЬКО что закрытый item ${it.id} плана ${PLAN}.`,
    ``,
    `Reads: ${reads(k)}; git-факты — "git log --oneline -6", "git show --stat HEAD", "git diff HEAD~${(exec.commits||[]).length||1}..HEAD" по затронутым файлам.`,
    `Свод исполнителя: status=${exec.status}, committed=${exec.committed}, validate_green=${exec.validate_green}. Коммиты: ${(exec.commits||[]).join(' | ')||'—'}. Итог: ${exec.summary}.`,
    ``,
    `Адверсариально, НЕ доверяя своду:`,
    `- Scope Included/Excluded item'а соблюдён; нет scope drift / no-op-коммита.`,
    `- Code Guidance соблюдён: скилл-правки — SKILL.ru.md И регенерённый SKILL.md синхронны (не рукописный EN); ${it.id.startsWith('P4') ? 'plan_lint/plan-protocol правки back-compat (plan-lint plans/'+PLAN+' зелёный, живые планы не ERROR-ят, union-regex D24); ' : ''}${it.id==='P3.4' ? 'ревьюер СТАТИЧЕСКИЙ (не исполняет скрипт), критерии=зеркало README конструктора; ' : ''}${it.id==='P6.2' ? 'строка "Glossary impact?" ВНЕ shared-регионов (test_agentpacks_shared зелёный); ' : ''}обязательные тесты реально написаны и гоняются (не заглушки).`,
    `- validate.sh реально зелёный (прогони сам при сомнении); CHANGELOG-деливери, если заблокирован средой, честно в Pending Work (НЕ выдан за сделанный).`,
    `- Статусы plan.md/phases/${k}.md обновлены; Update Log ≤2 строк; коммит-гейт соблюдён.`,
    ``,
    `Риск: ${it.risk}. Верни СТРОГО REVIEW_SCHEMA. RED только с конкретными blockers (файл+суть).`,
  ].join('\n')
}

function fixPrompt(it, k, review) {
  return [
    `Ты package-implementer. Ревью item ${it.id} плана ${PLAN} = RED. Устрани блокеры и НЕ более (никакого scope creep).`,
    `Блокеры: ${review.blockers.map((b, i) => `(${i + 1}) ${b}`).join(' ')}`,
    `Reads: ${reads(k)} + "### ${it.id}". Рамки те же (stdlib-only, скилл SKILL.ru.md→regen, CHANGELOG заблокирован→Pending Work). Validation до зелёного. Коммить ОТДЕЛЬНЫМ review-fix коммитом (НЕ amend), Conventional Commits + Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>. Блокер требует эскалации — верни status=blocked.`,
    `Верни СТРОГО EXEC_SCHEMA.`,
  ].join('\n')
}

function closePrompt(k, nextHint) {
  return [
    `Ты plan-closer (sonnet/low). Закрой ФАЗУ ${k} плана ${PLAN} — только бухгалтерия, кода не пиши.`,
    `Reads: ${PD}/phases/${k}.md, ${PD}/plan.md (раздел 4 Status Board), ${PD}/phases/P1.md (образец заполненного Phase Handoff).`,
    `Сделай: (1) заполни "## Phase Handoff" в phases/${k}.md (что сдали, известные отклонения, что дальше); (2) сверь Status Board plan.md строку ${k} с фактическими статусами items (счёт верный; тайм-гейт/скип-items честно открытыми); (3) перезапиши ${PD}/handoff.md целиком по канону (заголовок "# HANDOFF — <ISO-дата> — after <последний закрытый item>", Next=${nextHint}, launch-block самодостаточный); (4) прогони "python3 packages/task/scripts/plan-lint.py plans/${PLAN}" — почини КРАСНОЕ; (5) закоммить бухгалтерию одним коммитом docs(plan) на русском + Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>.`,
    `Верни СТРОГО EXEC_SCHEMA (status=done если lint зелёный и board сверён; commits — сабджект close-коммита).`,
  ].join('\n')
}

// ─── Оркестрация: строго серийно, phase-first ──────────────────────────────────
const results = []
let aborted = false
for (const ph of PHASES) {
  if (aborted) break
  phase(ph.phase)
  let phaseOk = true
  for (const it of ph.items) {
    const exec = await agent(execPrompt(it, ph.key), { label: `exec:${it.id}`, phase: ph.phase, schema: EXEC_SCHEMA, model: it.model, effort: it.effort })
    if (!exec) { log(`⛔ ${it.id}: exec null — стоп`); results.push({ id: it.id, status: 'aborted' }); phaseOk = false; aborted = true; break }
    if (exec.status === 'blocked') { log(`🔴 ${it.id}: ESCALATION — ${exec.escalation||'?'}. Стоп, нужен /task:plan-design или владелец.`); results.push({ id: it.id, ...exec }); phaseOk = false; aborted = true; break }
    if (!exec.committed || !exec.validate_green) { log(`⚠ ${it.id}: коммит-гейт НЕ соблюдён (committed=${exec.committed}, green=${exec.validate_green}) — стоп`); results.push({ id: it.id, ...exec, gate: 'FAILED' }); phaseOk = false; aborted = true; break }

    const review = await agent(reviewPrompt(it, ph.key, exec), { label: `review:${it.id}`, phase: ph.phase, schema: REVIEW_SCHEMA, model: it.review, effort: it.reviewEffort })
    let fixed = null
    if (review && review.verdict === 'RED' && review.blockers.length) {
      log(`🔧 ${it.id}: RED (${review.blockers.length}) — fix-проход`)
      fixed = await agent(fixPrompt(it, ph.key, review), { label: `fix:${it.id}`, phase: ph.phase, schema: EXEC_SCHEMA, model: it.model, effort: it.effort })
      if (!fixed || fixed.status === 'blocked' || !fixed.committed) { log(`🔴 ${it.id}: fix не закрыл — стоп, нужен человек`); results.push({ id: it.id, exec, review, fixed, gate: 'FIX_FAILED' }); phaseOk = false; aborted = true; break }
    }
    results.push({ id: it.id, status: exec.status, review: review?.verdict || 'n/a', fixed: !!fixed })
    log(`✅ ${it.id}: ${exec.status}, ревью ${review?.verdict || 'n/a'}${fixed ? ' (fix)' : ''}`)
  }
  if (!phaseOk) break

  const nextHint = ph.key === 'P3' ? '/task:plan-exec SKM-ROADMAP-005 P4.1'
    : ph.key === 'P4' ? '/task:plan-exec SKM-ROADMAP-005 P5.1'
    : ph.key === 'P5' ? '/task:plan-exec SKM-ROADMAP-005 P6.1'
    : 'ИНТЕРВЬЮ ВЛАДЕЛЬЦА по P7.1 (смысл ephemeral-дисциплины, D7), затем /task:plan-exec SKM-ROADMAP-005 P7.1'
  const close = await agent(closePrompt(ph.key, nextHint), { label: `close:${ph.key}`, phase: ph.phase, schema: EXEC_SCHEMA, model: 'sonnet', effort: 'low' })
  log(`📋 ${ph.key} phase-close: ${close?.status || 'n/a'}`)
  results.push({ id: `${ph.key}-close`, status: close?.status || 'n/a' })
  if (!close || close.status === 'blocked') { log(`🔴 ${ph.key}: phase-close упал — стоп`); aborted = true; break }
}

const done = results.filter(r => r.status === 'done' || r.status === 'done_with_deviations')
log(`Итог P3→P6: закрыто ${done.length} шагов${aborted ? ' (ЦЕПОЧКА ОСТАНОВЛЕНА — нужен человек)' : ''}. P6.4 (тайм-гейт D41) и P7 (интервью D7) НЕ исполнялись.`)
return { plan: PLAN, phases: 'P3-P6', aborted, deferred: ['P6.4 (тайм-гейт D41)', 'P7.1/P7.2 (интервью владельца D7)', 'CHANGELOG [Unreleased] строки (permission-deny среды)'], results }
