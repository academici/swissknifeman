# HANDOFF — 2026-07-02 — after P7.6

**Next:** /task:plan-exec SKM-MASTER-002 P8.1 (волна 4 = P8 rollout/acceptance + хвосты:
P1.8 пилотный цикл plan-exec→audit, P1.10 cold-start, P5.6 опц. pack-guard; спеки —
phases/P8.md, phases/P1.md, phases/P5.md + одобренный план-файл)
**Done:** волны 1–3. Волна 3 (workflow wf_faac2853-041, 18/19 агентов; sales/sales доделан
оркестратором): P4 закрыта 🟠 — analyst learning loop замкнут (token-report + двухслойный
baseline · агент-аналитик /analyst:deep digest-first · ingest ephemeral-only · proposals с
инвариантом «ноль записей вне ~/.swissknifeman/analyst/»); P7 — P7.1/P7.5/P7.6 🟢,
P7.2/P7.3 🟠: bucket-audit + решение-документ (dead=180·keep=13·thin=8·merge=3·r-o=2),
10/10 монолитов → thin-navigator (**on-trigger 512 608 → 279 802 ток, −45%**, ⊕ не вырос),
alias-механизм готов (слияний нет — D14), критерий в methodology.md. Попутно: whitelist
bin/analyst (status/compact/token-report) и bin/skiller (analyze-run/bucket-audit);
/analyst:proposals в роутере; конвенция «извлекатели чистые» в analyst/CLAUDE.md получила
задокументированное исключение. Все validate ×5 + 139 core-тестов зелёные; CHANGELOG
волны 3 внесён (Added + Fixed + Known gaps); plan-lint 0/0.
**Remaining:**
- Коммит волны 3 (оркестратор, сразу после этого handoff'а).
- Волна 4 = P8: (1) метрики ДО на пилотах azguard+chatom (`harness hooks --global` уже
  SCHEMA=2; пин baseline `analyst token-report --baseline set`), (2) пилотные планы в plans/
  пилотов + живой цикл plan-design→exec(sonnet)→audit → это же закрывает P1.8, (3) P1.10
  cold-start (/clear → продолжение только из файлов), (4) глобальная приёмка §15
  (audit GREEN · reset-выживаемость · doctor --drift чисто · token-report --vs-baseline ·
  «Эффективность» · bucket-решение-док · azguard package-acceptance · digest ≤2 канд/нед),
  (5) расширение на остальные проекты maind sync — только после зелёной недели пилотов
  (растянуто во времени — фиксировать как deferred, не ждать в сессии). P5.6 pack-guard —
  опциональный, по решению.
- ОТЛОЖЕННОЕ (не волна 4): P7.4 dead-pass — ≥2 недели прод-usage (середина июля) + починка
  слепой зоны usage-детектора; merge-решения по эскизу топологии — человек.
**Sources of truth:** plans/SKM-MASTER-002/plan.md · phases/P1–P8.md · одобренный план-файл
~/.claude/plans/perplexity-snappy-platypus.md · скилл plan-protocol · plan-lint.
**Open risks:** рабочие деревья azguard/chatom несут некоммиченные rendered-паки — не
коммитить без владельца; sonnet «дорисовывает» план — проверка в P1.8; effort-пин haiku не
проверен; usage-окно телеметрии SCHEMA=2 ~1 день — baseline пилотов пиннить как «до», но
честно помечать длину окна.
**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: P7.4 (окно+детектор); tier-2 учёт references/ в budget.py (модельное решение);
  RU-справки 7 монолитов ≠ навигаторы (контентный дрейф, отдельный проход); per-workflow
  токены в run-report → analyst --by phase (доработка harness-хука); интеграция usage
  bucket-audit со SCHEMA=2-трендом; 404 quality/tdd-discipline snippets/refactoring.md
  (upstream переехал); cost-enrichment USD — roadmap; follow-ups фазы F (pack:if BC-строки
  dev-loop; extension-point dev-loop.js/rules/tests.md; flake PACKAGE_NAMESPACE;
  *.pack-new в agelto — материал для /analyst:deep).
- open_questions: merge-вердикты (3 псевдо-overlap super-skill) — человек по эскизу
  топологии 45→~34.
