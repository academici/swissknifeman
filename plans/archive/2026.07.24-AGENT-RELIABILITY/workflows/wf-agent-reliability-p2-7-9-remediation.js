// Ремонт-реопен D70 (2026.07.24-AGENT-RELIABILITY, фаза P2): P2.7 → P2.8 → P2.9, СТРОГО
// последовательно (pipeline, не parallel) — каждый item потребляет терминальность
// предыдущего (P2.8 читает Deliverables P2.7 + P2.6, P2.9 отчитывается о фактах P2.6-P2.8).
// Предусловие ВСЕГО прогона: P2.6 закоммичен и терминален (исполняется другой сессией —
// не забота этого скрипта; Impl-агент P2.7 обязан перепроверить это сам, см. spec Rule (0)).
//
// Шаблон: wf-dev-slice.js (dev-тип, две-типа-матрица workflow-craft) + прецедент
// wf-corex-core-p1r-remediation.js (Impl → Verify(механический, bash, read raw) →
// Review(adversarial, risk-адаптивный) → Close(bookkeeping) на реальных items мастер-плана).
// Verify — ОТДЕЛЬНЫЙ агент без цели «сдать item»: гонит Validation-команды из спеки как есть
// и возвращает сырой вывод/exit-коды, ничего не интерпретируя — это и есть анти-self-deception
// механизм (Review судит по сырым фактам Verify + git-диффу, НЕ по прозе исполнителя).
export const meta = {
  name: 'wf-P2.7-P2.9',
  description: 'Ремонт-реопен D70 фазы P2 (2026.07.24-AGENT-RELIABILITY): P2.7 write-site/канон → P2.8 воспроизводимость доказательства → P2.9 реконсиляция записи, строго последовательно',
  whenToUse: 'Запускать НОВОЙ сессией после того, как P2.6 закоммичен и терминален (исполняется в другой сессии — предусловие, не забота этого скрипта). Запуск: Workflow({scriptPath}) — БЕЗ args (embedded-конфиг, известная ловушка named-workflow передаёт args строкой)',
  phases: [
    { title: 'Impl', detail: 'реализация Scope Included item\'а + прогон Validation исполнителем + коммит (модель — из §3 Routing item\'а)' },
    { title: 'Verify', detail: 'МЕХАНИЧЕСКИЙ агент (sonnet/low, bash): независимый прогон команд поля Validation, сырой вывод/exit-коды, без интерпретации' },
    { title: 'Review', detail: 'adversarial-ревью диффа против Deliverables/Implementation Rules (risk-класс из §3 Routing: full → opus/high, light → sonnet/medium), видит ТОЛЬКО дифф+Verify, не отчёт Impl' },
    { title: 'Close', detail: 'bookkeeping (sonnet/low): Status/Completion Notes/Known Deviations/Escalation item\'а ТОЛЬКО из машинных фактов Verify+Review, Status Board, Update Log, journal, handoff' },
  ],
}

// ── Конфиг (embedded, НЕ args-строка) ────────────────────────────────────────
const REPO = '/home/vostrikov/projects/packages/swissknifeman'
const PLAN_DIR = 'plans/2026.07.24-AGENT-RELIABILITY'
if (!REPO.startsWith('/')) throw new Error(`REPO должен быть абсолютным путём: "${REPO}"`)

const CTX = `
КОНТЕКСТ (репо ${REPO}, план ${PLAN_DIR}):
- Монорепо academici (swissknifeman). Мастер-план 2026.07.24-AGENT-RELIABILITY, фаза P2
  РЕОПЕНЕНА по D70 после RED-аудита (\`phases/P2.md\` § \`## Audit P2 — 2026-07-26\`, находки F1-F15).
  Ремонт — четыре последовательных item'а по поверхности мутации: P2.6 (packages/task/lib/**,
  чужая забота — исполняется в другой сессии, предусловие) → P2.7 (тела команд + канон) →
  P2.8 (воспроизводимость доказательства P2.5) → P2.9 (реконсиляция записи, без кода).
- ПОРЯДОК СТРОГИЙ: P2.8 потребляет Deliverables P2.7 (и P2.6), P2.9 отчитывается о ФАКТАХ
  закрытия P2.6-P2.8. Красный/blocked item ОСТАНАВЛИВАЕТ весь прогон — следующие items НЕ
  стартуют (в отличие от независимых items в других волнах): зависимость реальная, не мнимая.
- Каждый item несёт полное ТЗ (16 полей plan-protocol) — оно приведено НИЖЕ дословно из
  \`phases/P2.md\` (SSOT). Агент читает его как единственный источник Scope/Files/Validation/
  Implementation Rules/Code Guidance — не домысливает и не сверяется с памятью.
- Коммиты — Conventional Commits на русском; \`git add\` ТОЛЬКО по путям из Files item'а + файлы
  плана при bookkeeping. \`git add -A\`/\`git add .\` ЗАПРЕЩЕНЫ.
- \`assert_generated_scope.py\` НЕ запускается ни одним из этих items (P2.6-P2.9 отсутствуют в
  \`remediation-map.json::baseline_owners\` — сознательная граница реопена), \`base-sha.txt\` не
  создаётся; сверка Scope — ручная, прогоном \`git show --stat <item-коммит>\` против Files.
- Красное остаётся красным: если Validation/пересчитанная цифра расходится с ожиданием —
  ЭТО ЧЕСТНЫЙ РЕЗУЛЬТАТ, фиксируется как есть (Known Deviations/находка), НЕ подгоняется под
  зелёное и НЕ скрывается. Silent cap на статус ЗАПРЕЩЁН.
`

// Risk-класс review — из §3 Routing plan.md (P2.7 full, P2.8 full, P2.9 light).
// ДОПУЩЕНИЕ (не задано явно в plan.md/roadmap.md, разумный дефолт по прецеденту репо):
// full → opus/high (adversarial-панель одного ревьюера, полная глубина — как task:review
// и review-стадия wf-corex-core-p1r-remediation.js для high-risk items); light → sonnet/medium
// (свежий контекст, но не полная глубина — соразмерно item'у без мутации кода).
const REVIEW_FOR = {
  full: { model: 'opus', effort: 'high' },
  light: { model: 'sonnet', effort: 'medium' },
}

const IMPL_SCHEMA = {
  type: 'object',
  properties: {
    item: { type: 'string' },
    precondition_ok: { type: 'boolean', description: 'Implementation Rule (0)/(precondition) спеки перепроверена ЭТИМ агентом и прошла — иначе done обязан быть false' },
    precondition_detail: { type: 'string', description: 'вывод команд precondition-гейта дословно' },
    done: { type: 'boolean', description: 'true ТОЛЬКО если Scope Included исполнен и precondition_ok=true; красная Validation сама по себе НЕ обязана давать done=false, если это ожидаемый честный исход по Implementation Rules (см. "красное остаётся красным") — но тогда это обязано быть названо в known_deviations' },
    validation_report: { type: 'string', description: 'КАЖДАЯ команда поля Validation спеки, прогнанная исполнителем, с её выводом/exit-кодом дословно — не пересказ' },
    commits: { type: 'array', items: { type: 'string' } },
    files_outside_scope: { type: 'array', items: { type: 'string' }, description: 'тронутое вне Files item\'а — честно' },
    pending_work: { type: 'string' },
    known_deviations: { type: 'string' },
    escalation: { type: 'string', description: '"no" либо причина + триггер (plan-protocol §10)' },
  },
  required: ['item', 'precondition_ok', 'precondition_detail', 'done', 'validation_report', 'commits', 'files_outside_scope', 'pending_work', 'known_deviations', 'escalation'],
}

const REVIEW_SCHEMA = {
  type: 'object',
  properties: {
    item: { type: 'string' },
    verdict: { type: 'string', enum: ['GREEN', 'ATTENTION', 'RED'] },
    deliverables_met: { type: 'boolean' },
    validation_cross_check: { type: 'string', description: 'сверка Verify-вывода с ожиданиями спеки: что реально зелёное/красное, совпадает ли с отчётом Impl' },
    false_claims: { type: 'array', items: { type: 'string' }, description: 'заявлено Impl в отчёте, но Verify/дифф этого не подтверждают' },
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
  required: ['item', 'verdict', 'deliverables_met', 'validation_cross_check', 'false_claims', 'findings', 'summary'],
}

// safeAgent — try/catch над bare await agent() (вне parallel()/pipeline()): без обёртки
// бросок агента роняет весь прогон вместо контролируемого null, который ловит if (!res).
async function safeAgent(prompt, opts) {
  try { return await agent(prompt, opts) } catch (e) { log(`agent error (${opts.label || '?'}): ${e.message || e}`); return null }
}

// ── Спеки items (embedded ДОСЛОВНО из phases/P2.md — единственный SSOT ТЗ; 16 полей
// plan-protocol целиком, включая пустые Completion Notes/Pending Work/Known Deviations —
// их и обязан заполнить факт-based Close-агент). Не пересказ, не сокращение.
const SPEC_P27 = `
### P2.7 — Подключить write-site в командах и сделать канон истинным

**Status:** ⬜ Not started
**Intent:** RAG:— (repo-grounded: \`packages/task/commands/plan-exec.md:53-60,100-104\`, \`plan-close.md:42-45\`; \`packages/skiller/skills/general/plan-protocol/SKILL.md:1084-1090\`, \`SKILL.ru.md:1106-1112\`; plan-grounded: D8/D70, находки F1/F2). Заменить прозаические cross-reference-абзацы ИСПОЛНЯЕМЫМИ шагами \`build → check\` с fail-closed поведением в двух канонических точках, доставить недостающий evidence-bundle template и bundle-требования канона — и тем сделать уже опубликованное утверждение канона ИСТИННЫМ, а не смягчить его.
**Why:** RAG:— (repo-grounded: \`## Audit P2 — 2026-07-26\` F1 *failure_scenario*; \`research/07\` §3, §7). Канон \`plan-protocol@2.12.0\` раздаётся флоту через \`general\`/\`core\` units и утверждает, что команды зовут компилятор. Агент во внешнем проекте читает §13, считает pre-mutation/pre-final машинно проверенными и пропускает ручной гейт — контроль становится СЛАБЕЕ, чем до 2.12.0: раньше проза была единственным носителем и её читали, теперь она объявлена реализованной. Это ровно тот failure mode, ради которого написан план (§1: зелёный контроль при живом дефекте).
**Scope Included:** исполняемые шаги в \`plan-exec.md\` (pre-mutation, шаг 2) и \`plan-close.md\` (pre-final, шаг 4) — вызов \`python3 -m task.task_contract build … | check\` с ОБЯЗАТЕЛЬНЫМ, а не условным, характером и названным поведением на отказ; синхронная правка \`plan-run.md\`/\`plan-audit.md\` там, где они наследуют те же чекпоинты; \`snippets/source-evidence-template.md\` — недоставленный \`Files\` P2.2; bundle-требования (минимизация, запрет секретов/CoT/сырых тел, детерминированные manifest+verifier) в билингву канона; переформулировка §13 канона в утверждение, подкреплённое исполняемым доказательством; литеральный тест канона; бамп \`plan-protocol\` → \`2.13.0\`, \`skiller\` package API + \`general\`/\`core\` units → \`0.6.0\`, \`task\` plugin/routing → \`0.7.0\` с полной регенерацией обеих публикаций.
**Scope Excluded:** любая правка \`packages/task/lib/**\` (владелец — P2.6; если производитель ведёт себя не так, как нужно команде, — это D#-запись и реопен P2.6, не тихая правка здесь); \`plan_lint.py\` tiered-portability lint, его тесты и \`PORTABILITY_TIER_CANON_DATE\` (D69); \`repository-bootstrap@0.2.0\`, его 13 приватных канонов, 27 root-проекций и combined lock — read-only, байт-идентичны; \`artifacts/P1.1/remediation-map.json\` и \`assert_generated_scope.py\`; fresh-subagent dispatch (P3.4); \`artifacts/P2.5/**\` (P2.8); бухгалтерия закрытых items (P2.9); чужие планы FOREMAN/ECO-OPT.
**Inputs:** Deliverables P2.6 (\`task_contract build\`/\`bundle_lint\` существуют и протестированы — БЕЗ них item не стартует) · \`findings/P2.6-contract-mapping.md\` · аудит-блок F1/F2 · \`research/07-p2-reopen-remediation.md\` §§3,7.
**Files:** \`packages/task/commands/plan-exec.md\` · \`packages/task/commands/plan-close.md\` · \`packages/task/commands/plan-run.md\` · \`packages/task/commands/plan-audit.md\` · \`packages/task/tests/test_canon_literals.py\` · \`packages/task/tests/test_plan_command_routing.py\` · \`packages/task/tests/fixtures_data/claude-command-golden/\` · \`packages/task/.claude-plugin/plugin.json\` · \`packages/task/.codex-plugin/plugin.json\` · \`packages/task/configs/command-routing.json\` · \`packages/task/adapters/codex/\` · \`packages/task/docs/reference/provider-commands.md\` · \`packages/skiller/skills/general/plan-protocol/SKILL.md\` · \`packages/skiller/skills/general/plan-protocol/SKILL.ru.md\` · \`packages/skiller/skills/general/plan-protocol/snippets/source-evidence-template.md\` · \`packages/skiller/package.json\` · \`packages/skiller/configs/publication-versions.json\` · \`packages/skiller/skills/general/.claude-plugin/plugin.json\` · \`packages/skiller/skills/general/.codex-plugin/plugin.json\` · \`packages/skiller/adapters/codex/core/\` · \`packages/skiller/skills.json\` · \`packages/skiller/skills/_index.md\` · \`packages/skiller/docs/guide/graph.md\` · \`packages/skiller/docs/guide/budget.md\` · \`.agents/plugins/marketplace.json\` · \`.claude-plugin/marketplace.json\` · \`CHANGELOG.md\`.
**Required Reads:** 1) \`plans/2026.07.24-AGENT-RELIABILITY/research/07-p2-reopen-remediation.md\` §3 и §7 (ПЕРВЫМ) 2) \`plans/2026.07.24-AGENT-RELIABILITY/phases/P2.md\` § \`## Audit P2 — 2026-07-26\` находка F1 целиком (включая \`PROMOTE-CANDIDATE\`) 3) \`plans/2026.07.24-AGENT-RELIABILITY/findings/P2.6-contract-mapping.md\` 4) \`packages/task/lib/task/task_contract.py\` (форма CLI \`build\`/\`check\`, коды отказов) 5) \`packages/task/commands/plan-exec.md\` (весь) 6) \`packages/task/commands/plan-close.md\` (весь) 7) \`packages/task/commands/plan-run.md\` (весь) 8) \`packages/task/commands/plan-audit.md\` (весь) 9) \`packages/skiller/skills/general/plan-protocol/SKILL.md\` §13 и §§3–10 10) \`packages/skiller/skills/general/plan-protocol/SKILL.ru.md\` те же разделы 11) \`packages/skiller/skills/general/plan-protocol/snippets/handoff-template.md\` и \`launch-block-template.md\` (регистр и форма snippets — образец для нового) 12) \`plans/2026.07.24-AGENT-RELIABILITY/root/contracts/plan-portability-v1.md\` § bundle-требований (SSOT формулировок — канон их ЦИТИРУЕТ, не переписывает) 13) \`plans/2026.07.24-AGENT-RELIABILITY/root/contracts/task-contract-v1.md\` §§ Pre-mutation/Pre-final predicate 14) \`plans/2026.07.24-AGENT-RELIABILITY/phases/P2.md\` P2.2 Completion Notes (полный ритуал двойного бампа и регенерации: какие команды, в каком порядке, что обязано быть no-op) 15) \`packages/task/tests/test_canon_literals.py\` 16) \`packages/skiller/scripts/check-translations.sh\` (механика \`--stamp\`) 17) \`packages/skiller/configs/publication-versions.json\` 18) \`packages/skiller/CLAUDE.md\` 19) \`packages/skiller/skills/repository-bootstrap/skill-authoring/SKILL.md\` (билингва: RU — полный источник, EN — компактный канон) 20) \`packages/skiller/skills/architect/package-contribution-protocol/SKILL.md\` 21) \`AGENTS.md\`.
**Implementation Rules:** RAG:— (repo-grounded: \`plan-exec.md:53-60\`, \`SKILL.md:1084-1090\`; plan-grounded: D8/D23/D26/D27/D47/D70). **(0) Precondition-гейт до первой записи:** P2.6 закоммичен и терминален, \`python3 -m task.task_contract build --plan-dir plans/2026.07.24-AGENT-RELIABILITY --item P2.7\` печатает валидный контракт, \`git status --porcelain\` пуст по \`packages/task/**\` и \`packages/skiller/**\`. Отказ любого условия — стоп до первой мутации с названным путём и владельцем. \`assert_generated_scope.py\` не запускается, \`artifacts/P2.7/base-sha.txt\` не создаётся (та же граница, что в P2.6 (0)). **(1) Шаг обязателен или его нет.** Формулировка «при наличии смонтированного Task Contract JSON» и любые её синонимы ЗАПРЕЩЕНЫ: команда либо всегда собирает контракт и проверяет его, либо шага не существует. Текст шага обязан назвать: точную команду, что считается зелёным, и ЧТО ДЕЛАТЬ на каждый класс отказа (какой код → стоп/эскалация/D#). Обходной путь на случай недоступности модуля называется явно и остаётся fail-closed (нет модуля → стоп, а не «продолжай как раньше»). **(2) Канон говорит правду и это проверяется.** §13 обеих языковых версий переписывается так, чтобы утверждение соответствовало фактическому поведению ПОСЛЕ этого item'а, и получает литеральный тест в \`test_canon_literals.py\`, который краснеет, если формулировку изменят без изменения команд. Правило, вынесённое из F1 и обязательное к соблюдению здесь: **утверждение о поведении публикуется в канон только вместе с тестом, который его фальсифицирует.** **(3) Билингва.** RU (\`SKILL.ru.md\`) — полный источник, EN (\`SKILL.md\`) — компактный канон; правки идут парой, \`check-translations.sh\` обязан быть чист. Bundle-требования не переписываются заново: канон ЦИТИРУЕТ \`plan-portability-v1.md\` (SSOT), а \`snippets/source-evidence-template.md\` даёт исполнимую форму — структуру манифеста, обязательные поля, команду верификации и явный перечень запрещённых классов содержимого. **(4) Порядок публикации (дословно как в P2.2).** Сначала версии: \`plan-protocol\` → \`2.13.0\` (SKILL.md + SKILL.ru.md, \`check-translations.sh --stamp\` трогает только эти два файла), \`packages/skiller/package.json\` → \`0.6.0\`, \`publication-versions.json::units.{core,general}\` → \`0.6.0\`, \`task\` plugin/routing \`plugin_version\` → \`0.7.0\`. Затем полная регенерация: \`render-provider-commands.py --write --repair-owned\` → \`--check\` no-op; \`skiller registry\` → \`registry --check\` «артефакты актуальны». \`claude-command-golden/**\` синхронизируется вручную (не покрыт \`--write\`), \`provider-commands.md\` регенерируется тем же API. Изменённый канонический источник при переиспользованной версии, частичное дерево, изменённый лок под тем же кортежем, задетый непричастный unit, утечка приватного бакета или не-no-op второй прогон — провал item'а. \`skm\`/\`repository-bootstrap\` остаются байт-идентичны (подтвердить \`git status\`). **(5) Self-conformance.** Новый write-site прогоняется на ЭТОМ плане внутри item'а: собрать и проверить контракт для минимум трёх реальных items (один закрытый 🟢, один закрытый 🟠, текущий) и вписать результат каждого в Completion Notes с точным кодом отказа там, где он есть. Отказ на закрытом 🟠 item'е — ожидаемый и правильный исход, а не повод ослабить предикат. **(6) Companion-дифф.** Если регенерация задевает путь вне owner-набора карты P1.1 (прецедент \`provider-commands.md\`, D69), он выносится отдельным атомарным companion-коммитом ДО item-коммита; карта НЕ правится. **(7) И1–И3.** Каждый новый запрет в каноне называет владельца, причину и ПРОХОД (эскалация → D#).
**Code Guidance:** Не пересказывать логику компилятора прозой второй раз — команда ЗОВЁТ, объяснение остаётся только для интерпретации отказа. Тексты команд правятся хирургически: только два чекпоинта и наследующие их строки; переписывание команд «заодно» — scope drift и находка аудита. Новый snippet пишется в регистре существующих (\`handoff-template.md\`/\`launch-block-template.md\`): исполнимая форма, а не эссе. **Анти-подгонка:** если исполняемый шаг оказывается красным на реальных items этого плана, ПРАВИЛЬНЫЙ исход — оставить его красным и завести D#/Known Deviations, а НЕ ослабить предикат, не сделать шаг условным и не сузить его до «предупреждения». **Анти-самообман:** «канон говорит, что зовём» ≠ «зовём»: доказательством считается только прогон шага на реальном item'е с приложенным выводом; ссылка на модуль доказательством не является — ровно это и было находкой F1. Если после честной попытки выяснится, что обязательный шаг ломает реальный поток закрытия (например, ни один существующий item не может собрать валидный контракт), исполнитель СТОПИТСЯ, зафиксирует измерение и эскалирует D#-записью выбор между сужением шага и ремонтом \`build\` в P2.6 — тихая замена обязательности на условность запрещена явно.
**Validation:** \`PYTHONPATH=packages/task/lib python3 -m unittest discover -s packages/task/tests -p 'test_canon_literals.py'\` · \`PYTHONPATH=packages/task/lib python3 -m unittest discover -s packages/task/tests -p 'test_plan_command_routing.py'\` · \`PYTHONPATH=packages/task/lib python3 -m unittest discover -s packages/task/tests -p 'test_task_contract.py'\` · \`PYTHONPATH=packages/task/lib:. python3 packages/task/scripts/render-provider-commands.py --write --repair-owned --root .\` · \`PYTHONPATH=packages/task/lib:. python3 packages/task/scripts/render-provider-commands.py --check --root .\` (no-op) · \`./packages/skiller/bin/skiller registry\` · \`./packages/skiller/bin/skiller registry --check\` («артефакты актуальны») · \`bash packages/skiller/scripts/check-translations.sh\` · \`bash packages/task/scripts/validate.sh\` · \`bash packages/skiller/scripts/validate.sh\` · \`python3 packages/task/scripts/plan-lint.py plans/2026.07.24-AGENT-RELIABILITY\` (0 ERROR).
**Deliverables:** Два канонических чекпоинта, которые ДЕЙСТВИТЕЛЬНО зовут компилятор и падают закрыто; истинное утверждение канона, защищённое литеральным тестом; доставленный \`source-evidence-template.md\` с bundle-требованиями; полная публикация \`plan-protocol@2.13.0\` / \`skiller@0.6.0\` / \`task@0.7.0\` без переиспользования версий.
**Completion Notes:** —
**Pending Work:** —
**Known Deviations:** —
**Escalation Needed:** no
`

const SPEC_P28 = `
### P2.8 — Сделать доказательство P2.5 воспроизводимым из закоммиченных входов

**Status:** ⬜ Not started
**Intent:** RAG:— (repo-grounded: \`findings/P2.5-scenario-results.md:14-16\`; \`artifacts/P2.5/candidate-results.json\`; \`artifacts/P2.5/verify_result_manifest.py:87-93\`; plan-grounded: D25/D26/D30/D70, находки F3/F4). Перевести центральное доказательство фазы (30/31) из «неповторимого» в «пересчитываемое третьим лицом»: закоммитить детерминированный генератор транскриптов, перепрогнать замороженный банк от committed-входов и сделать перечень покрытых категорий честным.
**Why:** RAG:— (repo-grounded: \`## Audit P2 — 2026-07-26\` F3/F4 *failure_scenario*; \`research/07\` §4.3). Вход, породивший 30/31, не закоммичен, а \`verify_result_manifest.py\` grading не повторяет — он читает \`candidate-results.json\` как данность. Независимый аудитор не может ни воспроизвести цифру, ни опровергнуть её; при регрессии \`task_contract\`/\`review_policy\` она останется зелёной, потому что пересчитать её нечем. Симметрично: кейс \`portability-privacy-rawbulk\` зелен по полям, которые записал сам генератор и сам же прочитал — предиката, который бы их вычислял, в репозитории до P2.6 не существовало.
**Scope Included:** детерминированный генератор транскрипт-сета как ПЛАНОВЫЙ артефакт в \`artifacts/P2.5/\`; перепрогон \`run_bank.py candidate\` от закоммиченного входа; пересчитанные \`candidate-results.json\` и \`result-manifest.json\`; честный \`code_guidance_categories\` (категория без вычисляющего предиката снимается из «covered» либо подтверждается реально работающим \`bundle_lint\` P2.6); обновлённый \`findings/P2.5-scenario-results.md\` (провенанс входа, воспроизводимость, фактические цифры).
**Scope Excluded:** любая правка \`artifacts/reliability-bank-v1/**\` — банк, грейдеры, \`run_bank.py\` и манифест заморожены (D30, прямой запрет владельца); \`artifacts/source-evidence/**\`; изменение порогов/floors (D15 — только Owner D#); правка \`packages/**\` (владельцы — P2.6/P2.7); переклассификация статуса P2.5 или его Known Deviations по сужениям dispatch/temp-roots (это не предмет этого item'а); F9.
**Inputs:** Deliverables P2.6 (\`bundle_lint\`) и P2.7 (template/канон, если кейс их читает) · замороженный банк \`artifacts/reliability-bank-v1/**\` · существующие \`artifacts/P2.5/**\` · аудит-блок F3/F4.
**Files:** \`plans/2026.07.24-AGENT-RELIABILITY/artifacts/P2.5/generate_transcripts.py\` · \`plans/2026.07.24-AGENT-RELIABILITY/artifacts/P2.5/transcripts.json\` · \`plans/2026.07.24-AGENT-RELIABILITY/artifacts/P2.5/candidate-results.json\` · \`plans/2026.07.24-AGENT-RELIABILITY/artifacts/P2.5/result-manifest.json\` · \`plans/2026.07.24-AGENT-RELIABILITY/artifacts/P2.5/verify_result_manifest.py\` · \`plans/2026.07.24-AGENT-RELIABILITY/findings/P2.5-scenario-results.md\`.
**Required Reads:** 1) \`plans/2026.07.24-AGENT-RELIABILITY/research/07-p2-reopen-remediation.md\` §4.3 (ПЕРВЫМ) 2) \`plans/2026.07.24-AGENT-RELIABILITY/phases/P2.md\` § \`## Audit P2 — 2026-07-26\` находки F3 и F4 целиком 3) \`plans/2026.07.24-AGENT-RELIABILITY/phases/P2.md\` P2.5 (весь item: Scope, Code Guidance с двенадцатью категориями, Completion Notes, Known Deviations) 4) \`plans/2026.07.24-AGENT-RELIABILITY/findings/P2.5-scenario-results.md\` (весь) 5) \`plans/2026.07.24-AGENT-RELIABILITY/artifacts/reliability-bank-v1/run_bank.py\` (подкоманда \`candidate\`, форма \`--transcripts\`, что именно грейдится — ЧИТАЕТСЯ, НЕ ПРАВИТСЯ) 6) \`plans/2026.07.24-AGENT-RELIABILITY/artifacts/reliability-bank-v1/cases.json\` 7) \`plans/2026.07.24-AGENT-RELIABILITY/artifacts/reliability-bank-v1/graders.json\` 8) \`plans/2026.07.24-AGENT-RELIABILITY/artifacts/reliability-bank-v1/bank-manifest.json\` 9) \`plans/2026.07.24-AGENT-RELIABILITY/artifacts/P2.5/verify_result_manifest.py\` 10) \`plans/2026.07.24-AGENT-RELIABILITY/artifacts/P2.5/candidate-results.json\` 11) \`plans/2026.07.24-AGENT-RELIABILITY/artifacts/P2.5/result-manifest.json\` 12) \`plans/2026.07.24-AGENT-RELIABILITY/root/contracts/reliability-acceptance-v1.md\` §§69-113 (floors — читаются, не меняются) 13) \`packages/task/lib/task/task_contract.py\` (\`bundle_lint\` после P2.6) 14) \`packages/task/lib/task/review_policy.py\` 15) \`packages/task/lib/task/route_evidence.py\` 16) \`plans/2026.07.24-AGENT-RELIABILITY/plan.md\` D30/D48.
**Implementation Rules:** RAG:— (repo-grounded: \`run_bank.py\` § candidate; plan-grounded: D15/D25/D26/D30/D48/D70). **(0) Гейт до первой записи:** P2.6 и P2.7 закоммичены и терминальны; \`git diff --exit-code\` чист по \`artifacts/reliability-bank-v1/\` и \`artifacts/source-evidence/\`; хеши банка сходятся с \`bank-manifest.json\`. Расхождение — стоп до любой записи. \`assert_generated_scope.py\` не запускается, \`base-sha.txt\` не создаётся (та же граница, что в P2.6 (0)). **(1) Грейдинг не переписывается.** Единственный владелец оценки — \`run_bank.py candidate\` (D30). Item производит ВХОД и потребляет ВЫХОД; ни строки внутри банка. **(2) Генератор детерминирован по построению.** Без \`time\`/\`random\`/сети/переменных окружения/абсолютных путей; все пути — относительные от корня репо; два прогона подряд дают побайтово идентичный \`transcripts.json\`, и это отдельный пункт Validation. Генератор гоняет РЕАЛЬНЫЕ seam'ы (\`task.task_contract\`, \`task.review_policy\`, \`task.route_evidence\`, \`task.command_catalog\`/\`command_render\`) ровно как исходный скретч-генератор — воспроизводится поведение, а не подгоняется результат. **(3) D48 соблюдается без изменений:** никакой подмены \`HOME\`/\`CODEX_HOME\`, никакой записи в \`~/.codex\`/\`~/.claude\` и никакого user-owned глобального состояния; временные корни — только явные stdlib \`tempfile\`. Коммит собственного входа D48 НЕ запрещает — он запрещает подмену провайдерских корней; действующее правило противоположно (§2 «canonical execution inputs живут в repo paths», D25/D26). **(4) Провенанс входа записывается машинно.** \`result-manifest.json\` получает поля происхождения транскрипт-сета: путь генератора, путь/или sha256 \`transcripts.json\`, дерево-якорь прогона. \`verify_result_manifest.py\` расширяется проверкой, что записанный хеш совпадает с фактическим файлом — так регрессия входа станет видимой. **(5) \`covered\` честен.** Для КАЖДОЙ из двенадцати категорий Code Guidance P2.5 указывается, каким предикатом в репозитории она вычисляется (\`файл::функция\`). Категория, у которой такого предиката нет, снимается из «covered» и называется незакрытой; \`portability-privacy-rawbulk\` и bundle-строка зеленеют ТОЛЬКО через реально работающий \`task_contract.bundle_lint\` (P2.6). **(6) Красное остаётся красным.** Если после перепрогона цифра отличается от 30/31 — записывается ФАКТИЧЕСКАЯ цифра с разложением каждого расхождения по кейсам; подгонка генератора под прежний результат запрещена и является провалом item'а. Изменение floors недопустимо (D15). Каждый новый провал даёт одну типизированную находку с одним владеющим item'ом; ремонтные/аудиторские циклы этот item не запускает.
**Code Guidance:** stdlib-only, генератор — обычный плановый артефакт в регистре \`artifacts/P2.1/validate_state_cases.py\`: читает только объявленные аргументы, печатает \`FAIL:\`-строки, выходит 1 на ошибке. **Анти-подгонка:** генератор пишется ОТ кейса банка (его \`environment.fixture\`/ассершены), а не от желаемого выхода; если кейс не воспроизводится честно, он краснеет — правка описания кейса или банка запрещена (D30), вместо этого D#-запись. **Анти-самообман:** «зелено, потому что я так записал» — ровно диагноз F4; каждое поле \`outcome\`, по которому грейдер судит, обязано быть ВЫЧИСЛЕНО кодом репозитория, и в findings указывается, каким именно. Если для какого-то поля вычислителя нет и после P2.6 — кейс снимается из «covered», а не остаётся зелёным. Отчёт разделяет числитель, знаменатель и unknown; «Three cases», за которым идут семь id (F14), — образец того, как писать нельзя: числа в прозе обязаны совпадать с перечнем.
**Validation:** \`python3 -m py_compile plans/2026.07.24-AGENT-RELIABILITY/artifacts/P2.5/generate_transcripts.py\` · \`python3 -m py_compile plans/2026.07.24-AGENT-RELIABILITY/artifacts/P2.5/verify_result_manifest.py\` · \`python3 plans/2026.07.24-AGENT-RELIABILITY/artifacts/P2.5/generate_transcripts.py --out plans/2026.07.24-AGENT-RELIABILITY/artifacts/P2.5/transcripts.json && git diff --exit-code -- plans/2026.07.24-AGENT-RELIABILITY/artifacts/P2.5/transcripts.json\` (детерминизм: перегенерация поверх закоммиченного файла обязана дать exit 0 — побайтовое совпадение; временные пути вне репо в Validation запрещены правилом портируемости D26/D47) · \`python3 -m json.tool plans/2026.07.24-AGENT-RELIABILITY/artifacts/P2.5/transcripts.json >/dev/null\` · \`python3 -m json.tool plans/2026.07.24-AGENT-RELIABILITY/artifacts/P2.5/candidate-results.json >/dev/null\` · \`python3 -m json.tool plans/2026.07.24-AGENT-RELIABILITY/artifacts/P2.5/result-manifest.json >/dev/null\` · \`python3 plans/2026.07.24-AGENT-RELIABILITY/artifacts/reliability-bank-v1/run_bank.py candidate --transcripts plans/2026.07.24-AGENT-RELIABILITY/artifacts/P2.5/transcripts.json\` (фактическая цифра фиксируется как есть) · \`python3 plans/2026.07.24-AGENT-RELIABILITY/artifacts/P2.5/verify_result_manifest.py --bank-manifest plans/2026.07.24-AGENT-RELIABILITY/artifacts/reliability-bank-v1/bank-manifest.json --results plans/2026.07.24-AGENT-RELIABILITY/artifacts/P2.5/candidate-results.json --manifest plans/2026.07.24-AGENT-RELIABILITY/artifacts/P2.5/result-manifest.json\` · \`git diff --exit-code -- plans/2026.07.24-AGENT-RELIABILITY/artifacts/reliability-bank-v1 plans/2026.07.24-AGENT-RELIABILITY/artifacts/source-evidence\` (exit 0) · \`bash packages/task/scripts/validate.sh\` · \`python3 packages/task/scripts/plan-lint.py plans/2026.07.24-AGENT-RELIABILITY\` (0 ERROR).
**Deliverables:** Доказательство фазы, пересчитываемое третьим лицом из закоммиченных байтов: детерминированный генератор в \`Files\`, машинный провенанс входа в манифесте, честный перечень покрытых категорий и цифра, которая способна покраснеть при регрессии.
**Completion Notes:** —
**Pending Work:** —
**Known Deviations:** —
`

const SPEC_P29 = `
### P2.9 — Свести запись фазы: бухгалтерия находок F6/F7/F10–F15

**Status:** ⬜ Not started
**Intent:** RAG:— (plan-grounded: D70, находки F6, F7, F10, F11, F12, F13, F14, F15). Привести ЗАПИСЬ фазы в соответствие с фактами: починить неисполнимый литерал Validation, дописать неотчитанные пункты, назвать пропущенные отклонения, связать коммиты с items и снять расхождение §7 Exported. Ни одной мутации кода.
**Why:** RAG:— (repo-grounded: \`## Audit P2 — 2026-07-26\` F6/F7/F10–F15 *failure_scenario*). Исполнитель, копирующий литерал Validation P2.4 №3 из ТЗ, получает красный прогон и лечит несуществующий дефект окружения. Холодный resume P2.3 на \`77b574b5\` не находит baseline-носитель. Карта «коммит → item» рвётся именно на том item'е, который несёт терминальное доказательство фазы. Потребитель с закешированным \`task@0.5.0\` получает рантайм без \`route_evidence.py\`.
**Scope Included:** F7 — исправить литерал Validation P2.4 №3 на \`PYTHONPATH=packages/harness/lib:packages/harness\` и дописать в Completion Notes P2.4 отчёт по трём неотчитанным \`validate.sh\` (\`task\`/\`harness\`/\`analyst\`), убрав из отчёта два пункта, которых в поле Validation нет; F6 — Known Deviations P2.3 о \`artifacts/P2.3/base-sha.txt\`, уехавшем в bookkeeping-коммит \`324bae5d\` вместо item-коммита \`77b574b5\`; F11 — полнота отчёта Validation P2.3 (\`test_canon_literals.py\`, \`test_journal.py\`); F12 — хеш item-коммита \`14b3e6ce\` в Completion Notes P2.5 и в \`findings/P2.5-scenario-results.md:7\`; F13 — Known Deviations P2.5 об отсутствующей старт-записи журнала (D21 п.3); F14 — «Three cases» → фактические семь; F10/F15 — строка §7 Exported для \`task\` plugin/routing приводится в соответствие с фактически опубликованной версией, ссылка на D72/D73 из Known Deviations P2.4.
**Scope Excluded:** любая правка \`packages/**\` (кода, тестов, канона, конфигов) — item чисто реконсиляционный; правка ТЗ/Scope/Files закрытых items P0/P1 (прямой запрет владельца); переписывание или компенсация исторических строк \`journal.jsonl\` (append-only, D51 — фиксируется текстом, не событием); статусы items (их владелец — D71 и ритуал закрытия); \`artifacts/reliability-bank-v1/**\`, \`artifacts/source-evidence/**\`, \`remediation-map.json\`; F9; чужие планы.
**Inputs:** аудит-блок F6/F7/F10–F15 · факты закрытия P2.6–P2.8 · \`git log\`/\`git show --stat\` по коммитам фазы.
**Files:** \`plans/2026.07.24-AGENT-RELIABILITY/phases/P2.md\` · \`plans/2026.07.24-AGENT-RELIABILITY/plan.md\` · \`plans/2026.07.24-AGENT-RELIABILITY/findings/P2.5-scenario-results.md\`.
**Required Reads:** 1) \`plans/2026.07.24-AGENT-RELIABILITY/phases/P2.md\` § \`## Audit P2 — 2026-07-26\`, находки F6, F7, F10, F11, F12, F13, F14, F15 (ПЕРВЫМ, целиком) 2) \`plans/2026.07.24-AGENT-RELIABILITY/research/07-p2-reopen-remediation.md\` §8 (трассировка находка → носитель) 3) \`plans/2026.07.24-AGENT-RELIABILITY/phases/P2.md\` items P2.3, P2.4, P2.5 (Validation, Completion Notes, Known Deviations) 4) \`plans/2026.07.24-AGENT-RELIABILITY/findings/P2.5-scenario-results.md\` 5) \`plans/2026.07.24-AGENT-RELIABILITY/plan.md\` §5 D70–D73 и §7 Contracts 6) \`plans/2026.07.24-AGENT-RELIABILITY/plan.md\` D60 и D61 (прецедент правки дефектного литерала Validation закрытого item'а записью, а не эскалацией) 7) \`packages/skiller/skills/general/plan-protocol/SKILL.md\` §6 (предикат material/process) и §8 (топология коммитов, требование реального хеша).
**Implementation Rules:** RAG:— (plan-grounded: D21/D51/D60/D70). **(0)** Item стартует только после терминальных P2.6–P2.8: он отчитывается о фактах их закрытия, а не предвосхищает их. **(1) Каждая правка — проверенный факт, а не пересказ аудита.** Прежде чем вписать цифру или хеш, исполнитель ПРОГОНЯЕТ соответствующую проверку и приводит вывод: исправленный литерал Validation P2.4 №3 — фактическим прогоном (\`Ran 17 tests … OK\`); три \`validate.sh\` — фактическими прогонами; \`test_canon_literals.py\`/\`test_journal.py\` для F11 — перепрогоном; хеш \`14b3e6ce\` — \`git show --stat\`. Число, взятое из аудита без перепроверки, — дефект. **(2) История не переписывается.** Строки \`journal.jsonl\` (включая 45–46 с \`implementation/*\`) остаются как есть; отсутствующая старт-запись P2.5 не дописывается задним числом — она НАЗЫВАЕТСЯ в Known Deviations ровно так, как это уже сделали P2.3 и P2.4. Sidecar \`journal-exceptions.jsonl\` не заводится: строки schema-valid, а D51-исключение предназначено для schema-invalid. **(3) Правка ТЗ закрытого item'а разрешена только для F7** и только по прецеденту D60/D61: заменяется неисполнимый литерал команды, Scope/Files/Deliverables не трогаются; факт правки фиксируется строкой в Known Deviations соответствующего item'а. **(4) §7 Exported.** Строка \`task\` plugin/routing приводится к ФАКТИЧЕСКИ опубликованной версии на момент закрытия P2.7 с указанием коммита; расхождение, которое машинный гейт не ловит (lock хеширует commands/adapters, не \`lib/\`), называется в примечании строки как известная граница. **(5) Никакой мутации кода.** Если правка записи требует изменения кода — это НЕ этот item: стоп и D#-запись с указанием владельца.
**Code Guidance:** Правки хирургические: только названные поля названных items, ни одной «заодно» переформулировки соседнего текста — иначе дифф перестаёт быть проверяемым. Формулировки Known Deviations пишутся в регистре уже существующих в этой фазе (что отклонилось, почему, кто владелец ремонта, ПРОХОД). **Анти-подгонка:** «дописать красивее» не является ремонтом находки — каждая правка обязана однозначно сниматься конкретной находкой аудита, и это соответствие перечисляется в Completion Notes построчно (\`F# → файл:поле\`). **Анти-самообман:** запрещено объявлять находку закрытой, если факт не перепроверен своими руками в этом заходе; неперепроверенное честно называется неперепроверенным. Пересказ Completion Notes в Update Log запрещён (канон §6): строка Update Log — одна суть + ссылка.
**Validation:** \`PYTHONPATH=packages/harness/lib:packages/harness python3 -m unittest discover -s packages/harness/tests -p 'test_doctor_settings_cli.py'\` (обязан дать \`Ran 17 tests … OK\` — доказательство исправленного литерала) · \`PYTHONPATH=packages/task/lib python3 -m unittest discover -s packages/task/tests -p 'test_canon_literals.py'\` · \`PYTHONPATH=packages/task/lib python3 -m unittest discover -s packages/task/tests -p 'test_journal.py'\` · \`bash packages/task/scripts/validate.sh\` · \`bash packages/harness/scripts/validate.sh\` · \`bash packages/analyst/scripts/validate.sh\` · \`git show --stat 14b3e6ce\` (подтверждение хеша item-коммита P2.5) · \`git show --stat 324bae5d\` и \`git show --stat 77b574b5\` (подтверждение топологии F6) · \`python3 packages/task/scripts/plan-lint.py plans/2026.07.24-AGENT-RELIABILITY\` (0 ERROR).
**Deliverables:** Запись фазы, в которой каждая цифра, каждый литерал команды и каждый хеш проверены прогоном, все восемь бухгалтерских находок сняты поимённо, а известные границы названы вместо того, чтобы быть незаметными.
`

// ── Промпты ──────────────────────────────────────────────────────────────────
function implPrompt(item) {
  return `Ты исполнитель item'а ${item.id} мастер-плана 2026.07.24-AGENT-RELIABILITY (репо ${REPO}).
${CTX}
ТЗ item'а ЦЕЛИКОМ (SSOT, дословно из phases/P2.md) — единственный источник Scope/Files/Validation/Implementation Rules/Code Guidance, ниже:
${item.spec}

ПОРЯДОК:
1. ПЕРВЫМ делом — пункт (0) Implementation Rules выше (precondition-гейт). Прогони его КАК НАПИСАНО и впиши вывод в precondition_detail. Отказ ЛЮБОГО условия — precondition_ok=false, done=false, escalation с названным путём и владельцем, СТОП до первой мутации (ни одного файла не трогать).
2. Прочитай Required Reads item'а по объявленному порядку (пути — относительно ${REPO}).
3. Реализуй Scope Included ЦЕЛИКОМ по Implementation Rules и Code Guidance. Scope Excluded не трогай ни байтом.
4. Прогони КАЖДУЮ команду поля Validation (working dir ${REPO}) и впиши дословный вывод/exit-код в validation_report — не пересказ, не «все ок».
5. Коммить(ы) Conventional Commits на русском, ТОЛЬКО файлы из Files item'а (+ отдельный companion-коммит, если того требуют Implementation Rules). git add по путям, НЕ \`-A\`/\`.\`.
6. files_outside_scope — честно, если что-то тронуто вне Files.

ЗАПРЕЩЕНО: ослаблять Validation ради зелёного; подгонять реализацию/генератор под желаемый результат вместо честного прогона (см. «красное остаётся красным» и «Анти-подгонка»/«Анти-самообман» в Code Guidance спеки); объявлять done=true при незакрытом precondition; писать в отчёт то, что не прогонял руками.
ЭСКАЛАЦИЯ (plan-protocol §10): конфликт правил / неисполнимое требование / расхождение спеки с кодом → done=false + escalation с причиной.`
}

function verifyPrompt(item) {
  return `Ты МЕХАНИЧЕСКИЙ верификатор item'а ${item.id}. Тебе НЕЧЕГО защищать: ты НЕ чинишь код, НЕ интерпретируешь результаты, НЕ решаешь, сдан ли item — только выполняешь команды и возвращаешь их СЫРОЙ вывод дословно (включая ненулевые exit-коды).
Репо: ${REPO}.

Спека item'а (единственный источник команд — поле **Validation:** ниже; найди его сам и прогони КАЖДУЮ перечисленную в нём команду по порядку):
${item.spec}

Дополнительно выполни и верни дословно:
- \`git status --porcelain\` (working tree ${REPO})
- \`git log --oneline -5\` и \`git show --stat HEAD\` (последний коммит item'а, если он уже есть)
- \`python3 packages/task/scripts/plan-lint.py ${PLAN_DIR}\` (число ERROR/WARN)

Ничего не добавляй от себя, ничего не чини, ни одного файла не трогай. Вывод команд — единственное, что от тебя нужно.`
}

function reviewPrompt(item, verify) {
  return `Ты adversarial-ревьюер item'а ${item.id} мастер-плана 2026.07.24-AGENT-RELIABILITY. Read-only: КОД НЕ ПРАВИШЬ, план НЕ ПРАВИШЬ.
${CTX}
Механический верификатор (отдельный агент, которому нечего защищать) прогнал проверки — СЫРОЙ вывод; верь ЕМУ и git-диффу, а НЕ прозе исполнителя:
${verify}

ТЗ item'а (SSOT):
${item.spec}

ПОРЯДОК (начни с диффа, не с отчёта исполнителя — иначе якорь):
1. \`git log\`/\`git show --stat\` по коммиту(ам) item'а в ${REPO} — что РЕАЛЬНО изменилось.
2. Сверь дифф со Scope Included/Files/Implementation Rules/Deliverables спеки построчно.
3. Заполни validation_cross_check: что реально зелёное/красное по Verify-выводу — совпадает ли это с тем, что заявил исполнитель (расхождение → false_claims).
4. Помни «красное остаётся красным»: честно зафиксированное расхождение (например, пересчитанная цифра ≠ прежней, названная как есть) — ПРАВИЛЬНЫЙ исход, не дефект сам по себе; дефектом является СКРЫТОЕ или подогнанное расхождение.
5. Только теперь читай отчёт исполнителя (validation_report/known_deviations) и ищи расхождение с фактами.

Вердикт: RED — Scope Included не исполнен / есть Blocker / скрытое либо подогнанное расхождение; ATTENTION — исполнено с честно названным долгом (Minor/Major, без сокрытия); GREEN — чисто, всё по спеке.
Не занижай severity ради «не останавливать пайплайн»: RED на P2.7/P2.8 останавливает ВЕСЬ прогон (P2.8/P2.9 зависят от терминальности предыдущих) — это правильно, не повод для самоцензуры вердикта.
Каждая находка несёт конкретный failure scenario.`
}

function closePrompt(item, impl, review, verify) {
  return `Ты docs-curator плана 2026.07.24-AGENT-RELIABILITY. Работа механическая, thinking низкий. КОД НЕ ТРОГАТЬ — только bookkeeping плана.
${CTX}
Item ${item.id}. Факты верификатора (сырой вывод):
${verify}
Отчёт исполнителя: ${JSON.stringify(impl)}
Вердикт ревью: ${JSON.stringify(review)}

ЗАДАЧА (из МАШИННЫХ фактов выше, не из памяти/домысла):
1. phases/P2.md «### ${item.id}»: заполни Status (🟢 Done, если verdict=GREEN и deliverables_met=true и files_outside_scope пуст; иначе 🟠 Done with deviations — plan-protocol §6 material-предикат), Completion Notes (факты: коммиты, числа Validation дословно из verify), Pending Work, Known Deviations (КАЖДОЕ честно зафиксированное расхождение из review.findings/impl.known_deviations), Escalation Needed = no (review.verdict уже не RED на этом шаге).
2. plan.md «## 4. Status Board» строка ${item.id} + «## 6. Update Log» (одна строка: «${item.id} закрыт: <суть> — детали см. phases/P2.md ${item.id} Completion Notes»). НЕ трогай статусы/поля ДРУГИХ items, КРОМЕ случаев, явно предписанных Scope Included ${item.id} (это касается только P2.9, который правит записи P2.3/P2.4/P2.5 по своему ТЗ).
3. journal.jsonl: добавь запись закрытия ${item.id} append-only, по формату уже существующих строк (сверься с ними перед добавлением, не изобретай новую схему).
4. Перезапиши handoff.md: «# HANDOFF — <дата> — after ${item.id}», Next — launch-block на следующий item пайплайна (или на /task:plan-audit 2026.07.24-AGENT-RELIABILITY P2, если ${item.id} — последний, P2.9), Done/Remaining/Sources of truth/Open risks.
5. \`python3 packages/task/scripts/plan-lint.py ${PLAN_DIR}\` — новых ошибок от диффа быть не должно.
6. \`git add plans/2026.07.24-AGENT-RELIABILITY && git commit -m "docs(plan): закрыть ${item.id} — статус, completion notes, handoff"\`.

Верни одной строкой: статус + sha коммита bookkeeping.`
}

function stopClosePrompt(item, stage, reason) {
  return `Ты docs-curator плана 2026.07.24-AGENT-RELIABILITY. Пайплайн ОСТАНОВЛЕН на ${item.id} (стадия: ${stage}). P2.7→P2.8→P2.9 строго последовательный — следующие items НЕ стартуют.
${CTX}
Причина: ${reason}

ЗАДАЧА (план не имеет права лгать о состоянии — ровно та ошибка, за которую фаза уже получила RED однажды):
1. phases/P2.md «### ${item.id}»: Status = 🔴 Blocked, Escalation Needed = yes + причина, Pending Work = что успели (sha частичных коммитов, если есть).
2. Зафиксируй \`git status --porcelain\` в Pending Work item'а. Незакоммиченное не выбрасывай: \`git stash push -m "P2-remediation-${item.id}-partial"\` и назови stash-ref, если есть что стешить.
3. plan.md «## 4. Status Board» строка ${item.id}.
4. Перезапиши handoff.md: Next — launch-block на РАЗБОР остановки (человек/design-заход), НЕ на следующий item ремонта.
5. \`python3 packages/task/scripts/plan-lint.py ${PLAN_DIR}\`; \`git add plans/2026.07.24-AGENT-RELIABILITY && git commit -m "docs(plan): остановка ремонта D70 на ${item.id} — 🔴 Blocked, handoff"\`.`
}

// ── Items пайплайна (модель/effort/review-класс — §3 Routing plan.md, roadmap.md carrier'ы) ──
const ITEMS = [
  { id: 'P2.7', title: 'Write-site в командах и истинный канон plan-protocol', model: 'sonnet', effort: 'high', reviewClass: 'full', spec: SPEC_P27 },
  { id: 'P2.8', title: 'Воспроизводимое доказательство P2.5 из закоммиченных входов', model: 'sonnet', effort: 'high', reviewClass: 'full', spec: SPEC_P28 },
  { id: 'P2.9', title: 'Реконсиляция записи фазы: бухгалтерия F6/F7/F10-F15', model: 'sonnet', effort: 'medium', reviewClass: 'light', spec: SPEC_P29 },
]

// ── Оркестрация: строго последовательно, стоп на первом impl-провале или review RED ──────
log(`wf-P2.7-P2.9: ${ITEMS.length} items строго последовательно (реальная зависимость: P2.8 читает Deliverables P2.7, P2.9 отчитывается о фактах P2.6-P2.8) — стоп на первом RED/blocked останавливает ВЕСЬ прогон, не только item.`)

const done = []
let stoppedAt = null

for (const item of ITEMS) {
  phase('Impl')
  const impl = await safeAgent(implPrompt(item), {
    label: `impl:${item.id}`, phase: 'Impl', model: item.model, effort: item.effort, schema: IMPL_SCHEMA,
  })
  if (!impl || !impl.precondition_ok || !impl.done) {
    const reason = !impl ? 'агент не вернул результат'
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
  const review = await safeAgent(reviewPrompt(item, verify || '(верификатор не вернул результат — ревьюер учитывает это как риск)'), {
    label: `review:${item.id}`, phase: 'Review', ...REVIEW_FOR[item.reviewClass], schema: REVIEW_SCHEMA,
  })
  if (!review || review.verdict === 'RED') {
    const reason = review ? `RED: ${review.summary}` : 'ревьюер не вернул результат'
    await safeAgent(stopClosePrompt(item, 'review', reason), { label: `stop-close:${item.id}`, phase: 'Close', model: 'sonnet', effort: 'low' })
    done.push({ item: item.id, stopped: `review: ${reason}`, findings: review ? review.findings : [] })
    stoppedAt = item.id
    log(`СТОП пайплайна на ${item.id} (review RED). Следующие items НЕ стартуют.`)
    break
  }

  phase('Close')
  const close = await safeAgent(closePrompt(item, impl, review, verify || '(верификатор не вернул результат)'), {
    label: `close:${item.id}`, phase: 'Close', model: 'sonnet', effort: 'low',
  })

  done.push({
    item: item.id, stopped: null, verdict: review.verdict,
    validation_report: impl.validation_report, findings: review.findings, close_result: close,
  })
  log(`✅ ${item.id} — ${review.verdict} (${review.findings.length} находок). Терминальных: ${done.filter(d => !d.stopped).length}/${ITEMS.length}.`)
}

const allTerminal = done.length === ITEMS.length && done.every(d => !d.stopped)

return {
  pipeline: 'P2.7 → P2.8 → P2.9 (ремонт-реопен D70, строго последовательно)',
  items: done.map(d => ({
    item: d.item,
    stopped: d.stopped || null,
    verdict: d.verdict || null,
    findings: (d.findings || []).map(f => `${f.severity}: ${f.summary}`),
    validation_report: d.stopped ? null : d.validation_report,
  })),
  all_terminal: allTerminal,
  next: allTerminal
    ? 'Все три item\'а ремонта D70 (P2.7-P2.9) терминальны → /task:plan-audit 2026.07.24-AGENT-RELIABILITY P2 (opus/xhigh, НОВАЯ сессия, ВСЛЕПУЮ) для проверки закрытия реопена.'
    : `Пайплайн остановлен на ${stoppedAt} — разобрать причину (см. 🔴 Blocked в phases/P2.md и handoff.md), затем точечный фикс + повторный прогон. Аудит фазы НЕ запускать до устранения.`,
}
