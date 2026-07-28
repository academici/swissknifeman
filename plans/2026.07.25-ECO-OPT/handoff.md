# HANDOFF — 2026-07-28 — after P2

**Фаза P2 закрыта `🟠 Done with deviations`** (все три items терминальны: P2.1 🟢 · P2.2 🟠 ·
P2.3 🟠). Сдано: две model-notes Claude 5 в Brain-валте + указатели в `prompting.md` + две
строки `docs/reference.md` (P2.1); две карты `opus5-revision-map.md` (P2.2 — 18 разделов,
P2.3 — 5 разделов), правило A/B/C применено к 6 интент-командам + затронутым agent-packs +
5 плановым командам `plan-*.md` — **класс A пуст на обеих поверхностях** (замер
2026-07-25 подтвердился); добавлены капы делегирования (`design.md`, `research.md`,
`review.md`, `plan-design.md`) и ось `confidence` (`review.md`, `plan-audit.md`); пункт DoR
«внешние факт-классы фазы перечислены» внесён в `plan-design.md` дословно по спеке P6.3
(D81, §1.2). Docs-sync: обновлено P2.1 (`docs/reference.md`, Brain `prompting.md`);
P2.2/P2.3 не несут содержательного для `docs/` swissknifeman сверх CHANGELOG-строк, уже
внесённых обоими item'ами. Детали — `phases/P2.md` Phase Handoff и Completion Notes items.

**Известные отклонения (агрегат, собран механически из Known Deviations items):**
- P2.2/P2.3 (material, оба): item-коммиты несут пути ВНЕ `Files` — байтовые
  golden-фикстуры Claude-проекции + сгенерированный `docs/reference/provider-commands.md`
  (механические зеркала правленых команд, без них `validate.sh` красный).
- P2.3 (material): пункт DoR спеки P6.3 покрыт наполовину — §1.1 (канон `plan-protocol`)
  вне Scope этого item'а, внесён только §1.2 (команда).
- P2.2/P2.3 (process, оба): карты `artifacts/P2.{2,3}/opus5-revision-map.md` закоммичены
  bookkeeping-коммитом (carve-out `plans/<ID>/**` перебивает перечисление в `Files`);
  исполнено `opus/high` — ровно предписанный Routing `frontier/high`.

**Next:** фаза закрыта с deviations (🟠 на обоих нетривиальных items) — по правилу
launch-block'а «была хоть одна 🟠/эскалация → сперва `plan-audit`» следующий шаг —
адверсариальный аудит фазы P2, не сразу exec следующего item'а.

| Параметр | Значение |
|:--|:--|
| Model | opus — пин `/task:plan-audit` |
| Thinking | xhigh — пин команды (adversarial-аудит закрытой фазы) |
| Context | NEW SESSION — шаг-не-item |
| Суть | Adversarial-аудит закрытой фазы P2: сверка 🟢/🟠 с кодом/git, no-op, scope drift, handoff |

```
/task:plan-audit 2026.07.25-ECO-OPT P2
```

**Done:** **49/52 items терминальны** (29 🟢 · 19 🟠 · 1 ⛔), не изменилось этим заходом
(закрытие фазы не меняет счёт items). Закрыты фазы **P1** (1/2, 🟢), **P2** (1/3, 🟠 —
этот заход), **P3** (2/6, 🟠), **P4** (3/3, 🟠), **P5** (5/6, 🟠), **P8** (7/10, 🟠), **P9**
(3/4, 🟠), **P10** (1/4, 🟠), **P11** (6/8, 🟠). Фаза **P6** — все items терминальны,
Phase Status Board ждёт отдельного `plan-close`.

**Remaining:** 3 items: P7.1–P7.3 (порядок `P7.1 + P7.3 → P7.2`, все `Exec = manual`;
кандидаты dogfood P7.1 по roadmap — P8.7 · P1.2 · P3.2, статус сверить перед прогоном).
Плюс фазовое закрытие `/task:plan-close 2026.07.25-ECO-OPT P6` (все items терминальны,
Status Board не сведён) и аудит `/task:plan-audit 2026.07.25-ECO-OPT P2` (этот handoff).

**Sources of truth:** `plan.md` (§0 Meta; §4 Phase Index — P2 теперь `🟠 Done with
deviations`; §6 Update Log — запись закрытия фазы) · `phases/P2.md` (Phase Status + Phase
Handoff + Completion Notes/Known Deviations всех трёх items) · `closure/P2.json`
(отчёт закрытия фазы, Closure Protocol v1) · `artifacts/P2.{2,3}/opus5-revision-map.md`
(карты решений) · `research/14-P6.3-dor-delta-spec.md` (спека пункта DoR; §1.1 остался
неисполненным) · `findings/P2-opus5-guide.md` · `findings/P2-claude5-family-and-migration.md` ·
машинные гейты `packages/task/scripts/validate.sh`, `packages/task/scripts/plan-lint.py`,
`packages/task/scripts/render-provider-commands.py --check`.

**Open risks:** (наследованные — полный список см. предыдущий `handoff.md` git-историей,
записи (40)–(52), без изменений этим заходом):
(49) `Files` items, правящих `packages/task/commands/*.md`, структурно неполон — не
называет golden-фикстуры и сгенерированный `docs/reference/provider-commands.md`.
Сработал ВТОРОЙ раз подряд (P2.2, затем P2.3).
(50) Пре-существующий дрейф Codex-проекции (`render-provider-commands.py --check`) —
наследие AGENT-RELIABILITY, P2.2/P2.3 добавили к нему `design`/`research`/`review`/
`plan-design`/`plan-audit`. Чинится ОДНИМ отдельным item'ом (`--write --repair-owned`).
(51) `confidence` в пяти agent-pack ревьюерах не добавлен (носитель-канон
`packages/harness/configs/common/agent-packs/roles.json` вне `Files` P2.2); ось не
поднята и в таксономию `quality/artifact-review`.
(52) Пункт DoR живёт в ОДНОМ носителе из двух — `SKILL.ru.md` канона `plan-protocol` не
тронут (Scope Excluded P2.3), хотя `packages/task/CLAUDE.md` требует синхронной правки.

**Workarounds / Deferred / Open questions:** без изменений этим заходом (см. предыдущий
`handoff.md` — F1 roadmap-кандидат, расхождение flexcrm, апстрим-URL 404, backup-restore,
`PreCompact`/`PostCompact` хук, перекалибровка `skiller budget --first-turn` под
токенайзер Sonnet 5 — кандидат P3.1). OQ-8 закрыт исполнением (D81), OQ-11 остаётся
`Decision pending` до закрытия P11.
