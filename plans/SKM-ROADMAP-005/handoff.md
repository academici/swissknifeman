# HANDOFF — 2026-07-11 — after P6.3

**Next:** /task:plan-design SKM-ROADMAP-005 P7

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — P7.1 требует интервью владельца + авторинг спеки «ephemeral-дисциплины» (Routing: opus/high) |
| Context | fresh session — handoff свежий, рекомендован /clear |
| Суть | Фаза P7 — скелет (`Intent: —` у обоих items, 0/2 в Status Board): P7.1 нужно развернуть из скелета до полного ТЗ через `/task:plan-design`, а не исполнять напрямую — `plan-exec` упадёт на предусловии «Intent: —». P6.4 (наполнение term-index) остаётся тайм-гейтовым открытым item'ом на доске (D41, механизм сдан P6.1–P6.3) — P7 по этому же решению НЕ ждёт его закрытия |

```
/task:plan-design SKM-ROADMAP-005 P7
```

**Done:** Фазы **P1** (`settings-doctor`, 6/6 🟢), **P2** (`wf-status`, 4/5 🟢+🟠), **P3**
(`workflow-craft`, 5/5 🟢), **P4** (канон планов, 6/6 🟢), **P5** (`changelog-discipline`,
3/3 🟢) закрыты ранее. Фаза **P6** (`ecosystem-glossary`) в работе: P6.1 закрыт 🟠 (усиление
`domain-modeling` триггерами CONTEXT.md + Rule of Two + `## Conformance`, D42; известное
отклонение — вендоренный скилл, `check-translations.sh` не проставляет стамп автоматически,
маркер заполнен вручную, вопрос владельцу в OQ1). P6.2 закрыт 🟢: пункт «Glossary impact?»
в 5 `reviewer.md` + glossary-conformance-измерение в Stage B `task:review`. **P6.3 закрыт 🟢**:
скилл-указатель `packages/skiller/skills/axioma/axioma-glossary/{SKILL.ru.md,SKILL.md}`
(`requires:[domain-modeling]`, зеркалит `axioma-stack`, без вшитой копии содержимого); каркас
Brain-страницы `/home/vostrikov/Vaults/Brain/02-Knowledge/00-Strategy/Ecosystem_Glossary.md`
(пустая 4-колоночная таблица + пояснение Rule of Two/steward + пометка тайм-гейта P6.4) +
строка в `_index.md`; строка статуса `ecosystem-glossary` в `roadmap/README.md` →
«🟢 внедрено (механизм, P6.1–P6.3); наполнение — тайм-гейт P6.4». `skiller registry` прогнан
(`skills.json`/`_index.md`/`budget.md`/`graph.md`), `validate.sh` и `check-translations.sh`
зелёные (215 skills, 364 теста OK, 159/159 RU-источников свежих). Коммиты: SKM-часть в репо
swissknifeman, Brain-часть отдельным коммитом в vault Brain (свой git-репо). Known Deviations
P6.3: пункт Validation плана про `grep "axioma-glossary" .../marketplace.json` не находит
буквального совпадения — connect-канал bucket-granular, маркетплейс несёт запись бакета
`axioma` целиком, а не отдельных скиллов (тот же результат у прецедента `axioma-stack` —
0 вхождений); скилл раздаётся корректно через бакет, расхождение в тексте Validation, не
дефект реализации.

**Remaining:** P6.4 (наполнение term-index — ТАЙМ-ГЕЙТ, D41, остаётся ⬜, фаза P6 закрывается
с ним открытым, `plan-exec` его не трогает до dev-волны ECOSYSTEM P4) → P7 ephemeral-дисциплина
+ закрытие пакета (2 item'а, оба скелеты — начать с `/task:plan-design SKM-ROADMAP-005 P7`).

**Sources of truth:** plans/SKM-ROADMAP-005/plan.md (Meta, Routing, D-лог D1–D43) ·
phases/P6.md (P6.1–P6.3 закрыты — эталон Completion Notes; P6.4 тайм-гейт) · phases/P7.md
(скелет, `Intent: —`) · packages/skiller/skills/general/plan-protocol/SKILL.md (SSOT протокола
2.1.0) · packages/task/lib/task/plan_lint.py (валидатор схемы)

**Open risks:**
- P1.4 Pending Work: проверка №5 даёт ложный `error` на хук-командах с интерпретатор-префиксом
  (`bash …`, `python3 …`). Вне scope P1.
- P1.6 Pending Work: `maind doctor --audit all` падает на измерении `core` (`_present_skills`) на
  части флота. `--audit settings` в изоляции не задет.
- CHANGELOG-строки items P3.1–P3.5, консолидированная строка фазы P4, строки P5.1/P5.2/P5.3 и
  P6.2/P6.3 НЕ внесены — путь `CHANGELOG.md` заблокирован permission-deny среды (прецедент P2.4);
  внести при первой сессии со свободным доступом к файлу.
- D16 (канон имён планов) внедрён в P4 — этот план НЕ переименовывается (back-compat D24).
- `plan-lint` даёт pre-existing WARNING на других планах (SKM-AUDIT-004, SKM-MASTER-002/003) —
  вне scope этого плана.
- P6.1 Known Deviations: `domain-modeling` вендоренный (`upstream.json` strategy=notify) →
  `check-translations.sh --stamp` его не касается, авто-staleness слепа; политика vendored-vs-
  bilingual для этого скилла — открытый вопрос владельцу (OQ1, не блокирует).
- P6.3 Known Deviations: текст Validation плана (`grep "axioma-glossary" marketplace.json`) не
  совпадает с реальной bucket-granular архитектурой connect-канала — см. Done выше.

**Workarounds/Deferred/Open questions:**
- workarounds: семантика слияния `permissions.additionalDirectories` неизвестна → проверка №8
  per-layer (D15); полнота списка hook-событий не подтверждена → неизвестное событие даёт `info`;
  маркер оркестрации в plan_lint консервативен (без бумерного `fan-out`) — против ложных warning (P4.6);
  P6.1 `ru-source-sha256` проставлен вручную (вендоренный скилл, инструмент не стампит).
- deferred: opt-in `UserPromptSubmit`-хук settings-doctor (D12); авто-починка `--fix`; часть 2
  `workflow-craft` fleet-синтез (D1); `skill-rules-sidecar`, остаток `self-learning-memory`,
  default-on `mcp-config-example-emit` (D1); P1.4/P1.6 Pending Work; CHANGELOG-строки P3+P4+P5+
  P6.2+P6.3 (permission-deny); maind-провижионер `plans-doc` авто-раскатки CLAUDE.md во флот (D30);
  P6.4 наполнение term-index (тайм-гейт D41, после dev-волны ECOSYSTEM P4).
- open_questions: содержание «ephemeral-дисциплины» — снимается интервью владельца в P7.1 (D7);
  политика vendored-vs-bilingual для `domain-modeling` — OQ1 (`open-questions.md`).
