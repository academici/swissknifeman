---
description: "План-протокол: создать/детализировать мастер-план в plans/ — новый план, фаза Pn, ТЗ подпункта Pn.m или развёртка черновика plan mode (from-draft). Пинит Opus/high."
argument-hint: "[new <название> | <PLAN-ID> [Pn[.m]] | from-draft <файл>]"
model: opus
effort: high
---
Это ПРОЕКТИРОВАНИЕ мастер-плана (plan-протокол). Ввод пользователя: «$ARGUMENTS».
Модель/effort запинены (Opus/high) — не переключай вручную. SSOT протокола — скилл
`plan-protocol` (general): схемы, статусы, эскалация, routing-матрица, refine-цикл (§7);
шаблоны — его `snippets/{plan,phase,handoff,launch-block}-template.md`. Ты пишешь план,
который дешёвая модель исполнит БЕЗ доступа к этому чату.

## Режимы (по $ARGUMENTS)

1. **`new <название>`** — новый план: выбери `PLAN-ID` (`[A-Z][A-Z0-9-]+`, напр. `AUDIT-W2`),
   создай `plans/<ID>/plan.md` по шаблону (все секции 0–6), скелеты фаз `plans/<ID>/phases/Pn.md`
   (Phase Context со скелет-маркером — фиксированная строка
   `> СКЕЛЕТ — не детализирован, разворачивается /task:plan-design <ID> Pn` —
   + Phase Status + items-скелеты с «—»; при маркере пустые поля легальны, включая
   Code Guidance = «—») и `handoff.md` (Next: первый item;
   заголовок стартового handoff — `# HANDOFF — <дата> — after P0.0`: bootstrap-канон,
   закрытых items ещё нет, а линт требует строго `after Pn.m`).
   **Constitution-гейт (план нового Axioma-проекта/пакета):** ДО фиксации стека и несущих
   архитектурных решений в плане прогони `axioma-doctrine` → `ecosystem-reuse-gate`
   (аналог constitution-check spec-kit, RAG:✅ P5.1 §1); reuse-вердикт зафиксируй в
   `## 5. Decision Log`.
   Затем создай/обнови `plans/ACTIVE.md` (в корне `plans/`, НЕ внутри `plans/<ID>/`) —
   канонический формат 4 строки: `# ACTIVE`, пустая строка, `**Active:** <PLAN-ID>`,
   `**Updated:** <YYYY-MM-DD>` (файла нет — создай; есть — перезапиши по канону, указав
   новый `PLAN-ID`). Если ACTIVE указывал на другой незакрытый план — допиши ЕМУ в
   `## 0. Meta` поле `Paused By: <новый PLAN-ID>, <YYYY-MM-DD>` (+строка в его Update Log):
   перехват ACTIVE не бывает молчаливым. Смену Active зафиксируй строкой в
   `## 6. Update Log` нового плана.
2. **`<PLAN-ID> Pn`** — спроектировать фазу: заполнить `## Phase Context` (5–10 строк,
   самодостаточно — фаза исполнима без чтения других фаз; скелет-маркер убрать) и разложить
   на items `### Pn.m — Title` со всеми полями; синхронизировать Status Board в plan.md.
   Финал режима — обязательный refine-цикл + DoR-чеклист (ниже).
3. **`<PLAN-ID> Pn.m`** — довести один item до исполняемого ТЗ: дозаполнить все поля
   до уровня «sonnet исполнит без вопросов». Финал режима — refine-цикл + DoR-чеклист (ниже).
4. **`from-draft <файл>`** — мост встроенного plan mode Claude Code → протокол (событие
   ExitPlanMode не существует — авто-хука нет, мост ручной, но одношаговый). `<файл>` —
   плоский одобренный черновик `plans/<slug>.md` (конвенция: плоский `.md` в `plans/`, кроме
   `ACTIVE.md`/`README.md`, — черновик plan mode; `plan-lint` их видит и подсказывает этот
   режим WARNING'ом). Прочитай черновик целиком, предложи `PLAN-ID` из его slug'а (upper-kebab,
   `[A-Z][A-Z0-9-]+`; напр. `plans/pilot-azg.md` → `PILOT-AZG`) — **финальный ID подтверждает
   человек** перед созданием файлов. Затем разверни черновик в `plans/<ID>/` по тем же
   шаблонам скилла `plan-protocol`, что и режим `new` (`plan.md` все секции 0–6, скелеты
   `phases/Pn.md` со скелет-маркером, `handoff.md`): черновик НЕ переносится как есть —
   транскрибируется (все 16 полей каждого item'а, **Code Guidance обязателен**, как в режиме
   `new`). В `## 5. Decision Log` нового плана зафиксируй происхождение отдельной строкой:
   `D1 | <YYYY-MM-DD> | Источник — черновик plans/<slug>.md | bootstrap-транскрипция
   одобренного черновика plan mode`. После записи файлов **удали черновик** `plans/<slug>.md`
   (история — в git, дублей не держим). Финал — как у `new`: создай/обнови `plans/ACTIVE.md`
   в корне `plans/` по канону 4 строки (`**Active:** <новый PLAN-ID>`,
   `**Updated:** <YYYY-MM-DD>`), допиши `Paused By` предыдущему активному плану
   + строка в `## 6. Update Log` нового плана.

## Схема (компактная выжимка — на случай отсутствия скилла)

- `plan.md`: `## 0. Meta` (таблица: Plan ID / Title / Version / Status / Document Type /
  Authoring Model / Last Updated / Repository / Related Packages / Execution Mode /
  Target Operator Models / Approval Owner; необязательные: `Home` — `brain`|`repo:<путь>`,
  `Paused By` — кто перехватил ACTIVE и когда) · `## 1. Context` (5–15 строк, самодостаточно) ·
  `## 2. Execution Rules` (выжимка ≤20 строк) · `## 3. Routing` (ТОЛЬКО отклонения от
  SSOT-матрицы; пусто = дефолты; формат `Items | Model/effort И/ИЛИ Tool Capability | Почему` —
  tool-capability, типовое `perplexity-web/WebFetch (RAG)`, ДОПОЛНЯЕТ model/effort) ·
  `## 4. Phase Index & Status Board` (`Phase | Title | Items 🟢/всего | Status`) ·
  `## 5. Decision Log` (`D# | Дата | Решение | Почему`) · `## 6. Update Log` (append-only:
  `Дата | Кто | Что`; «Что» ≤ 2 строк, канон
  `<item> закрыт: <1 строка сути> — детали см. phases/Pn.md <item> Completion Notes`,
  пересказ Completion Notes запрещён).
- `phases/Pn.md`: `# Pn — Title` → `## Phase Context` (скелет-маркер, если фаза не
  детализирована) → `## Phase Status` (`ID | Title | Status | Updated`) → items →
  `## Phase Handoff`.
- Item: заголовок СТРОГО `### Pn.m — Title`; поля СТРОГО строками `**Поле:** значение`,
  в этом порядке: Status, Intent, Why, Scope Included, Scope Excluded, Inputs, Files,
  Required Reads, Implementation Rules, Code Guidance, Validation, Deliverables,
  Completion Notes, Pending Work, Known Deviations, Escalation Needed.
  Пустое значение — канонический символ «—» (не пустая строка, не «N/A»);
  у `Escalation Needed` — и ТОЛЬКО у него — маркер `no` равноправен «—».
- Статусы — РОВНО 6 канонических строк, байт-в-байт:
  `⬜ Not started` · `🟡 In progress` · `🟢 Done` · `🟠 Done with deviations` ·
  `🔴 Blocked` · `⛔ Skipped by decision`. Гейты статусов: коммит-гейт закрытия +
  DoR-гейт перевода фазы в исполнение (SKILL §6).
- `handoff.md`: `# HANDOFF — <ISO-дата> — after Pn.m` + Next / Done / Remaining /
  Sources of truth / Open risks / Workarounds-Deferred-Open questions; перезаписывается
  целиком. Next — в форме launch-block, самодостаточный из холодной сессии (SKILL §8).
- Раскладка 2.0: обязательны `plan.md`/`phases/`/`handoff.md`; опционально `findings/`,
  `20_research/`, `artifacts/` (судьба — архив), `root/` (судьба — docs проекта),
  `open-questions.md` (протокол спорного — SKILL §3).

## Требования к качеству

- **Каждый item исполним sonnet'ом без доп. контекста**: Required Reads конечны и
  упорядочены (не «посмотри по репо»), **Code Guidance обязателен** (стиль решения,
  запреты, обязательные тесты, запрещённые shortcuts — то, что дешёвая модель не выведет
  сама; формулировки бери из `snippets/code-guidance-patterns.md` — анти-подгонка,
  анти-самообман, if-then эскалация к D# — не изобретай заново), Validation — конкретные
  команды (что прогнать и что считается зелёным).
- **Никаких самовольных допущений.** Спорное/неоднозначное место — либо маркер
  `[NEEDS CLARIFICATION: <вопрос>]` прямо в тексте, либо вопрос владельцу; молча принятое
  допущение — дефект. Принятые решения фиксируй в `## 5. Decision Log`; правку плана
  отметь строкой в `## 6. Update Log`; долгоживущее спорное — в `open-questions.md`
  по протоколу SKILL §3.
- **RAG-маркеры на несущих.** Внешние факты верифицируй существующей RAG-лестницей
  (context7 → perplexity → WebSearch) — она источник; след в плане — маркер: каждый
  load-bearing факт/вердикт в Intent/Why/Implementation Rules и в D-логе несёт
  `RAG:✅ <дата/суть запроса>` либо `[UNVERIFIED]`. Несущий пункт без маркера =
  дефект схемы, находка аудита.
- **RAG-верификации фазы — в `findings/`, не только в чат.** Если при проектировании фазы
  делал RAG-верификацию внешних фактов, сохрани выжимку (источник-URL + дата + вердикт) в
  `plans/<PLAN-ID>/findings/<Pn>-<slug>.md` и сошлись на неё из `Inputs`/`Required Reads`
  соответствующих items (опционально: заводи файл, только если есть что сохранить).
- Phase-first: items не прыгают между фазами; фазы закрываются последовательно.
- **Тайм-гейтовый Deliverable — отдельный item.** Если часть Deliverables требует
  календарного окна (накопить данные, дождаться прод-недели) И от неё зависит Inputs
  более позднего item'а — выдели её в собственный follow-up item (доска честно покажет
  его открытым), а не оставляй хвост в Pending Work: downstream-исполнитель читает
  Status Board, а не прозу закрытого item'а.

## Refine-цикл и DoR (обязательный финал режимов `Pn`/`Pn.m`)

Канонический контур (SKILL §7): design → self-audit по DoR-чеклисту → правка → повтор
до 0 маркеров `[NEEDS CLARIFICATION]`. Перед выдачей «фаза готова» прогони DoR-чеклист:
маркеры сняты; Scope Included/Excluded фазы заполнены; Alternatives несущих решений —
в D-логе; Open Questions разнесены по статусам; несущие факты несут RAG-маркеры.
Фаза, ушедшая в exec без DoR, = находка plan-audit.

**Pre-mortem для high-stakes** (фискалка/платежи/tenant-isolation/ядро экосистемы):
перед закрытием фазы дизайна — раунд по протоколу Klein: «план провалился через
6–12 мес — почему»; независимая запись причин → кластеризация → mitigations с owner
в Risks/D-лог.

## Финал

Прогони линтер: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plan-lint.py" plans/<ID>`
(переменная не задана или скрипта нет — предупреди и пропусти, не блокер).
Красное линтера почини в созданных файлах.

**Expected output:** список созданных/изменённых файлов + число items + вердикт
DoR-чеклиста (режимы `Pn`/`Pn.m`) + строка
«Готово к: `/task:plan-exec <ID> Pn.m` (Sonnet/medium)».
