// Artifex P0.5 — майнинг фактических принципов владельца из истории планов.
// Fan-out: дешёвые экстракторы над корпусом планов → дедуп → синтез+классификация старшей.
// Read-only: агенты ничего не правят и не коммитят. Каталог пишет исполнитель item'а
// из вернувшегося JSON (владелец утверждает ПОСЛЕ — Scope Excluded P0.5).
export const meta = {
  name: 'foreman-principles-mining',
  description: 'Майнинг фактических принципов владельца из D-логов/handoff истории планов + память mAInd; бинарная классификация согласование/свободно с прецедентами',
  whenToUse: 'P0.5 плана 2026.07.18-FOREMAN; запускать через scriptPath из сессии-оператора (fable/opus)',
  phases: [
    { title: 'Extract', detail: 'экстракторы над срезами корпуса, дешёвыми моделями', model: 'haiku' },
    { title: 'Dedup', detail: 'слияние дублей принципов', model: 'sonnet' },
    { title: 'Classify', detail: 'синтез + бинарная классификация + прецеденты, старшей моделью', model: 'opus' },
  ],
}

// ── Корпус (срезы; агенты сами глоббят/грепят — пути устойчивы к отсутствию папки) ──
// ИНВАРИАНТ: абсолютные пути (cwd субагента сбрасывается между вызовами).
const CORPUS = [
  {
    key: 'brain-archive',
    brief: 'Архивные/терминальные планы Brain-vault. Глоббь plans/archive/ и 05-Projects/*/plans/*/ под /home/vostrikov/Vaults/Brain; читай ТОЛЬКО ## Decision Log (plan.md) и handoff.md — оттуда извлекай решения и их обоснования.',
  },
  {
    key: 'repo-plans',
    brief: 'Планы в код-репозиториях. Глоббь /home/vostrikov/projects/**/plans/*/ и /home/vostrikov/projects/packages/**/plans/*/; читай D-логи + handoff. Пропускай директории, которых нет — не падай.',
  },
  {
    key: 'maind-memory',
    brief: 'Память экосистемы mAInd. Вызови maind memory recall по темам: «эскалация», «согласование контракта», «breaking change», «package boundary», «reuse-гейт». Извлекай зафиксированные директивы владельца о том, что требовало согласования, а что делалось свободно.',
  },
  {
    key: 'audit-findings',
    brief: 'Findings аудитов. Глоббь **/plans/*/findings/*.md и **/findings/*audit*.md под /home/vostrikov/Vaults/Brain; извлекай, какие находки владелец эскалировал/блокировал vs пропускал.',
  },
]

const EXTRACT_MODEL = { model: 'haiku', effort: 'low' }
const DEDUP_MODEL = { model: 'sonnet', effort: 'low' }
const CLASSIFY_MODEL = { model: 'opus', effort: 'high' }

// Граница классификации — package-contribution-protocol (бинарная): межпакетное/
// концептуальное → согласование; внутрипакетное чистое улучшение → свободно.
const BOUNDARY_SKILL = '/home/vostrikov/projects/packages/swissknifeman/packages/skiller/skills/architect/package-contribution-protocol'

// ── Схемы structured-output ──────────────────────────────────────────────────
const PRINCIPLE = {
  type: 'object',
  properties: {
    principle: { type: 'string', description: 'Принцип одной фразой — как владелец фактически решал' },
    evidence: {
      type: 'array',
      description: 'Прецеденты: план + D#/цитата handoff. Пустой массив = гипотеза без прецедента.',
      items: {
        type: 'object',
        properties: {
          source: { type: 'string', description: 'Путь плана/файла + D#/якорь' },
          quote: { type: 'string', description: 'Короткая цитата-основание' },
        },
        required: ['source'],
      },
    },
  },
  required: ['principle', 'evidence'],
}
const EXTRACT_SCHEMA = {
  type: 'object',
  properties: { principles: { type: 'array', items: PRINCIPLE } },
  required: ['principles'],
}
const CATALOG_SCHEMA = {
  type: 'object',
  properties: {
    requires_alignment: {
      type: 'array', description: 'Класс «требует согласования» — межпроектное/концептуальное',
      items: { ...PRINCIPLE, properties: { ...PRINCIPLE.properties, rationale: { type: 'string' } } },
    },
    free: {
      type: 'array', description: 'Класс «свободно без вопросов» — внутрипакетное чистое улучшение',
      items: { ...PRINCIPLE, properties: { ...PRINCIPLE.properties, rationale: { type: 'string' } } },
    },
    hypotheses: {
      type: 'array', description: 'Принципы без грепаемого прецедента — НЕ смешивать с подтверждёнными',
      items: PRINCIPLE,
    },
    outside_binary: {
      type: 'array', description: 'Классы решений вне бинарной классификации — находка для D13',
      items: PRINCIPLE,
    },
  },
  required: ['requires_alignment', 'free', 'hypotheses', 'outside_binary'],
}

// ── Оркестрация ──────────────────────────────────────────────────────────────
phase('Extract')
const extracted = await parallel(CORPUS.map((slice) => () =>
  agent(
    `Ты экстрактор фактических принципов владельца из истории планов. Срез: ${slice.key}.\n${slice.brief}\n\n` +
    `ЗАДАЧА: извлеки повторяющиеся решения владельца — что эскалировалось/требовало согласования и ПОЧЕМУ; ` +
    `что решалось автономно/свободно. Каждый принцип — с прецедентом (план + D#/цитата). ` +
    `Принцип без грепаемого прецедента возвращай с пустым evidence (гипотеза). ` +
    `НЕ классифицируй (это стадия синтеза) — только извлекай факты. Ничего не правь, read-only.`,
    { label: `extract:${slice.key}`, phase: 'Extract', schema: EXTRACT_SCHEMA, ...EXTRACT_MODEL },
  ).then((r) => ({ slice: slice.key, principles: r?.principles ?? [] })),
))

const allPrinciples = extracted.filter(Boolean).flatMap((e) => e.principles)
log(`Extract: ${allPrinciples.length} сырых принципов из ${extracted.filter(Boolean).length} срезов`)

phase('Dedup')
const deduped = await agent(
  `Вот сырые принципы из майнинга истории планов (JSON):\n${JSON.stringify(allPrinciples, null, 2)}\n\n` +
  `ЗАДАЧА: слей семантические дубли в один принцип, ОБЪЕДИНИВ их evidence (не теряй прецеденты). ` +
  `Не выбрасывай принципы с прецедентами. Верни очищенный список.`,
  { label: 'dedup', phase: 'Dedup', schema: EXTRACT_SCHEMA, ...DEDUP_MODEL },
)
log(`Dedup: ${deduped?.principles?.length ?? 0} уникальных принципов`)

phase('Classify')
const catalog = await agent(
  `Прочитай скилл границы пакет↔экосистема: ${BOUNDARY_SKILL}/SKILL.md (бинарная граница — основа классификации).\n\n` +
  `Вот дедуплицированные принципы владельца (JSON):\n${JSON.stringify(deduped?.principles ?? [], null, 2)}\n\n` +
  `ЗАДАЧА: классифицируй по package-contribution-protocol:\n` +
  `- requires_alignment — межпроектные/межпакетные концептуальные взаимодействия (FlexCRM↔CoreX-класс: контракты «плавают»);\n` +
  `- free — внутрипакетные улучшения в рамках чистой реализации (fluent API, расширяемость, конфигурируемость, надёжность);\n` +
  `- hypotheses — принципы без прецедента (пустой evidence) — НЕ смешивать с подтверждёнными;\n` +
  `- outside_binary — классы решений, не влезающие в бинарь (находка для D13, НЕ насильно в бинарь).\n` +
  `Каждый классифицированный принцип несёт rationale (почему этот класс) и сохраняет evidence. ` +
  `Мета-принцип владельца «идеальные системы — главный козырь, улучшение качества не блокируется» учитывай при разнесении. Read-only.`,
  { label: 'classify', phase: 'Classify', schema: CATALOG_SCHEMA, ...CLASSIFY_MODEL },
)

return {
  catalog,
  stats: {
    raw: allPrinciples.length,
    deduped: deduped?.principles?.length ?? 0,
    requires_alignment: catalog?.requires_alignment?.length ?? 0,
    free: catalog?.free?.length ?? 0,
    hypotheses: catalog?.hypotheses?.length ?? 0,
    outside_binary: catalog?.outside_binary?.length ?? 0,
  },
}
