# HANDOFF — 2026-07-12 — after P6.4

**Next:** P8.1 (доктрина бюджета в CLAUDE.md + память mAInd).

| Параметр | Значение |
|:--|:--|
| Model | sonnet/medium |
| Thinking | medium — правка минимальная (1–3 строки CLAUDE.md + 1 запись памяти), но требует свежего чтения `--help`/памяти, не по шаблону вслепую |
| Context | fresh session — handoff свежий, рекомендован `/clear` (P6 закрыт, состояние в git+plan, ручной item без Workflow-оркестрации) |
| Суть | Пункт в root CLAUDE.md «Рамки»: любой новый always-on инжект — до раскатки через `skiller budget --first-turn`, вписывается в бюджет (3–7K/warn 10K); компактная запись в память mAInd (ns:axioma). Держать root CLAUDE.md ≤200 строк (сейчас 179) |

```
/task:plan-exec 2026.07.12-CONTEXT-ECONOMY P8.1
```

**Done:** P1–P7 закрыты (см. Update Log plan.md). P6 закрыта целиком (4/4: P6.1/P6.2 🟢,
P6.3/P6.4 🟠 Done with deviations) — фаза терминальна.

**P6.4 закрыт 🟠 Done with deviations (фаза P6 4/4 закрыта, терминальна):** after-замер
выполнен теми же командами, что baseline (`maind doctor --context --json`, `analyst
sessions --weeks 3 --json` на agelto/swissknifeman/brain) + разбивка по источникам
(`skiller budget --first-turn`). **Итог по 3 критериям приёмки Phase Context P6 — 0 из 3
формально пройдено** (не ослаблено, честно зафиксировано):
1. Медиана первого хода ≤10–12K — флот-медиана `doctor --context` 19864.5→18582 (−6.5%);
   `analyst sessions` W28-медианы 29781(swk)/50083.5(agelto)/31317.5(brain) — далеко выше
   порога.
2. agelto −≥40% — `doctor --context` 34538→32830 (−4.9%); `analyst sessions` W28 без
   изменений (те же сессии — раскатка и baseline пришлись на ту же ISO-неделю W28,
   недельная гранулярность инструмента не разделяет «до/после» внутри недели —
   ограничение измерения, не подгонка).
3. `doctor --context` без WARN кроме принятых — 20/22 проекта остались WARN (было 20/22),
   только axiomaerpsdk сменил тир ELEVATED→OK.

Реальный ненулевой эффект есть: флот-медиана −6.5%, 10/22 проектов снизили сырое число на
3–21%, качественный эффект (router v2, тихий health-хук, диета описаний/паков, снятие
легаси-бакетов на 14+ проектах) реально применён и будет виден в новых сессиях. Но он на
порядок меньше заявленных критериев: разбивка по источникам (`skiller budget --first-turn`)
показала, что во всех 3 замеряемых проектах CLAUDE.md/rules + MCP tool-defs дают 67–79%
итогового бюджета (agelto 46%+33%, swissknifeman 39%+21%, brain 36%+35%), а skills
(единственный рычаг items P1–P5: диета описаний P3, agent-pack диета P4) — только 17–24%.
Даже полное обнуление skills-слагаемого не увело бы agelto ниже WARN. Это структурный
разрыв между Context плана (медианный оверхед W28 ~31.9K) и фактически затронутыми P1–P6
рычагами — не дефект исполнения отдельных items (все закрыты с зелёной валидацией по
своему Scope). Рекомендация для plan-design (не exec): два новых кандидата вне Scope плана
— (1) per-project CLAUDE.md/rules фронтовых проектов (agelto CLAUDE.md=14379 ток — план
не трогал проектные CLAUDE.md вообще); (2) число подключённых MCP-серверов per-project
(agelto 6 серверов=10950 ток, методология отбора — `core:mcp-advisor`, применение
per-project — отдельная работа). Детали, все 5 таблиц — `findings/P6-after.md`.

**Remaining:** P8 доктрина+скиллы/доки+релиз v0.9.0 (5 items: P8.1 доктрина CLAUDE.md/
память, P8.2 скиллы/доки-синхронизация, P8.3 релиз-подготовка, P8.4 approve Owner+тег
[стоп-гейт], P8.5 task-package доктрина оркестрации). P8.2 должен явно отразить
ограничение эффекта P6 (не только достижения) — footprint-доктрина честнее без замалчивания
остаточного разрыва.

**Sources of truth:** plans/2026.07.12-CONTEXT-ECONOMY/plan.md (D-лог D1–D17) ·
phases/P1.md–P8.md · findings/P0-rag-context-economy.md ·
findings/P0-rag-bootstrap-memory-sync.md · findings/P6-baseline.md (точка отсчёта) ·
findings/P6-rollout.md (волны P6.2) · findings/P6-buckets.md (ревизия бакетов P6.3 +
находка про vendor-измерение) · findings/P6-after.md (новый, after-замер + вердикт
приёмки P6.4) · docs/rejected-optimizations.md · roadmap/cross-machine-memory.md.

**Open risks:**
- P8-доктрина (P8.1) фиксирует правило «новый always-on инжект — через budget-гейт», но
  сама фаза P6 доказала, что имеющийся гейт (`skiller budget --first-turn`) не покрывает
  CLAUDE.md/rules и MCP tool-defs как управляемые рычаги (только замеряет их, не диктует
  бюджет для них) — доктрина P8.1 должна либо явно ограничить область (только
  skills/hooks/agent-packs описания), либо это тоже кандидат в отдельный item (не
  расширять Scope P8.1 явочным порядком).
- vendor-измерение (`budget.py`↔`skillset.py`, находка P6.3 §0) остаётся неотремонти-
  рованным — любые будущие сравнения agelto/diabox/... через `doctor --context` продолжат
  измерять фиктивный autodetect-профиль, не реальный vendor-набор, пока это не починено
  отдельным item'ом (roadmap/новый item, не в этом плане).

**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: как в предыдущем handoff (OTEL-пресет D7, межкомпьютерная память D12, манифест
  `profile`-поле, burn-down desc-burndown.txt, KNOWN_MCP_TOOLS, encode_cwd `.`/`_`,
  flexcrm/sova `.swissknifeman/config.json` отсутствует, vintera legacy-имена бакетов,
  dterema 9-файловый конфликт, 4 проекта `.pack-new` ручной мерж, починка
  `budget.py`/`doctor --context` под vendor-канал, sibintek-insiders недо-поставка
  laravel-filament/frontend-vue/azguard, memster base `frontend` бакет, agelto vendor-бакет
  `general`) + новое: два кандидата в новый item/фазу из P6.4 Pending Work — per-project
  CLAUDE.md-диета фронтовых проектов; per-project MCP-сервер ревизия (`core:mcp-advisor`).
- open_questions: —
