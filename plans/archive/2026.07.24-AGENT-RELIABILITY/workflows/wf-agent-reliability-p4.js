// Фаза P4 плана 2026.07.24-AGENT-RELIABILITY — carrier оркестрации (D93).
// Порядок СТРОГО последовательный (D90): P4.4 → P4.5 → P4.1 → P4.2 → P4.3.
// Параллельность сознательно НЕ используется, хотя три items независимы по данным: все
// закрываются в ОДНУ ветку одного рабочего дерева топологией из двух коммитов
// (plan-protocol §8), а единственная изоляция (worktree на item) имеет измеренную цену —
// находка F6 захода 1 (живой debug-worktree, снятый отдельным ремонтным item'ом P3.6).
//
// Шаблон: wf-agent-reliability-p2-7-9-remediation.js этого же плана (Impl → Verify
// (механический, сырой вывод) → Review (adversarial, глубина по колонке `Review` §3) →
// Close (bookkeeping ТОЛЬКО из машинных фактов)). ОТЛИЧИЕ от прецедента: ТЗ items здесь НЕ
// встраивается в скрипт — агент читает его из `phases/P4.md` (единственный SSOT). Причина
// названа явно: встроенная копия ТЗ расходится с фазой при любом re-design'е, а фаза P4
// уже пережила переопределение входного гейта (D89) — второй носитель ТЗ был бы ровно тем
// «вторым носителем факта», который запрещает plan-protocol §3.
export const meta = {
  name: 'wf-P4',
  description: 'Фаза P4 (2026.07.24-AGENT-RELIABILITY): гейт кодов границ → оплата Contribution gate → вердикт гипотез → operator doctor → docs и Owner packet, строго последовательно',
  whenToUse: 'Запускать НОВОЙ сессией после того, как фаза P3 терминальна и фаза P4 доведена до DoR (D89–D93). Запуск: Workflow({scriptPath}) — БЕЗ args (embedded-конфиг; известная ловушка named-workflow передаёт args строкой)',
  phases: [
    { title: 'Impl', detail: 'исполнение Scope Included item\'а по ТЗ из phases/P4.md + прогон его Validation + коммит (модель/effort — из §3 Routing item\'а)' },
    { title: 'Verify', detail: 'МЕХАНИЧЕСКИЙ агент (sonnet/low): независимый прогон команд поля Validation, сырой вывод/exit-коды, без интерпретации' },
    { title: 'Review', detail: 'adversarial-ревью диффа против Deliverables/Implementation Rules (глубина из колонки Review §3: full → opus/high, light → sonnet/medium), видит дифф+Verify, не отчёт Impl' },
    { title: 'Close', detail: 'bookkeeping (sonnet/low): Status/Completion Notes/Known Deviations item\'а ТОЛЬКО из машинных фактов, Status Board, Update Log, journal, handoff' },
  ],
}

// ── Конфиг (embedded, НЕ args-строка) ────────────────────────────────────────
const REPO = '/home/vostrikov/projects/packages/swissknifeman'
const PLAN = '2026.07.24-AGENT-RELIABILITY'
const PLAN_DIR = `plans/${PLAN}`
if (!REPO.startsWith('/')) throw new Error(`REPO должен быть абсолютным путём: "${REPO}"`)

const CTX = `
КОНТЕКСТ (репо ${REPO}, план ${PLAN_DIR}):
- Монорепо academici (swissknifeman). Мастер-план ${PLAN}, фаза **P4** — последняя.
  Фазы P0–P3 терминальны; P3 закрыта \`🟠 Done with deviations\` с названным долгом **D88**:
  полная терминальная приёмка \`reliability-acceptance-v1.md\` НЕДОСТИЖИМА на этом
  инструментальном поколении (F1 = 0.96, F10 = unknown, 26/31 кейсов банка \`unmappable\`).
- Входной гейт P4 «не стартует до GREEN» ПЕРЕОПРЕДЕЛЁН **D89**: фаза исполняется на
  ИЗМЕРЕННОМ скоупе, её терминальный продукт — Owner packet, честно объявляющий приёмку
  НЕ выполненной. Ни один floor не повышается, замороженные контракты/банк (владелец P0.3)
  не правятся, слово GREEN не появляется ни в доках, ни в packet'е.
- ПОРЯДОК СТРОГИЙ (D90): P4.4 (гейт линтера) → P4.5 (оплата Contribution gate) → P4.1
  (вердикт гипотез) → P4.2 (read-only doctor) → P4.3 (docs + Owner packet). P4.4 первым —
  он меняет линтер, которым валидируются ВСЕ последующие закрытия; дальше — реальная
  зависимость по данным. Красный/blocked item ОСТАНАВЛИВАЕТ весь прогон.
- **ТЗ item'а — в \`${PLAN_DIR}/phases/P4.md\`, раздел \`### <ID> — …\`, и это единственный
  SSOT.** Читай его ЦЕЛИКОМ (все 16 полей) перед работой; в этом скрипте копии ТЗ нет
  сознательно. Не домысливай и не сверяйся с памятью.
- Коммиты — Conventional Commits на русском; \`git add\` ТОЛЬКО по путям из \`Files\` item'а +
  файлы плана при bookkeeping. \`git add -A\`/\`git add .\` ЗАПРЕЩЕНЫ (прецедент F1: чужой
  продуктовый файл уехал в item-коммит).
- **Коды границ печатаются в Completion Notes** (\`pre_mutation: …\`, \`pre_final: …\`) —
  ровно тот слип, ремонт которого несёт P4.4 (находка Ф2, событие 2 из 2). Отсутствие
  напечатанных кодов у закрытого item'а — дефект, а не мелочь.
- Красное остаётся красным: расхождение Validation/пересчитанной цифры с ожиданием —
  ЧЕСТНЫЙ РЕЗУЛЬТАТ, фиксируется как есть (Known Deviations/находка), НЕ подгоняется под
  зелёное и НЕ скрывается. Silent cap на статус ЗАПРЕЩЁН.
- **Граница наружу:** ни один агент этого прогона не делает \`git push\`, \`git tag\`, релиз,
  раскатку на флот/consumer-репозитории и не трогает \`plans/2026.07.18-FOREMAN\` /
  \`plans/2026.07.25-ECO-OPT\`. Решение G1 принимает ВЛАДЕЛЕЦ после packet'а P4.3.
`

// Глубина review — колонка `Review` §3 Routing plan.md (P4.4 full, P4.5 light, P4.1 full,
// P4.2 light, P4.3 full). Соответствие «класс → модель» — то же, что в прецеденте
// wf-agent-reliability-p2-7-9-remediation.js (full → opus/high, light → sonnet/medium).
const REVIEW_FOR = {
  full: { model: 'opus', effort: 'high' },
  light: { model: 'sonnet', effort: 'medium' },
}

const IMPL_SCHEMA = {
  type: 'object',
  properties: {
    item: { type: 'string' },
    spec_read: { type: 'boolean', description: 'ТЗ item\'а прочитано из phases/P4.md целиком (16 полей) ДО первой мутации' },
    precondition_ok: { type: 'boolean', description: 'precondition-гейт Implementation Rules (если он есть у item\'а) перепроверен ЭТИМ агентом и прошёл; если у item\'а гейта нет — true с пометкой в precondition_detail' },
    precondition_detail: { type: 'string', description: 'вывод команд precondition-гейта дословно либо «у item\'а precondition-гейта нет»' },
    done: { type: 'boolean', description: 'true ТОЛЬКО если Scope Included исполнен; красная Validation сама по себе НЕ обязана давать done=false, если это ожидаемый честный исход по Implementation Rules — но тогда обязана быть названа в known_deviations' },
    validation_report: { type: 'string', description: 'КАЖДАЯ команда поля Validation спеки с её выводом/exit-кодом ДОСЛОВНО — не пересказ, не «все ок»' },
    boundary_codes: { type: 'string', description: 'напечатанные коды границ ЭТОГО прогона: «pre_mutation: <код>, pre_final: <код>» (D76: зелёное — РОВНО allow/allow)' },
    commits: { type: 'array', items: { type: 'string' } },
    files_outside_scope: { type: 'array', items: { type: 'string' }, description: 'тронутое вне Files item\'а — честно' },
    pending_work: { type: 'string' },
    known_deviations: { type: 'string' },
    escalation: { type: 'string', description: '"no" либо причина + триггер (plan-protocol §10)' },
  },
  required: ['item', 'spec_read', 'precondition_ok', 'precondition_detail', 'done', 'validation_report', 'boundary_codes', 'commits', 'files_outside_scope', 'pending_work', 'known_deviations', 'escalation'],
}

const REVIEW_SCHEMA = {
  type: 'object',
  properties: {
    item: { type: 'string' },
    verdict: { type: 'string', enum: ['GREEN', 'ATTENTION', 'RED'] },
    deliverables_met: { type: 'boolean' },
    validation_cross_check: { type: 'string', description: 'сверка Verify-вывода с ожиданиями спеки: что реально зелёное/красное, совпадает ли с отчётом Impl' },
    false_claims: { type: 'array', items: { type: 'string' }, description: 'заявлено Impl в отчёте, но Verify/дифф этого не подтверждают' },
    scope_boundary_ok: { type: 'boolean', description: 'ни одной мутации вне Files item\'а и вне границ фазы (никакого push/tag/релиза/чужих планов)' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          severity: { type: 'string', enum: ['Blocker', 'Major', 'Minor', 'Nit'] },
          file: { type: 'string' },
          summary: { type: 'string' },
          failure_scenario: { type: 'string' },
        },
        required: ['severity', 'file', 'summary', 'failure_scenario'],
      },
    },
    summary: { type: 'string' },
  },
  required: ['item', 'verdict', 'deliverables_met', 'validation_cross_check', 'false_claims', 'scope_boundary_ok', 'findings', 'summary'],
}

// safeAgent — try/catch над bare await agent() (вне parallel()/pipeline()): без обёртки
// бросок агента роняет весь прогон вместо контролируемого null, который ловит if (!res).
async function safeAgent(prompt, opts) {
  try { return await agent(prompt, opts) } catch (e) { log(`agent error (${opts.label || '?'}): ${e.message || e}`); return null }
}

function implPrompt(item) {
  return `Ты исполнитель item'а ${item.id} («${item.title}») мастер-плана ${PLAN} (репо ${REPO}).
${CTX}
ПОРЯДОК:
1. Прочитай ЦЕЛИКОМ ТЗ item'а: файл ${PLAN_DIR}/phases/P4.md, раздел «### ${item.id} —» — все 16 полей (Status, Intent, Why, Scope Included, Scope Excluded, Inputs, Files, Required Reads, Implementation Rules, Code Guidance, Validation, Deliverables, Completion Notes, Pending Work, Known Deviations, Escalation Needed). Это единственный источник; spec_read=true только после этого.
2. Если Implementation Rules несут пункт (0)/precondition-гейт — прогони его КАК НАПИСАНО ДО первой мутации и впиши вывод в precondition_detail. Отказ любого условия → precondition_ok=false, done=false, escalation с названным путём и владельцем, ни одного файла не трогать.
3. Прочитай Required Reads item'а по объявленному порядку (пути — относительно ${REPO}).
4. Исполни Scope Included ЦЕЛИКОМ по Implementation Rules и Code Guidance. Scope Excluded не трогай ни байтом.
5. Прогони КАЖДУЮ команду поля Validation (working dir ${REPO}) и впиши дословный вывод/exit-код в validation_report.
6. Коммить(ы) Conventional Commits на русском, ТОЛЬКО файлы из Files item'а. \`git add\` по путям, НЕ \`-A\`/\`.\`.
7. Посчитай и впиши в boundary_codes коды границ по каноническому вызову компилятора (\`python3 -m task.task_contract …\`, как это делают тела команд plan-exec/plan-close), маршрутом ИСПОЛНИТЕЛЯ (D75) — не пином ревьюера. Зелёное — РОВНО \`allow\`/\`allow\` (D76: \`n/a\` не зелёное).
8. files_outside_scope — честно, если что-то тронуто вне Files.

ЗАПРЕЩЕНО: ослаблять Validation ради зелёного; подгонять реализацию под желаемый результат (см. «Анти-подгонка»/«Анти-самообман» в Code Guidance спеки); объявлять done=true при незакрытом precondition; писать в отчёт то, что не прогонял руками; выходить за границу наружу (push/tag/релиз/флот/чужие планы).
ЭСКАЛАЦИЯ (plan-protocol §10): конфликт правил / неисполнимое требование / расхождение спеки с кодом → done=false + escalation с причиной, БЕЗ импровизации на месте.`
}

function verifyPrompt(item) {
  return `Ты МЕХАНИЧЕСКИЙ верификатор item'а ${item.id}. Тебе НЕЧЕГО защищать: ты НЕ чинишь код, НЕ интерпретируешь результаты, НЕ решаешь, сдан ли item — только выполняешь команды и возвращаешь их СЫРОЙ вывод дословно (включая ненулевые exit-коды).
Репо: ${REPO}.

Источник команд — поле **Validation:** раздела «### ${item.id} —» файла ${PLAN_DIR}/phases/P4.md. Найди его сам и прогони КАЖДУЮ перечисленную команду по порядку.

Дополнительно выполни и верни дословно:
- \`git status --porcelain\` (working tree ${REPO})
- \`git log --oneline -5\` и \`git show --stat HEAD\`
- \`python3 packages/task/scripts/plan-lint.py ${PLAN_DIR}\` (число ERROR/WARN)
- \`git log --oneline origin/main..HEAD | wc -l\` и \`git tag --points-at HEAD\` (доказательство, что наружу ничего не ушло)

Ничего не добавляй от себя, ничего не чини, ни одного файла не трогай. Вывод команд — единственное, что от тебя нужно.`
}

function reviewPrompt(item, verify, boundaryCodes) {
  return `Ты adversarial-ревьюер item'а ${item.id} мастер-плана ${PLAN}. Read-only: КОД НЕ ПРАВИШЬ, план НЕ ПРАВИШЬ.
${CTX}
Механический верификатор (отдельный агент, которому нечего защищать) прогнал проверки — СЫРОЙ вывод; верь ЕМУ и git-диффу, а НЕ прозе исполнителя:
${verify}

ТЗ item'а — ${PLAN_DIR}/phases/P4.md, раздел «### ${item.id} —» (прочитай сам, целиком).

**ГРАНИЦА ТВОЕГО ПРЕДМЕТА (читай до первой находки).** Bookkeeping плана для ЭТОГО item'а —
Status, Completion Notes, Pending Work, Known Deviations, строка «## Phase Status», запись в
journal.jsonl, handoff.md — пишется стадией \`Close\` ПОСЛЕ твоего вердикта, а не исполнителем
до него. Их незаполненность на момент ревью — КОНСТРУКЦИЯ пайплайна, а не дефект item'а: она
НЕ находка, НЕ Blocker и НЕ основание для RED. Ты судишь ПРОДУКТ item'а: дифф против Scope
Included/Files/Implementation Rules/Deliverables и результаты Validation. Исключение ровно
одно: если исполнитель НЕ ПОСЧИТАЛ коды границ или код ≠ \`allow\` — это находка по существу
(D76/Ф2); сам факт, что посчитанные коды ещё не перенесены в Completion Notes, находкой НЕ
является. Посчитанное исполнителем, дословно: «${boundaryCodes}».

ПОРЯДОК (начни с диффа, не с отчёта исполнителя — иначе якорь):
1. \`git log\`/\`git show --stat\` по коммиту(ам) item'а в ${REPO} — что РЕАЛЬНО изменилось.
2. Сверь дифф со Scope Included/Files/Implementation Rules/Deliverables спеки построчно; заполни scope_boundary_ok (мутации вне Files, push/tag/релиз, правки чужих планов — всё это false).
3. validation_cross_check: что реально зелёное/красное по Verify-выводу — совпадает ли с заявленным исполнителем (расхождение → false_claims).
4. Помни «красное остаётся красным»: честно названное расхождение — ПРАВИЛЬНЫЙ исход; дефект — СКРЫТОЕ или подогнанное.
5. Отдельно проверь ПОСЧИТАННЫЕ коды границ (блок «ГРАНИЦА ТВОЕГО ПРЕДМЕТА» выше): код ≠ \`allow\` на любой из границ (включая \`pre_final: n/a\`) — находка Major (D76); коды не посчитаны вовсе — находка (ровно Ф2, ради которой существует P4.4).
6. Только теперь ищи расхождение фактов с тем, что заявлено о работе.

Вердикт: RED — Scope Included не исполнен / есть Blocker / скрытое либо подогнанное расхождение / нарушена граница наружу; ATTENTION — исполнено с честно названным долгом; GREEN — чисто, всё по спеке.
Не занижай severity ради «не останавливать пайплайн»: RED останавливает ВЕСЬ прогон — это правильно, не повод для самоцензуры вердикта.
Каждая находка несёт конкретный failure scenario.`
}

function closePrompt(item, impl, review, verify, isLast) {
  return `Ты docs-curator плана ${PLAN}. Работа механическая, thinking низкий. КОД НЕ ТРОГАТЬ — только bookkeeping плана.
${CTX}
Item ${item.id}. Факты верификатора (сырой вывод):
${verify}
Отчёт исполнителя: ${JSON.stringify(impl)}
Вердикт ревью: ${JSON.stringify(review)}

ЗАДАЧА (из МАШИННЫХ фактов выше, не из памяти/домысла):
1. ${PLAN_DIR}/phases/P4.md, раздел «### ${item.id}»: Status (🟢 Done, если verdict=GREEN, deliverables_met=true, files_outside_scope пуст; иначе 🟠 Done with deviations — plan-protocol §6 material-предикат), Completion Notes (факты: коммиты, числа Validation дословно из verify, **обязательно напечатанные коды \`pre_mutation\`/\`pre_final\` из impl.boundary_codes** и фактический маршрут исполнителя), Pending Work, Known Deviations (каждое расхождение из review.findings/impl.known_deviations), Escalation Needed = no.
2. Строка item'а в таблице «## Phase Status» файла phases/P4.md (колонка Updated — сегодняшняя ISO-дата).
3. ${PLAN_DIR}/plan.md: «## 4. Phase Index & Status Board» строка P4 (счётчик 🟢/5) + «## 6. Update Log» — ОДНА строка формата «${item.id} закрыт: <суть одной строкой> — детали см. phases/P4.md ${item.id} Completion Notes» (≤300 символов, пересказ Completion Notes запрещён) + бамп поля Version в «## 0. Meta».
4. journal.jsonl: append-запись закрытия ${item.id} по формату уже существующих строк (сверься с ними, схему не изобретай).
5. Перезапиши handoff.md: «# HANDOFF — <ISO-дата> — after ${item.id}», Next — launch-block ${isLast ? 'на `close: task:plan-close ' + PLAN + ' P4`' : 'на следующий item пайплайна'}, плюс Done/Remaining/Sources of truth/Open risks.
6. \`python3 packages/task/scripts/plan-lint.py ${PLAN_DIR}\` — новых ошибок от диффа быть не должно.
7. \`git add ${PLAN_DIR} && git commit -m "docs(plan): закрыть ${item.id} — статус, completion notes, handoff (${PLAN})"\`.

Верни одной строкой: статус item'а + sha bookkeeping-коммита.`
}

function stopClosePrompt(item, stage, reason) {
  return `Ты docs-curator плана ${PLAN}. Пайплайн ОСТАНОВЛЕН на ${item.id} (стадия: ${stage}); следующие items НЕ стартуют.
${CTX}
Причина: ${reason}

ЗАДАЧА (план не имеет права лгать о состоянии):
1. phases/P4.md «### ${item.id}»: Status = 🔴 Blocked, Escalation Needed = yes + причина, Pending Work = что успели (sha частичных коммитов, если есть).
2. Зафиксируй \`git status --porcelain\` в Pending Work item'а. Незакоммиченное не выбрасывай: \`git stash push -m "P4-${item.id}-partial"\` и назови stash-ref, если есть что стешить.
3. plan.md «## 4. Phase Index & Status Board» строка P4 + «## 6. Update Log» (одна строка про остановку).
4. Перезапиши handoff.md: Next — launch-block на РАЗБОР остановки (\`design-item: task:plan-design ${PLAN} ${item.id}\`, Opus/high, НОВАЯ сессия) со scope-payload (РЕЖИМ/ВХОД/СКОУП/НЕ ТРОГАТЬ), НЕ на следующий item.
5. \`python3 packages/task/scripts/plan-lint.py ${PLAN_DIR}\`; \`git add ${PLAN_DIR} && git commit -m "docs(plan): остановка фазы P4 на ${item.id} — 🔴 Blocked, handoff (${PLAN})"\`.`
}

// ── Items пайплайна: модель/effort/глубина review — §3 Routing plan.md (D90 — порядок) ──
const ITEMS = [
  { id: 'P4.4', title: 'Машинный гейт напечатанных кодов границ в plan_lint (ремонт Ф2)', model: 'sonnet', effort: 'high', reviewClass: 'full' },
  { id: 'P4.5', title: 'Оплатить Contribution gate: минорные бампы analyst/harness', model: 'sonnet', effort: 'medium', reviewClass: 'light' },
  { id: 'P4.1', title: 'Проверить external provider/core hypotheses по коду', model: 'opus', effort: 'high', reviewClass: 'full' },
  { id: 'P4.2', title: 'Добавить read-only effective source doctor', model: 'sonnet', effort: 'medium', reviewClass: 'light' },
  { id: 'P4.3', title: 'Синхронизировать docs и собрать Owner rollout/release packet', model: 'opus', effort: 'high', reviewClass: 'full' },
]

// START_FROM — дозапуск ХВОСТА фазы после остановки: items ДО указанного ID уже терминальны в
// плане (проверяется по `phases/P4.md`, не по памяти) и повторному прогону не подлежат — иначе
// заход переисполнит закрытый item и создаст второй носитель того же факта. Пустая строка —
// полный прогон с начала. Порядок D90 при этом НЕ нарушается: хвост исполняется в том же порядке.
const START_FROM = 'P4.3'
const startIdx = START_FROM ? ITEMS.findIndex(i => i.id === START_FROM) : 0
if (startIdx < 0) throw new Error(`START_FROM="${START_FROM}" не найден среди items: ${ITEMS.map(i => i.id).join(', ')}`)
const QUEUE = ITEMS.slice(startIdx)
if (startIdx > 0) log(`START_FROM=${START_FROM}: пропущены уже терминальные ${ITEMS.slice(0, startIdx).map(i => i.id).join(', ')} — исполняется хвост ${QUEUE.map(i => i.id).join(' → ')}.`)

log(`wf-P4: ${ITEMS.length} items строго последовательно (${ITEMS.map(i => i.id).join(' → ')}) — стоп на первом RED/blocked останавливает ВЕСЬ прогон. Наружу (push/tag/релиз/флот) не выходит ни один агент: решение G1 остаётся владельцу.`)

const done = []
let stoppedAt = null

for (const item of QUEUE) {
  const isLast = item.id === ITEMS[ITEMS.length - 1].id

  phase('Impl')
  const impl = await safeAgent(implPrompt(item), {
    label: `impl:${item.id}`, phase: 'Impl', model: item.model, effort: item.effort, schema: IMPL_SCHEMA,
  })
  if (!impl || !impl.spec_read || !impl.precondition_ok || !impl.done) {
    const reason = !impl ? 'агент не вернул результат'
      : !impl.spec_read ? 'ТЗ item\'а не прочитано из phases/P4.md — исполнение по домыслу запрещено'
      : !impl.precondition_ok ? `precondition-гейт не пройден: ${impl.precondition_detail}`
      : (impl.escalation && impl.escalation !== 'no' ? `ESCALATION: ${impl.escalation}` : 'done=false (Scope Included не закрыт)')
    await safeAgent(stopClosePrompt(item, 'impl', reason), { label: `stop-close:${item.id}`, phase: 'Close', model: 'sonnet', effort: 'low' })
    done.push({ item: item.id, stopped: `impl: ${reason}` })
    stoppedAt = item.id
    log(`СТОП пайплайна на ${item.id} (impl): ${reason}. Следующие items НЕ стартуют.`)
    break
  }

  phase('Verify')
  const verify = await safeAgent(verifyPrompt(item), { label: `verify:${item.id}`, phase: 'Verify', model: 'sonnet', effort: 'low' })

  phase('Review')
  const review = await safeAgent(reviewPrompt(item, verify || '(верификатор не вернул результат — ревьюер учитывает это как риск)', impl.boundary_codes), {
    label: `review:${item.id}`, phase: 'Review', ...REVIEW_FOR[item.reviewClass], schema: REVIEW_SCHEMA,
  })
  if (!review || review.verdict === 'RED' || review.scope_boundary_ok === false) {
    const reason = !review ? 'ревьюер не вернул результат'
      : review.verdict === 'RED' ? `RED: ${review.summary}`
      : `нарушена граница скоупа/наружу: ${review.summary}`
    await safeAgent(stopClosePrompt(item, 'review', reason), { label: `stop-close:${item.id}`, phase: 'Close', model: 'sonnet', effort: 'low' })
    done.push({ item: item.id, stopped: `review: ${reason}`, findings: review ? review.findings : [] })
    stoppedAt = item.id
    log(`СТОП пайплайна на ${item.id} (review). Следующие items НЕ стартуют.`)
    break
  }

  phase('Close')
  const close = await safeAgent(closePrompt(item, impl, review, verify || '(верификатор не вернул результат)', isLast), {
    label: `close:${item.id}`, phase: 'Close', model: 'sonnet', effort: 'low',
  })

  done.push({
    item: item.id, stopped: null, verdict: review.verdict,
    boundary_codes: impl.boundary_codes, validation_report: impl.validation_report,
    findings: review.findings, close_result: close,
  })
  log(`✅ ${item.id} — ${review.verdict} (${review.findings.length} находок), коды границ: ${impl.boundary_codes}. Терминальных: ${done.filter(d => !d.stopped).length}/${ITEMS.length}.`)
}

// Терминальность считается по ОЧЕРЕДИ этого захода (QUEUE), не по всей фазе: пропущенные
// START_FROM'ом items уже закрыты в плане — их статус берётся из `phases/P4.md`, а не отсюда.
const allTerminal = done.length === QUEUE.length && done.every(d => !d.stopped)

return {
  pipeline: `${QUEUE.map(i => i.id).join(' → ')} (фаза P4, строго последовательно, D90/D93${startIdx > 0 ? `; хвост после START_FROM=${START_FROM}` : ''})`,
  items: done.map(d => ({
    item: d.item,
    stopped: d.stopped || null,
    verdict: d.verdict || null,
    boundary_codes: d.boundary_codes || null,
    findings: (d.findings || []).map(f => `${f.severity}: ${f.summary}`),
    validation_report: d.stopped ? null : d.validation_report,
  })),
  all_terminal: allTerminal,
  stopped_at: stoppedAt,
  next: allTerminal
    ? `Все пять items фазы P4 терминальны → close: task:plan-close ${PLAN} P4 (implementation/low), затем audit-phase: task:plan-audit ${PLAN} P4 (frontier/xhigh, НОВАЯ сессия). Owner packet собран P4.3 — решение G1 (fleet/consumers/FOREMAN/tag/push/release либо hold) принимает ВЛАДЕЛЕЦ, ни один агент этого прогона наружу не выходил.`
    : `Прогон остановлен на ${stoppedAt}. Следующий шаг — разбор остановки: design-item: task:plan-design ${PLAN} ${stoppedAt} (frontier/high, НОВАЯ сессия), вход — handoff.md и Pending Work остановленного item'а.`,
}
