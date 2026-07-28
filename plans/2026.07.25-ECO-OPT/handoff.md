# HANDOFF — 2026-07-28 — after P2.3

**P2.3 закрыт `🟠 Done with deviations`** (`e067a7dc` — item-коммит). Ревизия пяти плановых команд
`packages/task/commands/plan-{design,exec,run,close,audit}.md` по правилу A/B/C и ФОРМАТУ карты
P2.2 (переиспользован, не изобретён заново). Все ЧЕТЫРЕ гейта item'а сняты цитатами до старта,
исходы положительные. **Класс A — снова ПУСТ**: единственное грep-совпадение (`plan-design.md:123`)
— перепрогон детерминированного линтера (B2), лесов статус-апдейтов 0 совпадений. Носители
машинных гейтов (`Pre-mutation`/`Pre-final` Task Contract, Validation, DoR-чеклист) разобраны как
класс B и сохранены — снос запрещён D86/D93. **Применены 3 правки в 2 файлах**: кап делегирования
в `plan-design.md` (гайд Opus 5 §6 — единственная из пятёрки, где субагент-разведка предполагается
текстом, `plan-design.md:216`) + ось `confidence ∈ {high,med,low}` в формате находки и Expected
output `plan-audit.md` (гайд Sonnet 5, «Code review harnesses»). **Пункт DoR (D81)** внесён в
`plan-design.md:252` дословно по спеке `research/14` §1.2 — побайтная сверка passed. Карта
`artifacts/P2.3/opus5-revision-map.md` — 5 разделов. Пины и `description` не тронуты (D16).
Отклонения (отсюда 🟠): item-коммит нёс 3 пути ВНЕ `Files` (две байтовые golden-фикстуры +
сгенерированный `docs/reference/provider-commands.md` — ровно риск, названный Open risk 49
прошлого handoff'а); и спека `research/14` покрыта наполовину — её §1.1 (канон `plan-protocol`)
прямо запрещён Scope Excluded. Детали — `phases/P2.md` P2.3 Completion Notes.

**Next:** **фаза P2 терминальна** — все три её item'а закрыты (P2.1 🟢 · P2.2 🟠 · P2.3 🟠),
Status Board ещё показывает `🟡 In progress` и ждёт отдельного `plan-close` (закрытие фазы —
не работа item-исполнителя, топология §8). Тем же шагом закрывается docs-sync-гейт фазы.

| Параметр | Значение |
|:--|:--|
| Model | sonnet — пин `/task:plan-close` (механическая сверка) |
| Thinking | low — пин команды, thinking на сверке жжёт токены |
| Context | NEW SESSION — шаг-не-item |
| Суть | Закрыть фазу P2: таблицы, Phase Handoff, docs-sync, `closure/P2.json` (Closure Protocol v1) |

```
/task:plan-close 2026.07.25-ECO-OPT P2
```

**Done:** **49/52 items терминальны** (29 🟢 · 19 🟠 · 1 ⛔). Закрыты фазы **P1** (1/2, 🟢),
**P3** (2/6, 🟠), **P4** (3/3, 🟠), **P5** (5/6, 🟠), **P8** (7/10, 🟠), **P9** (3/4, 🟠),
**P10** (1/4, 🟠), **P11** (6/8, 🟠); **P2** и **P6** — все items терминальны, их Phase Status
Board'ы ждут отдельных `plan-close`.

**Remaining:** 3 items: P7.1–P7.3 (порядок `P7.1 + P7.3 → P7.2`, все `Exec = manual`; кандидаты
dogfood P7.1 по roadmap — P8.7 · P1.2 · P3.2, статус сверить перед прогоном). Плюс два фазовых
закрытия: `/task:plan-close 2026.07.25-ECO-OPT P2` (следующий шаг) и
`/task:plan-close 2026.07.25-ECO-OPT P6`.

**Sources of truth:** `plan.md` (§0 Meta `Last Updated`; §4 Phase Index; §6 Update Log — запись
закрытия P2.3) · `phases/P2.md` (Phase Status + P2.3 Completion Notes/Known Deviations) ·
`artifacts/P2.3/opus5-revision-map.md` (карта решений: 5 разделов, §2 — предложения владельцу) ·
`artifacts/P2.2/opus5-revision-map.md` §0 (ФОРМАТ, переиспользован) ·
`research/14-P6.3-dor-delta-spec.md` (спека пункта DoR; §1.1 остался неисполненным) ·
`findings/P2-opus5-guide.md` §5–§6, §9 · `findings/P2-claude5-family-and-migration.md` §1/§4 ·
машинные гейты `packages/task/scripts/validate.sh`, `packages/task/scripts/plan-lint.py`,
`packages/task/scripts/render-provider-commands.py --check`.

**Open risks:** (наследованные — полный список см. предыдущий `handoff.md` git-историей, записи
(40)–(48)) плюс:
(49) **`Files` items, правящих `packages/task/commands/*.md`, структурно неполон** — не называет
производные носители (байтовые golden-фикстуры `tests/fixtures_data/claude-command-golden/` и
сгенерированный `docs/reference/provider-commands.md`). **Сработал ВТОРОЙ раз подряд** (P2.2, затем
P2.3 — оба 🟠 по этой причине). Любой будущий item, правящий тела команд, обязан либо назвать эти
пути в `Files`, либо принять отклонение заранее.
(50) **Пре-существующий дрейф Codex-проекции**: `render-provider-commands.py --check` даёт drift
`task.codex.plugin`, `task.codex.publication-lock` и skill/runtime `plan-*` команд (наследие
AGENT-RELIABILITY); P2.2 добавил `design`/`research`/`review`, P2.3 — `plan-design`/`plan-audit`.
Единственный регенератор пишет все артефакты сразу ⇒ нужен ОДИН отдельный item:
`render-provider-commands.py --write --repair-owned --root .` разом.
(51) **`confidence` в пяти agent-pack ревьюерах не добавлен** (носитель-канон
`packages/harness/configs/common/agent-packs/roles.json` вне `Files` P2.2) — плюс теперь ось не
поднята и в таксономию `quality/artifact-review` (`SKILL.ru.md:91` перечисляет severity+лейбл+
`file:line`+failure_scenario), хотя её уже несут `review.md` и `plan-audit.md`. Один item должен
закрыть оба носителя и решить, как ось соотносится с гейтом `GATE_MAX_CRITICAL`.
(52) **Пункт DoR «внешние факт-классы фазы перечислены» живёт в ОДНОМ носителе из двух** —
внесён в `packages/task/commands/plan-design.md`, но НЕ в канон
`packages/skiller/skills/general/plan-protocol/SKILL.ru.md` (Scope Excluded P2.3), тогда как
`packages/task/CLAUDE.md` требует править оба места синхронно. Нужен item: строка в `SKILL.ru.md`
(якорь `- [ ] Несущие факты несут RAG-маркеры.`) + регенерация `SKILL.md` +
`check-translations.sh --stamp` + `skiller registry` одним коммитом.

**Workarounds / Deferred / Open questions:**
· **workarounds** — нет.
· **deferred** — без изменений этим заходом (F1 roadmap-кандидат, расхождение flexcrm 142 vs
186, апстрим-URL `oss-dev/to-issues` 404, протокол backup-restore, `PreCompact`/`PostCompact`
хук — roadmap-кандидат); плюс перекалибровка порогов `skiller budget --first-turn` под токенайзер
Sonnet 5 (~+30%, D19) — кандидат для P3.1, повторно зафиксирован в карте P2.3 §2 п.3.
· **open questions** — без изменений; OQ-8 **закрыт исполнением** (пункт DoR внесён, D81), OQ-11
остаётся `Decision pending` до закрытия P11.
