export const meta = {
  name: 'wf-skm-roadmap-005-rest-design',
  description: 'Детально спроектировать фазы P4/P5/P6 плана SKM-ROADMAP-005 (параллельно, файлы не пересекаются) + adversarial design-audit каждой. P7 исключена (интервью владельца, D7).',
  whenToUse: 'Ночная проработка: развернуть скелеты P4-P6 в исполнимые ТЗ до запуска exec-воркфлоу. Возвращает D-log/routing-дельты для ручной интеграции в plan.md.',
  phases: [
    { title: 'P4 design', detail: 'plan-protocol + plan_lint (публичный контракт, opus)' },
    { title: 'P5 design', detail: 'changelog-discipline (release-engineering + harness-гейт)' },
    { title: 'P6 design', detail: 'ecosystem-glossary (трёхслойка)' },
  ],
}

const PLAN = 'SKM-ROADMAP-005'
const PD = `plans/${PLAN}`
// Общие reads: SSOT схемы протокола + образец полностью детализированной фазы (проходит lint).
const PROTO = 'packages/skiller/skills/general/plan-protocol/SKILL.md'
const GOLD = `${PD}/phases/P2.md` // эталон формата: 5 items, все 16 полей, DoR, Scope, RAG-маркеры

// Каждой фазе — резервный диапазон D-номеров (текущий max = D23), чтобы дельты не сталкивались.
const PHASES = [
  {
    id: 'P4', phase: 'P4 design', dRange: 'D24–D31', items: 6, model: 'opus', effort: 'high',
    specs: 'roadmap/plan-homes.md (весь) + roadmap/workflow-craft.md §Часть 1.6',
    touches: 'packages/skiller/skills/general/plan-protocol/SKILL.ru.md (+regen SKILL.md), packages/task/lib/task/plan_lint.py, скилл-карта экосистемы, секции CLAUDE.md обоих контекстов',
    notes: 'ПУБЛИЧНЫЙ КОНТРАКТ протокола: все design-items opus/high; plan_lint и скилл правятся СИНХРОННО (расхождение = класс дефекта, CLAUDE.md task). Канон имён D16 (ГГГГ.ММ.ДД-ИМЯ) + back-compat старого паттерна. Дом workflow-скриптов plans/<ID>/workflows/ (D2). Существующие планы НЕ переименовываются. P4.1/P4.2 уже opus/high в Routing.',
  },
  {
    id: 'P5', phase: 'P5 design', dRange: 'D32–D37', items: 3, model: 'opus', effort: 'high',
    specs: 'roadmap/changelog-discipline.md (весь)',
    touches: 'скилл oss-dev/release-engineering (SKILL.ru.md→regen), commit-гейт в harness (прецедент git-гейта SKM-AUDIT-004 P7.4), опц. `skm release`',
    notes: 'Два контура: пакеты SemVer-строгие (fix→patch/feat→minor, major — ВСЕГДА ручное решение владельца, breaking не выводится автоматикой); проекты без SemVer. Enforcement — warning В КОНТЕКСТ модели, НЕ блок; skip-маркер для docs/chore. Прецедент гейта — SKM-AUDIT-004 P7.4.',
  },
  {
    id: 'P6', phase: 'P6 design', dRange: 'D38–D43', items: 4, model: 'opus', effort: 'high',
    specs: 'roadmap/ecosystem-glossary.md (весь)',
    touches: 'скилл architect/domain-modeling (SKILL.ru.md→regen), чек-листы ревью-паков + conformance-finder Stage B в task:review, указатель в бакете axioma + каркас страницы term-index в Brain',
    notes: 'Трёхслойка БЕЗ мега-глоссария. P6.4 (наполнение term-index) — ТАЙМ-ГЕЙТ (после dev-волны ECOSYSTEM P4): остаётся отдельным ОТКРЫТЫМ item на доске, exec его НЕ закрывает. Ревьюер — СУЩЕСТВУЮЩИЙ (измерение conformance-finder), новый пак не заводить. Rule of Two входа в term-index (термин пересёк 2+ пакета). Раскладка «механизм в SKM, содержимое в Brain».',
  },
]

const DESIGN_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['phase', 'items_detailed', 'dor_pass', 'dlog_deltas', 'routing_deltas', 'needs_clarification', 'summary'],
  properties: {
    phase: { type: 'string' },
    items_detailed: { type: 'integer', description: 'сколько items доведено до полных 16 полей' },
    dor_pass: { type: 'boolean', description: 'DoR-чеклист фазы пройден (0 маркеров [NEEDS CLARIFICATION])' },
    dlog_deltas: { type: 'array', items: {
      type: 'object', additionalProperties: false, required: ['id', 'decision', 'why'],
      properties: { id: { type: 'string', description: 'D-номер из выданного диапазона' }, decision: { type: 'string' }, why: { type: 'string', description: 'причина + RAG-маркер если внешний факт' } },
    }, description: 'новые решения для plan.md ## 5. Decision Log' },
    routing_deltas: { type: 'array', items: { type: 'string' }, description: 'строки для plan.md ## 3. Routing (отклонения от дефолта), или пусто' },
    needs_clarification: { type: 'array', items: { type: 'string' }, description: 'нерешаемое без владельца — маркеры [NEEDS CLARIFICATION], оставленные в фазе' },
    summary: { type: 'string' },
  },
}

const AUDIT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['verdict', 'gaps', 'notes'],
  properties: {
    verdict: { type: 'string', enum: ['GREEN', 'ATTENTION', 'RED'] },
    gaps: { type: 'array', items: { type: 'string' }, description: 'конкретные дыры: item+поле+суть (пусто для GREEN)' },
    notes: { type: 'string' },
  },
}

function designPrompt(p) {
  return `Ты plan-designer (opus/high). Разверни СКЕЛЕТ фазы ${p.id} мастер-плана ${PLAN} в исполнимое ТЗ по plan-протоколу — так, чтобы sonnet исполнил каждый item БЕЗ доступа к этому чату.

Прочитай ПЕРЕД работой, в порядке:
1. ${PROTO} (SSOT схемы: секции, статусы, DoR §7, routing-матрица §9, refine-цикл).
2. ${GOLD} — ЭТАЛОН формата: полностью детализированная фаза, проходит plan-lint. Копируй её структуру байт-в-байт (Phase Context → Scope Included/Excluded фазы → DoR-чеклист с [x] → items со ВСЕМИ 16 полями в строгом порядке → Phase Handoff-заглушка).
3. ${PD}/phases/${p.id}.md — СКЕЛЕТ (Phase Context + item-заголовки/Intent-семена; убери строку-маркер «СКЕЛЕТ — не детализирован»).
4. ${p.specs} — ИСТОЧНИК содержания фазы.
5. ${PD}/plan.md (Meta, ## 3. Routing строки ${p.id}, ## 5. Decision Log — существующие D1–D23 для контекста и ссылок).

Спроектируй ${p.items} items фазы ${p.id}. Файлы, которые правят items: ${p.touches}.
Особенности фазы: ${p.notes}

ЖЁСТКИЕ требования качества (иначе = находка аудита):
- КАЖДЫЙ item исполним sonnet'ом без доп. контекста: Required Reads конечны и упорядочены (не «посмотри по репо»); **Code Guidance ОБЯЗАТЕЛЕН** (стиль решения, запреты, обязательные тесты, запрещённые shortcuts, if-then эскалация — то, что дешёвая модель не выведет сама); Validation — КОНКРЕТНЫЕ команды (что прогнать, что считается зелёным).
- Поля item'а СТРОГО строками «**Поле:** значение» в порядке: Status, Intent, Why, Scope Included, Scope Excluded, Inputs, Files, Required Reads, Implementation Rules, Code Guidance, Validation, Deliverables, Completion Notes, Pending Work, Known Deviations, Escalation Needed. Пустое = «—»; у Escalation Needed допустим «no».
- Статусы — РОВНО канонические строки (⬜ Not started для всех новых items).
- Правка скилла — двуязычная модель: источник SKILL.ru.md, SKILL.md регенерируется (укажи это в Implementation Rules/Code Guidance каждого скилл-item'а).
- stdlib-only в python-коде; сообщения на русском.
- RAG-маркеры на НЕСУЩИХ фактах: repo-grounded — подтверждай ссылкой на код/спеку; ВНЕШНИЙ факт (версия/API, «стандарт») — НЕ делай параллельный perplexity-запрос (профиль моста один, параллель = lock); пометь [UNVERIFIED] с пояснением — супервизор доверифицирует при интеграции. Не выдумывай внешние факты.
- НИКАКИХ самовольных допущений: спорное несущее место без владельца → маркер [NEEDS CLARIFICATION: <вопрос>] прямо в тексте И в поле needs_clarification возврата. Молча принятое допущение = дефект.
- Тайм-гейтовый item (если есть, напр. P6.4) — оставь ОТДЕЛЬНЫМ открытым item'ом (⬜), Deliverables честно про тайм-гейт, downstream читает доску.

Решения (Alternatives несущих развилок) НЕ пиши в plan.md сам — верни их в dlog_deltas с D-номерами из диапазона ${p.dRange}. В тексте item'ов ссылайся на них по этим D-номерам. Routing-отклонения от дефолта sonnet/medium верни в routing_deltas.

ЗАПИШИ результат в файл ${PD}/phases/${p.id}.md (перезапиши целиком по эталону ${GOLD}). Затем прогони: python3 packages/task/scripts/plan-lint.py plans/${PLAN} — почини КРАСНОЕ в своём файле (зелёное/warn по другим фазам не трогай). НЕ коммить (интеграцию D-log в plan.md делает супервизор).

Верни СТРОГО структурой DESIGN_SCHEMA. Финальный текст — данные, не сообщение человеку.`
}

function auditPrompt(p, design) {
  return `Ты design-auditor (opus/high), adversarial. Свежим взглядом (read-only по смыслу; можешь читать файлы и гонять plan-lint) проверь ТОЛЬКО что спроектированную фазу ${p.id} плана ${PLAN} на исполнимость дешёвой моделью.

Reads: ${PD}/phases/${p.id}.md (свежий дизайн); ${p.specs} (сверить scope со спекой); ${PROTO} §6-7 (DoR/статусы); ${GOLD} (эталон полноты).

Свод дизайнера: items_detailed=${design.items_detailed}, dor_pass=${design.dor_pass}, маркеров-clarification=${(design.needs_clarification||[]).length}. Итог: ${design.summary}.

Проверь адверсариально, НЕ доверяя своду:
- DoR РЕАЛЬНО пройден: 0 маркеров [NEEDS CLARIFICATION] (или они честно в needs_clarification и это владельцу, не лень дизайнера); Scope Included/Excluded фазы заполнены; Alternatives несущих решений — в dlog_deltas; несущие факты несут RAG:✅/[UNVERIFIED].
- КАЖДЫЙ item cold-start-исполним sonnet'ом: Required Reads конечны/упорядочены; Code Guidance НЕ пустой и НЕ generic («пиши хорошо» = дыра) — несёт конкретные запреты/тесты/if-then; Validation — исполнимые команды с критерием зелёного, не «проверь что работает».
- Нет scope drift от спеки; нет самовольных допущений, выданных за решение; тайм-гейтовые items оставлены открытыми, не фиктивно закрыты.
- Все 16 полей в строгом порядке; статусы канонические; скилл-items несут двуязычную модель SKILL.ru.md→regen.
- plan-lint по плану зелёный (прогони сам).

Верни СТРОГО структурой AUDIT_SCHEMA. RED только с конкретными gaps (item+поле+суть), которые обязан устранить fix. ATTENTION — некритичные шероховатости. GREEN — фаза готова к exec.`
}

// ─── Оркестрация: фазы независимы (разные файлы) → параллельно; внутри — design→audit ──
const results = await parallel(PHASES.map(p => async () => {
  phase(p.phase)
  const design = await agent(designPrompt(p), {
    label: `design:${p.id}`, phase: p.phase, schema: DESIGN_SCHEMA, model: p.model, effort: p.effort,
  })
  if (!design) { log(`⛔ ${p.id}: design-агент не вернул результат`); return { phase: p.id, design: null, audit: null }}

  const audit = await agent(auditPrompt(p, design), {
    label: `audit:${p.id}`, phase: p.phase, schema: AUDIT_SCHEMA, model: 'opus', effort: 'high',
  })
  log(`${p.id}: дизайн ${design.items_detailed}/${p.items} items, DoR=${design.dor_pass}, аудит=${audit?.verdict || 'n/a'}, clarify=${(design.needs_clarification||[]).length}`)
  return { phase: p.id, design, audit }
}))

const clean = results.filter(r => r.audit && r.audit.verdict === 'GREEN' && r.design.dor_pass)
log(`Итог design: GREEN ${clean.length}/${PHASES.length} фаз. Требуют доводки супервизором: ${results.filter(r => !clean.includes(r)).map(r => r.phase).join(', ') || 'нет'}`)
return { plan: PLAN, stage: 'rest-design', phases: results.map(r => ({
  phase: r.phase,
  verdict: r.audit?.verdict || 'n/a',
  dor: r.design?.dor_pass ?? null,
  items: r.design?.items_detailed ?? 0,
  dlog: r.design?.dlog_deltas || [],
  routing: r.design?.routing_deltas || [],
  needs_clarification: r.design?.needs_clarification || [],
  gaps: r.audit?.gaps || [],
})) }
