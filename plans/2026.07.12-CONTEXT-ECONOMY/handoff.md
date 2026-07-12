# HANDOFF — 2026-07-12 — after P6.3

**Next:** P6.4 (after-замер и приёмка).

| Параметр | Значение |
|:--|:--|
| Model | sonnet/medium |
| Thinking | medium — приёмка по существующим командам, но требует НЕТРИВИАЛЬНОГО решения из-за находки P6.3 (см. Open risks) |
| Context | fresh session — handoff свежий, рекомендован /clear |
| Суть | Свежие сессии на agelto + 2 медианных проектах → `analyst sessions` + `maind doctor --context` → `findings/P6-after.md` со сравнением против `findings/P6-baseline.md`; **ВАЖНО перед стартом**: прочитать `findings/P6-buckets.md §0` — `doctor --context` не измеряет vendor-проекты (agelto!) корректно, решить (в рамках item'а, без кода) — использовать `analyst sessions` как основной источник для agelto/vendor-проектов вместо/вместе с `doctor --context`, и явно разметить это в вердикте приёмки |

```
/task:plan-exec 2026.07.12-CONTEXT-ECONOMY P6.4
```

**Done:** P1–P5, P7 закрыты (см. Update Log plan.md). P6.1 (baseline), P6.2 (sync-волны)
закрыты 🟢.

**P6.3 закрыт 🟠 Done with deviations (фаза P6 2/4 🟢 + 1 🟠 🟡 In progress):** Owner в
цикле недоступен (форс-прогон D17) — применена эвристика вместо AskUserQuestion
per-project. Применено (высокая уверенность): CORE-политика-миграция — легаси
`general`/`oss-dev` (дублируют лёгкий плагин `core`) сняты на 14 проектах (azguard,
botkit, vaulter, swissknifeman, corex, memster, cms, edufy, dterema-app,
sibintek-insiders, chatom, perplexity-web-mcp, loqum, brain) через
`enabledPlugins[...]=false` + закрепляющий явный `.swissknife.json`; точечно — `roles`
(dterema-app, персоны нерелевантны Nuxt) и дрейф `php`/`php-packages`/`frontend-vue`/
`frontend-backend` (loqum, реальный стек TS/Vite без PHP/Vue). **ГЛАВНАЯ НАХОДКА:**
`skiller budget --first-turn`/`maind doctor --context` для **vendor-проектов**
(agelto, diabox, azguard/botkit-vendor, cms, vintera, dterema, dterema-app) НЕ читают
`.swissknifeman/config.json`/физические `.claude/skills/` вовсе — измеряют фиктивный
autodetect-профиль; agelto (флагманский «виновник» из Context плана, 32830 ток) на 86%
состоит из CLAUDE.md+rules/MCP tool-defs, а измеряемые skills (5571 ток) не отражают
реальный 19-бакетный vendor-набор. Это предсуществующий разрыв `budget.py`↔`skillset.py`
(budget.py спроектирован под старый `vendor.py`+`.swissknife.json`, не под новый
skill-granular `skillset.py`+`.swissknifeman/config.json`), не введён этим item'ом,
правка — код, вне Scope P6.3. Validation-критерий item'а («вердикт улучшился» per-project)
НЕ достигнут как смена тира ни для одного из 14 затронутых проектов (все остались WARN —
доминируют CLAUDE.md/MCP, не skills); сырое число снизилось у 6, не изменилось у 4
(измерение нечувствительно), честно ВЫРОСЛО у 4 (вскрытый предсуществующий дрейф-недоучёт,
не регресс). Реальный эффект в будущих Claude Code-сессиях достигнут у всех 14 проектов
независимо от измерения. Полная таблица + 4 сомнительных случая («нужен Owner», не
применено: agelto vendor-бакет general, memster base frontend, sibintek-insiders
недо-поставка laravel-filament/frontend-vue/azguard, vintera legacy-имена) —
findings/P6-buckets.md. Детали — phases/P6.md P6.3 Completion Notes.

**Remaining:** P6.4 after-замер и приёмка (медиана ≤10–12K, agelto −≥40%, `doctor --context`
без WARN кроме принятых — **пересмотреть критерий agelto с учётом находки P6.3**, см. выше)
· P8 доктрина+скиллы/доки+релиз v0.9.0 (5 items, P8.4 — approve Owner на тег).

**Sources of truth:** plans/2026.07.12-CONTEXT-ECONOMY/plan.md (D-лог D1–D17) ·
phases/P1.md–P8.md · findings/P0-rag-context-economy.md · findings/P0-rag-bootstrap-memory-sync.md ·
findings/P6-baseline.md (точка отсчёта) · findings/P6-rollout.md (волны P6.2) ·
findings/P6-buckets.md (новый, ревизия бакетов P6.3 + главная находка про vendor-измерение) ·
docs/rejected-optimizations.md · roadmap/cross-machine-memory.md.

**Open risks:**
- **P6.4 приёмка под угрозой для agelto**: критерий «agelto −≥40%» опирается на
  `doctor --context`/`skiller budget --first-turn`, которые для vendor-проектов (agelto)
  не видят реальный skill-набор вовсе (см. находка выше). P6.4 должен явно решить: мерить
  agelto через `analyst sessions` (реальные транскрипты — уже показывали в P6.1 baseline
  W27/W28 медианы), либо честно отметить числовой критерий как неприменимый к
  `doctor --context` для vendor-проектов до отдельной починки измерения (roadmap/новый item),
  не подгонять/не замалчивать разрыв.
- doctor --context после P6.3: 4 проекта (vaulter/memster/chatom/brain) показывают
  бо́льшее число, чем до P6.3 — это НЕ регресс (см. §3 findings/P6-buckets.md), но при
  поверхностном чтении может выглядеть как ухудшение — не путать со сравнением P6.1→P6.4.

**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: как в предыдущем handoff (OTEL-пресет D7, межкомпьютерная память D12, манифест
  `profile`-поле, burn-down desc-burndown.txt, KNOWN_MCP_TOOLS, encode_cwd `.`/`_`,
  flexcrm/sova `.swissknifeman/config.json` отсутствует, vintera legacy-имена бакетов,
  dterema 9-файловый конфликт, 4 проекта `.pack-new` ручной мерж) + новое: починка
  `budget.py`/`doctor --context` под vendor-канал (skillset.py) — кандидат в отдельный
  item/roadmap, не в этом плане; sibintek-insiders недо-поставка
  laravel-filament/frontend-vue/azguard (Owner-решение); memster base `frontend` бакет
  (сомнение, не тронут); agelto vendor-бакет `general` (сомнение, не тронут).
- open_questions: —
