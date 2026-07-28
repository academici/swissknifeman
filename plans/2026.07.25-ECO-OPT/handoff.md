# HANDOFF — 2026-07-28 — after P3

**Фаза P3 закрыта `🟠 Done with deviations`** (все 6 items терминальны: P3.1 🟢 · P3.3 🟢 ·
P3.2/P3.4/P3.5/P3.6 🟠). Закрывающий отчёт `closure/P3.json` заведён (`Closure Protocol | v1`).
Известные отклонения — механический агрегат по items, см. `phases/P3.md` Phase Handoff (не
пересказ Completion Notes). Docs-sync подтверждён: `packages/skiller/docs/guide/profiles.md`,
`bucket-audit-2026-07.md` (P3.5), `upstream-sync.md`, корневой `CLAUDE.md` (P3.6) уже обновлены
внутри items — доп. правок docs не требуется.

**Next:** следующая фаза по `roadmap.md` (строка 62) — **P4.1** (ADR: хост/транспорт/доверие/
офлайн-деградация памяти mAInd), `solo`/`manual`/`implementation-high`, гейтов нет (owner-гейт
снят D80, P3.2 терминален). Item уже детализирован (DoR готов) — запуск вручную (`Exec = manual`,
как у P4 целиком).

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | high — ADR: архитектурное решение с ценой/риском по вариантам |
| Context | continue (/clear) — ручной item |
| Суть | ADR памяти mAInd: хост, транспорт, доверие, офлайн-деградация (P4.1) |

```
ЗАПУСК ВРУЧНУЮ: sonnet/high
```
```
/task:plan-run 2026.07.25-ECO-OPT P4.1
```

**Done:** **41/52 items терминальны** (26 🟢 · 14 🟠 · 1 ⛔ — счёт снят машинно по `**Status:**`
всех `phases/P*.md`). Закрыты фазы **P1** (1/2, 🟢), **P3** (2/6, 🟠), **P5** (5/6, 🟠),
**P8** (7/10, 🟠), **P9** (3/4, 🟠), **P10** (1/4, 🟠), **P11** (6/8, 🟠). Вне этих фаз закрыт
только P2.1.

**Remaining:** 11 items, все `⬜ Not started`: P2.2/P2.3 · P4.1–P4.3 · P6.1–P6.3 · P7.1–P7.3.
Порядковые условия: P2.3 —
ПОСЛЕ P6.3 (D93) и ПОСЛЕ P8.1/P8.2/P8.3 (терминальны); P6.1 — ПОСЛЕ P9.1 (снято, терминален);
P4.1 → P4.2 → P4.3 (ADR определяет ветки, P3.2 терминален — гейт снят); P7.1 + P7.3 → P7.2.

**Sources of truth:** `plan.md` (§0 Meta `Last Updated`; §4 Phase Index — `P3 2/6 🟠`; §6 Update
Log — запись закрытия фазы P3) · `phases/P3.md` (Phase Status + Phase Handoff) ·
`closure/P3.json` · `roadmap.md` (строка 62 — порядок P4.1→P4.2→P4.3) · машинные гейты
`packages/task/scripts/plan-lint.py`, `plans/verify-citations.py`.

**Open risks:** (наследованные, без изменений этим заходом — полный список см. предыдущий
`handoff.md` git-историей, риски (33)/(34) о D137/D138 остаются открытыми) плюс:
(35) **Перекалибровка токенайзера `budget.py` (P3.4 Pending Work) не выполнена** — недоступен
`count_tokens`/`ANTHROPIC_API_KEY` в исполнительной песочнице; точная команда ждёт захода с
креденшелами (`findings/P3.4-tokenizer-calibration.md` §3).
(36) **`voice-ai/voice-ai/upstream.json` ломает `update-upstreams.sh --check`** (пустой `path` у
5 записей, `IsADirectoryError`) — пред-существующий дефект, сопровождение вне Scope P3.6.

**Workarounds / Deferred / Open questions:**
· **workarounds** — нет.
· **deferred** — roadmap-кандидат **F1** (дисциплина против класса R2, P3.3) не внесён в
`roadmap.md`; расхождение 142 vs 186 записей `flexcrm` (P3.1) не разобрано до корня;
`oss-dev/to-issues/upstream.json` — апстрим-URL вернул 404, паспорт нуждается в обновлении.
· **open questions** — нет новых этим заходом; `2026.07.15-TELEMETRY-OPT` OQ-4/OQ-5 закрыты
(D137/D138), OQ-11 остаётся `Decision pending` до закрытия P11.
