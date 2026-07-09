// Шаблон 2: author-by-spec — спека → N файловых заданий × author → self-check (pipeline, без барьера).
// Прототип: рабочий скрипт ECOSYSTEM P5 (wf-p5-author.js). Правила слотов — README.md рядом.
export const meta = {
  name: 'author-by-spec', // SLOT: имя под конкретный запуск
  description: 'Авторинг по спеке-SSOT: параллельные файловые задания + self-check каждого результата',
  whenToUse: 'Stage авторинга после готовой спеки; запускать через scriptPath (НЕ named-workflow — args приходит строкой)',
  phases: [
    { title: 'Author', detail: 'файловые задания параллельно по спеке', model: 'sonnet' },
    { title: 'Self-check', detail: 'сверка результата со спекой + валидация', model: 'sonnet' },
  ],
}

// ── Конфиг (embedded, НЕ через args-строку) ──────────────────────────────────
// SLOT: пути — репозиторий-цель и спека-SSOT (абсолютные: cwd субагента сбрасывается).
const REPO = '/abs/path/to/repo'
const SPEC = '/abs/path/to/spec.md'

// SLOT: FILES — файловые задания. Одно задание = один агент = один коммит.
//   files      — какие файлы правит/создаёт (дисциплина: ТОЛЬКО их);
//   brief      — плотное ТЗ со ссылкой на блок спеки (агент обязан читать спеку сам);
//   validation — команда/греп, которыми агент И self-check проверяют результат;
//   commit     — готовый subject Conventional Commits (агент не сочиняет свой).
const FILES = [
  {
    key: 'block-1',
    files: ['path/inside/repo/file.md'],
    brief: 'ЗАДАЧА (блок N спеки): что сделать, границы, чего НЕ трогать.',
    validation: 'grep -c "маркер" path/inside/repo/file.md — ожидается ≥1',
    commit: 'feat(scope): суть (PLAN-ID блок N)',
  },
]

// SLOT: конвейер-команды — обязательные прогоны после правки (пусто, если их нет).
// Пример swissknifeman: check-translations.sh --stamp → skiller registry → validate.sh.
const CONVEYOR = []

// SLOT: model/effort — авторинг обычно sonnet/medium, self-check sonnet/low.
const AUTHOR_MODEL = { model: 'sonnet', effort: 'medium' }
const CHECK_MODEL = { model: 'sonnet', effort: 'low' }

// ── Схема structured-summary (единая для author и self-check) ────────────────
const REPORT = {
  type: 'object',
  properties: {
    files_changed: { type: 'array', items: { type: 'string' } },
    commits: { type: 'array', items: { type: 'string' }, description: 'sha + subject каждого коммита; пусто если коммиты запрещены' },
    validation: { type: 'string', description: 'что прогнал и результаты (exit-коды, грепы)' },
    issues: { type: 'array', items: { type: 'string' }, description: 'что не удалось / отклонения от спеки с причиной' },
    summary: { type: 'string', description: 'суть сделанного, 3-5 строк' },
  },
  required: ['files_changed', 'commits', 'validation', 'issues', 'summary'],
}

// Общая дисциплина всех author-агентов — не размазывать по brief'ам.
const COMMON = [
  `Репозиторий: ${REPO}. Спека-SSOT: прочитай ${SPEC} ЦЕЛИКОМ прежде чем править.`,
  `Дисциплина: правишь ТОЛЬКО файлы своего задания; стиль — как соседний текст файла; ничего не выдумывать сверх спеки — неясность фиксируй в issues, не импровизируй.`,
  `Коммиты: свои файлы отдельным коммитом с заданным subject (тело — зачем, 1-3 строки). Перед коммитом git status — чужие файлы НЕ добавлять (git add только свои пути).`,
  `Финальный текст = данные по схеме, не сообщение человеку.`,
].join('\n')

function authorPrompt(f) {
  return [
    COMMON,
    f.brief,
    `Файлы задания: ${f.files.join(', ')}`,
    CONVEYOR.length ? `Конвейер после правки (обязательно, по порядку): ${CONVEYOR.join(' → ')}` : null,
    `Самопроверка перед коммитом: ${f.validation}`,
    `Коммит: ${f.commit}`,
  ].filter(Boolean).join('\n\n')
}

function checkPrompt(f, res) {
  return [
    `Self-check задания «${f.key}» свежим контекстом (ты НЕ автор). Репозиторий: ${REPO}, спека: ${SPEC} — прочитай блок задания в спеке и сами файлы: ${f.files.join(', ')}.`,
    `Отчёт автора: ${res.summary}\nЗаявленные коммиты: ${(res.commits || []).join('; ') || '—'}`,
    `Проверь: (1) результат соответствует блоку спеки — ничего не выброшено и не выдумано; (2) валидация реально зелёная — прогони сам: ${f.validation}; (3) коммит содержит только файлы задания (git show --stat).`,
    `НИЧЕГО не правь и не коммить — только вердикт. Расхождения — в issues (пустой массив = чисто). Финальный текст = данные по схеме.`,
  ].join('\n\n')
}

// ── Оркестрация: pipeline без барьера — self-check стартует сразу после авторинга файла ──
log(`author-by-spec: ${FILES.length} заданий по спеке ${SPEC}`)

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
if (failed.length) log(`ВНИМАНИЕ: задания без результата (пересобрать в main loop): ${failed.join(', ')}`)
if (issues.length) log(`issues по итогам self-check: ${issues.length}`)

return {
  done: ok.map(r => ({ key: r.key, commits: r.author.commits, check_issues: (r.check && r.check.issues) || [] })),
  failed,
  issues,
}
